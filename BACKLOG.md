# Backlog

Everything still to do, decide or check for the hyperscanning setup.
Tick items off here as they are done; move decisions into "Decided".

## Now

- [ ] Run the bench test on the Windows PC and fill in the results (`bench/README.md`)

## Next (depends on the bench test)

- [ ] Decide: one PC for all three Enobios, or split across PCs on the LAN
- [ ] Decide: use the SDK's own LSL outlets, or read samples and publish our own
      (depends on whether the SDK's LSL timestamps are on the LSL clock, and on
      the stream naming during sync)
- [ ] 32-bit Python for the SDK workers (the SDK DLL is 32-bit). conda-forge no
      longer builds 32-bit Windows packages, so this is probably a separate
      32-bit python.org install alongside the `columbia-study` conda env;
      check what is available before deciding
- [ ] Control program: one worker per headset, config file (MAC, participant,
      channel labels), wait for all three to sync, battery and connection checks,
      single "all ready" start
- [ ] Channel labels for the default 32-channel montage, plus alternative montages
- [ ] Recording conventions: file naming, participant and session IDs, storage location

## Task markers

- [ ] Wait for your examples of how markers will be sent
- [ ] Marker LSL stream design (name, format, what each event code means)

## Respiration and heart rate

- [ ] Make and model of the two devices
- [ ] How many of each: one set per participant (6 devices) or shared
- [ ] Sampling rates, and whether each device timestamps at acquisition or on
      arrival at the PC (Bluetooth devices often stamp on arrival, adding delay)
- [ ] Which PC they run on
- [ ] Add them to the bench test: check that they appear in LSL and record next to the EEG

## Questions for Neuroelectrics

- [ ] Units of the raw EEG integers (nanovolts?)
- [ ] Is it safe to connect several devices from one process with the SDK?
- [ ] Which clock the SDK's LSL timestamps use, before and after sync
- [ ] Does sync keep correcting in the background for long sessions?
- [ ] Accelerometer sampling rate

## Timing validation

- [ ] Millisecond-level check: feed one shared electrical test signal into one
      channel of all three Enobios and compare edge times (the tap test only
      resolves to about one accelerometer sample)
- [ ] Decide on a timing check to run at the start and end of every real session

## Parked

- NIC2 for the analysis pipeline (revisit later)
- Live inter-brain synchrony display (not needed; recording only for now)
- Interaction paradigm (not finalized yet)

## Decided

- 3 × Enobio 32, Wi-Fi via a dedicated router (USB as backup)
- Windows for acquisition; the Mac is for writing code only
- LSL as the recording backbone, LabRecorder to XDF
- Python for our code, in the `columbia-study` conda env (`environment.yml`),
  set up through VS Code tasks (`.vscode/tasks.json`)
- Respiration and heart rate on separate LSL devices, not on the Enobio channels
- Sessions are within Enobio battery life (verified)
