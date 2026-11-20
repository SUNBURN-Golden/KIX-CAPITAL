"""Blocking, single-request client for the synthetic local F04 credit desk.

Importing launches nothing. No restart, retry, replay, persistence or sockets.
An uncertain exchange fences this instance; cleanup cannot undo accepted work.
"""

import json
import math
from pathlib import Path
import subprocess
import sys
import threading

from credit_fixture import FixtureError, decode_json, exact_fields, validate_json
from mock_credit import PROVENANCE


class CreditClientStateError(RuntimeError):
    """Local rejection before submission: busy, closed or terminal client."""


class CreditTransportUncertainty(RuntimeError):
    """A submitted request has no trustworthy complete response.

    request is the serialized snapshot, not an inferred business outcome.
    reply_bytes contains bytes observed before the failure. Neither authorizes
    resubmission, even if the desk exits or cleanup terminates it.
    """

    def __init__(self, request, request_bytes, reply_bytes):
        super().__init__("local credit exchange uncertain; client fenced")
        self.request = request
        self.request_bytes = request_bytes
        self.reply_bytes = reply_bytes


class CreditClient:
    """Own one explicitly launched desk and at most one outstanding request.

    Use launch(), then request() synchronously, and close() or a with block.
    Reads have no response timeout. cleanup_timeout applies only to close().
    close() rejects concurrent use too; interrupt the requesting caller first.
    """

    @classmethod
    def launch(cls, fixture, *, cleanup_timeout):
        """Launch one fresh desk; fixture validation belongs to the child."""
        try:
            valid_timeout = (type(cleanup_timeout) in (int, float)
                             and math.isfinite(cleanup_timeout) and cleanup_timeout > 0)
        except OverflowError:
            valid_timeout = False
        if not valid_timeout:
            raise ValueError("cleanup_timeout must be a finite positive number")
        command = [sys.executable, str(Path(__file__).with_name("credit_cli.py").resolve()),
                   "--fixture", str(Path(fixture).resolve()), "--requests", "-"]
        # Ordinary Python buffering: the CLI itself must flush each reply.
        # Inherit stderr, keeping diagnostics out of JSONL and undrained pipes.
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   bufsize=0, shell=False)
        return cls(process, cleanup_timeout)

    def __init__(self, process, cleanup_timeout):
        self._process = process
        self._cleanup_timeout = cleanup_timeout
        self._guard = threading.Lock()
        self._terminal = False
        self._closed = False
        self._returncode = None
        self.uncertainty = None

    @staticmethod
    def _reply(raw, request):
        if not raw.endswith(b"\n"):
            raise FixtureError("response ended without a newline")
        reply = decode_json(raw.decode("utf-8"))
        if type(reply) is not dict:
            raise FixtureError("response must be an object")
        payload = set(reply) & {"receipt", "view", "claim", "error"}
        if len(payload) != 1:
            raise FixtureError("response requires one payload")
        exact_fields(reply, {"operation", "provenance"} | payload, "response")
        if reply["provenance"] != PROVENANCE:
            raise FixtureError("response provenance does not match synthetic credit desk")
        key = next(iter(payload))
        if type(reply[key]) is not dict:
            raise FixtureError("response payload must be an object")
        if key == "error":
            error = reply[key]
            fields = {"code"} if set(error) == {"code"} else {"type", "message"}
            exact_fields(error, fields, "response error")
            if any(type(error[field]) is not str for field in fields):
                raise FixtureError("response error values must be strings")
        startup = key == "error" and reply["operation"] is None
        expected = request.get("operation")
        expected = expected if type(expected) is str else None
        if not startup and (type(reply["operation"]) is not str
                            or reply["operation"] != expected):
            raise FixtureError("response operation does not match request")
        if key != "error":
            # Local selectors only; leave all argument/value acceptance to the CLI.
            expected_payload = {
                "offer": "receipt", "approve": "receipt", "reject": "receipt",
                "cancel": "receipt", "bind_settlement": "receipt", "draw": "receipt",
                "repay": "receipt", "close": "receipt", "default": "receipt",
                "reconcile": "receipt", "view": "view", "view_claim": "claim",
            }.get(expected)
            if key != expected_payload:
                raise FixtureError("response payload does not match operation")
        terminal = startup or (key == "error" and "type" in reply[key])
        return reply, terminal

    def request(self, request: dict) -> dict:
        if not self._guard.acquire(blocking=False):
            raise CreditClientStateError("another request or cleanup is outstanding")
        try:
            if self._closed or self._terminal or self.uncertainty is not None:
                raise CreditClientStateError("client is closed, terminal or uncertain")
            if type(request) is not dict:
                raise TypeError("request must be a dictionary")
            # Fail serialization before submission; retain the actual wire snapshot
            # even if the caller later mutates its dictionary.
            validate_json(request)
            wire = (json.dumps(request, allow_nan=False) + "\n").encode("utf-8")
            submitted = decode_json(wire.decode("utf-8"))
            raw = bytearray()
            try:
                written = self._process.stdin.write(wire)
                if written != len(wire):
                    raise OSError("short request write")
                self._process.stdin.flush()
                # Retain partial diagnostic bytes even on caller interruption.
                while True:
                    chunk = self._process.stdout.read(1)
                    if not chunk:
                        break
                    raw.extend(chunk)
                    if chunk == b"\n":
                        break
                reply, terminal = self._reply(bytes(raw), submitted)
                self._terminal = terminal
                return reply
            except BaseException as error:
                # Includes caller interruption after submission has begun. Never
                # interpret missing evidence as a business rejection or rollback.
                self._terminal = True
                self.uncertainty = CreditTransportUncertainty(submitted, wire, bytes(raw))
                raise self.uncertainty from error
        finally:
            self._guard.release()

    def close(self) -> int:
        """Close stdin, reap this child, and return its exit code; idempotent.

        After the explicit cleanup deadline, terminate then kill if necessary.
        Previous transport uncertainty remains available on self.uncertainty.
        """
        if not self._guard.acquire(blocking=False):
            raise CreditClientStateError("another request or cleanup is outstanding")
        try:
            if self._closed:
                return self._returncode
            self._terminal = True
            try:
                try:
                    self._process.stdin.close()
                except (BrokenPipeError, OSError):
                    pass
                try:
                    self._process.wait(timeout=self._cleanup_timeout)
                except subprocess.TimeoutExpired:
                    self._process.terminate()
                    try:
                        self._process.wait(timeout=self._cleanup_timeout)
                    except subprocess.TimeoutExpired:
                        self._process.kill()
                        self._process.wait()
                self._returncode = self._process.returncode
                self._closed = True
                return self._returncode
            finally:
                self._process.stdout.close()
        finally:
            self._guard.release()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
