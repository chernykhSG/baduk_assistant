import json
import queue
import subprocess
import threading


class KataGoCrashError(RuntimeError):
    """Raised when the KataGo process is not running or exits unexpectedly."""


def build_katago_command(katago_binary: str, config_path: str, model_path: str) -> list[str]:
    return [katago_binary, "analysis", "-config", config_path, "-model", model_path]


class EngineManager:
    def __init__(self, command: list[str]):
        self.command = command
        self._process: subprocess.Popen | None = None
        self._stdout_queue: queue.Queue = queue.Queue()
        self._reader_thread: threading.Thread | None = None
        self._stderr_lines: list[str] = []
        self._stderr_thread: threading.Thread | None = None

    def _close_pipes(self) -> None:
        # terminate()/wait()/kill() don't close the parent-side pipe file
        # objects (only communicate() or a `with` context manager does) -
        # close them explicitly here to avoid leaking file handles across
        # restart/crash-recovery cycles. Guard against streams that are
        # already closed or absent (e.g. Popen creation failed).
        if self._process is None:
            return
        for stream in (self._process.stdin, self._process.stdout, self._process.stderr):
            if stream is not None and not stream.closed:
                try:
                    stream.close()
                except OSError:
                    pass

    def start(self) -> None:
        # If a previous (e.g. crashed) process is still referenced, close its
        # pipes before dropping the reference so we don't leak file handles.
        self._close_pipes()
        self._process = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        self._stderr_lines = []
        self._reader_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader_thread.start()
        self._stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        self._stderr_thread.start()

    def _read_stdout(self) -> None:
        assert self._process is not None
        assert self._process.stdout is not None
        for line in self._process.stdout:
            line = line.strip()
            if line:
                self._stdout_queue.put(line)

    def _read_stderr(self) -> None:
        # Must be drained continuously, not just on demand: an unread stderr
        # pipe fills its OS buffer once the child logs enough (KataGo logs
        # heavily at startup), which blocks the child's own stderr write and
        # wedges analyze() for the full timeout instead of failing fast.
        assert self._process is not None
        assert self._process.stderr is not None
        for line in self._process.stderr:
            line = line.strip()
            if line:
                self._stderr_lines.append(line)

    def stderr_output(self) -> str:
        return "\n".join(self._stderr_lines)

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def stop(self) -> None:
        if self._process is not None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._close_pipes()
            self._process = None

    def _drain_stale_queue(self) -> None:
        # A prior call that hit TimeoutError may still have its late response
        # sitting in the queue; drop it so it can't be mistaken for the
        # answer to the next, unrelated request.
        while True:
            try:
                self._stdout_queue.get_nowait()
            except queue.Empty:
                break

    def analyze(self, request: dict, timeout: float = 30.0) -> dict:
        if not self.is_running():
            self.start()
        self._drain_stale_queue()
        assert self._process is not None
        assert self._process.stdin is not None
        request_id = request["id"]
        try:
            self._process.stdin.write(json.dumps(request) + "\n")
            self._process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise KataGoCrashError("KataGo process pipe closed unexpectedly") from exc
        try:
            line = self._stdout_queue.get(timeout=timeout)
        except queue.Empty:
            if not self.is_running():
                raise KataGoCrashError("KataGo process exited while waiting for response")
            raise TimeoutError(f"No response from KataGo within {timeout}s")
        response = json.loads(line)
        # A single request can in principle receive multiple lines (one per
        # analyzeTurns entry); Phase 1 only sends single-turn requests, so the
        # first matching-id line is assumed to be the whole answer.
        if response.get("id") != request_id:
            raise ValueError(f"Unexpected response id {response.get('id')!r}, expected {request_id!r}")
        return response
