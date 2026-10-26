"""NiceGUI front end: slot cards, confirm buttons, identifiers, record/stop, notes, live log.

    python -m session_monitor.gui manifests/bench.yaml
    python -m session_monitor.gui manifests/bench.yaml --set operator=FP --port 8080

Opens in the browser (http://127.0.0.1:8080). Every browser tab shows the same
session. Events are also printed in this terminal and written to the CSV log in
--out. Ctrl+C here stops a running recording, checks it, then quits.
"""
import argparse
import itertools
import logging
import sys
import threading
import time
from collections import deque

import pylsl
from nicegui import app, run, ui

from .manifest import ManifestError, load_manifest
from .monitor import DATA_STATES, SlotState
from .recorder import RecorderError
from .session import Session

STATE_COLOR = {SlotState.CONFIRMED: "positive", SlotState.PRESENT: "primary", SlotState.SILENT: "warning",
               SlotState.MISMATCH: "negative", SlotState.MISSING: "negative"}


class LogBuffer(logging.Handler):
    """Collects log lines from any thread; pages pull the new ones on a timer."""

    def __init__(self, maxlen=2000):
        super().__init__()
        self.lines = deque(maxlen=maxlen)
        self._seq = itertools.count(1)
        self._lock = threading.Lock()
        self.setFormatter(logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S"))

    def emit(self, record):
        with self._lock:
            self.lines.append((next(self._seq), self.format(record)))

    def since(self, seq):
        with self._lock:
            return [(n, line) for n, line in self.lines if n > seq]


class State:
    """Shared by every browser tab."""

    def __init__(self, session, values, logbuf):
        self.session, self.logbuf = session, logbuf
        self.values = {f.key: values.get(f.key, "") for f in session.manifest.session_fields}
        self.busy = None  # "starting" / "stopping" while LabRecorderCLI works

    def clean_values(self):
        return {k: v.strip() for k, v in self.values.items() if v and v.strip()}


def build_page(state):
    session = state.session
    manifest = session.manifest
    slot_ui = {}

    ui.page_title(f"Session monitor - {manifest.path.name}")
    with ui.header().classes("items-center justify-between"):
        ui.label(f"Session monitor · {manifest.path.name} · {session.host}").classes("text-lg")
        status = ui.badge("IDLE", color="grey").classes("text-base q-px-md q-py-xs")

    with ui.row().classes("w-full items-start no-wrap gap-4"):
        # ---------------------------------------------------------- left: identifiers + recording
        with ui.column().classes("w-96 gap-4"):
            with ui.card().classes("w-full"):
                ui.label("Session identifiers").classes("text-h6")
                for f in manifest.session_fields:
                    hint = f"e.g. {f.example}" if f.example else ("optional" if not f.required else "")
                    ui.input(f.label, placeholder=hint, validation=lambda v, f=f: f.check(v)) \
                        .bind_value(state.values, f.key).classes("w-full").props("dense")
                next_file = ui.label().classes("text-caption text-grey-8 break-all")

            with ui.card().classes("w-full"):
                ui.label("Recording").classes("text-h6")
                with ui.row():
                    start_btn = ui.button("Start recording", icon="fiber_manual_record", color="negative")
                    stop_btn = ui.button("Stop", icon="stop", color="grey-8")
                rec_info = ui.label().classes("text-caption break-all")
                rec_alert = ui.label().classes("text-body2 text-negative text-weight-medium")
                blockers = ui.column().classes("gap-0 text-caption text-negative")
                with ui.row().classes("w-full items-center no-wrap"):
                    note = ui.input("Note").classes("grow").props("dense")
                    note_btn = ui.button(icon="send").props("flat dense")

        # ---------------------------------------------------------- right: slots + extras
        with ui.column().classes("grow gap-4"):
            with ui.row().classes("items-center"):
                ui.label("Slots").classes("text-h6")
                confirm_all = ui.button("Confirm all present", icon="done_all").props("outline dense")
            seats = sorted({s.seat for s in manifest.slots}, key=lambda x: (x == "", x))
            for seat in seats:
                with ui.row().classes("w-full gap-3"):
                    for s in (s for s in manifest.slots if s.seat == seat):
                        with ui.card().classes("w-72"):
                            with ui.row().classes("w-full items-center justify-between no-wrap"):
                                ui.label(s.label).classes("text-subtitle1 text-weight-medium")
                                badge = ui.badge("MISSING", color="negative")
                            ui.label(f"{s.stream_name} @ {s.host}" + ("" if s.required else " · optional")) \
                                .classes("text-caption text-grey-8 break-all")
                            rate = ui.label().classes("text-body2")
                            detail = ui.label().classes("text-caption text-grey-8")
                            with ui.row():
                                cbtn = ui.button("Confirm", icon="check").props("dense")
                                ubtn = ui.button("Unconfirm").props("flat dense")
                            cbtn.on_click(lambda sid=s.id: session.monitor.confirm(sid))
                            ubtn.on_click(lambda sid=s.id: session.monitor.unconfirm(sid))
                            slot_ui[s.id] = dict(badge=badge, rate=rate, detail=detail, cbtn=cbtn, ubtn=ubtn)
            extras = ui.label().classes("text-caption text-grey-8")

    ui.label("Events").classes("text-h6 q-mt-md")
    log = ui.log(max_lines=500).classes("w-full h-64")

    # -------------------------------------------------------------- actions
    def do_confirm_all():
        for st in session.monitor.snapshot():
            if st.state == SlotState.PRESENT:
                session.monitor.confirm(st.slot.id)

    async def do_start():
        state.busy = "starting"
        refresh()
        try:
            xdf = await run.io_bound(session.start_recording, state.clean_values())
            ui.notify(f"Recording to {xdf.name}", type="positive")
        except RecorderError as e:
            ui.notify(f"Recording did not start: {e}", type="negative", multi_line=True, timeout=0, close_button=True)
        finally:
            state.busy = None

    async def do_stop():
        dialog.close()
        state.busy = "stopping"
        refresh()
        try:
            problems = await run.io_bound(session.stop_recording)
        finally:
            state.busy = None
        if problems:
            ui.notify("File problems: " + "; ".join(problems), type="negative", multi_line=True,
                      timeout=0, close_button=True)
        else:
            ui.notify("Recording stopped, file OK", type="positive")

    def do_note():
        text = (note.value or "").strip()
        if text:
            session.note(text, ts=pylsl.local_clock())
            note.value = ""

    with ui.dialog() as dialog, ui.card():
        ui.label("Stop the recording?")
        with ui.row():
            ui.button("Stop", color="negative", on_click=do_stop)
            ui.button("Keep recording", on_click=dialog.close).props("flat")

    start_btn.on_click(do_start)
    stop_btn.on_click(dialog.open)
    confirm_all.on_click(do_confirm_all)
    note_btn.on_click(do_note)
    note.on("keydown.enter", do_note)

    # -------------------------------------------------------------- refresh
    last_seq = [0]
    shown_reasons = [None]

    def refresh():
        for n, line in state.logbuf.since(last_seq[0]):
            log.push(line)
            last_seq[0] = n

        snap = session.monitor.snapshot()
        for st in snap:
            el = slot_ui[st.slot.id]
            el["badge"].set_text(st.state.value)
            color = STATE_COLOR[st.state] if (st.slot.required or st.state != SlotState.MISSING) else "grey"
            el["badge"].props(f"color={color}")
            el["rate"].set_text(f"{st.rate:.0f} samples/s" if st.rate is not None else "no data")
            found = f"from {st.found.host}" if st.found and st.found.host != st.slot.host else ""
            el["detail"].set_text(" · ".join(x for x in (st.detail, found) if x))
            el["cbtn"].set_enabled(st.state == SlotState.PRESENT)
            el["ubtn"].set_visibility(st.state == SlotState.CONFIRMED)
        ex = session.monitor.extras()
        extras.set_text("Not in the manifest: " + ", ".join(f"{f.name} @ {f.host}" for f in ex) if ex else "")

        cur = session.current
        values = state.clean_values()
        try:
            next_file.set_text("" if cur else
                               f"Next file: {manifest.build_filename(values, session.next_run(values))}.xdf")
        except (ValueError, KeyError):
            next_file.set_text("Next file: fill in the identifiers")
        lost = [st.slot.id for st in snap if st.slot.required and st.state not in DATA_STATES]
        rec_alert.set_text(f"No data from {', '.join(lost)}" if cur and lost else "")

        reasons = [] if cur or state.busy else session.blockers(values)
        if reasons != shown_reasons[0]:
            shown_reasons[0] = reasons
            blockers.clear()
            with blockers:
                for r in reasons:
                    ui.label(f"• {r}")
        start_btn.set_enabled(not cur and not state.busy and not reasons)
        stop_btn.set_enabled(bool(cur) and not state.busy)
        if state.busy:
            status.set_text(state.busy.upper() + "…")
            status.props("color=warning")
            rec_info.set_text("LabRecorderCLI is " + state.busy + "…")
        elif cur:
            elapsed = int(time.time() - cur["started"])
            status.set_text(f"REC {elapsed // 60:02d}:{elapsed % 60:02d}")
            status.props("color=negative")
            rec_info.set_text(f"Recording to {cur['xdf'].name}")
        else:
            status.set_text("IDLE")
            status.props("color=grey")
            rec_info.set_text("")

    refresh()
    ui.timer(0.5, refresh)


def parse_args(argv):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("manifest")
    p.add_argument("--out", default="data", help="folder for recordings and logs (default: data)")
    p.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="session identifier, repeatable")
    p.add_argument("--host", default="127.0.0.1",
                   help="address to serve on (0.0.0.0 to open the page from other computers on the network)")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--no-browser", action="store_true", help="do not open a browser tab")
    p.add_argument("--labrecorder-cli", default=None)
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("pyxdf").setLevel(logging.WARNING)
    logbuf = LogBuffer()
    logging.getLogger("session_monitor").addHandler(logbuf)
    try:
        manifest = load_manifest(args.manifest)
    except ManifestError as e:
        print(f"Manifest has problems:\n{e}")
        return 1
    values = {}
    for item in args.set:
        key, sep, value = item.partition("=")
        if not sep:
            print(f"--set expects KEY=VALUE, got {item!r}")
            return 2
        values[key.strip()] = value.strip()
    try:
        session = Session(manifest, out_dir=args.out, labrecorder_cli=args.labrecorder_cli)
    except RecorderError as e:
        print(e)
        return 1
    state = State(session, values, logbuf)
    session.start()

    app.on_shutdown(session.close)  # stops and checks a running recording before quitting
    ui.page("/")(lambda: build_page(state))
    ui.run(host=args.host, port=args.port, title="Session monitor", reload=False, show=not args.no_browser,
           show_welcome_message=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
