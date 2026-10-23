"""Session controller: the monitor, the event log and the recorder, for a front end to drive.

    session = Session(load_manifest("manifests/bench.yaml"), out_dir="data")
    session.start()
    ... session.monitor.snapshot(), session.monitor.confirm("P1-EEG") ...
    session.start_recording({"group": "G01", ...})
    session.note("participant P2 adjusted the cap")
    problems = session.stop_recording()
    session.close()
"""
import logging
import threading
import time
from pathlib import Path

import pylsl

from .events import EventLog
from .monitor import DATA_STATES, Monitor
from .recorder import LabRecorderCLI, RecorderError
from .session_info import host_label, make_session_info, payload_text, software_version
from .verify import verify_recording, write_sidecar

log = logging.getLogger("session_monitor")


class Session:
    def __init__(self, manifest, out_dir="data", labrecorder_cli=None, host=None, monitor_kwargs=None):
        self.manifest = manifest
        self.out_dir = Path(out_dir)
        self.host = host or host_label()
        self.version = software_version()
        self.events = EventLog(self.out_dir, self.host)
        self.monitor = Monitor(manifest, on_change=self._on_slot_change, **(monitor_kwargs or {}))
        self.recorder = LabRecorderCLI(labrecorder_cli)
        self.current = None  # the recording in progress
        self._lock = threading.Lock()

    @property
    def recording(self):
        return self.current is not None

    def start(self):
        self.monitor.start()
        self.events.event("monitor_start", manifest=self.manifest.path.name, host=self.host,
                          software_version=self.version)

    def close(self):
        if self.recording:
            self.stop_recording()
        self.monitor.stop()
        self.events.event("monitor_stop")
        self.events.close()

    def note(self, text):
        return self.events.event("note", text=text.strip(), recording=self.recording)

    def blockers(self, values):
        """Reasons recording cannot start now (empty list = ready)."""
        reasons = list(self.manifest.check_session(values))
        reasons += [f"{st.slot.id} is {st.state.value}" + (f" ({st.detail})" if st.detail else "")
                    for st in self.monitor.unconfirmed_required()]
        if self.recording:
            reasons.append("already recording")
        return reasons

    def next_run(self, values):
        """First run number after the highest one already in out_dir for these identifiers."""
        before, _, after = self.manifest.filename.format(
            **{k: str(v).strip() for k, v in values.items()}, run="\0").partition("\0")
        runs = [0]
        for p in self.out_dir.glob("*.xdf"):
            stem = p.stem
            if stem.startswith(before) and stem.endswith(after):
                middle = stem[len(before):len(stem) - len(after)]
                if middle.isdigit():
                    runs.append(int(middle))
        return max(runs) + 1

    def start_recording(self, values):
        with self._lock:
            reasons = self.blockers(values)
            if reasons:
                raise RecorderError("cannot start: " + "; ".join(reasons))
            run = self.next_run(values)
            stem = self.manifest.build_filename(values, run)
            xdf = self.out_dir / f"{stem}.xdf"
            outlet, payload = make_session_info(self.manifest, values, run, stem, self.host, self.version)
            info_sid = outlet.get_info().source_id()

            own = self._own_streams(info_sid)
            data = [(st.found.name, st.found.host, st.slot.required)
                    for st in self.monitor.snapshot() if st.state in DATA_STATES]
            streams = [(n, h) for n, h, _ in data] + own
            try:
                self.recorder.start(xdf, streams)
            except RecorderError as e:
                self.events.event("recording_failed", file=xdf.name, error=str(e))
                raise
            outlet.push_sample([payload_text(payload)])
            self.events.event("recording_start", file=xdf.name, run=run, streams=[n for n, _ in streams])
            self.current = dict(xdf=xdf, run=run, payload=payload, outlet=outlet, info_sid=info_sid,
                                expected=data, values=dict(values), started=time.time(), slot_events=[])
            return xdf

    def stop_recording(self):
        """Stop, verify the file, write the JSON sidecar. Returns the problems found."""
        with self._lock:
            cur = self.current
            if cur is None:
                return []
            self.events.event("recording_stop", file=cur["xdf"].name, run=cur["run"])
            time.sleep(1.0)  # let the last markers reach the recorder
            code = self.recorder.stop()
            self.current = None
            try:
                problems, summary = verify_recording(cur["xdf"], cur["expected"], cur["info_sid"],
                                                     self.events.source_id, cur["values"])
            except Exception as e:
                problems, summary = [f"could not read {cur['xdf'].name}: {e}"], []
            if code not in (0, None):
                problems.append(f"LabRecorderCLI exit code {code}")
            lost = sorted({e["slot"] for e in cur["slot_events"] if e["lost"] and e["required"]})
            problems += [f"required slot {sid} lost data during the recording (see slot events)" for sid in lost]
            write_sidecar(cur["xdf"].with_suffix(".json"), {
                **cur["payload"], "duration_s": round(time.time() - cur["started"], 1),
                "labrecorder_exit_code": code, "streams": summary, "slot_events": cur["slot_events"],
                "problems": problems})
            self.events.event("recording_checked", file=cur["xdf"].name, ok=not problems, problems=problems)
            del cur["outlet"]
            return problems

    def _own_streams(self, info_sid, timeout=5.0):
        """Our marker and session-info streams as LSL reports them (they must be resolvable first)."""
        own = []
        for sid in (self.events.source_id, info_sid):
            found = pylsl.resolve_byprop("source_id", sid, minimum=1, timeout=timeout)
            if not found:
                raise RecorderError(f"own stream {sid} is not visible on LSL")
            own.append((found[0].name(), found[0].hostname()))
        return own

    def _on_slot_change(self, old, new):
        fields = dict(slot=new.slot.id, state=new.state.value, previous=old.state.value)
        if new.detail:
            fields["detail"] = new.detail
        if new.found:
            fields["host"] = new.found.host
        cur = self.current
        if cur is not None:
            fields["recording"] = True
        ts = self.events.event("slot", **fields)
        if cur is not None:
            lost = old.state in DATA_STATES and new.state not in DATA_STATES
            cur["slot_events"].append(dict(lsl_time=round(ts, 3), slot=new.slot.id, required=new.slot.required,
                                           state=new.state.value, detail=new.detail, lost=lost))
            if lost and new.slot.required:
                log.warning("required slot %s lost during recording: %s", new.slot.id, new.detail)
