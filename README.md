# Caching HTTP Proxy

A lightweight HTTP proxy built with **Python, FastAPI, and HTTPX**. It forwards incoming HTTP requests to a configured origin server and temporarily stores eligible `GET` responses in an in-memory cache.

This project demonstrates backend concepts such as HTTP request forwarding, cache policies, TTL expiration, LRU eviction, and request/response header handling. It is intended for learning and local development, not as a production-ready or internet-facing proxy.

## Features

- Forwards `GET`, `HEAD`, `POST`, `PUT`, `PATCH`, `DELETE`, and `OPTIONS` requests.
- Caches eligible successful `GET` responses with status code `200`.
- Uses an in-memory cache with TTL expiration and LRU eviction.
- Supports response variants based on the `Vary` header.
- Adds an `X-Cache` response header to indicate cache results.
- Supports cache size limits and configurable request timeouts.
- Provides health-check and protected cache-clear endpoints.
- Avoids caching requests and responses that contain headers or directives that make caching unsafe.

## Requirements

- Python 3.10+
- pip

Dependencies are listed in `requirements.txt`:

- FastAPI
- HTTPX
- Uvicorn

## Installation

Clone the repository and enter the project directory:

```bash
git clone https://github.com/AmirRezaiyan/caching_proxy_project.git
cd caching_proxy_project
```

Create and activate a virtual environment.

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

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

## Running the proxy

The proxy requires an origin URL and a listening port.

For example, to forward requests to JSONPlaceholder:

```bash
python main.py --host 127.0.0.1 --port 8000 --origin https://jsonplaceholder.typicode.com
```

The proxy will be available at:

```text
http://127.0.0.1:8000
```

You can now send requests to the proxy using the same paths exposed by the origin server.

### Example request

```bash
curl -i http://127.0.0.1:8000/posts/1
```

Send the same request again to check whether the response is served from the cache:

```bash
curl -i http://127.0.0.1:8000/posts/1
```

Check the `X-Cache` response header:

- `X-Cache: MISS` — the response was not found in the cache and was fetched from the origin.
- `X-Cache: HIT` — the cached response was returned.
- `X-Cache: BYPASS` — the request or response was not eligible for caching.

## Configuration

The application accepts the following command-line arguments:

| Argument | Description | Default |
| --- | --- | --- |
| `--host` | Host address on which the proxy listens. | `127.0.0.1` |
| `--port` | Port on which the proxy listens. Required when starting the server. | Required |
| `--origin` | Base URL of the upstream origin server. Required when starting the server. | Required |
| `--ttl` | Default cache time-to-live in seconds. Must be a positive finite number. | `60` |
| `--max-cache-entries` | Maximum number of cache entries. | `512` |
| `--timeout` | Upstream request timeout in seconds. | `10` |
| `--admin-token` | Token required by the cache-clear endpoint. Can also be set with `PROXY_ADMIN_TOKEN`. | Environment variable |

Example with custom settings:

```bash
python main.py --host 0.0.0.0 --port 8000 --origin https://jsonplaceholder.typicode.com --ttl 120 --max-cache-entries 1000 --timeout 15
```

Only expose the proxy on a trusted network. Binding to `0.0.0.0` makes it reachable through the machine's network interfaces.

## Cache behavior

The proxy applies conservative caching rules.

### Requests that bypass the cache

Requests are not served from or stored in the cache when, for example:

- The method is not `GET`.
- The request contains a body.
- The request contains `Authorization`, `Cookie`, or `Range`.
- Conditional request headers are present.
- The request includes `Cache-Control: no-store`.

Requests with `Cache-Control: no-cache`, `max-age=0`, or `Pragma: no-cache` force a fetch from the origin rather than reusing a cached response.

### Responses that are not cached

A response is not stored when, for example:

- Its status code is not `200`.
- It contains `Set-Cookie`.
- Its body exceeds 1 MiB.
- Its cache directives include `no-store`, `private`, or `no-cache`.
- Its `Vary` header is `*`.

The proxy honors `s-maxage` or `max-age` response directives, subject to a maximum cache lifetime of 3600 seconds. Otherwise, it uses the configured default TTL.

## Internal endpoints

The proxy exposes two internal endpoints:

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/__proxy__/health` | Returns the proxy health status. |
| `POST` | `/__proxy__/cache/clear` | Clears the in-memory cache. Requires the admin token. |

### Clear the cache

Start the proxy with an admin token:

**Windows PowerShell**

```powershell
$env:PROXY_ADMIN_TOKEN = "change-this-token"
python main.py --port 8000 --origin https://jsonplaceholder.typicode.com
```

**macOS / Linux**

```bash
export PROXY_ADMIN_TOKEN="change-this-token"
python main.py --port 8000 --origin https://jsonplaceholder.typicode.com
```

Send a cache-clear request with the matching token:

```bash
curl -X POST http://127.0.0.1:8000/__proxy__/cache/clear \
  -H "X-Proxy-Admin-Token: change-this-token"
```

The command-line cache-clear mode can also be used against a running local proxy:

```bash
python main.py --port 8000 --clear-cache --admin-token "change-this-token"
```

When using `--clear-cache`, do not provide `--origin`.

## Project structure

```text
caching_proxy_project/
├── cache.py          # In-memory cache, TTL expiration, and eviction
├── main.py           # CLI arguments and application startup
├── proxy_server.py   # Proxy routes and upstream request handling
├── requirements.txt  # Runtime dependencies
└── README.md
```

## Technical notes and limitations

- Cache data is stored in memory and is lost when the process stops.
- The cache is local to the running application process; it is not shared across multiple workers or instances.
- This project is not designed to replace a production reverse proxy or CDN.
- Authentication, TLS termination, distributed caching, and production-grade operational controls are outside its current scope.

## License

No license file is currently included in this repository. Unless a license is added, the project should be treated as having no explicit open-source license.
