from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException


class DisputeNotFoundError(Exception):
    """Raised when a dispute id has no matching dispute."""


class ErrorDetail(BaseModel):
    field: str
    message: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail]


class ErrorResponse(BaseModel):
    error: ErrorBody


def _field_name(error: dict) -> str:
    """Drop the leading 'body' or 'path' part; use 'body' if nothing is left.

    Malformed JSON is reported with the character position as location, so it is
    mapped to 'body' directly.
    """
    if error["type"] == "json_invalid":
        return "body"
    location = error["loc"]
    parts = [str(part) for part in location if part not in ("body", "path", "query")]
    return ".".join(parts) if parts else "body"


async def validation_error_handler(request: Request, exc: RequestValidationError):
    details = [
        ErrorDetail(field=_field_name(error), message=error["msg"])
        for error in exc.errors()
    ]
    body = ErrorResponse(
        error=ErrorBody(
            code="validation_error",
            message="Request validation failed",
            details=details,
        )
    )
    return JSONResponse(status_code=422, content=body.model_dump())


async def not_found_handler(request: Request, exc: DisputeNotFoundError):
    body = ErrorResponse(
        error=ErrorBody(code="not_found", message="Dispute not found", details=[])
    )
    return JSONResponse(status_code=404, content=body.model_dump())


HTTP_ERROR_CODES = {404: "not_found", 405: "method_not_allowed"}


async def http_error_handler(request: Request, exc: StarletteHTTPException):
    """Wrap the framework's own HTTP errors (unknown route, wrong method)."""
    body = ErrorResponse(
        error=ErrorBody(
            code=HTTP_ERROR_CODES.get(exc.status_code, "http_error"),
            message=str(exc.detail),
            details=[],
        )
    )
    return JSONResponse(
        status_code=exc.status_code, content=body.model_dump(), headers=exc.headers
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(DisputeNotFoundError, not_found_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
