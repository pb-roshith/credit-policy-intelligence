from fastapi import FastAPI
from contextlib import asynccontextmanager
import asyncio
from app.database import initialize_database
from app.scripts.map_policy_relationships import map_policy_relationships
from app.http_server import configure_http
from app.routers import auth,compliance,controls,dashboard,decision,exceptions,observability,policies,requests,rules,credit_data,risk_knowledge

initialize_database()
from app.services.policy_knowledge_package import autoload_package
autoload_package()
map_policy_relationships()

@asynccontextmanager
async def lifespan(application):
    from app.services.policy_knowledge_auto_export import create_auto_exporter
    exporter = create_auto_exporter()
    application.state.knowledge_auto_exporter = exporter
    if exporter:
        exporter.start()
    try:
        yield
    finally:
        if exporter:
            await asyncio.to_thread(exporter.stop)


app=FastAPI(title="TCS Credit Policy Intelligence API",version="2.0.0",lifespan=lifespan)
app.state.application_id='cpi'
configure_http(app)
for router in (auth.router,requests.router,dashboard.router,compliance.router,controls.router,
               exceptions.router,policies.router,rules.router,credit_data.router,risk_knowledge.router,
               decision.router,observability.router):
    app.include_router(router)
