"""Fail-closed assertions shared by infrastructure reviews."""


class OperatorCheckError(RuntimeError):
    """A source-authored validation message safe for operational receipts."""


def require(ok, message):
    if not ok:
        raise OperatorCheckError(message)


def one(rows, message):
    require(len(rows) == 1, message)
    return rows[0]
