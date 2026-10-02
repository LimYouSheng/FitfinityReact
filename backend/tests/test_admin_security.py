"""Portable invitation and serialization checks. All provider responses are deterministic."""

from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from botocore.exceptions import ClientError, ReadTimeoutError
from pydantic import ValidationError

from app.api.staff_schemas import NewAdmin
from app.auth.errors import AuthError
from app.auth.invitations import CognitoInvitations
from app.authorization import Principal
from app.config import Settings

BODY = {
    "name": "Staff One",
    "email": "staff@example.test",
    "phone_country_code": "+65",
    "phone_number": "91234567",
    "birthday": "1990-01-02",
    "gender": "Female",
}


def test_admin_input_normalizes_contacts_and_accepts_no_role_choice():
    value = NewAdmin.model_validate(
        {**BODY, "name": " Staff One ", "email": " STAFF@EXAMPLE.TEST "}
    )
    assert value.name == "Staff One" and value.email == BODY["email"]
    assert set(value.model_dump()) == set(BODY)


@pytest.mark.parametrize(
    "patch",
    [
        {"role": "owner"},
        {"rates": {"peak": 0}},
        {"trainer_id": str(uuid4())},
        {"name": " "},
        {"name": "bad\nvalue"},
        {"email": "not-email"},
        {"phone_country_code": "65"},
        {"phone_number": "abc123456"},
        {"phone_number": "123456789012345"},
        {"birthday": "2026-02-30"},
        {"birthday": "2999-01-01"},
        {"birthday": 0},
        {"gender": "unknown"},
    ],
)
def test_admin_input_rejects_protected_fields_and_invalid_contacts(patch):
    with pytest.raises(ValidationError):
        NewAdmin.model_validate({**BODY, **patch})


def test_admin_operations_never_imply_owner_authority():
    principal = Principal(uuid4(), "Admin", "admin", None)
    principal.operations()
    with pytest.raises(AuthError) as error:
        principal.owner()
    assert error.value.status == 403
    with pytest.raises(AuthError):
        Principal(uuid4(), "Trainer", "trainer", uuid4()).operations()


def invited_settings(auth_settings):
    return Settings(
        **{
            **auth_settings.model_dump(),
            "staff_invitations_enabled": True,
            "staff_portal_url": "https://staff.example/",
        }
    )


def remote_user(user_id, **changes):
    return {
        "Username": "provider-user",
        "Enabled": True,
        "UserStatus": "FORCE_CHANGE_PASSWORD",
        "UserAttributes": [
            {"Name": k, "Value": v}
            for k, v in {
                "sub": "verified-subject",
                "custom:staff_id": str(user_id),
                "email": BODY["email"],
                "email_verified": "true",
                **changes,
            }.items()
        ],
    }


@pytest.mark.parametrize(
    "patch",
    [
        {"custom:staff_id": str(uuid4())},
        {"custom:staff_id": ""},
        {"email": "another@example.test"},
        {"email_verified": "false"},
        {"sub": ""},
    ],
)
def test_existing_remote_user_is_never_adopted_by_email_alone(patch):
    identity = uuid4()
    with pytest.raises(AuthError) as error:
        CognitoInvitations.validate(remote_user(identity, **patch), identity, BODY["email"])
    assert error.value.code == "STAFF_IDENTITY_CONFLICT"


def test_cognito_creates_suppressed_then_sends_only_after_identity_is_verified(auth_settings):
    identity, calls = uuid4(), []
    remote = remote_user(identity)

    def get(**kwargs):
        calls.append(("get", kwargs))
        if len(calls) == 1:
            raise ClientError({"Error": {"Code": "UserNotFoundException"}}, "AdminGetUser")
        return remote

    def create(**kwargs):
        calls.append(("create", kwargs))
        return {"User": {**remote, "Attributes": remote["UserAttributes"]}}

    provider = CognitoInvitations(
        invited_settings(auth_settings),
        SimpleNamespace(admin_get_user=get, admin_create_user=create),
    )
    result = provider.ensure(identity, BODY["name"], BODY["email"])
    assert result == {
        "subject": "verified-subject",
        "username": "provider-user",
        "status": "FORCE_CHANGE_PASSWORD",
    }
    assert calls[-1][1]["MessageAction"] == "SUPPRESS"
    assert calls[-1][1]["ForceAliasCreation"] is False
    assert not any("TemporaryPassword" in args for _, args in calls)
    assert provider.send(identity, BODY["email"]) is True
    assert calls[-1][1] == {
        "UserPoolId": auth_settings.cognito_pool_id,
        "Username": "provider-user",
        "MessageAction": "RESEND",
        "DesiredDeliveryMediums": ["EMAIL"],
        "ForceAliasCreation": False,
    }


def test_confirmed_account_is_not_reset_or_emailed_again(auth_settings):
    identity, remote = uuid4(), None
    remote = remote_user(identity)
    remote["UserStatus"] = "CONFIRMED"
    provider = CognitoInvitations(
        invited_settings(auth_settings), SimpleNamespace(admin_get_user=lambda **_: remote)
    )
    assert provider.send(identity, BODY["email"]) is False


@pytest.mark.parametrize("operation", ["ensure", "send"])
def test_provider_errors_do_not_leak_emails_passwords_or_aws_details(auth_settings, operation):
    def error(**_):
        raise ReadTimeoutError(endpoint_url="https://private-provider-sentinel/")

    provider = CognitoInvitations(
        invited_settings(auth_settings), SimpleNamespace(admin_get_user=error)
    )
    with pytest.raises(AuthError) as failure:
        if operation == "ensure":
            provider.ensure(uuid4(), BODY["name"], BODY["email"])
        else:
            provider.send(uuid4(), BODY["email"])
    assert failure.value.status == 503 and "sentinel" not in failure.value.message
    assert BODY["email"] not in failure.value.message


