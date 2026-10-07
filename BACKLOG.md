# Backlog

Everything still to do, decide or check for the hyperscanning setup.
Tick items off here as they are done; move decisions into "Decided".

## Now

- [x] Get USB Ethernet adapters for the tablets if they have no Ethernet port
- [ ] Run the bench test (tablets + recording PC) and fill in the results (`bench/README.md`)

## Next (depends on the bench test)

- [ ] Confirm NIC2's LSL timestamps are on the LSL clock once the synchronizer is done
- [ ] Session checklist per tablet: NECBOX Wi-Fi, synchronizer on, LSL outlet
      name, battery, signal quality, then a single "all ready" start
- [ ] Recording PC: LabRecorder config (stream list, file naming), or a small
      script that checks all 12 streams before starting
- [ ] Channel labels for the default 32-channel montage, plus alternative montages
- [ ] Recording conventions: file naming, participant and session IDs, storage
      location; how NIC2's own per-tablet files are kept as backup

## Task markers

- [ ] Wait for your examples of how markers will be sent
- [ ] Marker LSL stream design (name, format, what each event code means), and
      whether markers also go into NIC2 (`P1-Markers` inlets) or only into LSL

## Respiration and heart rate

- [ ] Make and model of the two devices
- [ ] How many of each: one set per participant (6 devices) or shared
- [ ] Sampling rates, and whether each device timestamps at acquisition or on
      arrival at the PC (Bluetooth devices often stamp on arrival, adding delay)
- [ ] Which computer they run on (the participant's tablet or the recording PC)
- [ ] Add them to the bench test: check that they appear in LSL and record next to the EEG

## Questions for Neuroelectrics

- [ ] Units of the EEG values NIC2 sends over LSL (microvolts? nanovolts?)
- [ ] Which clock NIC2's LSL timestamps use, before and after the synchronizer finishes
- [ ] Does the synchronizer keep correcting in the background for long sessions?
- [ ] Accelerometer sampling rate, and whether it is always on in NIC2's LSL output
- [ ] Can an Enobio join an existing router instead of making its own network?

## Timing validation

- [ ] Millisecond-level check: feed one shared electrical test signal into one
      channel of all three Enobios and compare edge times (the tap test only
      resolves to about one accelerometer sample)
- [ ] Decide on a timing check to run at the start and end of every real session

## Parked

- NE SDK (`NESDK-1.0.0`, `NEDeviceStreamer.exe`) for our own acquisition code:
  not needed while NIC2 does the streaming
- NIC2 for the analysis pipeline (revisit later)
- Live inter-brain synchrony display (not needed; recording only for now)
- Interaction paradigm (not finalized yet)

## Decided

- 3 × Enobio 32, each on its own Windows tablet running NIC2
- Each Enobio makes its own Wi-Fi network (NECBOX); the tablet's Wi-Fi joins it,
  so the tablets talk to each other over a wired network
- One recording PC on the same wired network, running LabRecorder
- NIC2 publishes LSL per participant (`P1-EEG`, `P1-Accelerometer`,
  `P1-Quality`, `P1-Markers`, ...), with its synchronizer on
- LSL as the recording backbone, LabRecorder to XDF; NIC2 also saves its own files
- Python for our code, in the `lab-intercom-study-cu` conda env (`environment.yml`),
  set up through VS Code tasks (`.vscode/tasks.json`)
- Respiration and heart rate on separate LSL devices, not on the Enobio channels
- Sessions are within Enobio battery life (verified)
