# Bench test: three Enobios, three NIC2 computers, the recording Mac

Goal: confirm that three Enobio 32, each driven by NIC2 on its own Windows
computer, stream to the recording Mac through LSL at the same time; that the
session monitor sees, records and checks them; and measure how well the
devices' timestamps line up.

```
Enobio P1 ──USB── NIC2 computer 1 ──Ethernet──┐
Enobio P2 ──USB── NIC2 computer 2 ──Ethernet──┼── switch ── router ── recording Mac
Enobio P3 ──USB── NIC2 computer 3 ──Ethernet──┘                       (session monitor + LabRecorderCLI)
```

What it answers:

- Do three NIC2 instances stream side by side without dropping data?
- How long does NIC2's synchronizer take before a recording can start?
- What do NIC2's `Quality` and `Accelerometer` streams look like (channels, rate)?
- Are NIC2's timestamps on the LSL clock (needed to align with other devices)?
- Does the session monitor confirm, record and check the real streams?
- How far apart in time do the three devices see the same physical event, and
  does that drift?

## Before the day (once)

1. **NIC2 computers**: install the latest NIC2. Label the computers 1, 2, 3
   and the Enobios P1, P2, P3; Enobio PN is always plugged by USB into
   computer N. In Windows: set the wired network as *Private*, allow NIC2
   through the firewall, turn Wi-Fi off.
2. **NIC2 settings** (each computer):
   - When choosing the device, enable the **synchronizer** in the Settings pane.
   - In **Protocol Settings**, turn on LSL. NIC2 on computer N publishes
     `ENOBIO<N>-EEG`, `-Quality`, `-Accelerometer` and `-Markers` (the number
     comes from the NIC2 install, so ENOBIO1 is always computer 1, seat P1).
     The session monitor records `EEG` and `Quality`, plus `Accelerometer`
     when present; NIC2's `Markers` stream is not used.
   - Turn the accelerometer on if NIC2 has an option for it (the tap test needs it).
   - Keep NIC2's own file saving on: it is a per-computer backup of each recording.
3. **Network**: NIC2 computers and the Mac on the same wired network, with fixed
   addresses for the NIC2 computers (DHCP reservations on the router).
4. **Recording Mac**:
   - Install Miniforge (https://conda-forge.org/download/) and run
     `conda init zsh` once; restart VS Code.
   - Open this folder in VS Code: **Terminal > Run Task... > Env: create**, then
     **Env: check**. After `environment.yml` changes: **Env: update**.
   - Install LabRecorder, which brings `LabRecorderCLI`: `brew install labrecorder`.
   - Copy `manifests/bench_EXAMPLE.yaml` to `manifests/bench.yaml` (git-ignored)
     and set each slot's `host` to the NIC2 computer's LSL host name.
   - **Local Network permission**: System Settings > Privacy & Security >
     Local Network, allow VS Code (or Terminal) and Python. Without it macOS
     silently blocks LSL.
   - **KnownPeers**: create `~/lsl_api/lsl_api.cfg` with the NIC2 computers'
     addresses, so discovery does not rely on multicast alone:
     ```ini
     [lab]
     KnownPeers = {192.168.10.x, 192.168.10.y, 192.168.10.z}
     ```
   - Turn the Mac's **Wi-Fi off** during the test.
5. **Rehearse on the Mac, no tablets needed**: run task **Fakes: publish bench
   streams**, then task **Session: GUI** with manifest `data/bench_local.yaml`.
   Fill in the identifiers, **Confirm all present**, **Start recording**, add a
   note, **Stop**: expect "Recording stopped, file OK". Stop the fakes (Ctrl+C)
   before the real test.

## On the day

1. Charge and power on the three Enobios (electrodes are not needed). On each
   NIC2 computer: connect its Enobio by USB, start NIC2, connect the device,
   load the protocol and start streaming. Note how long the synchronizer takes
   until NIC2 allows recording.
2. On the Mac: task **Bench: check streams**. Expect the `ENOBIO1` to
   `ENOBIO3` streams, each number from its own computer, every slot "OK" against
   [`manifests/bench.yaml`](../manifests/bench.yaml), and delays of tens of
   milliseconds. If it prints "Put these host names in manifests/bench.yaml",
   a computer's name changed: copy the new name into the manifest and run task
   **Manifest: check**. Copy the output into the results below, including the
   channels and rates of the `Quality` and `Accelerometer` streams.
3. Task **Session: GUI** with manifest `manifests/bench.yaml`. Identifiers for
   the bench run: group `G00`, session `01`, task `bench`, condition `taps`,
   participants `S901`, `S902`, `S903`, your initials as operator.
4. Every required slot card should show PRESENT with a plausible rate (EEG
   about 500 samples/s). Confirm each one (or **Confirm all present**). The
   accelerometer cards are optional: they are recorded when present.
5. Put the three Enobio amplifiers **touching each other on a hard table**,
   then **Start recording**.
6. Add the note `taps start`, then make 5 sharp knuckle taps on the table next
   to the devices, about 3 seconds apart.
7. **Wait at least 30 minutes** (ideally a full session length) without
   touching the devices. A red "No data from ..." line or a red card means a
   stream dropped: note the time and what happened.
8. Add the note `taps end`, make 5 more taps, then **Stop**. Expect "file OK";
   otherwise copy the problems listed.
9. Task **Bench: analyze recording** with the path of the new file in `data/`
   (`grp-G00_ses-01_task-bench_cond-taps_run-01.xdf`).
10. Optional, a short second recording: unplug one NIC2 computer's Ethernet
    cable for 10 seconds. Expect its cards to turn red, the alert, and the file
    check to report the lost slots.

If streams are missing, see the troubleshooting list in the lab's network
notes (ping, Local Network permission, KnownPeers, Windows firewall, switch
multicast settings). If something fails with all three, repeat with one NIC2
computer only to tell device problems apart from multi-device problems.

The tap test resolves timing only to about one accelerometer sample (the
analysis prints the value). It catches large offsets and drift, but cannot
confirm millisecond-level alignment; that needs a shared electrical test signal.

## Results (fill in and send back)

```
Date / NIC2 computers / recording Mac / switch:
NIC2 version:
NIC2 computers' LSL host names, if changed (P1 / P2 / P3):

Synchronizer time       P1        P2        P3
  ready to record     (mm:ss)   (mm:ss)   (mm:ss)

NIC2 Quality stream:        channels      rate
NIC2 Accelerometer stream:  channels      rate

check_streams.py output:

Recording file and check result (file OK / problems):

analyze_recording.py output:

Anything unexpected (red cards, alerts, disconnects, NIC2 warnings):
```