def pool_config():
    return {
        "SchemaAttributes": [
            {"Name": "custom:staff_id", "Mutable": False, "AttributeDataType": "String"}
        ],
        "AdminCreateUserConfig": {
            "AllowAdminCreateUserOnly": True,
            "InviteMessageTemplate": {
                "EmailMessage": '<a href="https://staff.example/">Open</a> {username} {####}'
            },
        },
    }


@pytest.mark.parametrize("change", ["none", "mutable", "marker", "link", "password", "signup"])
def test_invitation_config_requires_owner_only_signup_marker_and_correct_email_link(
    auth_settings, change
):
    config = pool_config()
    if change == "mutable":
        config["SchemaAttributes"][0]["Mutable"] = True
    if change == "marker":
        config["SchemaAttributes"] = []
    if change in {"link", "password"}:
        message = config["AdminCreateUserConfig"]["InviteMessageTemplate"]["EmailMessage"]
        config["AdminCreateUserConfig"]["InviteMessageTemplate"]["EmailMessage"] = message.replace(
            "https://staff.example/" if change == "link" else "{####}", "wrong"
        )
    if change == "signup":
        config["AdminCreateUserConfig"]["AllowAdminCreateUserOnly"] = False
    provider = CognitoInvitations(
        invited_settings(auth_settings),
        SimpleNamespace(describe_user_pool=lambda **_: {"UserPool": deepcopy(config)}),
    )
    if change == "none":
        provider.check_configuration()
    else:
        with pytest.raises(AuthError) as error:
            provider.check_configuration()
        assert error.value.code == "INVITATIONS_UNAVAILABLE"


@pytest.mark.parametrize(
    "url",
    [
        "",
        "http://staff.example/",
        "https://attacker.example/",
        "https://staff.example/?x=1",
        "https://staff.example/<script>",
    ],
)
def test_invitation_setting_requires_trusted_https_portal(auth_settings, url):
    with pytest.raises(ValidationError):
        Settings(
            **{
                **auth_settings.model_dump(),
                "staff_invitations_enabled": True,
                "staff_portal_url": url,
            }
        )


@pytest.mark.parametrize("role", ["owner", "admin", "trainer"])
def test_actual_directory_projection_and_response_serialization_preserve_rate_boundary(
    monkeypatch, role
):
    from datetime import date

    from app.api import directory
    from app.models.people import Trainer

    trainer = Trainer(
        id=uuid4(),
        version=1,
        name="Coach",
        status="active",
        email="coach@example.test",
        phone_country_code="+65",
        phone_number="91234567",
        birthday=date(1990, 1, 2),
        gender="Female",
        trainer_type="Personal",
        qualifications="Coach",
        public_profile=True,
        peak_rate_cents=987654,
        off_peak_rate_cents=876543,
        approve_availability=True,
        approve_session_time=True,
        approve_session_trainer=True,
        approve_weekly_schedule=True,
    )
    query_results = iter([[], [trainer], [], [], [], [], []])
    monkeypatch.setattr(directory, "bounded", lambda *args: next(query_results))
    session = SimpleNamespace(
        execute=lambda _: SimpleNamespace(all=lambda: []), scalars=lambda _: []
    )
    principal = Principal(uuid4(), "Viewer", role, trainer.id if role == "trainer" else None)
    value = directory.snapshot(session, principal).model_dump(mode="json")
    assert value["trainers"][0]["name"] == "Coach"
    if role == "admin":
        assert "peak_rate_cents" not in value["trainers"][0]
        assert "off_peak_rate_cents" not in value["trainers"][0]
        assert "987654" not in str(value) and "876543" not in str(value)
    else:
        assert value["trainers"][0]["peak_rate_cents"] == 987654
        assert value["trainers"][0]["off_peak_rate_cents"] == 876543


def test_migration_process_does_not_enable_runtime_invitation_permissions(
    auth_settings, monkeypatch
):
    from app.config import load_settings

    values = auth_settings.model_dump()
    values["auth_enabled"] = False
    monkeypatch.setenv("FITFINITY_STAFF_INVITATIONS_ENABLED", "true")
    monkeypatch.setattr("app.config.managed_values", lambda _: values)
    result = load_settings(purpose="migration")
    assert result.auth_enabled is False and result.staff_invitations_enabled is False


def test_invitation_infrastructure_keeps_immutable_marker_and_narrow_test_pool_permissions():
    import json
    from pathlib import Path

    root = Path(__file__).parents[1] / "infrastructure"
    template = json.loads((root / "cognito.json").read_text())
    pool = template["Resources"]["StaffPool"]["Properties"]
    marker = next(item for item in pool["Schema"] if item["Name"] == "staff_id")
    assert marker["Mutable"] is False and marker["Required"] is False
    app_client = template["Resources"]["StaffClient"]["Properties"]
    assert "custom:staff_id" not in app_client["WriteAttributes"]
    assert "custom:staff_id" not in app_client["ReadAttributes"]
    statement = json.loads((root / "test-staff-invitations-policy.json").read_text())["Statement"]
    assert len(statement) == 1
    assert set(statement[0]["Action"]) == {
        "cognito-idp:DescribeUserPool",
        "cognito-idp:AdminGetUser",
        "cognito-idp:AdminCreateUser",
    }
    assert statement[0]["Resource"] == (
        "arn:aws:cognito-idp:ap-southeast-1:418638389566:userpool/ap-southeast-1_La0Y3MXCj"
    )
