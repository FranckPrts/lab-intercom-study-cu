# Bench test: three Enobios, three tablets, one recording PC

Goal: confirm that three Enobio 32, each driven by its own NIC2 on its own
Windows tablet, can stream to one recording PC through LSL at the same time,
and measure how well their timestamps line up.

Setup in one picture:

```
Enobio P1 ──Wi-Fi (its own NECBOX network)── Tablet 1 (NIC2) ──Ethernet──┐
Enobio P2 ──Wi-Fi (its own NECBOX network)── Tablet 2 (NIC2) ──Ethernet──┼── switch/router ── Recording PC (LabRecorder + scripts)
Enobio P3 ──Wi-Fi (its own NECBOX network)── Tablet 3 (NIC2) ──Ethernet──┘
```

Each Enobio makes its own Wi-Fi network, which takes the tablet's Wi-Fi. So
each tablet reaches the others over a cable (USB Ethernet adapter if it has no
port). Neuroelectrics also recommends a wired connection when LSL is on, so it
does not compete with the Enobio link.

What it answers:

- Do three NIC2 instances stream side by side without dropping data?
- How long does NIC2's synchronizer take before a recording can start?
- Are NIC2's LSL timestamps on the LSL clock (needed to align with other devices)?
- How far apart in time do the three devices see the same physical event, and does that drift?

## Setup (once)

1. **Tablets**: install the latest NIC2 on each tablet. Label tablets 1, 2, 3
   and the Enobios P1, P2, P3; tablet N always drives Enobio PN. Fill in each
   Enobio's MAC (back of the device) and the tablet's computer name in
   `bench/devices.json` (copy `devices_EXAMPLE.json`).
2. **Wi-Fi**: on each tablet, join its own Enobio's NECBOX network in Windows
   Wi-Fi settings, with only that Enobio switched on, so each tablet remembers
   the right one. Untick "connect automatically" on any other Wi-Fi network.
3. **Wired network**: plug each tablet and the recording PC into the same
   switch/router. Nothing else on it.
4. **NIC2 settings** (each tablet):
   - When choosing the device, enable the **synchronizer** in the Settings pane.
   - In **Protocol Settings**, turn on LSL and set the outlet name to the
     participant: `P1` on tablet 1, `P2` on tablet 2, `P3` on tablet 3. NIC2 then
     publishes `P1-EEG`, `P1-Accelerometer`, `P1-Quality` and `P1-Markers`.
   - If NIC2 has an option to enable the accelerometer, turn it on (the tap
     test needs it).
   - Keep NIC2's own file saving on: it is a per-tablet backup of each recording.
5. **Recording PC**:
   - Install Miniforge (https://conda-forge.org/download/), open "Miniforge
     Prompt", run `conda init powershell` once, restart VS Code.
   - Open this folder in VS Code: **Terminal > Run Task... > Env: create**, then
     **Env: check**. Later, after `environment.yml` changes: **Env: update**.
   - Install LabRecorder:
     https://github.com/labstreaminglayer/App-LabRecorder/releases
6. **Firewall**: when Windows asks on the first run, allow NIC2 (tablets),
   `python` and `LabRecorder` (recording PC) on private networks. LSL needs this.

## Run

1. Charge and power on the three Enobios. Electrodes are not needed.
2. On each tablet: check it is on its own NECBOX Wi-Fi, start NIC2, connect its
   Enobio, load the protocol and start streaming. Note how long the
   synchronizer takes until NIC2 allows recording.
3. On the recording PC: task **Bench: check streams**. Expect 12 streams
   (4 per participant), each participant on a different host, measured rates
   close to nominal, delays of tens of milliseconds, and "All streams look
   healthy". The Markers streams show "no data" until a marker is sent; that is
   fine. Copy the output into the results below.
4. Put the three Enobio amplifiers **touching each other on a hard table**.
5. In LabRecorder, select all 12 streams and start recording to
   `bench_<date>.xdf`.
6. **Start taps**: 5 sharp knuckle taps on the table next to the devices,
   about 3 seconds apart.
7. **Wait at least 30 minutes** (ideally a full session length) without
   touching the devices.
8. **End taps**: 5 more taps, same as step 6. Stop the recording.
9. Analyze: task **Bench: analyze recording**, and give it the path to
   `bench_<date>.xdf` when prompted.

If something fails, repeat with one tablet only to tell device problems apart
from multi-device problems.

The tap test resolves timing only to about one accelerometer sample (the script
prints the value). It catches large offsets and drift, but cannot confirm
millisecond-level alignment; that needs a shared electrical test signal (see
BACKLOG.md).

## Results (fill in and send back)

```
Date / tablets / recording PC / switch:
NIC2 version:

Synchronizer time    P1        P2        P3
  ready to record (mm:ss)   (mm:ss)   (mm:ss)

NECBOX network names seen (one per Enobio?):

check_streams.py output:

analyze_recording.py output:

Anything unexpected (disconnects, reconnects, NIC2 warnings):
```
