"""Session manifest: the streams a session expects, and the identifiers it records.

A manifest is a YAML file with three parts:

    session_fields   identifiers typed in before recording (group, session, task, ...)
    filename         template for XDF file names, built from those fields + {run}
    slots            the LSL streams expected, each matched by stream name + host

Check a manifest from the terminal:

    python -m session_monitor.manifest manifests/bench.yaml
"""
import re
import string
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
RUN_KEY = "run"  # counted by the recorder, not typed in

TOP_KEYS = {"session_fields", "filename", "slots"}
FIELD_KEYS = {"key", "label", "required", "pattern", "example", "help"}
SLOT_KEYS = {"id", "seat", "label", "stream_name", "host", "required"}


class ManifestError(Exception):
    """Raised with every problem found, one per line."""

    def __init__(self, path, problems):
        self.problems = problems
        super().__init__(f"{path}:\n  " + "\n  ".join(problems))


@dataclass(frozen=True)
class SessionField:
    key: str
    label: str
    required: bool = True
    pattern: str | None = None
    example: str | None = None
    help: str | None = None

    def check(self, value):
        """Return a problem for this value, or None."""
        value = (value or "").strip()
        if not value:
            return f"{self.label} is required" if self.required else None
        if self.pattern and not re.fullmatch(self.pattern, value):
            hint = f" (e.g. {self.example})" if self.example else ""
            return f"{self.label} '{value}' does not match {self.pattern}{hint}"
        return None


@dataclass(frozen=True)
class Slot:
    id: str
    seat: str
    label: str
    stream_name: str
    host: str
    required: bool = True

    def matches(self, stream_name, host):
        return stream_name == self.stream_name and host == self.host


@dataclass(frozen=True)
class Manifest:
    path: Path
    session_fields: tuple
    filename: str
    slots: tuple

    @property
    def required_slots(self):
        return tuple(s for s in self.slots if s.required)

    def check_session(self, values):
        """Problems with the identifiers typed in (empty list = all good)."""
        problems = [p for f in self.session_fields if (p := f.check(values.get(f.key)))]
        unknown = sorted(set(values) - {f.key for f in self.session_fields})
        problems += [f"unknown session field '{k}'" for k in unknown]
        return problems

    def build_filename(self, values, run):
        """File name (without .xdf) for one recording; run is counted by the recorder."""
        problems = self.check_session(values)
        if problems:
            raise ValueError("; ".join(problems))
        name = self.filename.format(**{k: str(v).strip() for k, v in values.items()}, run=f"{run:02d}")
        if not SAFE_FILENAME_RE.match(name):
            raise ValueError(f"file name '{name}' has characters other than letters, digits, _ . -")
        return name


def _unknown_keys(where, item, allowed):
    return [f"{where}: unknown key '{k}' (allowed: {', '.join(sorted(allowed))})"
            for k in item if k not in allowed]


def _parse_fields(raw, problems):
    fields, seen = [], set()
    if not isinstance(raw, list) or not raw:
        problems.append("session_fields: must be a non-empty list")
        return fields
    for i, item in enumerate(raw):
        where = f"session_fields[{i}]"
        if not isinstance(item, dict):
            problems.append(f"{where}: must be a mapping")
            continue
        problems += _unknown_keys(where, item, FIELD_KEYS)
        key = str(item.get("key", ""))
        if not SLUG_RE.match(key) or not key.isidentifier():
            problems.append(f"{where}: key '{key}' must be letters, digits and _ (starting with a letter)")
            continue
        if key == RUN_KEY:
            problems.append(f"{where}: '{RUN_KEY}' is counted by the recorder; remove it from session_fields")
            continue
        if key in seen:
            problems.append(f"{where}: duplicate key '{key}'")
            continue
        seen.add(key)
        pattern = item.get("pattern")
        if pattern is not None:
            try:
                re.compile(pattern)
            except re.error as e:
                problems.append(f"{where} ({key}): pattern does not compile: {e}")
                pattern = None
        field = SessionField(key=key, label=str(item.get("label", key)), required=bool(item.get("required", True)),
                             pattern=pattern, example=item.get("example"), help=item.get("help"))
        if field.example is not None and pattern and not re.fullmatch(pattern, str(field.example)):
            problems.append(f"{where} ({key}): example '{field.example}' does not match its own pattern")
        fields.append(field)
    return fields


