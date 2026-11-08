"""Separate simulated interlock service, bound to loopback by the launcher.

This service is not a real safety control and never sends physical commands.
"""
from dotenv import load_dotenv
from fastapi import FastAPI

# Interlock secrets belong here, never in the agent service's .env file.
load_dotenv('.env.interlock')
from app.interlock import router

app = FastAPI(title="Sentinel simulated interlock service")
app.include_router(router)

@app.get('/health')
def health():
    return {'status': 'ok', 'simulation': True}
