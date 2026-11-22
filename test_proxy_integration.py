import asyncio

import httpx

from proxy_server import create_app


def run(coro):
    return asyncio.run(coro)


async def make_proxy_client(app: object) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://proxy.test",
    )


def test_get_response_is_cached_after_first_origin_request() -> None:
    origin_calls = 0

    async def origin_handler(request: httpx.Request) -> httpx.Response:
        nonlocal origin_calls
        origin_calls += 1
        return httpx.Response(
            200,
            headers={"Cache-Control": "public, max-age=60", "Content-Type": "text/plain"},
            content=b"origin response",
        )

    async def scenario() -> None:
        app = create_app("https://origin.test", admin_token="secret")
        app.state.http_client = httpx.AsyncClient(transport=httpx.MockTransport(origin_handler))
        async with await make_proxy_client(app) as client:
            first = await client.get("/resource")
            second = await client.get("/resource")

        await app.state.http_client.aclose()
        assert first.status_code == 200
        assert first.headers["x-cache"] == "MISS"
        assert second.headers["x-cache"] == "HIT"
        assert second.content == b"origin response"

    run(scenario())
    assert origin_calls == 1


def test_post_request_body_is_forwarded_to_origin() -> None:
    received: dict[str, object] = {}

    async def origin_handler(request: httpx.Request) -> httpx.Response:
        received["method"] = request.method
        received["body"] = request.content
        return httpx.Response(201, content=request.content)

    async def scenario() -> None:
        app = create_app("https://origin.test")
        app.state.http_client = httpx.AsyncClient(transport=httpx.MockTransport(origin_handler))
        async with await make_proxy_client(app) as client:
            response = await client.post("/items", content=b'{"name":"book"}')

        await app.state.http_client.aclose()
        assert response.status_code == 201
        assert response.headers["x-cache"] == "BYPASS"
        assert response.content == b'{"name":"book"}'

    run(scenario())
    assert received == {"method": "POST", "body": b'{"name":"book"}'}


def test_authorized_requests_are_never_cached() -> None:
    origin_calls = 0

    async def origin_handler(request: httpx.Request) -> httpx.Response:
        nonlocal origin_calls
        origin_calls += 1
        authorization = request.headers.get("authorization", "missing")
        return httpx.Response(
            200,
            headers={"Cache-Control": "public, max-age=60"},
            content=authorization.encode("utf-8"),
        )

    async def scenario() -> None:
        app = create_app("https://origin.test")
        app.state.http_client = httpx.AsyncClient(transport=httpx.MockTransport(origin_handler))
        async with await make_proxy_client(app) as client:
            first = await client.get("/private", headers={"Authorization": "Bearer one"})
            second = await client.get("/private", headers={"Authorization": "Bearer two"})

        await app.state.http_client.aclose()
        assert first.headers["x-cache"] == "BYPASS"
        assert second.headers["x-cache"] == "BYPASS"
        assert first.content == b"Bearer one"
        assert second.content == b"Bearer two"

    run(scenario())
    assert origin_calls == 2


def test_admin_cache_clear_requires_valid_token_and_clears_running_cache() -> None:
    origin_calls = 0

    async def origin_handler(request: httpx.Request) -> httpx.Response:
        nonlocal origin_calls
        origin_calls += 1
        return httpx.Response(
            200,
            headers={"Cache-Control": "public, max-age=60"},
            content=f"response-{origin_calls}".encode("ascii"),
        )

    async def scenario() -> None:
        app = create_app("https://origin.test", admin_token="correct-token")
        app.state.http_client = httpx.AsyncClient(transport=httpx.MockTransport(origin_handler))
        async with await make_proxy_client(app) as client:
            first = await client.get("/resource")
            unauthorized = await client.post("/__proxy__/cache/clear", headers={
                "X-Proxy-Admin-Token": "wrong-token"
            })
            cleared = await client.post("/__proxy__/cache/clear", headers={
                "X-Proxy-Admin-Token": "correct-token"
            })
            after_clear = await client.get("/resource")

        await app.state.http_client.aclose()
        assert first.headers["x-cache"] == "MISS"
        assert unauthorized.status_code == 403
        assert cleared.status_code == 200
        assert cleared.json() == {"status": "cleared"}
        assert after_clear.headers["x-cache"] == "MISS"

    run(scenario())
    assert origin_calls == 2


def test_origin_connection_error_returns_502() -> None:
    async def origin_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    async def scenario() -> None:
        app = create_app("https://origin.test")
        app.state.http_client = httpx.AsyncClient(transport=httpx.MockTransport(origin_handler))
        async with await make_proxy_client(app) as client:
            response = await client.get("/unavailable")

        await app.state.http_client.aclose()
        assert response.status_code == 502
        assert response.json() == {"detail": "Could not connect to the origin server."}

    run(scenario())
