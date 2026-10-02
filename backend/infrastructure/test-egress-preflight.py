"""Command entry point; implementation and state belong to EgressPreflightOperator."""

from egress_preflight import EgressPreflightOperator


def create_operator(*, context=None):
    return EgressPreflightOperator(context=context)


if __name__ == "__main__":
    create_operator().run()
