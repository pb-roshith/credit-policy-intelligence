"""Dedicated Data Manufacturing API, sharing CPI identity and data services."""
import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager

CPI_BACKEND=Path(__file__).resolve().parents[2]/'cpi_server'/'backend'
sys.path.insert(0,str(CPI_BACKEND))
from fastapi import FastAPI
from app.database import initialize_database
from app.http_server import configure_http
from app.routers import auth,requests
from app.manufacture_data import credit_requests,exposure_history,policy_controls,policy_pdfs


@asynccontextmanager
async def lifespan(app):
    try:yield
    finally:policy_pdfs.shutdown_policy_workers()


def create_app(initialize=True):
    if initialize:initialize_database()
    application=FastAPI(title='TCS Data Manufacturing API',version='1.0.0',lifespan=lifespan)
    application.state.application_id='dm'
    origins=[value.strip().rstrip('/') for value in os.getenv('DM_CORS_ORIGINS','http://localhost:5174,http://127.0.0.1:5174').split(',') if value.strip()]
    configure_http(application,cors_origins=origins)
    for router in (auth.router,credit_requests.router,exposure_history.router,policy_controls.router,policy_pdfs.router):
        application.include_router(router)
    application.add_api_route('/api/requests',requests.credit_requests,methods=['GET'])
    @application.get('/api/health')
    def health():return {'status':'ok','service':'data-manufacturing'}
    return application


app=create_app()
