import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("app")


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, details=None):
        self.status, self.code, self.message, self.details = status, code, message, details


def bad_request(msg, code="bad_request", details=None):
    return AppError(400, code, msg, details)


def unauthorized(msg="Not authenticated"):
    return AppError(401, "unauthorized", msg)


def forbidden(msg="You do not have permission to do that"):
    return AppError(403, "forbidden", msg)


def not_found(what="Resource"):
    return AppError(404, "not_found", f"{what} not found")


def conflict(msg, code="conflict", details=None):
    return AppError(409, code, msg, details)


def _body(code, message, details=None):
    return {"error": {"code": code, "message": message, "details": details}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, e: AppError):
        return JSONResponse(_body(e.code, e.message, e.details), status_code=e.status)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, e: StarletteHTTPException):
        return JSONResponse(_body("http_error", str(e.detail)), status_code=e.status_code, headers=e.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, e: RequestValidationError):
        details = [
            {"field": ".".join(str(p) for p in err["loc"] if p != "body"), "message": err["msg"]}
            for err in e.errors()
        ]
        return JSONResponse(_body("validation_error", "Invalid request", details), status_code=422)

    @app.exception_handler(IntegrityError)
    async def _integrity(_: Request, e: IntegrityError):
        log.warning("integrity error: %s", e.orig)
        return JSONResponse(_body("conflict", "Conflicts with existing data (duplicate or referenced)"), status_code=409)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, e: Exception):
        log.exception("unhandled error")
        return JSONResponse(_body("internal_error", "Something went wrong"), status_code=500)
