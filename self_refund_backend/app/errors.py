"""Errors raised by domain services and turned into JSON by the API layer."""


class DomainError(Exception):
    """A business rule stopped the operation.

    ``message`` is safe to show to a customer or employee; technical details
    belong in the log, not here.
    """

    def __init__(self, code, message, status=400, **extra):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.extra = extra

    def body(self):
        return {"success": False, "code": self.code, "message": self.message, **self.extra}
