# Bench test: three Enobios on one Windows PC

Goal: confirm that three Enobio 32 can stream at the same time over Wi-Fi from
one PC through LSL, with synchronized clocks, and measure how well their
timestamps line up. No custom SDK code is involved yet; this uses the
`NEDeviceStreamer.exe` that ships with the SDK.

What it answers:

- Do three streamers run side by side on one PC without dropping data?
- How long do sync phases 1 and 2 take on our router?
- What are the LSL stream names during and after sync?
- Are the SDK's LSL timestamps on the LSL clock (needed to align with other devices)?
- How far apart in time do the three devices see the same physical event, and does that drift?

## Setup (once)

1. **SDK**: copy the `NESDK-1.0.0` folder into the repo root (it is git-ignored),
   or set the `NESDK_DIR` environment variable to its location. Check that
   `NEDeviceStreamer.exe` exists inside it (extract `bin-win.zip` if not).
2. **Conda env** (64-bit is fine here; the bench scripts never load the SDK DLL):
   - Install Miniforge (https://conda-forge.org/download/) if conda is not
     already on the PC.
   - Make conda usable from the VS Code terminal: open "Miniforge Prompt"
     (or "Anaconda Prompt") and run `conda init powershell` once, then restart
     VS Code.
   - In VS Code: **Terminal > Run Task... > Env: create**, then
     **Env: check** to confirm the packages import.
   - Later, after `environment.yml` changes: **Env: update**.
   - Optional: pick `lab-intercom-study-cu` with **Python: Select Interpreter** so the
     editor uses the same env.
3. **LabRecorder**: download the latest Windows release from
   https://github.com/labstreaminglayer/App-LabRecorder/releases
4. **Network**: PC wired to the dedicated router; Enobios on that router's Wi-Fi
   (same procedure as for NIC2). Nothing else using the router.
5. **Firewall**: when Windows asks on the first run, allow `NEDeviceStreamer`,
   `python` and `LabRecorder` on private networks (LSL needs this).
6. **Close NIC2** so it does not hold on to the devices.
7. **MAC addresses**: write each device's MAC (back of the device) into
   `bench/devices.json`, and label the devices P1, P2, P3 physically.

## Run

Each step has a VS Code task (**Terminal > Run Task...**). From a terminal
with `conda activate lab-intercom-study-cu`, the equivalent `python bench/...`
command works too.

1. Charge and power on the three Enobios. Electrodes are not needed.
2. Start the streamers: task **Bench: launch streamers**.
   Three console windows open, one per device. Note the time each one reports
   phase 1 complete and phase 2 complete. Wait until all three report
   synchronized outlets. To stop, press Ctrl+C in the task terminal (if a
   streamer window stays open, close it).
3. Check the streams (second task terminal): task **Bench: check streams**.
   Expect 6 streams (`P1-EEG`, `P1-Accelerometer`, ...), measured rates close
   to nominal, delays of tens of milliseconds, and "All streams look healthy".
   Copy the output into the results below.
4. Put the three Enobio amplifiers **touching each other on a hard table**.
5. In LabRecorder, select the 6 streams and start recording to
   `bench_<date>.xdf`.
6. **Start taps**: 5 sharp knuckle taps on the table next to the devices,
   about 3 seconds apart.
7. **Wait at least 30 minutes** (ideally a full session length) without
   touching the devices.
8. **End taps**: 5 more taps, same as step 6. Stop the recording.
9. Analyze: task **Bench: analyze recording**, and give it the path to
   `bench_<date>.xdf` when prompted.

If something fails, repeat with one device only (remove the other two from
`devices.json`) to tell device problems apart from multi-device problems.

The tap test resolves timing only to about one accelerometer sample (the script
prints the value). It catches large offsets and drift, but cannot confirm
millisecond-level alignment; that needs a shared electrical test signal (see
BACKLOG.md).

## Results (fill in and send back)

```
Date / PC / router:
SDK streamer version (NEDeviceStreamer.exe -v):

Sync timing         P1        P2        P3
  phase 1 done   (mm:ss)   (mm:ss)   (mm:ss)
  phase 2 done   (mm:ss)   (mm:ss)   (mm:ss)

Stream names seen during sync:
Stream names seen after sync:

check_streams.py output:

analyze_recording.py output:

Anything unexpected (disconnects, reconnects, errors in the streamer windows):
```
