"""Terminal front end: monitor the manifest's streams, confirm slots, record, add notes.

    python -m session_monitor.cli manifests/bench.yaml
    python -m session_monitor.cli manifests/bench.yaml --set group=G01 --set session=01

Type a command and press Enter (? for the list). Every event is printed here,
sent on the LSL marker stream and written to the CSV log in --out.
"""
import argparse
import logging
import queue
import sys
import threading
import time

import pylsl

from .manifest import ManifestError, load_manifest
from .monitor import SlotState
from .recorder import RecorderError
from .session import Session

HELP = """
  Commands (type, then Enter):
    s            show the slot table now
    c SLOT       confirm a slot (its data must be arriving)    c all  confirm every PRESENT slot
    u SLOT       remove a slot's confirmation
    v            enter or change the session identifiers
    r            start recording (needs every required slot CONFIRMED)
    x            stop recording (then the file is checked)
    n TEXT       note, timestamped when you press Enter
    q            quit (stops a recording first)
    ?            this help
"""

STATE_MARK = {SlotState.CONFIRMED: "ok", SlotState.PRESENT: "--", SlotState.SILENT: "!!",
              SlotState.MISMATCH: "!!", SlotState.MISSING: "!!"}


def parse_args(argv):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("manifest")
    p.add_argument("--out", default="data", help="folder for recordings and logs (default: data)")
    p.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="session identifier, repeatable")
    p.add_argument("--status-every", type=float, default=10.0, help="seconds between status lines (0 = off)")
    p.add_argument("--labrecorder-cli", default=None, help="path to LabRecorderCLI (default: found automatically)")
    p.add_argument("--debug", action="store_true", help="also print LabRecorderCLI's output")
    return p.parse_args(argv)


def slot_table(session):
    lines = [f"  {'':2} {'slot':<22} {'state':<9} {'rate':>7}  {'stream @ host':<36} detail"]
    for st in session.monitor.snapshot():
        s = st.slot
        rate = f"{st.rate:.0f}/s" if st.rate is not None else "-"
        where = f"{s.stream_name} @ {st.found.host if st.found else s.host}"
        req = ("" if s.required else " (optional)") + ("" if s.needs_data else " (presence only)")
        lines.append(f"  {STATE_MARK[st.state]:2} {s.id:<22} {st.state.value:<9} {rate:>7}  {where:<36} {st.detail}{req}")
    extras = session.monitor.extras()
    if extras:
        lines.append("  not in the manifest: " + ", ".join(f"{f.name} @ {f.host}" for f in extras))
    return "\n".join(lines)


def status_line(session):
    parts = [f"{st.slot.id}:{st.state.value}" for st in session.monitor.snapshot()]
    cur = session.current
    rec = f" | REC {cur['xdf'].name} {time.time() - cur['started']:.0f}s" if cur else ""
    return "[status] " + " ".join(parts) + rec


class Terminal:
    def __init__(self, session, values, status_every):
        self.session, self.values, self.status_every = session, values, status_every
        self.lines = queue.Queue()

    def read_stdin(self):
        try:
            for line in sys.stdin:
                self.lines.put((pylsl.local_clock(), line.rstrip("\n")))  # stamp at Enter
        except Exception:
            pass
        self.lines.put((pylsl.local_clock(), None))  # stdin closed

    def ask(self, prompt):
        print(prompt, end="", flush=True)
        _, line = self.lines.get()
        return None if line is None else line.strip()

    def edit_values(self):
        print("  Session identifiers (Enter keeps the current value, '-' clears it):")
        for f in self.session.manifest.session_fields:
            current = self.values.get(f.key, "")
            hint = f"e.g. {f.example}" if f.example else ("optional" if not f.required else "")
            while True:
                answer = self.ask(f"    {f.label} [{current or hint}]: ")
                if answer is None:
                    return
                value = current if answer == "" else ("" if answer == "-" else answer)
                problem = f.check(value)
                if not problem:
                    break
                print(f"      {problem}")
            if value:
                self.values[f.key] = value
            else:
                self.values.pop(f.key, None)
        self.show_values()

    def show_values(self):
        stem = None
        try:
            stem = self.session.manifest.build_filename(self.values, self.session.next_run(self.values))
        except (ValueError, KeyError):
            pass
        print("  " + ", ".join(f"{k}={v}" for k, v in self.values.items()) if self.values else "  (no identifiers yet: v)")
        if stem:
            print(f"  next file: {stem}.xdf")

    def confirm(self, arg):
        if arg == "all":
            ids = [st.slot.id for st in self.session.monitor.snapshot() if st.state == SlotState.PRESENT]
            if not ids:
                print("  no PRESENT slot to confirm")
        else:
            ids = [arg]
        known = {s.id for s in self.session.manifest.slots}
        for sid in ids:
            if sid not in known:
                print(f"  unknown slot {sid!r} (slots: {', '.join(sorted(known))})")
            elif not self.session.monitor.confirm(sid):
                st = next(s for s in self.session.monitor.snapshot() if s.slot.id == sid)
                print(f"  {sid} cannot be confirmed: it is {st.state.value} {st.detail}".rstrip())

    def start(self):
        reasons = self.session.blockers(self.values)
        if reasons:
            print("  cannot start:\n    " + "\n    ".join(reasons))
            return
        print("  starting LabRecorderCLI...")
        try:
            xdf = self.session.start_recording(self.values)
            print(f"  RECORDING to {xdf}")
        except RecorderError as e:
            print(f"  recording did not start: {e}")

    def stop(self):
        if not self.session.recording:
            print("  not recording")
            return
        print("  stopping and checking the file...")
        problems = self.session.stop_recording()
        print("  file OK" if not problems else "  PROBLEMS:\n    " + "\n    ".join(problems))
        self.show_values()

    def handle(self, ts, line):
        cmd, _, arg = line.strip().partition(" ")
        arg = arg.strip()
        if cmd == "s":
            print(slot_table(self.session))
        elif cmd == "c" and arg:
            self.confirm(arg)
        elif cmd == "u" and arg:
            self.session.monitor.unconfirm(arg)
        elif cmd == "v":
            self.edit_values()
        elif cmd == "r":
            self.start()
        elif cmd == "x":
            self.stop()
        elif cmd == "n" and arg:
            self.session.note(arg, ts=ts)
        elif cmd == "q":
            return False
        elif cmd:
            print(HELP)
        return True

    def run(self):
        threading.Thread(target=self.read_stdin, daemon=True).start()
        print(HELP)
        self.show_values()
        last_status = time.monotonic()
        while True:
            try:
                ts, line = self.lines.get(timeout=0.5)
            except queue.Empty:
                if self.status_every and time.monotonic() - last_status >= self.status_every:
                    print(status_line(self.session))
                    last_status = time.monotonic()
                continue
            if line is None or not self.handle(ts, line):
                return


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("session_monitor").setLevel(logging.DEBUG if args.debug else logging.INFO)
    logging.getLogger("pyxdf").setLevel(logging.WARNING)
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
    problems = [p for p in manifest.check_session(values) if "unknown" in p]
    if problems:
        print("\n".join(problems))
        return 2

    try:
        session = Session(manifest, out_dir=args.out, labrecorder_cli=args.labrecorder_cli)
    except RecorderError as e:
        print(e)
        return 1
    session.start()
    print(f"Monitoring {len(manifest.slots)} slot(s) from {manifest.path}; events log: {session.events.csv_path}")
    try:
        Terminal(session, values, args.status_every).run()
    except KeyboardInterrupt:
        print()
    finally:
        if session.recording:
            print("stopping the recording before quitting...")
        session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
