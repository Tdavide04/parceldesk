"""ParcelDesk: sends each number to its carrier's provider and gathers the answers."""
import logging
import re
from collections.abc import Iterable

from parceldesk.domain import RejectedNumber, TrackedNumber, TrackingResult, TrackingSnapshot, normalize_number
from parceldesk.provider import PermanentTrackingError, TrackingProvider, TransientTrackingError

logger = logging.getLogger(__name__)

# Formats as the carriers describe them on their tracking pages. They overlap (12 digits fits BRT and GLS
# international alike), so detection gives hints for the user to confirm, never the carrier itself.
NUMBER_FORMATS: dict[str, tuple[re.Pattern[str], ...]] = {
    "poste": (re.compile(r"[A-Z]{2}\d{9}IT"), re.compile(r"[A-Z0-9]{12,13}")),
    "inpost": (re.compile(r"\d{24}"),),
    "gls": (re.compile(r"[A-Z][A-Z0-9]\d{1,9}"), re.compile(r"\d{11,12}")),
    "brt": (re.compile(r"\d{12}"), re.compile(r"\d{15}"), re.compile(r"\d{18,19}")),
}


def detect_carriers(number: str) -> list[str]:
    """Carriers whose format fits the number, most specific first. Empty when none fits."""
    value = normalize_number(number)
    matches = []
    for carrier, patterns in NUMBER_FORMATS.items():
        for rank, pattern in enumerate(patterns):
            if pattern.fullmatch(value):
                matches.append((rank, carrier))
                break
    return [carrier for _, carrier in sorted(matches)]


class ParcelDesk:
    """Holds one provider per carrier. A failing carrier does not stop the others: its numbers come back rejected."""

    def __init__(self, providers: Iterable[TrackingProvider]):
        self._providers: dict[str, TrackingProvider] = {}
        for provider in providers:
            if provider.carrier in self._providers:
                raise ValueError(f"two providers for {provider.carrier!r}")
            self._providers[provider.carrier] = provider

    @property
    def carriers(self) -> tuple[str, ...]:
        return tuple(self._providers)

    def track(self, numbers: Iterable[TrackedNumber]) -> TrackingResult:
        by_carrier: dict[str, list[str]] = {}
        for tracked in numbers:
            group = by_carrier.setdefault(tracked.carrier, [])
            if tracked.number not in group:
                group.append(tracked.number)

        snapshots: list[TrackingSnapshot] = []
        rejected: list[RejectedNumber] = []
        for carrier, group in by_carrier.items():
            provider = self._providers.get(carrier)
            if provider is None:
                rejected += [RejectedNumber(n, carrier, "no provider for this carrier", retryable=False) for n in group]
                continue
            for start in range(0, len(group), provider.max_batch):
                batch = group[start:start + provider.max_batch]
                got, missing = self._track_batch(provider, batch)
                snapshots += got
                rejected += missing
        return TrackingResult(snapshots, rejected)

    def _track_batch(self, provider: TrackingProvider, batch: list[str]) -> tuple[list[TrackingSnapshot], list[RejectedNumber]]:
        carrier = provider.carrier
        try:
            answered = provider.track(batch)
        except (TransientTrackingError, PermanentTrackingError) as exc:
            retryable = isinstance(exc, TransientTrackingError)
            logger.warning("carrier failed", extra={"event": "tracking_failed", "carrier": carrier, "retryable": retryable, "reason": str(exc)})
            return [], [RejectedNumber(n, carrier, str(exc), retryable) for n in batch]
        asked = set(batch)
        snapshots = [s for s in answered if s.number in asked]
        seen = {s.number for s in snapshots}
        missing = [RejectedNumber(n, carrier, "the carrier did not answer for this number", retryable=True) for n in batch if n not in seen]
        return snapshots, missing
