"""Analyze a bench-test XDF recording made with LabRecorder.

Reports, for every stream: sample count, duration, effective sampling rate and
gaps in the data. Then finds the table taps in each Enobio's accelerometer and
reports how far apart in time the devices saw the same tap, which is the
timing error between devices. Taps at the start and the end of a long
recording also show whether that error drifts over time.

    python bench/analyze_recording.py path/to/recording.xdf
"""
import argparse
import re

import numpy as np
import pyxdf

NAME_RE = re.compile(r"^(?P<pid>.+?)-(?P<kind>EEG|Accelerometer)(?P<suffix>.*)$")
GAP_FACTOR = 2.5  # a jump larger than this many sample periods counts as a gap


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("xdf", help="Recording to analyze")
    p.add_argument("--tap-threshold", type=float, default=8.0,
                   help="Tap detection threshold in robust standard deviations (default: 8)")
    p.add_argument("--tap-spacing", type=float, default=0.5, help="Minimum seconds between two taps (default: 0.5)")
    p.add_argument("--match-window", type=float, default=0.25,
                   help="Max seconds between the same tap on two devices (default: 0.25)")
    return p.parse_args()


def stream_name(stream):
    return stream["info"]["name"][0]


def stream_health(stream):
    ts = np.asarray(stream["time_stamps"], dtype=float)
    nominal = float(stream["info"]["nominal_srate"][0])
    out = {"name": stream_name(stream), "n": len(ts), "nominal": nominal}
    if len(ts) < 2:
        return out
    dt = np.diff(ts)
    out["start"] = ts[0]
    out["duration"] = ts[-1] - ts[0]
    out["effective"] = (len(ts) - 1) / out["duration"] if out["duration"] > 0 else float("nan")
    out["backwards"] = int(np.sum(dt <= 0))
    if nominal > 0:
        gaps = dt[dt > GAP_FACTOR / nominal]
        out["gaps"] = len(gaps)
        out["max_gap_ms"] = float(gaps.max() * 1000) if len(gaps) else 0.0
        out["lost_s"] = float(np.sum(gaps - 1 / nominal))
    return out


def print_health(streams):
    print(f"{'stream':<32} {'samples':>9} {'dur (s)':>9} {'nominal':>8} {'effective':>10} {'gaps':>5} {'max gap ms':>11} {'lost s':>7}")
    rows = [stream_health(s) for s in streams]
    for r in rows:
        if r["n"] < 2:
            print(f"{r['name']:<32} {r['n']:>9}   (too few samples)")
            continue
        gaps = r.get("gaps", "-")
        max_gap = f"{r['max_gap_ms']:.0f}" if "max_gap_ms" in r else "-"
        lost = f"{r['lost_s']:.2f}" if "lost_s" in r else "-"
        print(f"{r['name']:<32} {r['n']:>9} {r['duration']:>9.1f} {r['nominal']:>8.1f} {r['effective']:>10.2f} {gaps:>5} {max_gap:>11} {lost:>7}")
        if r["backwards"]:
            print(f"  ! {r['backwards']} timestamps go backwards or repeat")
    return rows


def check_clock_domains(rows):
    starts = {r["name"]: r["start"] for r in rows if "start" in r}
    if len(starts) < 2:
        return
    spread = max(starts.values()) - min(starts.values())
    if spread > 5:
        print(f"\n! Stream start times differ by {spread:.1f} s. Some streams are probably not on the LSL clock:")
        for name, start in sorted(starts.items(), key=lambda kv: kv[1]):
            print(f"    {name:<32} first timestamp {start:.3f}")