def _parse_filename(raw, fields, problems):
    if not isinstance(raw, str) or not raw.strip():
        problems.append("filename: must be a template string, e.g. 'grp-{group}_run-{run}'")
        return ""
    known = {f.key for f in fields} | {RUN_KEY}
    try:
        used = {name for _, name, spec, _ in string.Formatter().parse(raw) if name is not None}
    except ValueError as e:
        problems.append(f"filename: {e}")
        return raw
    for name in sorted(used - known):
        problems.append(f"filename: '{{{name}}}' is not a session field (known: {', '.join(sorted(known))})")
    if RUN_KEY not in used:
        problems.append("filename: must include {run}, or two recordings of the same task would collide")
    optional = sorted(f.key for f in fields if not f.required and f.key in used)
    for key in optional:
        problems.append(f"filename: '{{{key}}}' is optional, so file names could have an empty part; make it required")
    return raw


def _parse_slots(raw, problems):
    slots, ids, pairs = [], set(), set()
    if not isinstance(raw, list) or not raw:
        problems.append("slots: must be a non-empty list")
        return slots
    for i, item in enumerate(raw):
        where = f"slots[{i}]"
        if not isinstance(item, dict):
            problems.append(f"{where}: must be a mapping")
            continue
        problems += _unknown_keys(where, item, SLOT_KEYS)
        sid = str(item.get("id", ""))
        if not SLUG_RE.match(sid):
            problems.append(f"{where}: id '{sid}' must be letters, digits, _ and - (max 64)")
            continue
        missing = [k for k in ("stream_name", "host") if not str(item.get(k, "")).strip()]
        if missing:
            problems.append(f"{where} ({sid}): missing {', '.join(missing)}")
            continue
        slot = Slot(id=sid, seat=str(item.get("seat", "")).strip(), label=str(item.get("label", sid)),
                    stream_name=str(item["stream_name"]).strip(), host=str(item["host"]).strip(),
                    required=bool(item.get("required", True)))
        if sid in ids:
            problems.append(f"{where}: duplicate slot id '{sid}'")
            continue
        if (slot.stream_name, slot.host) in pairs:
            problems.append(f"{where} ({sid}): stream '{slot.stream_name}' on host '{slot.host}' is already another slot")
            continue
        ids.add(sid)
        pairs.add((slot.stream_name, slot.host))
        slots.append(slot)
    if slots and not any(s.required for s in slots):
        problems.append("slots: at least one slot must be required")
    return slots


def load_manifest(path):
    """Load and validate a manifest; raises ManifestError listing every problem."""
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError) as e:
        raise ManifestError(path, [str(e)]) from e
    if not isinstance(raw, dict):
        raise ManifestError(path, ["top level must be a mapping with session_fields, filename, slots"])

    problems = _unknown_keys("top level", raw, TOP_KEYS)
    fields = _parse_fields(raw.get("session_fields"), problems)
    filename = _parse_filename(raw.get("filename"), fields, problems)
    slots = _parse_slots(raw.get("slots"), problems)
    if problems:
        raise ManifestError(path, problems)
    return Manifest(path=path, session_fields=tuple(fields), filename=filename, slots=tuple(slots))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: python -m session_monitor.manifest <manifest.yaml>")
        return 2
    try:
        m = load_manifest(argv[0])
    except ManifestError as e:
        print(f"Manifest has problems:\n{e}")
        return 1

    print(f"{m.path}: OK\n\nSession fields:")
    for f in m.session_fields:
        req = "required" if f.required else "optional"
        print(f"  {f.key:<12} {f.label:<24} {req:<9} e.g. {f.example or '-'}")
    examples = {f.key: f.example for f in m.session_fields if f.example is not None}
    try:
        print(f"\nExample file name: {m.build_filename(examples, run=1)}.xdf")
    except ValueError as e:
        print(f"\nExample file name: cannot build from the examples ({e})")
    print(f"\nSlots ({len(m.required_slots)} required of {len(m.slots)}):")
    print(f"  {'id':<14} {'seat':<6} {'stream name':<20} {'host':<20} required")
    for s in m.slots:
        print(f"  {s.id:<14} {s.seat:<6} {s.stream_name:<20} {s.host:<20} {'yes' if s.required else 'no'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
