"""LSL monitor: matches the streams on the network to the manifest's slots.

Read-only: it never connects to a device. It watches LSL announcements, and
for each matched stream opens an inlet only to count the samples arriving.

Slot states:
    MISSING    no stream with this name on the network
    MISMATCH   the name is there, but from another host, or twice on this host
    SILENT     the stream is there but no data has arrived recently
    PRESENT    data is arriving
    CONFIRMED  PRESENT, and an operator confirmed it (drops back if data stops)
"""
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum

import pylsl
from pylsl.util import LostError

from .events import OWN_SOURCE_PREFIX

log = logging.getLogger("session_monitor")


class SlotState(str, Enum):
    MISSING = "MISSING"
    MISMATCH = "MISMATCH"
    SILENT = "SILENT"
    PRESENT = "PRESENT"
    CONFIRMED = "CONFIRMED"


DATA_STATES = (SlotState.PRESENT, SlotState.CONFIRMED)


@dataclass(frozen=True)
class FoundStream:
    name: str
    host: str
    type: str
    channels: int
    nominal_rate: float
    source_id: str
    uid: str

    @classmethod
    def from_info(cls, info):
        return cls(info.name(), info.hostname(), info.type(), info.channel_count(),
                   info.nominal_srate(), info.source_id(), info.uid())


@dataclass(frozen=True)
class SlotStatus:
    slot: object               # manifest.Slot
    state: SlotState
    detail: str = ""           # why it is MISSING / MISMATCH / SILENT
    found: FoundStream | None = None
    rate: float | None = None  # samples per second measured over the last window
    last_data_age: float | None = None


class _Live:
    """Monitor-thread-only bookkeeping for one slot."""

    def __init__(self, slot):
        self.slot = slot
        self.found = None
        self.inlet = None
        self.bound_at = 0.0
        self.last_data = None
        self.counts = deque()     # (local_clock, n samples)
        self.confirmed = False
        self.match_state = SlotState.MISSING
        self.match_detail = "not on the network"
        self.dead_uid = None      # a lost stream still announced for a few seconds; never reopened
        self.failed_uid = None    # last stream that could not be opened (warned once)

    def unbind(self):
        if self.inlet is not None:
            try:
                self.inlet.close_stream()
            except Exception:
                pass
        self.inlet = self.found = self.last_data = None
        self.counts.clear()
        self.confirmed = False


