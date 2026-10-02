"""Command entry point; implementation and state belong to DatabaseAccessOperator."""

from database_access import DatabaseAccessOperator


def create_operator(*, context=None):
    return DatabaseAccessOperator(context=context)


if __name__ == "__main__":
    create_operator().run()
