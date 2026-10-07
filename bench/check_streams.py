"""Live check of the LSL streams on the network, before recording.

Lists every visible stream, then reads from all of them for a few seconds and
reports the measured sampling rate and the delay between each sample's
timestamp and this computer's LSL clock. A delay of seconds or more means a
stream's timestamps are not on the LSL clock and cannot be aligned as-is.

    python bench/check_streams.py
    python bench/check_streams.py --seconds 30
"""
import argparse
import json
import time
from pathlib import Path

import pylsl

HERE = Path(__file__).resolve().parent
MAX_REASONABLE_DELAY_S = 1.0


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--wait", type=float, default=5.0, help="Seconds to look for streams (default: 5)")
    p.add_argument("--seconds", type=float, default=10.0, help="Seconds to read data for (default: 10)")
    p.add_argument("--config", type=Path, default=HERE / "devices.json", help="Device list used to check expected streams")
    return p.parse_args()


def expected_streams(config_path):
    if not config_path.exists():
        return []
    devices = json.loads(config_path.read_text()).get("devices", [])
    return [f"{d['name']}-{kind}" for d in devices for kind in ("EEG", "Accelerometer")]


def main():
    args = parse_args()
    print(f"Looking for LSL streams for {args.wait:.0f} s...")
    infos = sorted(pylsl.resolve_streams(wait_time=args.wait), key=lambda i: i.name())
    if not infos:
        print("No streams found. Check that the streamers are running and the firewall allows LSL.")
        return

    print(f"\n{'name':<32} {'type':<14} {'ch':>3} {'rate':>7}  host")
    for info in infos:
        print(f"{info.name():<32} {info.type():<14} {info.channel_count():>3} {info.nominal_srate():>7.1f}  {info.hostname()}")

    names = {i.name() for i in infos}
    missing = [n for n in expected_streams(args.config) if n not in names]
    if missing:
        print(f"\nMissing expected streams: {', '.join(missing)}")
    not_synced = [n for n in names if "NOT_SYNCED" in n.upper()]
    if not_synced:
        print(f"\nStill synchronizing (wait before recording): {', '.join(not_synced)}")

    print(f"\nReading all streams for {args.seconds:.0f} s...")
    inlets = []
    for info in infos:
        inlet = pylsl.StreamInlet(info, max_buflen=60)
        inlet.open_stream(timeout=5)
        inlets.append((info, inlet, inlet.time_correction(timeout=5)))

    counts = {info.name(): 0 for info, _, _ in inlets}
    last_ts = {}
    t_end = time.monotonic() + args.seconds
    first_pull = True
    while time.monotonic() < t_end:
        for info, inlet, _ in inlets:
            _, stamps = inlet.pull_chunk(timeout=0.0, max_samples=4096)
            if stamps and not first_pull:  # first pull drains the backlog
                counts[info.name()] += len(stamps)
            if stamps:
                last_ts[info.name()] = stamps[-1]
        first_pull = False
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
            if abs(delay) > MAX_REASONABLE_DELAY_S:
                problems.append(f"{name}: timestamps are {delay:.1f} s away from the LSL clock")
        else:
            delay_txt = f"{'no data':>11}"
            problems.append(f"{name}: no samples received")
        nominal = info.nominal_srate()
        if nominal > 0 and name in last_ts and abs(measured - nominal) / nominal > 0.05:
            problems.append(f"{name}: measured {measured:.1f} Hz vs nominal {nominal:.1f} Hz")
        print(f"{name:<32} {nominal:>8.1f} {measured:>9.1f} {delay_txt}")

    print("\n" + ("Problems:\n  " + "\n  ".join(problems) if problems else "All streams look healthy."))


if __name__ == "__main__":
    main()
