from fastapi import Request

from app.core.errors import TeamsNotConfigured
from app.jobs.store import JobStore
from app.pipeline import Pipeline
from app.services.teams import TeamsClient


def get_store(request: Request) -> JobStore:
    return request.app.state.services.store


def get_pipeline(request: Request) -> Pipeline:
    return request.app.state.services.pipeline


def get_teams(request: Request) -> TeamsClient:
    teams = request.app.state.services.teams
    if teams is None:
        raise TeamsNotConfigured("Teams import is not configured, set the TEAMS_* variables in .env")
    return teams
