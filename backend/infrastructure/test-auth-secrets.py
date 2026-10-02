"""Command entry point; implementation and state belong to AuthenticationSecretOperator."""

from authentication_secrets import AuthenticationSecretOperator


def create_operator(*, context=None):
    return AuthenticationSecretOperator(context=context)


if __name__ == "__main__":
    create_operator().run()