class Monitor:
    def __init__(self, manifest, on_change=None, tick=0.25, resolve_every=1.0, rate_window=5.0,
                 stale_s=3.0, stale_irregular_s=10.0, forget_after=5.0):
        self.manifest = manifest
        self.on_change = on_change  # called as on_change(old: SlotStatus, new: SlotStatus) from the monitor thread
        self.tick, self.resolve_every, self.rate_window = tick, resolve_every, rate_window
        self.stale_s, self.stale_irregular_s, self.forget_after = stale_s, stale_irregular_s, forget_after
        self._live = {s.id: _Live(s) for s in manifest.slots}
        self._status = {s.id: SlotStatus(s, SlotState.MISSING, "not on the network") for s in manifest.slots}
        self._extras = ()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    # ------------------------------------------------------------ public API (any thread)
    def start(self):
        self._thread = threading.Thread(target=self._run, name="lsl-monitor", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(5)

    def snapshot(self):
        with self._lock:
            return tuple(self._status[s.id] for s in self.manifest.slots)

    def extras(self):
        """Streams on the network that belong to no slot (and are not ours)."""
        with self._lock:
            return self._extras

    def confirm(self, slot_id):
        """Operator confirms a slot; only possible while its data is arriving."""
        with self._lock:
            if self._status[slot_id].state != SlotState.PRESENT:
                return False
            self._live[slot_id].confirmed = True
        return True

    def unconfirm(self, slot_id):
        with self._lock:
            self._live[slot_id].confirmed = False

    def unconfirmed_required(self):
        """Required slots not CONFIRMED yet (empty = ready to record)."""
        return [st for st in self.snapshot() if st.slot.required and st.state != SlotState.CONFIRMED]

    # ------------------------------------------------------------ monitor thread
    def _run(self):
        resolver = pylsl.ContinuousResolver(forget_after=self.forget_after)
        next_resolve = 0.0
        while not self._stop.is_set():
            now = pylsl.local_clock()
            if now >= next_resolve:
                infos = resolver.results()
                self._match([FoundStream.from_info(i) for i in infos], infos)
                next_resolve = now + self.resolve_every
            self._pull()
            self._update_states()
            time.sleep(self.tick)
        for live in self._live.values():
            live.unbind()

    def _match(self, found, infos):
        info_by_uid = {f.uid: i for f, i in zip(found, infos)}
        claimed = set()
        for live in self._live.values():
            slot = live.slot
            named = [f for f in found if f.name == slot.stream_name]
            here = [f for f in named if slot.matches(f.name, f.host)]
            claimed.update(f.uid for f in named)
            if len(here) == 1 and here[0].uid == live.dead_uid:
                continue  # keep "stream lost" until it disappears or comes back with a new uid
            if len(here) == 1:
                f = here[0]
                if live.found is None or live.found.uid != f.uid:
                    if live.found is not None:
                        log.info("%s: stream restarted (new uid), reopening", slot.id)
                    live.unbind()
                    self._bind(live, f, info_by_uid[f.uid])
                live.match_state, live.match_detail = SlotState.PRESENT, ""
                continue
            live.unbind()
            if len(here) > 1:
                live.match_state = SlotState.MISMATCH
                live.match_detail = f"{len(here)} streams named {slot.stream_name} on {slot.host}"
            elif named:
                hosts = ", ".join(sorted({f.host for f in named}))
                live.match_state = SlotState.MISMATCH
                live.match_detail = f"found on {hosts}, expected {slot.host}"
            else:
                live.match_state, live.match_detail = SlotState.MISSING, "not on the network"
        extras = tuple(sorted((f for f in found if f.uid not in claimed
                               and not f.source_id.startswith(OWN_SOURCE_PREFIX)),
                              key=lambda f: (f.name, f.host)))
        with self._lock:
            self._extras = extras

    def _bind(self, live, found, info):
        try:
            inlet = pylsl.StreamInlet(info, max_buflen=10, recover=False)
            inlet.open_stream(timeout=2.0)
        except Exception as e:  # stream vanished or is unreachable; retried on the next resolve
            if live.failed_uid != found.uid:
                log.warning("%s: could not open %s@%s (%s)", live.slot.id, found.name, found.host, e)
                live.failed_uid = found.uid
            return
        live.found, live.inlet, live.bound_at = found, inlet, pylsl.local_clock()

    def _pull(self):
        now = pylsl.local_clock()
        for live in self._live.values():
            if live.inlet is None:
                continue
            n = 0
            try:
                while True:
                    _, stamps = live.inlet.pull_chunk(timeout=0.0, max_samples=4096)
                    if not stamps:
                        break
                    n += len(stamps)
            except LostError:
                log.info("%s: stream lost", live.slot.id)
                live.dead_uid = live.found.uid
                live.unbind()
                live.match_state, live.match_detail = SlotState.MISSING, "stream lost"
                continue
            if n:
                live.counts.append((now, n))
                live.last_data = now
            while live.counts and live.counts[0][0] < now - self.rate_window:
                live.counts.popleft()

    def _update_states(self):
        now = pylsl.local_clock()
        changes = []
        with self._lock:
            for live in self._live.values():
                old = self._status[live.slot.id]
                new = self._compute(live, now)
                self._status[live.slot.id] = new
                if (old.state, old.detail) != (new.state, new.detail):
                    changes.append((old, new))
        if self.on_change:
            for old, new in changes:
                try:
                    self.on_change(old, new)
                except Exception:
                    log.exception("on_change failed")

    def _compute(self, live, now):
        slot = live.slot
        if live.inlet is None:
            live.confirmed = False
            state = live.match_state if live.match_state != SlotState.PRESENT else SlotState.MISSING
            detail = live.match_detail or "could not open the stream"
            return SlotStatus(slot, state, detail)
        f = live.found
        span = min(self.rate_window, now - live.bound_at)
        rate = sum(n for _, n in live.counts) / span if span > 0.5 else None
        age = None if live.last_data is None else now - live.last_data
        stale = self.stale_irregular_s if f.nominal_rate <= 0 else max(self.stale_s, 3 / f.nominal_rate)
        if age is None or age > stale:
            live.confirmed = False
            detail = "no data yet" if age is None else f"no data for over {stale:.0f} s"
            return SlotStatus(slot, SlotState.SILENT, detail, f, rate, age)
        state = SlotState.CONFIRMED if live.confirmed else SlotState.PRESENT
        return SlotStatus(slot, state, "", f, rate, age)
