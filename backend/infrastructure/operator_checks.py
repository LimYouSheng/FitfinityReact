"""Fail-closed assertions shared by infrastructure reviews."""


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def one(rows, message):
    require(len(rows) == 1, message)
    return rows[0]
