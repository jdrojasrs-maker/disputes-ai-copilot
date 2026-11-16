from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from disputes.models import DisputeState


class DisputeNotFoundError(Exception):
    """Raised when a dispute id has no matching dispute."""


class InvalidTransitionError(Exception):
    """Raised when a dispute cannot move to the requested state.

    `from_state` is the state the dispute is in. With `state_changed` the dispute moved
    after the caller read it, so the move may be allowed from the new state.
    """

    def __init__(
        self,
        from_state: DisputeState,
        to_state: DisputeState,
        state_changed: bool = False,
    ) -> None:
        super().__init__(from_state, to_state)
        self.from_state = from_state
        self.to_state = to_state
        self.state_changed = state_changed


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


async def invalid_transition_handler(request: Request, exc: InvalidTransitionError):
    if exc.state_changed:
        message = (
            f"The dispute changed to {exc.from_state.value} while this request was being "
            "handled; read it again and retry if the move is still wanted"
        )
    else:
        message = f"Cannot change state from {exc.from_state.value} to {exc.to_state.value}"
    body = ErrorResponse(
        error=ErrorBody(code="invalid_transition", message=message, details=[])
    )
    return JSONResponse(status_code=409, content=body.model_dump())


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
    app.add_exception_handler(InvalidTransitionError, invalid_transition_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
