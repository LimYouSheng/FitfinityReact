"""Command entry point; implementation and state belong to PrivateEgressOperator."""

from private_egress import PrivateEgressOperator


def create_operator(*, context=None):
    return PrivateEgressOperator(context=context)


if __name__ == "__main__":
    create_operator().run()
