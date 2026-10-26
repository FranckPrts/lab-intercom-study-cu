"""Live check of the LSL streams on the network, before recording.

Lists every visible stream, then reads from all of them for a few seconds and
reports the measured sampling rate and the delay between each sample's
timestamp and this computer's LSL clock. A delay of seconds or more means a
stream's timestamps are not on the LSL clock and cannot be aligned as-is.

It also compares the streams with a session manifest, and when a slot's
stream comes from another computer than the manifest says, prints the host
name to put in the manifest (how to find the tablets' real names on the day).

Run it on the recording computer, with NIC2 streaming on all three tablets.

    python bench/check_streams.py
    python bench/check_streams.py --manifest manifests/bench.yaml --seconds 30
"""
import argparse
import sys
import time
from pathlib import Path

import pylsl

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from session_monitor.manifest import ManifestError, load_manifest  # noqa: E402

MAX_REASONABLE_DELAY_S = 1.0


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--wait", type=float, default=5.0, help="Seconds to look for streams (default: 5)")
    p.add_argument("--seconds", type=float, default=10.0, help="Seconds to read data for (default: 10)")
    p.add_argument("--manifest", type=Path, default=REPO / "manifests" / "bench.yaml",
                   help="session manifest to compare with (default: manifests/bench.yaml)")
    return p.parse_args()


def compare_with_manifest(manifest, infos):
    """Print, per slot, whether its stream is on the expected host; suggest host values."""
    print(f"\nCompared with {manifest.path}:")
    suggestions, seat_hosts = {}, {}
    for slot in manifest.slots:
        found = [i for i in infos if i.name() == slot.stream_name]
        here = [i for i in found if i.hostname().casefold() == slot.host.casefold()]
        req = "" if slot.required else " (optional)"
        if len(here) == 1:
            verdict = f"OK on {slot.host}"
            seat_hosts.setdefault(slot.seat, set()).add(here[0].hostname())
        elif len(here) > 1:
            verdict = f"{len(here)} streams with this name on {slot.host}"
        elif found:
            hosts = sorted({i.hostname() for i in found})
            verdict = f"found on {', '.join(hosts)}, manifest says {slot.host}"
            if len(hosts) == 1:
                suggestions[slot.id] = hosts[0]
                seat_hosts.setdefault(slot.seat, set()).add(hosts[0])
        else:
            verdict = "not on the network"
        print(f"  {slot.id:<20} {verdict}{req}")
    if suggestions:
        print(f"\nPut these host names in {manifest.path} (slots section):")
        for sid, host in suggestions.items():
            print(f"  {sid:<20} host: {host}")
    shared = {h for hs in seat_hosts.values() for h in hs
              if sum(h in other for other in seat_hosts.values()) > 1}
    if shared:
        print(f"\nSeveral seats stream from the same computer: {', '.join(sorted(shared))}")


def main():
    args = parse_args()
    print(f"Looking for LSL streams for {args.wait:.0f} s...")
    infos = sorted(pylsl.resolve_streams(wait_time=args.wait), key=lambda i: i.name())
    if not infos:
        print("No streams found. Check that NIC2 is streaming LSL on each tablet, the tablets are on the wired\n"
              "network, and the firewall allows NIC2 and python.")
        return

    print(f"\n{'name':<32} {'type':<14} {'ch':>3} {'rate':>7}  host")
    for info in infos:
        print(f"{info.name():<32} {info.type():<14} {info.channel_count():>3} {info.nominal_srate():>7.1f}  {info.hostname()}")

    try:
        compare_with_manifest(load_manifest(args.manifest), infos)
    except ManifestError as e:
        print(f"\n(manifest not compared: {e})")

    print(f"\nReading all streams for {args.seconds:.0f} s...")
    inlets = []
    for info in infos:
        inlet = pylsl.StreamInlet(info, max_buflen=60)
        inlet.open_stream(timeout=5)
        inlets.append((info, inlet, inlet.time_correction(timeout=5)))

    counts = {info.name(): 0 for info, _, _ in inlets}
    last_ts = {}
    for info, inlet, _ in inlets:  # drop what piled up while the inlets were opening
        while True:
            _, stamps = inlet.pull_chunk(timeout=0.0, max_samples=4096)
            if not stamps:
                break
            last_ts[info.name()] = stamps[-1]
    t_end = time.monotonic() + args.seconds
    while time.monotonic() < t_end:
        for info, inlet, _ in inlets:
            _, stamps = inlet.pull_chunk(timeout=0.0, max_samples=4096)
            if stamps:
                counts[info.name()] += len(stamps)
                last_ts[info.name()] = stamps[-1]
        time.sleep(0.05)
    now = pylsl.local_clock()

    print(f"\n{'name':<32} {'nominal':>8} {'measured':>9} {'delay (ms)':>11}")
    problems = []
    for info, _, correction in inlets:
        name = info.name()
        measured = counts[name] / args.seconds
        if name in last_ts:
            delay = now - (last_ts[name] + correction)
            delay_txt = f"{delay * 1000:11.1f}"
            period = 1 / info.nominal_srate() if info.nominal_srate() > 0 else 0.0
            if abs(delay) > MAX_REASONABLE_DELAY_S + period:  # slow streams lag by up to one sample
                problems.append(f"{name}: timestamps are {delay:.1f} s away from the LSL clock")
        else:
            delay_txt = f"{'no data':>11}"
            if info.nominal_srate() > 0:  # irregular streams (markers) are often silent
                problems.append(f"{name}: no samples received")
        nominal = info.nominal_srate()
        if nominal > 0 and name in last_ts and abs(measured - nominal) / nominal > 0.05:
            problems.append(f"{name}: measured {measured:.1f} Hz vs nominal {nominal:.1f} Hz")
        print(f"{name:<32} {nominal:>8.1f} {measured:>9.1f} {delay_txt}")

    print("\n" + ("Problems:\n  " + "\n  ".join(problems) if problems else "All streams look healthy."))


if __name__ == "__main__":
    main()
