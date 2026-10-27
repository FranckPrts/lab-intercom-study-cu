"""Fake streams: publish a manifest's slots with fake data, to rehearse without the tablets.

LSL always reports the real computer as a stream's host, so fakes on this
computer only match a manifest whose hosts are this computer. Write such a copy
with --local-manifest and point the monitor at it; with the original manifest
every slot shows MISMATCH (wrong host), which is a rehearsal too.

    # publish the bench streams and write a manifest matching this computer
    python -m session_monitor.fakes manifests/bench.yaml --local-manifest data/bench_local.yaml

    # problems to rehearse
    python -m session_monitor.fakes manifests/bench.yaml --skip P3-Quality \\
        --silent P2-EEG@30+15 --kill P1-EEG@90 --duplicate P3-EEG --extra Stray-Stream

Slot ids are the manifest's `id`s. Times are seconds after start.
"""
import argparse
import logging
import math
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pylsl
import yaml

from .manifest import ManifestError, load_manifest

log = logging.getLogger("session_monitor.fakes")

# (channels, nominal rate in Hz, LSL type), chosen from the stream name's suffix.
# Markers: irregular text stream (rate 0) that stays silent, like NIC2's between events.
KINDS = {
    "-EEG": (32, 500.0, "EEG"),
    "-Quality": (32, 1.0, "Quality"),
    "-Accelerometer": (3, 100.0, "Accelerometer"),  # rate is a guess; check NIC2's
    "-Markers": (1, 0.0, "Markers"),
}
DEFAULT_KIND = (1, 100.0, "Misc")


def kind_for(stream_name):
    for suffix, kind in KINDS.items():
        if stream_name.endswith(suffix):
            return kind
    return DEFAULT_KIND


@dataclass
class Fake:
    name: str
    channels: int
    rate: float
    type: str
    source_id: str
    silent: tuple = ()       # (start, end) seconds without data, outlet kept
    kill_at: float | None = None
    outlet: object = None
    sent: int = 0
    killed: bool = False

    def open(self):
        fmt = pylsl.cf_string if self.type == "Markers" else pylsl.cf_float32
        info = pylsl.StreamInfo(self.name, self.type, self.channels, self.rate, fmt, self.source_id)
        info.desc().append_child_value("manufacturer", "session_monitor.fakes")
        self.outlet = pylsl.StreamOutlet(info)

    def step(self, t0, elapsed):
        """Push every sample due by now (none while silent); returns an event string or None."""
        if self.killed:
            return None
        if self.kill_at is not None and elapsed >= self.kill_at:
            self.outlet, self.killed = None, True
            return f"{self.name} ({self.source_id}) killed"
        if self.rate <= 0:
            return None  # event stream: nothing to send
        due = int(elapsed * self.rate)
        if self.silent and self.silent[0] <= elapsed < self.silent[1]:
            self.sent = due  # skip the samples of the silent window
            return None
        if due <= self.sent:
            return None
        n = due - self.sent
        stamps = [t0 + (self.sent + i) / self.rate for i in range(n)]
        if self.type == "EEG":
            chunk = [[10 * math.sin(2 * math.pi * 10 * t + c) + random.gauss(0, 5) for c in range(self.channels)]
                     for t in stamps]
        else:
            chunk = [[random.uniform(0, 1) for _ in range(self.channels)] for _ in stamps]
        self.outlet.push_chunk(chunk, stamps)
        self.sent = due
        return None


def parse_window(text):
    """'P2-EEG@30+15' -> ('P2-EEG', 30.0, 45.0)"""
    slot, _, rest = text.partition("@")
    start, _, length = rest.partition("+")
    try:
        return slot, float(start), float(start) + float(length)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected SLOT@START+SECONDS, got {text!r}")


def parse_at(text):
    """'P1-EEG@90' -> ('P1-EEG', 90.0)"""
    slot, _, at = text.partition("@")
    try:
        return slot, float(at)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected SLOT@SECONDS, got {text!r}")


