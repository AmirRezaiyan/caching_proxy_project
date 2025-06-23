import argparse
from proxy_server import start_proxy_server, clear_cache

def main():
    parser = argparse.ArgumentParser(description="Caching Proxy CLI")
    parser.add_argument('--port', type=int, help="Port to run proxy server")
    parser.add_argument('--origin', type=str, help="Origin server URL")
    parser.add_argument('--clear-cache', action='store_true', help="Clear the cache")

    args = parser.parse_args()

    if args.clear_cache:
        clear_cache()
        print("✅ Cache cleared.")
    elif args.port and args.origin:
        start_proxy_server(port=args.port, origin=args.origin)
    else:
        print("❗ لطفاً یا --clear-cache وارد کن یا --port و --origin رو با هم.")

if __name__ == "__main__":
    main()
