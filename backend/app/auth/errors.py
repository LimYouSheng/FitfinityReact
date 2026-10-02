"""Safe public authentication failures; provider details and credentials never escape."""


class AuthError(Exception):
    def __init__(self, code="AUTH_FAILED", message="Sign-in could not be completed.", status=401):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def expired():
    return AuthError("SESSION_EXPIRED", "Your session has ended. Sign in again.")


def unavailable():
    return AuthError("AUTH_UNAVAILABLE", "Authentication is temporarily unavailable.", 503)


def busy():
    return AuthError("AUTH_BUSY", "An authentication operation is in progress. Try again.", 409)
