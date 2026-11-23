import httpx
from starlette.requests import Request

from app.proxy_server import (
    _request_forces_origin,
    _request_is_cacheable,
    _response_cache_policy,
    build_target_url,
)

def make_request(
    path: str = "/posts/1",
    method: str = "GET",
    headers: list[tuple[bytes, bytes]] | None = None,
    query_string: bytes = b"",
) -> Request:
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": query_string,
        "root_path": "",
        "headers": headers or [],
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 8000),
    }
    return Request(scope)


def test_target_url_keeps_origin_base_path_and_query() -> None:
    request = make_request(path="/posts/1", query_string=b"page=2&sort=desc")

    result = build_target_url("https://example.com/api", request)

    assert result == "https://example.com/api/posts/1?page=2&sort=desc"


def test_target_url_does_not_allow_request_path_to_change_host() -> None:
    request = make_request(path="//evil.example/path")

    result = build_target_url("https://example.com", request)

    assert httpx.URL(result).host == "example.com"


def test_authorized_and_cookie_requests_are_not_cacheable() -> None:
    authorized = make_request(headers=[(b"authorization", b"Bearer secret")])
    cookie_request = make_request(headers=[(b"cookie", b"session=secret")])

    assert not _request_is_cacheable(authorized, b"")
    assert not _request_is_cacheable(cookie_request, b"")


def test_get_with_body_is_not_cacheable() -> None:
    request = make_request()
    assert not _request_is_cacheable(request, b"payload")


def test_post_is_not_cacheable() -> None:
    request = make_request(method="POST")
    assert not _request_is_cacheable(request, b"")


def test_no_store_private_and_vary_star_responses_are_not_cached() -> None:
    body = b"response"

    no_store = httpx.Response(200, headers={"Cache-Control": "no-store"}, content=body)
    private = httpx.Response(200, headers={"Cache-Control": "private"}, content=body)
    vary_star = httpx.Response(200, headers={"Vary": "*"}, content=body)

    assert _response_cache_policy(no_store, body, 60, 3600) is None
    assert _response_cache_policy(private, body, 60, 3600) is None
    assert _response_cache_policy(vary_star, body, 60, 3600) is None


def test_max_age_and_vary_are_read_from_origin_response() -> None:
    response = httpx.Response(
        200,
        headers={"Cache-Control": "public, max-age=30", "Vary": "Accept-Language"},
        content=b"hello",
    )

    assert _response_cache_policy(response, b"hello", 60, 3600) == (
        30.0,
        ("accept-language",),
    )


def test_non_200_response_is_not_cached() -> None:
    response = httpx.Response(404, content=b"not found")
    assert _response_cache_policy(response, b"not found", 60, 3600) is None


def test_absolute_looking_request_path_cannot_change_origin_host() -> None:
    request = make_request(path="/http://evil.example/steal")

    result = build_target_url("https://example.com/api", request)

    assert httpx.URL(result).host == "example.com"
    assert httpx.URL(result).path == "/api/http://evil.example/steal"


def test_request_no_cache_forces_origin_and_no_store_disables_cache() -> None:

    no_cache = make_request(headers=[(b"cache-control", b"no-cache")])
    zero_age = make_request(headers=[(b"cache-control", b"max-age=0")])
    no_store = make_request(headers=[(b"cache-control", b"no-store")])

    assert _request_forces_origin(no_cache)
    assert _request_forces_origin(zero_age)
    assert not _request_is_cacheable(no_store, b"")


def test_invalid_origin_cache_max_age_is_not_cached() -> None:
    response = httpx.Response(
        200,
        headers={"Cache-Control": "max-age=nan"},
        content=b"hello",
    )

    assert _response_cache_policy(response, b"hello", 60, 3600) is None


def test_range_and_conditional_requests_are_not_cacheable() -> None:
    range_request = make_request(headers=[(b"range", b"bytes=0-10")])
    conditional_request = make_request(
        headers=[(b"if-none-match", b'"etag-value"')]
    )

    assert not _request_is_cacheable(range_request, b"")
    assert not _request_is_cacheable(conditional_request, b"")
