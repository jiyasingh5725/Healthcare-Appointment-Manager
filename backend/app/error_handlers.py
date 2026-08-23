import logging
from typing import Any, Dict
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("healthcare_manager.errors")

STATUS_CODE_ERROR_MAP: Dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "BAD_REQUEST",
    status.HTTP_401_UNAUTHORIZED: "UNAUTHORIZED",
    status.HTTP_403_FORBIDDEN: "FORBIDDEN",
    status.HTTP_404_NOT_FOUND: "NOT_FOUND",
    status.HTTP_409_CONFLICT: "CONFLICT",
    status.HTTP_422_UNPROCESSABLE_ENTITY: "VALIDATION_ERROR",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "INTERNAL_SERVER_ERROR",
}


def register_error_handlers(app: FastAPI) -> None:
    """
    Registers centralized error handlers for the FastAPI application.
    Standardized response envelope across 400, 401, 403, 404, 409, 422, 500:
    {
        "success": false,
        "message": "...",
        "error_code": "..."
    }
    """

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        default_code = STATUS_CODE_ERROR_MAP.get(exc.status_code, "ERROR")
        detail = exc.detail
        headers = getattr(exc, "headers", None)

        if isinstance(detail, dict):
            error_code = detail.get("error_code") or detail.get("code") or default_code
            message = detail.get("message") or detail.get("detail") or "Request failed."
        elif isinstance(detail, str):
            # Check if string itself is a custom error code
            if detail in ("SLOT_ALREADY_BOOKED", "EMAIL_ALREADY_EXISTS", "INVALID_CREDENTIALS", "UNAUTHORIZED", "FORBIDDEN", "NOT_FOUND"):
                error_code = detail
                message = detail.replace("_", " ").capitalize()
            elif exc.status_code == status.HTTP_409_CONFLICT and "already booked" in detail.lower():
                error_code = "SLOT_ALREADY_BOOKED"
                message = detail
            else:
                error_code = default_code
                message = detail
        else:
            error_code = default_code
            message = str(detail) if detail else "An error occurred."

        payload = {
            "success": False,
            "message": message,
            "error_code": error_code,
            "detail": message  # Backward compatibility alias
        }

        return JSONResponse(
            status_code=exc.status_code,
            content=payload,
            headers=headers
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        error_msgs = []
        for err in errors:
            loc = " -> ".join([str(p) for p in err.get("loc", []) if p != "body"])
            msg = err.get("msg", "Invalid value")
            if loc:
                error_msgs.append(f"{loc}: {msg}")
            else:
                error_msgs.append(msg)

        summary_msg = "; ".join(error_msgs) if error_msgs else "Input validation failed."

        payload = {
            "success": False,
            "message": summary_msg,
            "error_code": "VALIDATION_ERROR",
            "detail": summary_msg
        }

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=payload
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # Log unhandled exceptions without leaking credentials
        logger.error(f"Unhandled server exception on {request.method} {request.url.path}: {str(exc)}", exc_info=True)

        payload = {
            "success": False,
            "message": "An internal server error occurred. Please try again later.",
            "error_code": "INTERNAL_SERVER_ERROR",
            "detail": "An internal server error occurred."
        }

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=payload
        )
