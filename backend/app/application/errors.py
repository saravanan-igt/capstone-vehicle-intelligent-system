from typing import Any


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, details: Any = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details


def not_found(entity: str) -> AppError:
    # Same response for "absent" and "belongs to another tenant/user" to avoid leaking existence.
    return AppError(404, "NOT_FOUND", f"{entity} not found")


def forbidden(message: str = "Not permitted") -> AppError:
    return AppError(403, "FORBIDDEN", message)


def conflict(code: str, message: str, details: Any = None) -> AppError:
    return AppError(409, code, message, details)


def unprocessable(code: str, message: str, details: Any = None) -> AppError:
    return AppError(422, code, message, details)
