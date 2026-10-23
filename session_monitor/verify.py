"""After each recording: reopen the XDF and check it holds what it should."""
import json

import pyxdf


def _first(d, key, default=""):
    v = (d or {}).get(key)
    return v[0] if isinstance(v, list) and v else default


def verify_recording(xdf_path, expected, info_source_id, markers_source_id, session_values):
    """expected: [(name, hostname, required)]. Returns (problems, summary)."""
    streams, _ = pyxdf.load_xdf(str(xdf_path), dejitter_timestamps=False)
    problems, summary = [], []
    by_key = {}
    for s in streams:
        i = s["info"]
        key = (_first(i, "name"), _first(i, "hostname"))
        by_key.setdefault(key, []).append(s)
        summary.append({"name": key[0], "host": key[1], "type": _first(i, "type"),
                        "source_id": _first(i, "source_id"), "samples": len(s["time_stamps"])})

    for name, host, required in expected:
        found = by_key.get((name, host), [])
        if not found:
            if required:
                problems.append(f"missing required stream {name}@{host}")
        elif not len(found[0]["time_stamps"]):
            problems.append(f"{name}@{host} recorded no samples")

    by_source = {_first(s["info"], "source_id"): s for s in streams}
    info = by_source.get(info_source_id)
    if info is None:
        problems.append("session-info stream missing")
    else:
        desc = (_first(info["info"], "desc", {}) or {})
        session = _first(desc, "session", {}) or {}
        for key, value in session_values.items():
            if str(_first(session, key, "") or "") != str(value).strip():
                problems.append(f"session-info field {key} does not match ({_first(session, key, '')!r})")

    markers = by_source.get(markers_source_id)
    kinds = []
    if markers is None:
        problems.append("marker stream missing")
    else:
        for sample in markers["time_series"]:
            try:
                kinds.append(json.loads(sample[0]).get("type"))
            except (ValueError, AttributeError):
                pass
        for kind in ("recording_start", "recording_stop"):
            if kind not in kinds:
                problems.append(f"no {kind} marker in the file")
    return problems, summary


def write_sidecar(path, payload):
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
