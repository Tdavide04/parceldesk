"""The port between the hub and a tracking service, and the errors it may raise."""
from typing import Protocol

from parceldesk.domain import BatchResult, Quota, Registration, TrackedNumber, TrackingResult


class TransientTrackingError(Exception):
    """Worth retrying later: network, timeout, 5xx, 429 once the client's own retries are exhausted."""


class PermanentTrackingError(Exception):
    """Retrying will not help: bad key, IP not allowed, quota exhausted, unexpected response. `code` is the provider's."""

    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code


class TrackingProvider(Protocol):
    """Translates only: no persistence, scheduling or notifications. Batches of any size are split internally."""

    name: str

    def register(self, registrations: list[Registration]) -> BatchResult:
        """Start tracking. Costs quota at most once per number; an already registered number is rejected, not charged."""
        ...

    def track(self, numbers: list[TrackedNumber]) -> TrackingResult:
        """Current snapshot of registered numbers (polling, ADR-0010 of the hub). Starts no new tracking."""
        ...

    def stop(self, numbers: list[TrackedNumber]) -> BatchResult:
        ...

    def reactivate(self, numbers: list[TrackedNumber]) -> BatchResult:
        """Restart tracking of stopped numbers; the provider may allow it only once per number."""
        ...

    def quota(self) -> Quota:
        ...
