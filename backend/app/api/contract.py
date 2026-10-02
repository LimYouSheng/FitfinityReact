"""Offline reproducible OpenAPI generation/checking; never opens DB or provider connections."""

import argparse
import base64
import json
from pathlib import Path

from fastapi.openapi.models import OpenAPI

from app.config import Settings

SNAPSHOT = Path(__file__).parents[2] / "contracts/openapi.json"


def generate_contract():
    from app.main import create_app

    settings = Settings(
        _env_file=None,
        environment="test",
        database_url="postgresql+psycopg://contract:contract@127.0.0.1:1/contract_not_connected",
        auth_enabled=True,
        cognito_pool_id="ap-southeast-1_Contract",
        cognito_client_id="contractclient",
        cognito_client_secret="contract_test_secret_not_deployed",
        auth_encryption_keys=[base64.urlsafe_b64encode(bytes(range(32))).decode()],
        auth_origins=["https://staff.example.test"],
        auth_cookie_secure=True,
        root_path="",
        allowed_hosts=["testserver"],
    )
    app = create_app(settings)  # Composition only; no ASGI lifespan/startup.
    schema = app.openapi()
    validate_contract(schema)
    return schema


def validate_contract(schema):
    OpenAPI.model_validate(schema)
    operations = []
    for methods in schema["paths"].values():
        for method, operation in methods.items():
            if method not in {"get", "post"}:
                continue
            operations.append(operation["operationId"])
            assert operation.get("description") and operation.get("tags")
            assert operation["responses"]["200"]["content"]["application/json"]["schema"]
            for code, response in operation["responses"].items():
                if int(code) >= 400:
                    assert response["content"]["application/json"]["schema"] == {
                        "$ref": "#/components/schemas/ErrorEnvelope"
                    }
    assert len(operations) == len(set(operations))

    def references(value):
        if isinstance(value, dict):
            if "$ref" in value:
                ref = value["$ref"]
                assert ref.startswith("#/components/schemas/"), ref
                assert ref.rsplit("/", 1)[-1] in schema["components"]["schemas"], ref
            for item in value.values():
                references(item)
        elif isinstance(value, list):
            for item in value:
                references(item)

    references(schema)


def encode(schema):
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def check_contract(schema, snapshot=SNAPSHOT):
    validate_contract(schema)
    if encode(schema) != snapshot.read_text():
        raise ValueError(
            "OpenAPI contract changed. Review compatibility and regenerate "
            "the canonical snapshot explicitly."
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("/tmp/fitfinity-openapi.json"))
    args = parser.parse_args()
    schema = generate_contract()
    check_contract(schema)
    args.output.write_text(encode(schema))
    operations = sum(len(methods) for methods in schema["paths"].values())
    print(
        f"\033[32mPASS — {operations} typed OpenAPI operations; "
        "safe errors, resolved references and exact reviewed contract.\033[0m"
    )


if __name__ == "__main__":
    main()
