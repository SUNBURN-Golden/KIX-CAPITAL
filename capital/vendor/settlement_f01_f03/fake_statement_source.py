"""Immutable local JSON recordings. No clocks, I/O, retry or consumption."""

import json
from collections.abc import Mapping
from enum import Enum
from types import MappingProxyType

from statement_source import InvalidStatementRecord, StatementSourceError


class SyntheticStatementFault(Enum):
    ERROR = "synthetic_statement_error"
    TIMEOUT = "synthetic_statement_timeout"


class FakeStatementSource:
    def __init__(
        self, *, recordings: Mapping[tuple[str, str], str | SyntheticStatementFault],
    ) -> None:
        copied = dict(recordings)
        for identity, recording in copied.items():
            if (type(identity) is not tuple or len(identity) != 2
                    or any(type(part) is not str for part in identity)):
                raise TypeError("recording keys must be (settlement_id, movement_id) strings")
            if type(recording) not in (str, SyntheticStatementFault):
                raise TypeError("recordings must be JSON text or SyntheticStatementFault")
        self._recordings = MappingProxyType(copied)
        self._calls: list[tuple[str, str]] = []

    @property
    def recordings(self) -> Mapping[tuple[str, str], str | SyntheticStatementFault]:
        return self._recordings

    @property
    def calls(self) -> tuple[tuple[str, str], ...]:
        return tuple(self._calls)

    def fetch(self, settlement_id: str, movement_id: str) -> dict | None:
        self._calls.append((settlement_id, movement_id))
        recording = self._recordings.get((settlement_id, movement_id))
        if recording is None:
            return None
        if isinstance(recording, SyntheticStatementFault):
            raise StatementSourceError(recording.value)
        try:
            record = json.loads(recording)
        except json.JSONDecodeError as error:
            raise InvalidStatementRecord("recording must be JSON text") from error
        if type(record) is not dict:
            raise InvalidStatementRecord("recording must be a JSON object")
        return record
