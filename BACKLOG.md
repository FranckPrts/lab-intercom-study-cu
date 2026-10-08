# Backlog

Everything still to do, decide or check for the hyperscanning setup.
Tick items off here as they are done; move decisions into "Decided".

## Now

- [x] Get USB Ethernet adapters for the tablets if they have no Ethernet port
- [ ] Check each tablet has enough USB ports for the Enobio cable and the
      Ethernet adapter (and power, if it must charge during sessions); plan a
      hub if not
- [ ] Confirm NIC2 connects to each Enobio over USB, with the synchronizer on
- [ ] Run the bench test (tablets + main computer) and fill in the results (`bench/README.md`)

## Next (depends on the bench test)

- [ ] Confirm NIC2's LSL timestamps are on the LSL clock once the synchronizer is done
- [ ] Session checklist per tablet: Enobio USB cable, synchronizer on, LSL outlet
      name, battery, signal quality, then a single "all ready" start
- [ ] Main computer: LabRecorder config (stream list, file naming), or a small
      script that checks all streams before starting
- [ ] Channel labels for the default 32-channel montage, plus alternative montages
- [ ] Recording conventions: file naming, participant and session IDs, storage
      location; how NIC2's own per-tablet files are kept as backup

## Experimental paradigm (main computer)

- [ ] Define the interaction paradigm (not finalized yet)
- [ ] Choose the experiment software that shows it and sends markers over LSL
- [ ] How participants see it: one shared screen, or one screen each (and
      whether all screens are driven by the main computer)
- [ ] Check the main computer can run the paradigm and LabRecorder together
      without dropped frames or recording gaps
- [ ] Measure the delay between a marker and the stimulus actually appearing
      on screen (e.g. photodiode), per screen

## AV system (testing room)

Questions for the lab assistant and the options are in [`AV_SYSTEM.md`](AV_SYSTEM.md).

- [ ] Decide what video and audio are for in the analysis (sets frame rate,
      channels and how precisely they must line up with the EEG)
- [ ] Meet the lab assistant and go through `AV_SYSTEM.md`; get the equipment
      list or diagram
- [ ] Find out what the cameras' Ethernet cables carry (NDI, NDI|HX, RTSP,
      HDBaseT, ...) and whether we can receive the streams ourselves
- [ ] Microphones: one channel per participant, raw (no echo cancellation or
      automatic gain), and how to get it into the main computer
- [ ] Displays: how the main computer connects, what sits in between, delay
      measured with a photodiode
- [ ] Network: keep our own router for LSL, or use the lab's (multicast,
      device isolation, firewall, time server)? If the main computer joins
      the AV network too, check LSL in the bench test with both connected
- [ ] Choose how video and audio are recorded (our main computer over LSL, or
      the AV system plus a sync event) and add it to the bench test
- [ ] Sync event at the start and end of each session, seen by the cameras,
      heard by the microphones and recorded as an LSL marker
- [ ] Data protection for video and audio (storage, access, deletion) in the
      ethics application

## Task markers

- [ ] Wait for your examples of how markers will be sent
- [ ] Marker LSL stream design (name, format, what each event code means), and
      whether markers also go into NIC2 (`P1-Markers` inlets) or only into LSL

## Respiration and heart rate

- [ ] Make and model of the two devices
- [ ] How many of each: one set per participant (6 devices) or shared
- [ ] Sampling rates, and whether each device timestamps at acquisition or on
      arrival at the PC (Bluetooth devices often stamp on arrival, adding delay)
- [ ] Which computer they connect to (main computer by default, or a tablet)
- [ ] Add them to the bench test: check that they appear in LSL and record next to the EEG

## Questions for Neuroelectrics

- [ ] Units of the EEG values NIC2 sends over LSL (microvolts? nanovolts?)
- [ ] Which clock NIC2's LSL timestamps use, before and after the synchronizer finishes
- [ ] Does the synchronizer keep correcting in the background for long sessions?
- [ ] Accelerometer sampling rate, and whether it is always on in NIC2's LSL output
- [ ] Does the synchronizer work (and is it needed) over USB?
- [ ] Is a USB-connected Enobio safe on a participant, and under which conditions
      (e.g. tablet on battery)?
- [ ] For a later Wi-Fi option: can an Enobio join an existing router instead
      of making its own network?

## Timing validation

- [ ] Millisecond-level check: feed one shared electrical test signal into one
      channel of all three Enobios and compare edge times (the tap test only
      resolves to about one accelerometer sample)
- [ ] Decide on a timing check to run at the start and end of every real session

## USB connection

- [ ] Electrical safety of a participant cabled to a tablet: tablets on battery
      during recording? Confirm with Neuroelectrics and the ethics board
- [ ] Cable length and routing, so participants can move as the paradigm needs
- [ ] Wi-Fi (each Enobio's own NECBOX network) stays a fallback if cables turn
      out to be a problem

## Parked

- NE SDK (`NESDK-1.0.0`, `NEDeviceStreamer.exe`) for our own acquisition code:
  not needed while NIC2 does the streaming
- NIC2 for the analysis pipeline (revisit later)
- Live inter-brain synchrony display (not needed; recording only for now)

## Decided

- 3 × Enobio 32, each on its own Windows tablet running NIC2
- Each Enobio connects to its tablet by USB cable; no Wi-Fi for now
- The tablets and the main computer are on a wired local network; the router
  only provides that network (its Wi-Fi is not used)
- One main computer on the same wired network: runs the experimental paradigm
  (and its LSL markers), LabRecorder, and any other data collection
- NIC2 publishes LSL per participant (`P1-EEG`, `P1-Accelerometer`,
  `P1-Quality`, `P1-Markers`, ...), with its synchronizer on
- LSL as the recording backbone, LabRecorder to XDF; NIC2 also saves its own files
- Python for our code, in the `lab-intercom-study-cu` conda env (`environment.yml`),
  set up through VS Code tasks (`.vscode/tasks.json`)
- Respiration and heart rate on separate LSL devices, not on the Enobio channels
- Sessions are within Enobio battery life (verified)
