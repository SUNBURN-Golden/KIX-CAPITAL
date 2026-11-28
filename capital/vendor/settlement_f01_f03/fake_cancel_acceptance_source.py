"""Immutable local JSON recordings. No clocks, I/O, retry or consumption."""

import json
from collections.abc import Mapping
from enum import Enum
from types import MappingProxyType

from cancel_acceptance_source import InvalidCancelAcceptanceRecord, CancelAcceptanceSourceError


class SyntheticCancelAcceptanceFault(Enum):
    ERROR = "synthetic_cancel_acceptance_error"
    TIMEOUT = "synthetic_cancel_acceptance_timeout"


class FakeCancelAcceptanceSource:
    def __init__(
        self, *, recordings: Mapping[tuple[str, str], str | SyntheticCancelAcceptanceFault],
    ) -> None:
        copied = dict(recordings)
        for identity, recording in copied.items():
            if (type(identity) is not tuple or len(identity) != 2
                    or any(type(part) is not str for part in identity)):
                raise TypeError("recording keys must be (settlement_id, source_id) strings")
            if type(recording) not in (str, SyntheticCancelAcceptanceFault):
                raise TypeError("recordings must be JSON text or SyntheticCancelAcceptanceFault")
        self._recordings = MappingProxyType(copied)
        self._calls: list[tuple[str, str]] = []

    @property
    def recordings(self) -> Mapping[tuple[str, str], str | SyntheticCancelAcceptanceFault]:
        return self._recordings

    @property
    def calls(self) -> tuple[tuple[str, str], ...]:
        return tuple(self._calls)

    def fetch(self, settlement_id: str, source_id: str) -> dict | None:
        self._calls.append((settlement_id, source_id))
        recording = self._recordings.get((settlement_id, source_id))
        if recording is None:
            return None
        if isinstance(recording, SyntheticCancelAcceptanceFault):
            raise CancelAcceptanceSourceError(recording.value)
        try:
            record = json.loads(recording)
        except json.JSONDecodeError as error:
            raise InvalidCancelAcceptanceRecord("recording must be JSON text") from error
        if type(record) is not dict:
            raise InvalidCancelAcceptanceRecord("recording must be a JSON object")
        return record
