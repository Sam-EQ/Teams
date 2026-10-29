import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import health, jobs, teams
from app.bootstrap import build_services
from app.core.errors import register_error_handlers

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    services = await asyncio.to_thread(build_services)
    services.store.fail_interrupted()
    app.state.services = services
    yield
    await services.client.close()
    if services.teams:
        await services.teams.close()


app = FastAPI(title="Meeting Transcription API", version="2.0.0", lifespan=lifespan)
register_error_handlers(app)
app.include_router(health.router)
app.include_router(teams.router)
app.include_router(jobs.router)
