"""Drives LabRecorderCLI: records exactly the listed streams to one XDF file.

LabRecorderCLI (ships with LabRecorder) takes an output file and one LSL query
per stream, resolves them once, records until it reads Enter on stdin, and
exits with code 2 if a query matches nothing. Behaviour checked on the Mac
(Homebrew LabRecorder), 2026-10-23:
  * queries must use `hostname='...'` (the `host=` in its help text matches nothing)
  * it prints "Started data collection for stream <name>." once per stream, from
    several threads at once: messages interleave mid-line (a name can end up on
    the next line), so we count the messages instead of reading the names
  * Enter stops it cleanly (exit 0, a few seconds to close the file)
"""
import logging
import os
import queue
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

log = logging.getLogger("session_monitor")

DEFAULT_PATHS = ["/opt/homebrew/bin/LabRecorderCLI", "/usr/local/bin/LabRecorderCLI"]
STARTED = "Started data collection for stream"
NO_MATCH_RE = re.compile(r'"(.+?)" matched no stream!')


class RecorderError(Exception):
    pass


def find_labrecorder_cli(path=None):
    for cand in [path, os.environ.get("LABRECORDERCLI"), shutil.which("LabRecorderCLI"), *DEFAULT_PATHS]:
        if cand and Path(cand).is_file():
            return str(cand)
    raise RecorderError("LabRecorderCLI not found: install LabRecorder (brew install labrecorder) "
                        "or set LABRECORDERCLI to its path")


def _xpath_string(value):
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    raise RecorderError(f"stream name or host contains both quote kinds: {value!r}")


def stream_query(name, hostname):
    return f"name={_xpath_string(name)} and hostname={_xpath_string(hostname)}"


class LabRecorderCLI:
    def __init__(self, exe=None):
        self.exe = find_labrecorder_cli(exe)
        self.proc = None
        self.path = None
        self.output = []          # every line LabRecorderCLI printed, for the log
        self._lines = queue.Queue()

    @property
    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self, xdf_path, streams, timeout=20.0):
        """streams: [(name, hostname), ...] exactly as LSL reports them.
        Returns once every stream is recording; raises RecorderError otherwise."""
        if self.running:
            raise RecorderError("already recording")
        self.path = Path(xdf_path)
        if self.path.exists():
            raise RecorderError(f"{self.path} already exists")
        queries = [stream_query(n, h) for n, h in streams]
        self.output = []
        self._lines = queue.Queue()
        self.proc = subprocess.Popen([self.exe, str(self.path), *queries], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        threading.Thread(target=self._read, args=(self.proc,), daemon=True).start()

        started, no_match = 0, []
        t_end = time.monotonic() + timeout
        while started < len(streams):
            try:
                line = self._lines.get(timeout=0.2)
            except queue.Empty:
                line = None
            if line is not None:
                started += line.count(STARTED)
                no_match += NO_MATCH_RE.findall(line)
                continue
            if self.proc.poll() is not None:
                self._drain()
                if no_match:
                    raise RecorderError(f"stream(s) not found: {'; '.join(no_match)}")
                raise RecorderError(f"LabRecorderCLI exited (code {self.proc.returncode}) before recording")
            if time.monotonic() > t_end:
                self.stop(timeout=10)
                raise RecorderError(f"only {started} of {len(streams)} streams started recording in {timeout:.0f} s")
        log.info("recording %d stream(s) to %s", len(streams), self.path.name)

    def stop(self, timeout=60.0):
        """Send Enter, wait for exit and for the file to stop changing. Returns the exit code."""
        if self.proc is None:
            return None
        if self.proc.poll() is None:
            try:
                self.proc.stdin.write("\n")
                self.proc.stdin.flush()
            except (BrokenPipeError, OSError):
                pass
            try:
                self.proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                log.warning("LabRecorderCLI did not stop in %.0f s; terminating", timeout)
                self.proc.terminate()
                self.proc.wait(10)
        self._wait_file_settled()
        self._drain()
        code, self.proc = self.proc.returncode, None
        return code

    def _read(self, proc):
        for line in proc.stdout:
            line = line.rstrip()
            self.output.append(line)
            self._lines.put(line)
            if line and "INFO|" not in line:
                log.debug("LabRecorderCLI: %s", line)

    def _drain(self):
        while not self._lines.empty():
            self._lines.get_nowait()

    def _wait_file_settled(self, quiet_s=1.0, max_s=30.0):
        last, since, t_end = -1, time.monotonic(), time.monotonic() + max_s
        while time.monotonic() < t_end:
            size = self.path.stat().st_size if self.path.exists() else -1
            if size != last:
                last, since = size, time.monotonic()
            elif time.monotonic() - since >= quiet_s:
                return
            time.sleep(0.2)
