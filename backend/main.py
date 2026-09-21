import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.database import initialize_database
from app.routers import auth, compliance, controls, dashboard, decision, exceptions, observability, policies, requests
from app.manufacture_data import credit_requests, exposure_history, policy_controls, policy_pdfs

initialize_database()

app = FastAPI(title="TCS Credit Policy Intelligence API", version="2.0.0")
logger = logging.getLogger("credit_policy_intelligence")
GENERIC_ERROR_MESSAGE = "An unexpected error occurred. Please try again later."


@app.exception_handler(HTTPException)
async def safe_http_exception_handler(_: Request, error: HTTPException):
    if error.status_code >= 500:
        logger.error("Server request failed with status %s", error.status_code, exc_info=error)
        return JSONResponse(
            status_code=error.status_code,
            content={"detail": GENERIC_ERROR_MESSAGE},
            headers=error.headers,
        )
    return JSONResponse(
        status_code=error.status_code,
        content={"detail": error.detail},
        headers=error.headers,
    )


@app.exception_handler(Exception)
async def safe_unhandled_exception_handler(request: Request, error: Exception):
    logger.exception("Unhandled error while processing %s %s", request.method, request.url.path, exc_info=error)
    return JSONResponse(status_code=500, content={"detail": GENERIC_ERROR_MESSAGE})

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (
    auth.router,
    requests.router,
    dashboard.router,
    compliance.router,
    credit_requests.router,
    exposure_history.router,
    policy_controls.router,
    policy_pdfs.router,
    controls.router,
    exceptions.router,
    policies.router,
    decision.router,
    observability.router,
):
    app.include_router(router)
