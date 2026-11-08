"""Sentinel Orbital intelligence API and built frontend, simulation only.

The interlock runs in a different process. This service has no approval routes.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv('.env')
from app import data, agents

app = FastAPI(title='Sentinel Orbital Intelligence', version='0.1.0')

@app.on_event('startup')
def startup() -> None:
    data.initialize()

@app.get('/api/health')
def health() -> dict:
    return {'status': 'ok', 'simulation': True}

@app.get('/api/overview')
def overview() -> dict:
    result = data.overview()
    result['data_mode'] = result.get('mode')
    result['mode'] = agents.model_mode()
    return result

@app.get('/api/vulnerabilities')
def vulnerabilities(q: str = Query(default='', max_length=300), characteristic: str = Query(default='', max_length=100), status: str = Query(default='', max_length=100), limit: int = Query(default=30, ge=1, le=200), offset: int = Query(default=0, ge=0)) -> dict:
    return data.list_vulnerabilities(q=q, characteristic=characteristic, status=status, limit=limit, offset=offset)

@app.get('/api/vulnerabilities/{identifier}')
def vulnerability(identifier: str) -> dict:
    record = data.get_vulnerability(identifier)
    if record is None:
        raise HTTPException(status_code=404, detail='Record not found')
    return record

@app.get('/api/momentum/{identifier}')
def momentum(identifier: str) -> dict:
    if data.get_vulnerability(identifier) is None:
        raise HTTPException(status_code=404, detail='Record not found')
    return data.get_momentum(identifier)

@app.get('/api/profiles')
def profiles():
    return data.profiles()

@app.get('/api/stats')
def statistics():
    return data.statistics()

@app.get('/api/model')
def model():
    return data.model_status()

@app.get('/api/data-quality')
def data_quality():
    return data.quality_report()

class InvestigationRequest(BaseModel):
    question: str = Field(min_length=1, max_length=3000)
    cve: Optional[str] = Field(default=None, max_length=80)

@app.post('/api/investigate')
async def investigate(request: InvestigationRequest):
    return await agents.investigate(request.question, request.cve)

DIST = Path(__file__).resolve().parent.parent / 'dist'
if (DIST / 'assets').is_dir():
    app.mount('/assets', StaticFiles(directory=DIST / 'assets'), name='assets')

@app.get('/manus-routes.json')
def route_manifest():
    manifest = DIST / 'manus-routes.json'
    if manifest.exists():
        return FileResponse(manifest, media_type='application/json')
    raise HTTPException(status_code=404, detail='Frontend not built')

@app.get('/{path:path}', include_in_schema=False)
def spa(path: str):
    if path.startswith('api/'):
        raise HTTPException(status_code=404, detail='Unknown API route')
    root = DIST.resolve()
    candidate = (DIST / path).resolve()
    if candidate.is_relative_to(root) and candidate.is_file():
        return FileResponse(candidate)
    index = DIST / 'index.html'
    if index.exists():
        return FileResponse(index)
    raise HTTPException(status_code=503, detail='Frontend not built; run npm ci && npm run build')
