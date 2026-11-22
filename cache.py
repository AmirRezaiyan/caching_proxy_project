from __future__ import annotations

import math
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping


@dataclass(slots=True)
class CacheEntry:
    """One cached response variant."""

    value: Any
    expires_at: float
    vary_headers: tuple[str, ...]
    vary_values: tuple[tuple[str, str], ...]


class Cache:
    """Thread-safe-in-practice event-loop-local cache with TTL and LRU limits.

    Cache operations are synchronous and contain no await points, so each
    operation is atomic relative to other asyncio tasks running on the same
    event loop. This class is not intended to be shared between OS processes.
    """

    def __init__(
        self,
        ttl_seconds: float = 60.0,
        max_entries: int = 512,
        max_variants_per_key: int = 8,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not math.isfinite(ttl_seconds) or ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be a finite number greater than zero")
        if max_entries <= 0:
            raise ValueError("max_entries must be greater than zero")
        if max_variants_per_key <= 0:
            raise ValueError("max_variants_per_key must be greater than zero")

        self.default_ttl = float(ttl_seconds)
        self.max_entries = int(max_entries)
        self.max_variants_per_key = int(max_variants_per_key)
        self._clock = clock
        self._entries: OrderedDict[str, list[CacheEntry]] = OrderedDict()
        self._entry_count = 0

    @staticmethod
    def _normalize_headers(
        headers: Mapping[str, str] | Iterable[tuple[str, str]] | None,
    ) -> dict[str, str]:
        if headers is None:
            return {}

        items = headers.items() if hasattr(headers, "items") else headers
        normalized: dict[str, str] = {}
        for name, value in items:
            normalized[str(name).lower()] = str(value)
        return normalized

    def get(
        self,
        key: str,
        request_headers: Mapping[str, str] | Iterable[tuple[str, str]] | None = None,
    ) -> Any | None:
        """Return a matching unexpired value, or None when no variant matches."""
        variants = self._entries.get(key)
        if not variants:
            return None

        now = self._clock()
        normalized_headers = self._normalize_headers(request_headers)
        valid_variants: list[CacheEntry] = []
        matched: CacheEntry | None = None

        for entry in variants:
            if entry.expires_at <= now:
                self._entry_count -= 1
                continue

            valid_variants.append(entry)
            expected = dict(entry.vary_values)
            if all(
                normalized_headers.get(name, "") == expected.get(name, "")
                for name in entry.vary_headers
            ):
                matched = entry

        if valid_variants:
            self._entries[key] = valid_variants
            if matched is not None:
                self._entries.move_to_end(key)
                return matched.value
        else:
            self._entries.pop(key, None)

        return None

    def set(
        self,
        key: str,
        value: Any,
        ttl: float | None = None,
        vary_headers: Iterable[str] = (),
        request_headers: Mapping[str, str] | Iterable[tuple[str, str]] | None = None,
    ) -> None:
        """Store a value, optionally varying it by selected request headers."""
        effective_ttl = self.default_ttl if ttl is None else float(ttl)
        if not math.isfinite(effective_ttl) or effective_ttl <= 0:
            return

        normalized_headers = self._normalize_headers(request_headers)
        normalized_vary = tuple(sorted({name.strip().lower() for name in vary_headers if name.strip()}))
        vary_values = tuple(
            (name, normalized_headers.get(name, "")) for name in normalized_vary
        )

        entry = CacheEntry(
            value=value,
            expires_at=self._clock() + effective_ttl,
            vary_headers=normalized_vary,
            vary_values=vary_values,
        )

        variants = self._entries.setdefault(key, [])

        # Replace an existing variant with the same Vary definition and values.
        retained: list[CacheEntry] = []
        for existing in variants:
            if (
                existing.vary_headers == normalized_vary
                and existing.vary_values == vary_values
            ):
                self._entry_count -= 1
            else:
                retained.append(existing)

        retained.append(entry)
        self._entry_count += 1

        while len(retained) > self.max_variants_per_key:
            retained.pop(0)
            self._entry_count -= 1

        self._entries[key] = retained
        self._entries.move_to_end(key)
        self._evict_if_needed()

    def _evict_if_needed(self) -> None:
        while self._entry_count > self.max_entries and self._entries:
            oldest_key = next(iter(self._entries))
            variants = self._entries[oldest_key]
            if len(variants) > 1:
                variants.pop(0)
                self._entry_count -= 1
                self._entries.move_to_end(oldest_key)
            else:
                self._entries.pop(oldest_key)
                self._entry_count -= 1

    def clear(self) -> None:
        """Remove every cached entry."""
        self._entries.clear()
        self._entry_count = 0

    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None

    def __len__(self) -> int:
        return self._entry_count
