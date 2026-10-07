"""Start one NEDeviceStreamer per Enobio for the bench test (Windows only).

Each streamer opens in its own console window so its connection and sync
progress stay visible. Press Ctrl+C in this window to stop all of them.

    python bench/launch_streamers.py            # uses bench/devices.json
    python bench/launch_streamers.py --dry-run  # print the commands only

The SDK folder is located from --sdk-dir, then the NESDK_DIR environment
variable, then <repo>/NESDK-1.0.0 (git-ignored, so it can be copied there).
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
MAC_RE = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", type=Path, default=HERE / "devices.json", help="Device list (default: bench/devices.json)")
    p.add_argument("--sdk-dir", type=Path, default=None, help="Path to the NESDK-1.0.0 folder")
    p.add_argument("--stagger", type=float, default=5.0, help="Seconds between streamer launches (default: 5)")
    p.add_argument("--dry-run", action="store_true", help="Print the commands without starting anything")
    return p.parse_args()


def load_devices(config_path):
    cfg = json.loads(config_path.read_text())
    devices = cfg.get("devices", [])
    if not devices:
        sys.exit(f"No devices listed in {config_path}")

    problems = []
    for d in devices:
        d["mac"] = d.get("mac", "").strip().upper()
        if not MAC_RE.match(d["mac"]):
            problems.append(f"  {d.get('name', '?')}: '{d['mac']}' is not a full MAC address (see the back of the device)")
    names = [d.get("name") for d in devices]
    macs = [d["mac"] for d in devices]
    if len(set(names)) != len(names):
        problems.append("  device names must be unique")
    if len(set(macs)) != len(macs):
        problems.append("  MAC addresses must be unique")
    if problems:
        sys.exit(f"Fix {config_path}:\n" + "\n".join(problems))
    return devices, bool(cfg.get("sync", True))


def find_streamer(sdk_dir_arg):
    sdk_dir = sdk_dir_arg or (Path(os.environ["NESDK_DIR"]) if os.environ.get("NESDK_DIR") else REPO_ROOT / "NESDK-1.0.0")
    if not sdk_dir.is_dir():
        sys.exit(f"SDK folder not found: {sdk_dir}\nCopy NESDK-1.0.0 into the repo root, or pass --sdk-dir / set NESDK_DIR.")
    matches = sorted(sdk_dir.rglob("NEDeviceStreamer.exe"))
    if not matches:
        sys.exit(f"NEDeviceStreamer.exe not found under {sdk_dir}. Extract bin-win.zip there first.")
    return matches[0]


def main():
    args = parse_args()
    devices, sync = load_devices(args.config)
    exe = Path("NEDeviceStreamer.exe") if args.dry_run and os.name != "nt" else find_streamer(args.sdk_dir)

    commands = []
    for d in devices:
        cmd = [str(exe), "-d", d["mac"], "-o", d["name"]]
        if sync:
            cmd.append("-s")
        commands.append((d["name"], cmd))

    if args.dry_run:
        for name, cmd in commands:
            print(f"{name}: {subprocess.list2cmdline(cmd)}")
        return
    if os.name != "nt":
        sys.exit("The NE SDK streamer only runs on Windows. Use --dry-run to preview the commands.")

    procs = []
    try:
        for i, (name, cmd) in enumerate(commands):
            if i:
                time.sleep(args.stagger)  # avoid three simultaneous Wi-Fi scans
            print(f"[{time.strftime('%H:%M:%S')}] starting {name}: {subprocess.list2cmdline(cmd)}")
            procs.append((name, subprocess.Popen(cmd, cwd=exe.parent, creationflags=subprocess.CREATE_NEW_CONSOLE)))

        print("\nAll streamers started. Wait for each window to report synchronized outlets.")
        print("Press Ctrl+C here to stop all streamers.\n")
        running = {name for name, _ in procs}
        while running:
            for name, p in procs:
                if name in running and p.poll() is not None:
                    print(f"[{time.strftime('%H:%M:%S')}] {name} exited with code {p.returncode}")
                    running.discard(name)
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping streamers...")
    finally:
        for _, p in procs:
            if p.poll() is None:
                p.terminate()
        for _, p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    main()
