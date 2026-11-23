# Caching HTTP Proxy

A lightweight HTTP caching proxy built with **Python, FastAPI, and HTTPX**. It forwards incoming HTTP requests to a configured origin server and temporarily stores eligible `GET` responses in an in-memory cache.

The project demonstrates practical backend and HTTP concepts, including request forwarding, response caching, cache-control policies, TTL expiration, LRU eviction, `Vary` header handling, and request/response header management.

It is designed for learning and local development, not as a production-ready or internet-facing proxy.

## Features

- Forwards `GET`, `HEAD`, `POST`, `PUT`, `PATCH`, `DELETE`, and `OPTIONS` requests.
- Caches eligible successful `GET` responses with HTTP status code `200`.
- Uses an in-memory cache with configurable TTL expiration.
- Implements LRU (Least Recently Used) eviction when the cache reaches its capacity.
- Supports response variants based on the `Vary` header.
- Respects relevant request and response `Cache-Control` directives.
- Adds an `X-Cache` response header to indicate cache behavior.
- Supports configurable cache capacity and upstream request timeouts.
- Provides a health-check endpoint.
- Provides a protected endpoint and CLI command for clearing the cache.
- Filters hop-by-hop HTTP headers when forwarding requests and responses.
- Avoids caching requests and responses that contain headers or directives that make caching unsafe.
- Includes unit, helper, and integration tests.

## Requirements

- Python 3.10 or later
- pip

Runtime dependencies are listed in `requirements.txt`:

- FastAPI
- HTTPX
- Uvicorn

Development and testing dependencies are listed in `requirements-dev.txt`.

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/AmirRezaiyan/caching_proxy_project.git
cd caching_proxy_project
```

### 2. Create a virtual environment

**Windows PowerShell**

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install runtime dependencies

```bash
python -m pip install -r requirements.txt
```

On Windows, you can use `py -m pip` instead of `python -m pip` if the `python` command is not available in PATH.

### 4. Install development dependencies

To install the tools required for running the test suite:

```bash
python -m pip install -r requirements-dev.txt
```

## Running the Proxy

The proxy requires an origin URL and a listening port.

For example, to forward requests to JSONPlaceholder, run:

```bash
python -m app.main --host 127.0.0.1 --port 8000 --origin https://jsonplaceholder.typicode.com
```

On Windows, if the `python` command is unavailable, use:

```powershell
py -m app.main --host 127.0.0.1 --port 8000 --origin https://jsonplaceholder.typicode.com
```

The proxy will be available at:

```text
http://127.0.0.1:8000
```

You can now send requests to the proxy using the same paths exposed by the configured origin server.

### Example Request

Using curl:

```bash
curl -i http://127.0.0.1:8000/posts/1
```

On Windows PowerShell:

```powershell
Invoke-WebRequest http://127.0.0.1:8000/posts/1 -UseBasicParsing
```

Send the same request again to check whether the response is served from the cache.

### Cache Response Header

The proxy adds an `X-Cache` response header to indicate how the request was handled.

| Header | Description |
| --- | --- |
| `X-Cache: MISS` | The response was not found in the cache and was fetched from the origin. |
| `X-Cache: HIT` | A matching cached response was returned. |
| `X-Cache: BYPASS` | The request or origin response was not eligible for caching. |

For example, the first request to an eligible resource will normally return `MISS`. A subsequent request may return `HIT` while the cached response remains valid.

## Configuration

The application accepts the following command-line arguments:

| Argument | Description | Default |
| --- | --- | --- |
| `--host` | Host address on which the proxy listens. | `127.0.0.1` |
| `--port` | Port on which the proxy listens. Required when starting the server. | Required |
| `--origin` | Base URL of the upstream origin server. Required when starting the server. | Required |
| `--ttl` | Default cache time-to-live in seconds. Must be a positive finite number. | `60` |
| `--max-cache-entries` | Maximum number of cached response entries. | `512` |
| `--timeout` | Upstream request timeout in seconds. | `10` |
| `--admin-token` | Token required by the cache-clear endpoint. Can also be configured using `PROXY_ADMIN_TOKEN`. | Environment variable |

### Custom Configuration Example

```bash
python -m app.main \
  --host 127.0.0.1 \
  --port 8000 \
  --origin https://jsonplaceholder.typicode.com \
  --ttl 120 \
  --max-cache-entries 1000 \
  --timeout 15
