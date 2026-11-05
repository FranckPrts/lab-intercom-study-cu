"""Session-info stream: makes every XDF identify its own session.

A new outlet is created for each recording, with the session identifiers,
run, file name, expected slots and software version in its stream header
(`desc`). LabRecorder writes stream headers into the XDF, so the information is
in the file whatever happens to the file name or the CSV log.
"""
import json
import os
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pylsl

from .events import OWN_SOURCE_PREFIX

REPO_DIR = Path(__file__).resolve().parent.parent


def host_label():
    """This computer's name, without the network suffix (stable across Wi-Fi/DHCP changes)."""
    if sys.platform == "darwin":
        try:
            r = subprocess.run(["scutil", "--get", "LocalHostName"], capture_output=True, text=True, timeout=3)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        except Exception:
            pass
    if sys.platform == "win32" and os.environ.get("COMPUTERNAME"):
        return os.environ["COMPUTERNAME"]
    return socket.gethostname().split(".")[0]


def software_version():
    """git commit of this code ('-dirty' if there are uncommitted changes), or 'unknown'."""
    try:
        r = subprocess.run(["git", "describe", "--always", "--dirty", "--tags"], cwd=REPO_DIR,
                           capture_output=True, text=True, timeout=5)
        return r.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def make_session_info(manifest, values, run, file_stem, host, version):
    """Returns (outlet, payload). Push json.dumps(payload) once recording has started."""
    payload = {
        "session": {f.key: str(values.get(f.key, "")).strip() for f in manifest.session_fields},
        "run": run,
        "file": f"{file_stem}.xdf",
        "manifest": manifest.path.name,
        "recording_host": host,
        "software_version": version,
        "created": datetime.now().astimezone().isoformat(timespec="seconds"),
        "slots": [{"id": s.id, "seat": s.seat, "label": s.label, "stream_name": s.stream_name,
                   "host": s.host, "required": s.required, "needs_data": s.needs_data} for s in manifest.slots],
    }
    info = pylsl.StreamInfo(f"SessionMonitor-{host}-SessionInfo", "SessionInfo", 1, 0, pylsl.cf_string,
                            f"{OWN_SOURCE_PREFIX}{host}-info-{file_stem}")
    d = info.desc()
    d.append_child_value("manufacturer", "session_monitor")
    session = d.append_child("session")
    for key, value in payload["session"].items():
        session.append_child_value(key, value)
    for key in ("run", "file", "manifest", "recording_host", "software_version", "created"):
        d.append_child_value(key, str(payload[key]))
    slots = d.append_child("slots")
    for s in payload["slots"]:
        node = slots.append_child("slot")
        for key, value in s.items():
            node.append_child_value(key, str(value))
    return pylsl.StreamOutlet(info), payload


def payload_text(payload):
    return json.dumps(payload, ensure_ascii=False)
