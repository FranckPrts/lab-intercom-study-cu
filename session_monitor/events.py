"""Event log: each event goes to an LSL marker stream, a CSV file and the terminal.

Events are JSON objects with a "type" (slot, recording_start, note, ...), so
they can be parsed back out of the XDF. The CSV keeps events sent while no
recording is running, which never reach an XDF file.
"""
import csv
import json
import logging
import threading
from datetime import datetime
from pathlib import Path

import pylsl

log = logging.getLogger("session_monitor")

OWN_SOURCE_PREFIX = "session-monitor-"  # source_id prefix of every stream this program publishes


class EventLog:
    def __init__(self, out_dir, host):
        self.stream_name = f"SessionMonitor-{host}-Markers"
        self.source_id = f"{OWN_SOURCE_PREFIX}{host}-markers"
        info = pylsl.StreamInfo(self.stream_name, "Markers", 1, 0, pylsl.cf_string, self.source_id)
        info.desc().append_child_value("manufacturer", "session_monitor")
        self.outlet = pylsl.StreamOutlet(info)

        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        self.csv_path = out_dir / f"{datetime.now():%Y%m%d_%H%M%S}_{host}_events.csv"
        self._file = open(self.csv_path, "w", newline="")
        self._csv = csv.writer(self._file)
        self._csv.writerow(["lsl_time", "wall_time", "event"])
        self._lock = threading.Lock()

    def event(self, kind, ts=None, **fields):
        """Send one event; returns its LSL timestamp."""
        ts = pylsl.local_clock() if ts is None else ts
        text = json.dumps({"type": kind, **fields}, ensure_ascii=False)
        with self._lock:
            self.outlet.push_sample([text], ts)
            self._csv.writerow([f"{ts:.6f}", datetime.now().isoformat(timespec="milliseconds"), text])
            self._file.flush()
        log.info("%s %s", kind, " ".join(f"{k}={v}" for k, v in fields.items()))
        return ts

    def close(self):
        with self._lock:
            self._file.close()
