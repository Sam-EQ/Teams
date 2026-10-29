from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    status_code = 500


class JobNotFound(AppError):
    status_code = 404


class JobNotReady(AppError):
    status_code = 409


class UploadTooLarge(AppError):
    status_code = 413


class InvalidMedia(AppError):
    status_code = 415


class UnknownSpeaker(AppError):
    status_code = 422


class UnknownEngine(AppError):
    status_code = 422


class MeetingNotFound(AppError):
    status_code = 404


class RecordingNotReady(AppError):
    status_code = 409


class TeamsError(AppError):
    status_code = 502


class TeamsNotConfigured(AppError):
    status_code = 503


def register_error_handlers(app: FastAPI):
    @app.exception_handler(AppError)
    async def handle(request: Request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})
