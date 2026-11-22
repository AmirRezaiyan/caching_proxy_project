Caching HTTP Proxy
A lightweight HTTP proxy built with Python, FastAPI, and HTTPX. It forwards incoming HTTP requests to a configured origin server and temporarily stores eligible GET responses in an in-memory cache.
The project is intended as a learning project for backend concepts such as HTTP request forwarding, middleware-style request handling, caching, cache policies, TTL expiration, and LRU eviction. It is not intended to be a production-ready or internet-facing proxy.
Features
Forwards GET, HEAD, POST, PUT, PATCH, DELETE, and OPTIONS requests.
Caches successful GET responses (200 OK) when the request and response are eligible for caching.
Returns X-Cache: MISS when a cacheable request is fetched from the origin, X-Cache: HIT when a cached response is returned, and X-Cache: BYPASS when caching is not applicable.
Supports a configurable default cache TTL and honors an origin response's s-maxage or max-age when present.
Supports the response Vary header so different request-header variants are not mixed together.
Uses LRU-style eviction and a configurable maximum number of cached response variants.
Avoids caching requests containing Authorization or Cookie headers, and avoids caching responses marked private, no-store, or no-cache, responses containing Set-Cookie, non-200 responses, and responses larger than 1 MiB.
Uses asynchronous HTTP requests and connection pooling through HTTPX.
Provides a token-protected endpoint and CLI command for clearing the cache of a running proxy.
Returns 502 Bad Gateway for origin connection errors and 504 Gateway Timeout for origin timeouts.
Requirements
Python 3.10 or newer
pip
Installation
Create and activate a virtual environment, then install the dependencies.
Windows PowerShell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
Run the proxy
For example, to proxy requests to JSONPlaceholder on local port 8000:
python main.py --port 8000 --origin https://jsonplaceholder.typicode.com
The proxy listens on 127.0.0.1 by default. Open this URL in a browser or send a request with Postman or curl:
http://127.0.0.1:8000/posts/1
The request is forwarded to:
https://jsonplaceholder.typicode.com/posts/1
To bind to a different interface, pass --host. Do not expose the proxy to an untrusted network without adding appropriate access controls and deployment hardening.
Check the cache
Send the same GET request twice:
curl -i http://127.0.0.1:8000/posts/1
The first eligible request should include:
X-Cache: MISS
A subsequent request, before the entry expires, should include:
X-Cache: HIT
Requests that should not be cached return:
X-Cache: BYPASS
The cache stores data in process memory. Restarting the proxy clears the cache.
Clear the cache while the proxy is running
Start the proxy with an admin token. Use your own long, random token rather than the example below.
Windows PowerShell
$env:PROXY_ADMIN_TOKEN = "replace-this-with-a-long-random-token"
python main.py --port 8000 --origin https://jsonplaceholder.typicode.com
Open a second terminal, set the same token, and run:
$env:PROXY_ADMIN_TOKEN = "replace-this-with-a-long-random-token"
python main.py --port 8000 --clear-cache
macOS / Linux
export PROXY_ADMIN_TOKEN="replace-this-with-a-long-random-token"
python main.py --port 8000 --origin https://jsonplaceholder.typicode.com
In a second terminal:
export PROXY_ADMIN_TOKEN="replace-this-with-a-long-random-token"
python main.py --port 8000 --clear-cache
The clear-cache command sends an authenticated request to the running proxy. It does not attempt to clear a separate, newly created Python process's memory.
Configuration
Argument
Default
Description
--port
Required
Local port used by the proxy
--origin
Required when starting
Base URL of the origin server; supports an optional path prefix
--host
127.0.0.1
Network interface to bind
--ttl
60
Default cache lifetime in seconds
--max-cache-entries
512
Maximum number of cached response variants
--timeout
10
Origin request timeout in seconds
--admin-token
PROXY_ADMIN_TOKEN
Token required to clear a running proxy's cache
--clear-cache
Off
Clear the cache of a running proxy instead of starting it
The maximum cache lifetime for an origin-provided max-age or s-maxage is capped at one hour. The maximum cacheable response body size is currently 1 MiB.
Project structure
caching_proxy_project/
├── cache.py               # In-memory TTL cache with LRU eviction and Vary support
├── main.py                # Command-line interface
├── proxy_server.py        # FastAPI application and HTTP forwarding logic
├── requirements.txt       # Runtime dependencies
├── requirements-dev.txt   # Test dependencies
├── tests/
│   ├── test_cache.py
│   └── test_proxy_helpers.py
├── .gitignore
└── README.md
Run tests
Install development dependencies:
pip install -r requirements-dev.txt
Run the test suite:
python -m pytest -q
Current limitations
The cache is in-memory and local to one process; it is cleared when the server restarts and is not shared across multiple workers.
This project does not implement cache revalidation with ETag / If-Modified-Since, streaming uploads/downloads, WebSockets, or HTTPS tunneling via the CONNECT method.
Request and response bodies are buffered in memory. Responses larger than 1 MiB are forwarded but are not stored in the cache.
The proxy does not include production features such as user authentication, rate limiting, detailed metrics, or a hardened deployment configuration.
The administrative cache-clear endpoint is disabled unless an admin token is configured.
License
No license is currently specified. Add a LICENSE file before allowing reuse or redistribution of this project.