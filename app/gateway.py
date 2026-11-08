"""Local reverse gateway; forwards interlock traffic to its separate process.

No model or credential logic runs here. This is not a production reverse proxy.
"""
from __future__ import annotations
import os
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

app = FastAPI(title='Sentinel simulation gateway', docs_url=None, redoc_url=None, openapi_url=None)
INTELLIGENCE_PORT = int(os.getenv('SENTINEL_INTELLIGENCE_PORT', '8000'))
INTERLOCK_PORT = int(os.getenv('SENTINEL_INTERLOCK_PORT', '8001'))

@app.api_route('/{path:path}', methods=['GET', 'POST', 'HEAD'])
async def forward(path: str, request: Request):
    is_interlock = path == 'api/interlock' or path.startswith('api/interlock/')
    port = INTERLOCK_PORT if is_interlock else INTELLIGENCE_PORT
    body = await request.body()
    if len(body) > 1_000_000:
        return JSONResponse({'detail': 'Request too large'}, status_code=413)
    url = f'http://127.0.0.1:{port}/' + path
    headers = {name: request.headers[name] for name in ('content-type', 'accept', 'x-interlock-signature') if name in request.headers}
    try:
        async with httpx.AsyncClient(timeout=65.0, trust_env=False, follow_redirects=False) as client:
            upstream = await client.request(request.method, url, params=request.query_params, content=body, headers=headers)
    except httpx.RequestError:
        return JSONResponse({'detail': 'Interlock unavailable; authorization is unknown and must be held.' if is_interlock else 'Intelligence service unavailable.'}, status_code=503, headers={'Cache-Control': 'no-store'})
    response_headers = {name: upstream.headers[name] for name in ('content-type', 'cache-control', 'location') if name in upstream.headers}
    if is_interlock:
        response_headers['Cache-Control'] = 'no-store'
    return Response(content=upstream.content, status_code=upstream.status_code, headers=response_headers)
