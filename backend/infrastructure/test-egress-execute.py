"""Command entry point; implementation and state belong to EgressOperator."""

from egress_execution import EgressOperator


def create_operator(*, context=None):
    return EgressOperator(context=context)


if __name__ == "__main__":
    create_operator().run()