def parse_args(argv):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("manifest", help="manifest whose slots to publish")
    p.add_argument("--local-manifest", type=Path, help="write a copy of the manifest with every host set to this computer")
    p.add_argument("--skip", action="append", default=[], metavar="SLOT", help="do not publish this slot (MISSING)")
    p.add_argument("--silent", action="append", default=[], type=parse_window, metavar="SLOT@START+SECONDS",
                   help="publish the slot but send no data during this window (SILENT)")
    p.add_argument("--kill", action="append", default=[], type=parse_at, metavar="SLOT@SECONDS",
                   help="remove the slot's stream at this time (stream lost)")
    p.add_argument("--duplicate", action="append", default=[], metavar="SLOT",
                   help="publish the slot twice (MISMATCH: same name twice)")
    p.add_argument("--extra", action="append", default=[], metavar="NAME", help="also publish a stream no slot expects")
    p.add_argument("--duration", type=float, default=0, help="stop after this many seconds (0 = until Ctrl+C)")
    return p.parse_args(argv)


def write_local_manifest(src, dest, host):
    raw = yaml.safe_load(Path(src).read_text())
    for slot in raw.get("slots", []):
        slot["host"] = host
    dest.parent.mkdir(parents=True, exist_ok=True)
    header = f"# Generated by session_monitor.fakes from {src}: every host set to {host}.\n"
    dest.write_text(header + yaml.safe_dump(raw, sort_keys=False, allow_unicode=True))


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    try:
        manifest = load_manifest(args.manifest)
    except ManifestError as e:
        print(f"Manifest has problems:\n{e}")
        return 1

    ids = {s.id for s in manifest.slots}
    named = args.skip + args.duplicate + [w[0] for w in args.silent] + [k[0] for k in args.kill]
    unknown = sorted(set(named) - ids)
    if unknown:
        print(f"Unknown slot id(s): {', '.join(unknown)} (known: {', '.join(sorted(ids))})")
        return 2

    silent = {slot: (a, b) for slot, a, b in args.silent}
    kill = dict(args.kill)
    fakes = []
    for s in manifest.slots:
        if s.id in args.skip:
            continue
        ch, rate, kind = kind_for(s.stream_name)
        copies = 2 if s.id in args.duplicate else 1
        for k in range(copies):
            fakes.append(Fake(s.stream_name, ch, rate, kind, f"fake-{s.id}-{k}",
                              silent=silent.get(s.id, ()), kill_at=kill.get(s.id)))
    for name in args.extra:
        ch, rate, kind = kind_for(name)
        fakes.append(Fake(name, ch, rate, kind, f"fake-extra-{name}"))

    for f in fakes:
        f.open()
    host = fakes[0].outlet.get_info().hostname() if fakes else pylsl.StreamOutlet(
        pylsl.StreamInfo("probe", "Misc", 1, 0, pylsl.cf_float32, "fake-probe")).get_info().hostname()
    if args.local_manifest:
        write_local_manifest(args.manifest, args.local_manifest, host)
        log.info("wrote %s (hosts = %s)", args.local_manifest, host)

    log.info("publishing %d fake stream(s) from %s: %s", len(fakes), host,
             ", ".join(f"{f.name} {f.channels}ch {f.rate:g}Hz" if f.rate > 0 else f"{f.name} (events)" for f in fakes))
    for slot, (a, b) in silent.items():
        log.info("  %s silent from %g s to %g s", slot, a, b)
    for slot, at in kill.items():
        log.info("  %s killed at %g s", slot, at)

    t0 = pylsl.local_clock()
    try:
        while not args.duration or pylsl.local_clock() - t0 < args.duration:
            elapsed = pylsl.local_clock() - t0
            for f in fakes:
                if msg := f.step(t0, elapsed):
                    log.info(msg)
            time.sleep(0.02)
    except KeyboardInterrupt:
        pass
    log.info("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
