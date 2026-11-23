
"""FastAPI-based HTTP caching proxy."""

from __future__ import annotations

import hmac
import logging
import math
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from .cache import Cache

logger = logging.getLogger("caching_proxy")

SUPPORTED_METHODS = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
HOP_BY_HOP_HEADERS = {
    "connection",
    "proxy-connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
CACHEABLE_STATUS_CODES = {200}
MAX_CACHEABLE_RESPONSE_BYTES = 1_048_576  # 1 MiB
ADMIN_CLEAR_PATH = "/__proxy__/cache/clear"


def _connection_tokens(headers: httpx.Headers) -> set[str]:
    value = headers.get("connection", "")
    return {token.strip().lower() for token in value.split(",") if token.strip()}


def _request_headers_for_origin(request: Request) -> dict[str, str]:
    """Copy end-to-end headers and let httpx calculate framing headers."""
    connection_tokens = _connection_tokens(httpx.Headers(request.headers.raw))
    excluded = HOP_BY_HOP_HEADERS | connection_tokens | {
        "host",
        "content-length",
        "accept-encoding",
    }

    headers = {
        name: value
        for name, value in request.headers.items()
        if name.lower() not in excluded
    }
    # Avoid compressed upstream bodies: httpx transparently decompresses
    # responses, and identity encoding keeps the returned representation clear.
    headers["accept-encoding"] = "identity"
    return headers


def build_target_url(origin: str, request: Request) -> str:
    """Append a request path to the configured origin without changing its host."""
    base_url = httpx.URL(origin)
    base_path = base_url.path.rstrip("/") + "/"
    relative_path = request.url.path.lstrip("/")
    target_path = f"{base_path}{relative_path}"
    query = request.url.query.encode("ascii")
    return str(base_url.copy_with(path=target_path, query=query))


def _parse_cache_control(value: str) -> dict[str, str | None]:
    directives: dict[str, str | None] = {}
    for item in value.lower().split(","):
        item = item.strip()
        if not item:
            continue
        if "=" in item:
            name, directive_value = item.split("=", 1)
            directives[name.strip()] = directive_value.strip().strip('"')
        else:
            directives[item] = None
    return directives


def _request_is_cacheable(request: Request, body: bytes) -> bool:
    if request.method != "GET" or body:
        return False
    if request.headers.get("authorization") or request.headers.get("cookie"):
        return False
    if any(
        request.headers.get(name)
        for name in (
            "range",
            "if-match",
            "if-none-match",
            "if-modified-since",
            "if-unmodified-since",
            "if-range",
        )
    ):
        return False

    directives = _parse_cache_control(request.headers.get("cache-control", ""))
    return "no-store" not in directives


def _request_forces_origin(request: Request) -> bool:
    directives = _parse_cache_control(request.headers.get("cache-control", ""))
    pragma = _parse_cache_control(request.headers.get("pragma", ""))
    return (
        "no-cache" in directives
        or directives.get("max-age") == "0"
        or "no-cache" in pragma
    )


def _response_cache_policy(
    upstream: httpx.Response,
    response_body: bytes,
    default_ttl: float,
    max_ttl: float,
) -> tuple[float, tuple[str, ...]] | None:
    if upstream.status_code not in CACHEABLE_STATUS_CODES:
        return None
    if len(response_body) > MAX_CACHEABLE_RESPONSE_BYTES:
        return None
    if "set-cookie" in upstream.headers:
        return None

    directives = _parse_cache_control(upstream.headers.get("cache-control", ""))

    if any(name in directives for name in ("no-store", "private", "no-cache")):
        return None

    vary_value = upstream.headers.get("vary", "")
    vary_headers = tuple(
        sorted({name.strip().lower() for name in vary_value.split(",") if name.strip()})
    )
    if "*" in vary_headers:
        return None

    ttl = default_ttl
    max_age = directives.get("s-maxage") or directives.get("max-age")
    if max_age is not None:
        try:
            ttl = float(int(max_age))
        except ValueError:
            return None

    if not math.isfinite(ttl):
        return None
    ttl = min(ttl, max_ttl)
    if ttl <= 0:
        return None

    return ttl, vary_headers


def _response_from_upstream(
    body: bytes,
    upstream: httpx.Response,
    cache_status: str,
    request_method: str,
) -> Response:
    """Build a downstream response while preserving repeated headers."""
    upstream_headers = upstream.headers
    connection_tokens = _connection_tokens(upstream_headers)
    excluded = HOP_BY_HOP_HEADERS | connection_tokens | {"content-encoding", "x-cache"}

    raw_headers: list[tuple[bytes, bytes]] = []
    has_content_length = False

    for name, value in upstream.headers.raw:
        lower_name = name.decode("latin-1").lower()
        if lower_name in excluded:
            continue
        if lower_name == "content-length":
            has_content_length = True
            # HEAD has no body but may legitimately report the GET body length.
            if request_method != "HEAD":
                continue
        raw_headers.append((name, value))

    response = Response(content=body, status_code=upstream.status_code)
    if request_method != "HEAD" or not has_content_length:
        raw_headers.append((b"content-length", str(len(body)).encode("ascii")))
    raw_headers.append((b"x-cache", cache_status.encode("ascii")))
    response.raw_headers = raw_headers
    return response


def _response_from_cache(cached: dict, cache_status: str = "HIT") -> Response:
    response = Response(content=cached["content"], status_code=cached["status_code"])
    cached_headers = httpx.Headers(cached["headers"])
    connection_tokens = _connection_tokens(cached_headers)
    excluded = {
        name.encode("ascii")
        for name in (HOP_BY_HOP_HEADERS | connection_tokens)
    } | {b"content-length", b"content-encoding", b"x-cache"}

    raw_headers = [
        (name, value)
        for name, value in cached["headers"]
        if name.lower() not in excluded
    ]
    raw_headers.append((b"content-length", str(len(cached["content"])).encode("ascii")))
    raw_headers.append((b"x-cache", cache_status.encode("ascii")))
    response.raw_headers = raw_headers
    return response


def create_app(
    origin: str | None = None,
    *,
    cache_ttl: float = 60.0,
    max_cache_entries: int = 512,
    timeout: float = 10.0,
    admin_token: str | None = None,
) -> FastAPI:
    """Create an independently configured proxy application."""
    if not math.isfinite(cache_ttl) or cache_ttl <= 0:
        raise ValueError("cache_ttl must be a finite number greater than zero")
    if max_cache_entries <= 0:
        raise ValueError("max_cache_entries must be greater than zero")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be a finite number greater than zero")

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=min(timeout, 5.0)),
            follow_redirects=False,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )
        try:
            yield
        finally:
            await application.state.http_client.aclose()

    application = FastAPI(
        title="Caching HTTP Proxy",
        description="A small HTTP proxy with an in-memory TTL cache.",
        version="2.0.0",
        lifespan=lifespan,
    )
    application.state.origin_url = origin
    application.state.cache = Cache(
        ttl_seconds=cache_ttl,
        max_entries=max_cache_entries,
    )
    application.state.cache_ttl = float(cache_ttl)
    application.state.max_cache_ttl = 3600.0
    application.state.admin_token = admin_token
    application.state.timeout = float(timeout)

    @application.get("/__proxy__/health", include_in_schema=False)
    async def health() -> dict[str, str | int]:
        return {
            "status": "ok",
            "cache_entries": len(application.state.cache),
        }

    @application.post(ADMIN_CLEAR_PATH, include_in_schema=False)
    async def clear_cache_endpoint(request: Request) -> Response:
        configured_token = application.state.admin_token
        if not configured_token:
            return JSONResponse(status_code=404, content={"detail": "Not found"})

        supplied_token = request.headers.get("x-proxy-admin-token", "")
        if not hmac.compare_digest(
            supplied_token.encode("utf-8"), configured_token.encode("utf-8")
        ):
            return JSONResponse(status_code=403, content={"detail": "Forbidden"})

        application.state.cache.clear()
        return JSONResponse(content={"status": "cleared"})

    async def handle_proxy_request(request: Request) -> Response:
        origin_url = application.state.origin_url
        if not origin_url:
            return JSONResponse(
                status_code=503,
                content={"detail": "Proxy origin is not configured."},
            )

        try:
            target_url = build_target_url(origin_url, request)
        except (TypeError, ValueError, httpx.InvalidURL):
            return JSONResponse(status_code=400, content={"detail": "Invalid target URL."})

        try:
            request_body = await request.body()
            cache_allowed = _request_is_cacheable(request, request_body)
            cache_key = f"GET:{target_url}"

            if cache_allowed and not _request_forces_origin(request):
                cached = application.state.cache.get(cache_key, request.headers)
                if cached is not None:
                    return _response_from_cache(cached)

            client: httpx.AsyncClient = application.state.http_client
            upstream = await client.request(
                method=request.method,
                url=target_url,
                headers=_request_headers_for_origin(request),
                content=request_body if request_body else None,
            )

            response_body = upstream.content
            cache_status = "BYPASS" if not cache_allowed else "MISS"
            if cache_allowed:
                policy = _response_cache_policy(
                    upstream,
                    response_body,
                    application.state.cache_ttl,
                    application.state.max_cache_ttl,
                )
                if policy is not None:
                    ttl, vary_headers = policy
                    cached_response = {
                        "content": response_body,
                        "status_code": upstream.status_code,
                        "headers": list(upstream.headers.raw),
                    }
                    application.state.cache.set(
                        cache_key,
                        cached_response,
                        ttl=ttl,
                        vary_headers=vary_headers,
                        request_headers=request.headers,
                    )
                else:
                    cache_status = "BYPASS"

            return _response_from_upstream(
                response_body,
                upstream,
                cache_status,
                request.method,
            )

        except httpx.TimeoutException:
            logger.warning("Timed out while forwarding request to %s", origin_url)
            return JSONResponse(
                status_code=504,
                content={"detail": "The origin server timed out."},
            )
        except httpx.RequestError as exc:
            logger.warning("Could not reach origin (%s)", type(exc).__name__)
            return JSONResponse(
                status_code=502,
                content={"detail": "Could not connect to the origin server."},
            )
        except Exception:
            logger.exception("Unexpected error while proxying request")
            return JSONResponse(
                status_code=502,
                content={"detail": "An unexpected proxy error occurred."},
            )

    application.api_route("/", methods=SUPPORTED_METHODS, include_in_schema=False)(
        handle_proxy_request
    )
    application.api_route(
        "/{path:path}", methods=SUPPORTED_METHODS, include_in_schema=False
    )(handle_proxy_request)

    return application


# Backwards-compatible default application and helper for in-process use.
app = create_app()
cache: Cache = app.state.cache


def clear_cache() -> None:
    """Clear the currently configured application's in-process cache."""
    cache.clear()


def start_proxy_server(
    port: int,
    origin: str,
    host: str = "127.0.0.1",
    cache_ttl: float = 60.0,
    max_cache_entries: int = 512,
    timeout: float = 10.0,
    admin_token: str | None = None,
) -> None:
    """Start the configured proxy server."""
    import uvicorn

    global app, cache
    app = create_app(
        origin=origin,
        cache_ttl=cache_ttl,
        max_cache_entries=max_cache_entries,
        timeout=timeout,
        admin_token=admin_token,
    )
    cache = app.state.cache
    uvicorn.run(app, host=host, port=port, log_level="info")
