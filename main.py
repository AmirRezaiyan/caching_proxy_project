
"""Command-line interface for the caching proxy."""

from __future__ import annotations

import argparse
import math
import os
import sys

import httpx

from proxy_server import start_proxy_server


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def valid_port(value: str) -> int:
    parsed = positive_int(value)
    if parsed > 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return parsed


def positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("must be a finite number greater than zero")
    return parsed


def validate_origin(value: str) -> str:
    try:
        url = httpx.URL(value)
    except (TypeError, ValueError, httpx.InvalidURL) as exc:
        raise argparse.ArgumentTypeError("origin must be a valid HTTP or HTTPS URL") from exc

    if url.scheme not in {"http", "https"} or not url.host:
        raise argparse.ArgumentTypeError("origin must start with http:// or https://")
    if url.username or url.password:
        raise argparse.ArgumentTypeError("origin must not contain username or password")
    if url.query or url.fragment:
        raise argparse.ArgumentTypeError("origin must not contain a query string or fragment")

    return value.rstrip("/")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Forward HTTP requests to an origin server and cache eligible GET responses."
    )
    parser.add_argument("--port", type=valid_port, required=True, help="Local proxy port")
    parser.add_argument(
        "--origin",
        type=validate_origin,
        help="Origin base URL, for example https://jsonplaceholder.typicode.com",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Interface to bind (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--ttl",
        type=positive_float,
        default=60.0,
        help="Default cache lifetime in seconds (default: 60)",
    )
    parser.add_argument(
        "--max-cache-entries",
        type=positive_int,
        default=512,
        help="Maximum number of cached response variants (default: 512)",
    )
    parser.add_argument(
        "--timeout",
        type=positive_float,
        default=10.0,
        help="Origin request timeout in seconds (default: 10)",
    )
    parser.add_argument(
        "--admin-token",
        default=os.getenv("PROXY_ADMIN_TOKEN"),
        help="Token required by the cache-clear command (or PROXY_ADMIN_TOKEN env var)",
    )
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear the cache of a running local proxy instead of starting a server",
    )
    return parser


def clear_running_cache(port: int, token: str) -> int:
    url = f"http://127.0.0.1:{port}/__proxy__/cache/clear"
    try:
        response = httpx.post(
            url,
            headers={"X-Proxy-Admin-Token": token},
            timeout=5.0,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 403:
            print("Cache clear failed: invalid admin token.", file=sys.stderr)
        elif exc.response.status_code == 404:
            print(
                "Cache clear failed: the running proxy has no admin token configured.",
                file=sys.stderr,
            )
        else:
            print(
                f"Cache clear failed: proxy returned HTTP {exc.response.status_code}.",
                file=sys.stderr,
            )
        return 1
    except httpx.RequestError:
        print(
            "Cache clear failed: could not connect to the proxy on 127.0.0.1.",
            file=sys.stderr,
        )
        return 1

    print("Cache cleared successfully.")
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.clear_cache:
        if not args.admin_token:
            parser.error("--clear-cache requires --admin-token or PROXY_ADMIN_TOKEN")
        if args.origin:
            parser.error("do not provide --origin when using --clear-cache")
        return clear_running_cache(args.port, args.admin_token)

    if not args.origin:
        parser.error("--origin is required when starting the proxy")

    start_proxy_server(
        port=args.port,
        origin=args.origin,
        host=args.host,
        cache_ttl=args.ttl,
        max_cache_entries=args.max_cache_entries,
        timeout=args.timeout,
        admin_token=args.admin_token,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
