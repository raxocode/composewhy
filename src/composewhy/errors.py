"""Error classes and exit codes for ComposeWhy."""

class ComposeWhyExitCode:
    EXPLAINED = 0
    USAGE_ERROR = 2
    UNSUPPORTED_OR_UNKNOWN = 3
    INPUT_ERROR = 4
    DOCKER_ERROR = 5
    INTERNAL_ERROR = 6


class ComposeWhyError(Exception):
    """Base class for user-facing, sanitized ComposeWhy errors."""
    def __init__(self, message: str, exit_code: int = ComposeWhyExitCode.INPUT_ERROR):
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code


class UsageError(ComposeWhyError):
    def __init__(self, message: str):
        super().__init__(message, exit_code=ComposeWhyExitCode.USAGE_ERROR)


class InputError(ComposeWhyError):
    def __init__(self, message: str):
        super().__init__(message, exit_code=ComposeWhyExitCode.INPUT_ERROR)


class DockerError(ComposeWhyError):
    def __init__(self, message: str):
        super().__init__(message, exit_code=ComposeWhyExitCode.DOCKER_ERROR)


class UnsupportedError(ComposeWhyError):
    def __init__(self, message: str, reason_code: str = "UNSUPPORTED_COMPOSE_FEATURE"):
        super().__init__(message, exit_code=ComposeWhyExitCode.UNSUPPORTED_OR_UNKNOWN)
        self.reason_code = reason_code
