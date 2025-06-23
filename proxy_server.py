from fastapi import FastAPI, Request, Response
import requests
import uvicorn
from urllib.parse import urljoin
from cache import Cache

app = FastAPI()
origin_url = ""
cache = Cache()

@app.middleware("http")
async def proxy_request(request: Request, call_next):
    path = request.url.path
    query = request.url.query
    full_url = urljoin(origin_url, path)
    if query:
        full_url += f"?{query}"

    cache_key = f"{request.method}:{full_url}"
    print("Received:", cache_key)

    if cache_key in cache:
        print("Cache HIT")
        cached = cache.get(cache_key)
        return Response(
            content=cached['content'],
            status_code=cached['status_code'],
            media_type=cached['media_type'],
            headers={"X-Cache": "HIT"}
        )

    try:
        print("Cache MISS - Forwarding to origin")
        origin_response = requests.request(
            method=request.method,
            url=full_url,
            headers={k: v for k, v in request.headers.items() if k.lower() != 'host'},
            timeout=10
        )

        content = origin_response.content
        media_type = origin_response.headers.get('Content-Type', 'text/plain')
        cache.set(cache_key, {
            'content': content,
            'status_code': origin_response.status_code,
            'media_type': media_type
        })

        return Response(
            content=content,
            status_code=origin_response.status_code,
            media_type=media_type,
            headers={"X-Cache": "MISS"}
        )
    except Exception as e:
        print("Error occurred while forwarding:", e)
        return Response(content=str(e), status_code=500)

def start_proxy_server(port: int, origin: str):
    global origin_url
    origin_url = origin
    uvicorn.run(app, host="0.0.0.0", port=port)

def clear_cache():
    cache.clear()