```

The proxy can also listen on all available network interfaces:

```bash
python -m app.main --host 0.0.0.0 --port 8000 --origin https://jsonplaceholder.typicode.com
```

**Security note:** Binding to `0.0.0.0` makes the proxy reachable through the machine's network interfaces. Only use this setting on a trusted network with appropriate access controls. The default `127.0.0.1` binding is recommended for local development.

## Cache Behavior

The proxy applies conservative caching rules to avoid storing responses that may be unsafe or inappropriate to reuse.

### Cacheable Requests

A request is considered eligible for caching when:

- Its HTTP method is `GET`.
- It does not contain a request body.
- It does not contain an `Authorization` or `Cookie` header.
- It does not contain `Range` or conditional request headers.
- It does not include the request directive `Cache-Control: no-store`.

### Requests That Bypass Existing Cache Entries

Some request directives force the proxy to fetch a fresh response from the origin instead of using an existing cached response:

- `Cache-Control: no-cache`
- `Cache-Control: max-age=0`
- `Pragma: no-cache`

### Responses That Are Not Cached

An origin response is not stored when:

- Its HTTP status code is not `200`.
- It contains a `Set-Cookie` header.
- Its response body exceeds 1 MiB.
- Its `Cache-Control` directives include `no-store`, `private`, or `no-cache`.
- Its `Vary` header contains `*`.
- Its cache lifetime is invalid or not positive.

### TTL and Cache-Control

The proxy supports both a configurable default TTL and cache lifetime directives returned by the origin server.

The cache lifetime is determined as follows:

1. The proxy uses `s-maxage` when it is present.
2. Otherwise, it uses `max-age` when available.
3. If neither directive is present, it uses the configured default TTL.
4. The resulting lifetime is capped at a maximum of 3600 seconds.

For example, when the proxy is started with `--ttl 10`, the default cache lifetime is 10 seconds. However, an eligible origin response with a valid `Cache-Control: max-age` or `s-maxage` directive can specify a different lifetime, subject to the proxy's 3600-second maximum.

### TTL Expiration

Each cached entry has an expiration time. Once that time is reached, the entry is no longer returned from the cache.

An expired entry is removed when the cache is accessed.

### LRU Eviction

The cache uses the Least Recently Used (LRU) strategy when its capacity is exceeded.

When a new entry needs to be stored and the cache is full, the least recently used entry is evicted to make room for the new one.

Accessing a cached entry updates its recency.

### Vary Header Support

The proxy supports response variants based on the origin response's `Vary` header.

For example, when an origin returns:

```http
Vary: Accept-Language
```

the proxy stores separate response variants according to the corresponding request header value.

This prevents a response generated for one header variation from being incorrectly reused for a different variation.

## Internal Endpoints

The proxy exposes internal endpoints for health monitoring and cache management.

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/__proxy__/health` | Returns the proxy health status and current cache entry count. |
| `POST` | `/__proxy__/cache/clear` | Clears the in-memory cache. Requires a valid admin token. |

### Health Check

Send a request to:

```bash
curl http://127.0.0.1:8000/__proxy__/health
```

Example response:

```json
{
  "status": "ok",
  "cache_entries": 1
}
```

The `cache_entries` value represents the current number of cached response entries.

### Clear the Cache

The cache-clear endpoint requires an admin token configured when the proxy starts.

First, configure the token.

**Windows PowerShell**

```powershell
$env:PROXY_ADMIN_TOKEN = "change-this-token"

py -m app.main --port 8000 --origin https://jsonplaceholder.typicode.com
```

**macOS / Linux**

```bash
export PROXY_ADMIN_TOKEN="change-this-token"

python -m app.main --port 8000 --origin https://jsonplaceholder.typicode.com
```

Send a POST request with the matching token.

**Using curl**

```bash
curl -X POST http://127.0.0.1:8000/__proxy__/cache/clear \
  -H "X-Proxy-Admin-Token: change-this-token"
```