def detect_taps(times, xyz, threshold, spacing):
    """Return tap onset times: where the sample-to-sample change in acceleration jumps above baseline."""
    jerk = np.linalg.norm(np.diff(xyz, axis=0), axis=1)
    t = times[1:]
    med = np.median(jerk)
    mad = np.median(np.abs(jerk - med)) * 1.4826
    if mad == 0:
        mad = jerk.std() or 1.0
    level = med + threshold * mad
    above = jerk > level
    onsets = np.flatnonzero(above & ~np.concatenate(([False], above[:-1])))

    taps = []
    for i in onsets:
        if i > 0:  # interpolate the threshold crossing between the two samples
            frac = (level - jerk[i - 1]) / (jerk[i] - jerk[i - 1])
            onset = t[i - 1] + frac * (t[i] - t[i - 1])
        else:
            onset = t[i]
        if not taps or onset - taps[-1] >= spacing:
            taps.append(onset)
    return np.asarray(taps)


def tap_analysis(acc_streams, args):
    if len(acc_streams) < 2:
        print("\nTap analysis needs accelerometer streams from at least two devices.")
        return

    taps = {}
    periods_ms = []
    for pid, s in sorted(acc_streams.items()):
        times = np.asarray(s["time_stamps"], dtype=float)
        xyz = np.asarray(s["time_series"], dtype=float)[:, :3]
        rate = (len(times) - 1) / (times[-1] - times[0])
        periods_ms.append(1000 / rate)
        taps[pid] = detect_taps(times, xyz, args.tap_threshold, args.tap_spacing)
        print(f"  {pid}: {len(taps[pid])} taps found (accelerometer at {rate:.0f} Hz, "
              f"so single-sample resolution is {1000 / rate:.1f} ms)")

    ref = sorted(taps)[0]
    others = [p for p in sorted(taps) if p != ref]
    if not len(taps[ref]):
        print(f"\nNo taps found on {ref}. Try a lower --tap-threshold.")
        return

    t0 = taps[ref][0]
    print(f"\nTiming of each tap relative to {ref} (ms, positive = later than {ref}):")
    print(f"{'tap':>4} {'time (s)':>9} " + " ".join(f"{p:>10}" for p in others))
    offsets = {p: [] for p in others}
    for k, t_ref in enumerate(taps[ref], 1):
        cells = []
        for p in others:
            if len(taps[p]):
                j = np.argmin(np.abs(taps[p] - t_ref))
                d = taps[p][j] - t_ref
                if abs(d) <= args.match_window:
                    offsets[p].append((t_ref, d))
                    cells.append(f"{d * 1000:>10.1f}")
                    continue
            cells.append(f"{'no match':>10}")
        print(f"{k:>4} {t_ref - t0:>9.1f} " + " ".join(cells))

    print("\nSummary:")
    for p in others:
        if not offsets[p]:
            print(f"  {p} vs {ref}: no matching taps")
            continue
        when = np.array([o[0] for o in offsets[p]])
        d_ms = np.array([o[1] for o in offsets[p]]) * 1000
        line = (f"  {p} vs {ref}: {len(d_ms)} taps, median {np.median(d_ms):.1f} ms, "
                f"range {d_ms.min():.1f} to {d_ms.max():.1f} ms")
        if len(d_ms) >= 4 and when.max() - when.min() > 60:
            slope = np.polyfit(when - when[0], d_ms, 1)[0]
            line += f", drift {slope * 3600:.1f} ms/hour"
        print(line)
    print(f"\nNote: a tap's timing is only known to within one accelerometer sample (~{max(periods_ms):.0f} ms here),\n"
          "so offsets below that are not resolved by this test. Larger offsets and drift are.")


def main():
    args = parse_args()
    streams, _ = pyxdf.load_xdf(args.xdf, dejitter_timestamps=False)
    streams = sorted(streams, key=stream_name)
    print(f"{args.xdf}: {len(streams)} streams\n")

    rows = print_health(streams)
    check_clock_domains(rows)

    acc = {}
    for s in streams:
        m = NAME_RE.match(stream_name(s))
        if not m:
            continue
        if "NOT_SYNCED" in m["suffix"].upper():
            print(f"\n! {stream_name(s)} was recorded before synchronization finished")
        if m["kind"] == "Accelerometer" and len(s["time_stamps"]) > 1:
            acc[m["pid"]] = s

    print("\nTap detection:")
    tap_analysis(acc, args)


if __name__ == "__main__":
    main()
