# Respiration belts: Vernier Go Direct → LSL

Each participant wears a Vernier Go Direct respiration belt (GDX-RB). The belt
connects over Bluetooth to that participant's computer (the same Windows
computer that runs NIC2 for their Enobio). [`vernier_connect.py`](vernier_connect.py)
runs there and publishes the belt as an LSL stream. The recording Mac then
tracks and records it like the EEG.

```
Belt A ──Bluetooth── computer 1 (P1) ─┐
Belt B ──Bluetooth── computer 2 (P2) ─┼── Ethernet · LSL ── recording Mac
Belt C ──Bluetooth── computer 3 (P3) ─┘                     (session monitor + LabRecorderCLI)
```


## What the script does

1. Asks which belt this computer uses (or takes `--belt N`).
2. Scans Bluetooth with `vernier-lsl --scan` until that belt's serial shows
   up. While it can't find the belt, it prints a checklist (belt on, not
   connected elsewhere, not paired in Windows, in range).
3. Starts `vernier-lsl` for that serial only, then waits up to 30 s for the
   LSL stream to appear.
4. Watches the stream and restarts everything after 5 s if `vernier-lsl` exits
   or no sample arrives for 10 s, for example when the belt is switched off or
   out of range.

Everything it does is written to the console and appended to
`vernier_connect.log` in the folder it is run from (git-ignored).

## Belts and seats

Belts are interchangeable: the computer decides the seat, not the belt. Any
belt streaming from computer N counts as seat PN's respiration, so a belt with
a flat battery can be swapped for a spare without touching the manifests.
(Unlike NIC2, which names its streams after the computer, `vernier-lsl` names
them after the belt, `GDX-RB_<serial>`; the session manifests accept any
`GDX-RB_*` name.) The serial stays in the recorded stream name, so the XDF
still says which belt each participant wore.

The belt list is `MANIFEST` at the top of `vernier_connect.py`. Pick any belt
that no other computer is using; `--belt N` skips the menu. Add a new belt's
serial there (no manifest change needed).

## Setup on each participant computer (Windows, once)

Use the project's conda environment and VS Code tasks, as on the Mac:

1. Install VS Code and Miniforge (conda), and make sure `conda` works in the
   VS Code terminal (see [bench/README.md](../bench/README.md)).
2. Clone this repository and open it in VS Code.
3. Run **Terminal → Run Task → Env: create**. The env includes `vernier-lsl`
   and `pylsl`. After `environment.yml` changes, run **Env: update** instead.
4. Do **not** pair the belt in Windows Bluetooth settings. `vernier-lsl`
   connects to it directly.

## Running it

On participant computer N, before each session: run **Terminal → Run Task →
Respiration: connect belt**, and pick belt N in the menu (Belt A on
computer 1, and so on).

Leave the task running for the whole session; Ctrl+C in its terminal stops it.

To see which LSL streams are on the network (useful to check the stream
name, see ⚠️ below), from the VS Code terminal:

```
conda run --no-capture-output --name lab-intercom-study-cu python respiration/vernier_connect.py --list-streams
```

### On the Mac (testing only)

The same task works on the Mac to test a belt. The stream then comes from the
Mac, so the session monitor shows it as MISMATCH (wrong host) with the study
manifest.

## How the session monitor tracks the belts

The belts are slots in the session manifests (`manifests/bench.yaml`, and the
tracked template [`manifests/bench_EXAMPLE.yaml`](../manifests/bench_EXAMPLE.yaml)):
one slot per seat, `P1-Respiration` … `P3-Respiration`. Each slot is matched
by its computer's host name and any stream named `GDX-RB_*`, whichever belt
that is (the GUI cell shows the belt's stream name, i.e. its serial). The GUI shows them
as a **respiration** row under P1, P2 and P3, with the same states as the EEG
(MISSING / MISMATCH / SILENT / PRESENT / CONFIRMED), and LabRecorderCLI
records them into the same XDF file.

Common states:
- **MISSING**: `vernier_connect.py` isn't running on that computer, or the
  belt isn't streaming yet.
- **MISMATCH, found on another host**: a belt is streaming from a computer
  that isn't a seat (e.g. the Mac, when testing).
- **MISMATCH, 2 streams on …**: two belts are connected to the same computer.
- **SILENT**: the stream exists but no data arrived for 10 s (belt off, out of
  range). The script restarts it on its own.

For now the respiration slots are `required: false`: they are tracked and
recorded when present, but never block Start. Make them required once the
bench test with the belts has passed.

To rehearse without belts, the VS Code task **Fakes: publish bench streams**
publishes fake respiration streams too. They're 1 channel at 100 Hz, which
isn't the real belt's format.

## Open points

- ⚠️ **Stream name.** `vernier-lsl` names the stream after the belt's device
  name with spaces replaced by `_`. For a GDX-RB this is expected to be
  `GDX-RB_<serial>` (confirmed: `GDX-RB_0K7017F1`, `GDX-RB_0K7017C4`), but a
  belt renamed in Graphical Analysis would publish a different name and not
  match `GDX-RB_*`. Check with `--list-streams` or `bench/check_streams.py`.

- ⚠️ **Channels.** `vernier-lsl` streams the belt's default sensors. Check
  which channels (force, respiration rate, …) and units end up in the XDF.