**Using Windows PowerShell**

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/__proxy__/cache/clear `
  -Headers @{"X-Proxy-Admin-Token" = "change-this-token"}
```

A successful request returns:

```json
{
  "status": "cleared"
}
```

Requests without a configured admin token receive `404`. Requests with an invalid token receive `403`.

### CLI Cache-Clear Mode

The command-line interface also supports clearing the cache of a running local proxy:

```bash
python -m app.main --port 8000 --clear-cache --admin-token "change-this-token"
```

When using `--clear-cache`, do not provide `--origin`.

The token can be supplied through the `PROXY_ADMIN_TOKEN` environment variable or directly through `--admin-token`.

## Running Tests

The project includes unit tests, helper tests, and integration tests.

To run the complete test suite:

```bash
python -m pytest -v
```

On Windows:

```powershell
py -m pytest -v
```

The tests cover areas including:

- Cache storage and retrieval.
- TTL expiration.
- LRU eviction and capacity limits.
- Cache variants and `Vary` header handling.
- Cache clearing.
- Origin URL construction.
- Request cache eligibility.
- `Cache-Control` request and response policies.
- Authorization and cookie handling.
- Conditional and range requests.
- Proxy request forwarding.
- Cache hit and miss behavior.
- Protected cache management.
- Origin connection errors.

The integration tests use HTTPX mock transports and an in-process ASGI transport, so they do not require an external origin server.

## Local Origin Server for Manual Testing

The repository also includes `local_origin.py`, a small local HTTP origin server useful for manually testing proxy behavior without depending on an external API.

Start the local origin server in a separate terminal:

```powershell
py local_origin.py
```

It listens on:

```text
http://127.0.0.1:9000
```

Start the proxy in another terminal and use the local server as its origin:

```powershell
py -m app.main --host 127.0.0.1 --port 8001 --origin http://127.0.0.1:9000 --ttl 10
```

You can now test cache behavior through the proxy:

```powershell
Invoke-WebRequest http://127.0.0.1:8001/posts/1 -UseBasicParsing
```

Repeat the request to observe a cache hit. After the configured TTL expires, send another request to verify that the response is fetched again from the origin.

This helper is intended for local development and manual testing.

## Project Structure

```text
caching_proxy_project/
│
├── app/
│   ├── __init__.py
│   ├── cache.py
│   ├── main.py
│   └── proxy_server.py
│
├── tests/
│   ├── test_cache.py
│   ├── test_proxy_helpers.py
│   └── test_proxy_integration.py
│
├── .gitignore
├── README.md
├── requirements.txt
├── requirements-dev.txt
└── local_origin.py
```

### Main Components

| File | Responsibility |
| --- | --- |
| `app/cache.py` | In-memory cache implementation, TTL expiration, LRU eviction, and response variants. |
| `app/main.py` | Command-line argument parsing, configuration validation, and application startup. |
| `app/proxy_server.py` | FastAPI application, proxy routes, request forwarding, response handling, and cache policies. |
| `tests/test_cache.py` | Unit tests for cache storage, expiration, variants, and eviction. |
| `tests/test_proxy_helpers.py` | Tests for URL construction and request/response cache policies. |
| `tests/test_proxy_integration.py` | Integration tests for proxy behavior and upstream request handling. |
| `local_origin.py` | Lightweight local origin server for manual testing. |
| `requirements.txt` | Runtime dependencies. |
| `requirements-dev.txt` | Development and testing dependencies. |

## Technical Notes and Limitations

- Cache data is stored in memory and is lost when the application process stops.
- The cache is local to the running application process and is not shared across multiple workers or instances.
- The cache is not persistent and does not use an external storage system.
- The proxy is designed around a configured origin server rather than acting as a general-purpose forwarding proxy.
- It is not intended to replace a production reverse proxy or CDN.
- Production-grade authentication, TLS termination, distributed caching, advanced monitoring, and operational controls are outside the current scope.
- The application should only be exposed to trusted clients and networks.

## License

No license file is currently included in this repository.

Unless a license is added, the project should be treated as having no explicit open-source license.