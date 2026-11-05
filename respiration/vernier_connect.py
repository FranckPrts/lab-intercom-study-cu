"""
vernier_connect.py

Makes THIS computer connect to ONE specific Vernier Go Direct sensor
(e.g. a GDX-RB respiration belt) over Bluetooth, checks it's the right one,
streams it to LSL with vernier-lsl, and restarts the stream if it drops.

Usage:
    python3.12 vernier_connect.py                 # run normally
    python3.12 vernier_connect.py --list-streams  # show LSL streams (for setup)

Requires: pip install vernier-lsl pylsl
"""
import argparse
import datetime
import subprocess
import sys
import time

# ------------- SETTINGS -------------
# Belts the user can choose from at startup: (label, serial number).
MANIFEST = [
    ("Green nunchucks", "0K7017C4"),
    ("No sticker-----", "0K702267"),
    ("Purple shuriken", "0K702263"),
    ("Blue nunchucks-", "0K7017F1"),
]
VERNIER_LSL = "vernier-lsl"    # or full path, e.g. r"C:\...\Scripts\vernier-lsl.exe"
MODE = "ble"

# Set at startup from the chosen belt; don't edit these.
EXPECTED_SERIAL = None
STREAM_MATCH = None
SCAN_TIMEOUT = 40              # seconds to allow each Bluetooth scan
STALL_SECONDS = 10             # restart if no samples arrive for this long
LOG_FILE = "vernier_connect.log"
# ------------------------------------------------------------------

CHECKLIST = """
  Belt {serial} not found. Check:
   - Belt is switched on (press power; LED should blink)
   - Belt is NOT connected to Graphical Analysis, a phone, or another computer
   - Belt is NOT paired in Windows Bluetooth settings (remove it if it is)
   - Belt is within a few metres and the battery is charged
"""


def log(msg):
    line = f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def scan_once():
    """Run a vernier-lsl scan; return (found, output)."""
    try:
        # The scan ends with "Press return to close", so send Enter for it.
        result = subprocess.run(
            [VERNIER_LSL, "--scan", "--mode", MODE],
            input="\n", capture_output=True, text=True, timeout=SCAN_TIMEOUT,
        )
        output = (result.stdout or "") + (result.stderr or "")
    except subprocess.TimeoutExpired as e:
        partial = e.stdout or ""
        if isinstance(partial, bytes):
            partial = partial.decode(errors="replace")
        if EXPECTED_SERIAL.lower() in partial.lower():
            return True, partial
        return False, "(scan timed out)\n" + partial
    except FileNotFoundError:
        log(f"Cannot run '{VERNIER_LSL}'. Set VERNIER_LSL to the full path of vernier-lsl.exe.")
        sys.exit(1)
    return EXPECTED_SERIAL.lower() in output.lower(), output


def wait_for_belt():
    """Keep scanning until the expected belt is visible."""
    attempt = 0
    while True:
        attempt += 1
        log(f"Scanning for belt {EXPECTED_SERIAL} (attempt {attempt})...")
        found, output = scan_once()
        if found:
            log("Belt found.")
            return
        log("Not found. Scan output was:\n" + output.strip())
        print(CHECKLIST.format(serial=EXPECTED_SERIAL), flush=True)
        time.sleep(5)


def start_stream():
    log("Starting vernier-lsl stream...")
    return subprocess.Popen(
        [VERNIER_LSL, "--mode", MODE, "--serial_number", EXPECTED_SERIAL]
    )


def find_lsl_stream(timeout=30):
    """Wait for an LSL stream whose details contain STREAM_MATCH."""
    from pylsl import resolve_streams
    end = time.time() + timeout
    while time.time() < end:
        for info in resolve_streams(wait_time=2.0):
            text = " ".join([info.name(), info.type(), info.source_id(), info.as_xml()])
            if STREAM_MATCH.lower() in text.lower():
                log(f"LSL stream confirmed: name='{info.name()}' type='{info.type()}'")
                return info
    return None


def monitor(proc, info):
    """Return when the stream process exits or data stops arriving."""
    from pylsl import StreamInlet
    inlet = StreamInlet(info)
    while True:
        if proc.poll() is not None:
            log(f"vernier-lsl exited (code {proc.returncode}).")
            return
        sample, _ = inlet.pull_sample(timeout=STALL_SECONDS)
        if sample is None:
            log(f"No data for {STALL_SECONDS} s - belt may have disconnected or switched off.")
            return


def stop(proc):
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def list_streams():
    from pylsl import resolve_streams
    streams = resolve_streams(wait_time=3.0)
    if not streams:
        print("No LSL streams found. Start vernier-lsl first, then run this again.")
    for info in streams:
        print(f"name={info.name()!r} type={info.type()!r} source_id={info.source_id()!r}")
        print(info.as_xml()[:1500], "\n")


def scan_visible_serials():
    """One quick scan; return the set of manifest serials currently visible."""
    try:
        result = subprocess.run(
            [VERNIER_LSL, "--scan", "--mode", MODE],
            input="\n", capture_output=True, text=True, timeout=SCAN_TIMEOUT,
        )
        output = ((result.stdout or "") + (result.stderr or "")).lower()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return set()
    return {serial for _, serial in MANIFEST if serial.lower() in output}


def choose_belt():
    """Show the manifest as a numbered menu and return the chosen (label, serial)."""
    visible = None
    while True:
        print("\nWhich belt should this computer use?")
        for i, (label, serial) in enumerate(MANIFEST, start=1):
            status = ""
            if visible is not None:
                status = "  [available]" if serial in visible else "  [not seen]"
            print(f"  {i}. {label}  ({serial}){status}")
        print("  s. Scan to see which belts are available")
        print("  q. Quit")
        choice = input("Enter a number and press Enter: ").strip().lower()

        if choice == "q":
            sys.exit(0)
        if choice == "s":
            print("Scanning...", flush=True)
            visible = scan_visible_serials()
            continue
        if choice.isdigit() and 1 <= int(choice) <= len(MANIFEST):
            return MANIFEST[int(choice) - 1]
        print(f"'{choice}' isn't an option - enter 1 to {len(MANIFEST)}, s, or q.")


def main():
    global EXPECTED_SERIAL, STREAM_MATCH
    parser = argparse.ArgumentParser()
    parser.add_argument("--list-streams", action="store_true")
    parser.add_argument("--belt", type=int,
                        help="skip the menu and use this manifest number (e.g. for Task Scheduler)")
    args = parser.parse_args()
    if args.list_streams:
        list_streams()
        return

    if args.belt is not None:
        if not 1 <= args.belt <= len(MANIFEST):
            print(f"--belt must be between 1 and {len(MANIFEST)}")
            sys.exit(2)
        label, serial = MANIFEST[args.belt - 1]
    else:
        label, serial = choose_belt()
    EXPECTED_SERIAL = serial
    STREAM_MATCH = serial

    log(f"vernier_connect started. Belt: {label} ({EXPECTED_SERIAL})")
    proc = None
    try:
        while True:
            wait_for_belt()
            proc = start_stream()
            info = find_lsl_stream()
            if info is None:
                log(f"Stream started but no LSL stream matching '{STREAM_MATCH}' appeared. "
                    "Run with --list-streams to check STREAM_MATCH.")
            else:
                log("Streaming OK. Monitoring...")
                monitor(proc, info)
            stop(proc)
            log("Restarting in 5 s...")
            time.sleep(5)
    except KeyboardInterrupt:
        log("Stopped by user.")
    finally:
        stop(proc)


if __name__ == "__main__":
    main()