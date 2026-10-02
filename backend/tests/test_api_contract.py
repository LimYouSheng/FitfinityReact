"""Offline contract, safe transport and authorization boundaries without provider/network access."""

from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.contract import check_contract, generate_contract, validate_contract
from app.api.schemas import NewAssessment, SaveAssessment
from app.main import create_app


def test_generated_openapi_matches_reviewed_snapshot_without_network(monkeypatch):
    import socket

    def blocked(*args, **kwargs):
        raise AssertionError("Schema generation must not access the network")

    monkeypatch.setattr(socket, "create_connection", blocked)
    schema = generate_contract()
    check_contract(schema)
    assert len(schema["paths"]) == 26
    assert sum(len(methods) for methods in schema["paths"].values()) == 28
    assert schema["paths"]["/auth/session"]["get"]["security"] == [{"StaffSession": []}]
    for path, methods in schema["paths"].items():
        for method, operation in methods.items():
            if path.startswith("/api/"):
                expected = {"StaffSession": []}
                if method == "post":
                    expected["SessionCSRF"] = []
                assert operation["security"] == [expected]
                if method == "post":
                    assert any(
                        p["name"] == "Idempotency-Key" and p["required"]
                        for p in operation["parameters"]
                    )
    assert (
        schema["components"]["securitySchemes"]["StaffSession"]["name"]
        == "__Host-fitfinity-session"
    )
    assert "HTTPValidationError" not in schema["components"]["schemas"]


@pytest.mark.parametrize("mutation", ["remove_route", "response", "security", "required_field"])
def test_contract_gate_rejects_unreviewed_breaks(mutation):
    schema = deepcopy(generate_contract())
    if mutation == "remove_route":
        del schema["paths"]["/api/clients"]
    elif mutation == "response":
        schema["components"]["schemas"]["ClientSummary"]["properties"]["version"] = {
            "type": "string"
        }
    elif mutation == "security":
        schema["paths"]["/api/clients"]["get"]["security"] = []
    else:
        schema["components"]["schemas"]["NewAssessment"]["required"].append("invented")
    with pytest.raises(ValueError, match="contract changed"):
        check_contract(schema)


def test_contract_validation_rejects_dangling_refs_and_duplicate_operation_ids():
    schema = generate_contract()
    schema["paths"]["/api/clock"]["get"]["operationId"] = "listClients"
    with pytest.raises(AssertionError):
        validate_contract(schema)
    schema = generate_contract()
    schema["paths"]["/api/clock"]["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ] = {"$ref": "#/components/schemas/Missing"}
    with pytest.raises(AssertionError):
        validate_contract(schema)


@pytest.mark.parametrize(
    "path",
    [
        "/api/clock",
        "/api/directory",
        f"/api/sessions/{uuid4()}/client",
        "/api/clients",
        "/api/trainers",
        "/api/sessions",
        "/api/assessment-forms",
        f"/api/people/{uuid4()}/assessments",
        f"/api/assessments/{uuid4()}",
    ],
)
def test_all_staff_routes_require_an_actual_session(auth_settings, path):
    with TestClient(create_app(auth_settings)) as client:
        response = client.get(path, headers={"X-Role": "owner", "X-User-ID": "owner"})
        assert response.status_code == 401
        assert response.headers["cache-control"] == "no-store"
        assert set(response.json()) == {"error"}
        assert response.json()["error"]["requestId"] == response.headers["x-request-id"]


@pytest.mark.parametrize(
    "headers,content,status",
    [
        ({"Origin": "https://evil.example", "Content-Type": "application/json"}, "{}", 403),
        ({"Origin": "https://staff.example", "Content-Type": "text/plain"}, "{}", 415),
        (
            {
                "Origin": "https://staff.example",
                "Content-Type": "application/json",
                "Authorization": "Bearer fake",
            },
            "{}",
            401,
        ),
        (
            [
                ("Origin", "https://staff.example"),
                ("Content-Type", "application/json"),
                ("Idempotency-Key", str(uuid4())),
                ("Idempotency-Key", str(uuid4())),
            ],
            "{}",
            400,
        ),
        (
            {"Origin": "https://staff.example", "Content-Type": "application/json"},
            '{"secret":"' + "x" * 131073 + '"}',
            413,
        ),
    ],
)
def test_domain_transport_rejects_ambiguous_cross_origin_and_oversized_requests(
    auth_settings, headers, content, status
):
    with TestClient(create_app(auth_settings)) as client:
        response = client.post(
            f"/api/people/{uuid4()}/assessments", content=content, headers=headers
        )
        assert response.status_code == status
        assert "secret" not in response.text and "Bearer fake" not in response.text


@pytest.mark.parametrize(
    "patch",
    [
        {"actorId": str(uuid4())},
        {"assessor": "Forged"},
        {"assessmentDate": "2000-01-01"},
        {"formVersion": True},
        {"expectedPersonVersion": "1"},
        {"answers": {"eyes_open_1": False}},
    ],
)
def test_assessment_inputs_forbid_authority_headers_and_coercion(patch):
    with pytest.raises(ValidationError):
        NewAssessment.model_validate(
            {
                "formId": "balance",
                "formVersion": 1,
                "expectedPersonVersion": 1,
                "answers": {"eyes_open_1": 0},
                **patch,
            }
        )
    with pytest.raises(ValidationError):
        SaveAssessment.model_validate({"expectedVersion": 0, "answers": {}, "event": "draft"})


def test_private_contract_endpoints_stay_off_in_production_and_auth_off(settings, auth_settings):
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/clients").status_code == 404
    deployed = auth_settings.model_copy(update={"environment": "production"})
    with TestClient(create_app(deployed)) as client:
        assert client.get("/openapi.json").status_code == 404
        assert client.get("/docs").status_code == 404
    app = create_app(auth_settings.model_copy(update={"root_path": "/staff-api"}))
    with TestClient(app) as client:
        assert client.get("/staff-api/api/clients").status_code == 401
