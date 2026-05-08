class MotorError(Exception):
    def __init__(self, message: str, code: str = "MOTOR_ERROR"):
        super().__init__(message)
        self.code = code


class AuthError(Exception):
    def __init__(self, message: str = "No autorizado", code: str = "AUTH_ERROR"):
        super().__init__(message)
        self.code = code


class ValidationError(Exception):
    def __init__(self, message: str, field: str | None = None, code: str = "VALIDATION_ERROR"):
        super().__init__(message)
        self.field = field
        self.code = code
