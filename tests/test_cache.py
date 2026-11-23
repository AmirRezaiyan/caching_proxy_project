from app.cache import Cache

class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_cache_stores_and_returns_value() -> None:
    cache = Cache()
    cache.set("item", {"value": 1})
    assert cache.get("item") == {"value": 1}


def test_cache_expires_entries() -> None:
    clock = FakeClock()
    cache = Cache(ttl_seconds=5, clock=clock)
    cache.set("item", "value")

    clock.advance(5)

    assert cache.get("item") is None
    assert len(cache) == 0


def test_cache_supports_vary_headers() -> None:
    cache = Cache()
    cache.set(
        "item",
        "english",
        vary_headers=("accept-language",),
        request_headers={"Accept-Language": "en"},
    )
    cache.set(
        "item",
        "french",
        vary_headers=("accept-language",),
        request_headers={"Accept-Language": "fr"},
    )

    assert cache.get("item", {"accept-language": "en"}) == "english"
    assert cache.get("item", {"accept-language": "fr"}) == "french"
    assert cache.get("item", {"accept-language": "de"}) is None


def test_cache_replaces_same_variant() -> None:
    cache = Cache()
    cache.set("item", "old", vary_headers=("accept",), request_headers={"accept": "application/json"})
    cache.set("item", "new", vary_headers=("accept",), request_headers={"accept": "application/json"})

    assert cache.get("item", {"accept": "application/json"}) == "new"
    assert len(cache) == 1


def test_cache_evicts_least_recently_used_key_when_capacity_is_reached() -> None:
    cache = Cache(max_entries=2)

    cache.set("first", 1)
    cache.set("second", 2)

    # Make the first entry recently used.
    assert cache.get("first") == 1

    # This should evict the second entry.
    cache.set("third", 3)

    assert cache.get("first") == 1
    assert cache.get("second") is None
    assert cache.get("third") == 3
    assert len(cache) == 2

def test_clear_removes_all_entries() -> None:
    cache = Cache()
    cache.set("first", 1)
    cache.set("second", 2)

    cache.clear()

    assert cache.get("first") is None
    assert cache.get("second") is None
    assert len(cache) == 0


def test_cache_capacity_evicts_oldest_variant_without_dropping_new_one() -> None:
    cache = Cache(max_entries=1)
    cache.set(
        "item",
        "english",
        vary_headers=("accept-language",),
        request_headers={"accept-language": "en"},
    )
    cache.set(
        "item",
        "french",
        vary_headers=("accept-language",),
        request_headers={"accept-language": "fr"},
    )

    assert len(cache) == 1
    assert cache.get("item", {"accept-language": "en"}) is None
    assert cache.get("item", {"accept-language": "fr"}) == "french"


def test_cache_rejects_non_finite_default_ttl() -> None:
    import pytest

    with pytest.raises(ValueError):
        Cache(ttl_seconds=float("nan"))
