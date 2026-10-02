"""Command entry point; implementation and state belong to DatabaseMigrationOperator."""

from database_migrations import DatabaseMigrationOperator


def create_operator(*, context=None):
    return DatabaseMigrationOperator(context=context)


if __name__ == "__main__":
    create_operator().run()
