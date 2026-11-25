from fastapi import FastAPI
from app.config import APP_ENV, validate_operational_config
from app.database import initialize_database, verify_runtime_database_role
from app.http_server import configure_http
from app.routers import auth,compliance,controls,dashboard,decision,exceptions,observability,policies,requests,rules,credit_data,risk_knowledge

validate_operational_config()
development = APP_ENV == "development"
if development:
    initialize_database()
else:
    verify_runtime_database_role()

app = FastAPI(
    title="TCS Credit Policy Intelligence API", version="2.0.0",
    docs_url="/docs" if development else None,
    redoc_url="/redoc" if development else None,
    openapi_url="/openapi.json" if development else None,
)
app.state.application_id='cpi'
configure_http(app, require_https=not development)
for router in (auth.router,requests.router,dashboard.router,compliance.router,controls.router,
               exceptions.router,policies.router,rules.router,credit_data.router,risk_knowledge.router,
               decision.router,observability.router):
    app.include_router(router)
