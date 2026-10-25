"""Synthetic rehearsal of the operator runbook; no live AWS or new app admin powers."""

import boto3
import pytest
from botocore.exceptions import ClientError
from botocore.stub import Stubber
from sqlalchemy import select

from app.auth.errors import AuthError
from app.models.authentication import AuthAccount, AuthSession
from app.models.people import StaffIdentity, StaffUser

pytestmark = pytest.mark.database


@pytest.mark.parametrize("uncertain", [False, True])
def test_operator_recovery_preserves_identity_and_never_revives_old_authority(
    auth_service, auth_settings, fake_cognito, login, graph, uncertain
):
    """Exercise actual identity triggers/epochs; substitute only the Cognito operation."""
    signed = login()
    pending = auth_service.sign_in("owner@example.test", "initial-password-value")
    db = auth_service.db
    with db.transaction() as session:
        identity = session.scalar(
            select(StaffIdentity).where(StaffIdentity.user_id == graph["owner_id"])
        )
        bound = (
            identity.id,
            identity.user_id,
            identity.issuer,
            identity.subject,
            identity.provider_username,
        )
        session.add(AuthAccount(user_id=graph["user_id"], epoch=7))
    with db.transaction() as session:
        session.get(AuthAccount, graph["owner_id"], with_for_update=True)
        identity = session.get(StaffIdentity, bound[0], with_for_update=True)
        assert (
            identity.user_id,
            identity.issuer,
            identity.subject,
            identity.provider_username,
        ) == bound[1:]
        identity.status = "inactive"
    for operation in (
        lambda: auth_service.me(signed.session_handle),
        lambda: auth_service.refresh(signed.session_handle),
        lambda: auth_service.challenge(pending.flow_handle, code="123456"),
        lambda: auth_service.sign_in("owner@example.test", "initial-password-value"),
    ):
        with pytest.raises(AuthError):
            operation()
    # This operator-owned SDK client is deliberately separate from runtime Cognito.
    admin = boto3.client(
        "cognito-idp",
        region_name="ap-southeast-1",
        aws_access_key_id="synthetic-test-only",
        aws_secret_access_key="synthetic-test-only",
    )
    parameters = {"UserPoolId": auth_settings.cognito_pool_id, "Username": bound[4]}
    try:
        with Stubber(admin) as stub:
            stub.add_response("admin_user_global_sign_out", {}, parameters)
            if uncertain:
                stub.add_client_error(
                    "admin_delete_software_token",
                    "InternalErrorException",
                    expected_params=parameters,
                )
            else:
                stub.add_response("admin_delete_software_token", {}, parameters)
                stub.add_response(
                    "admin_get_user",
                    {
                        "Username": bound[4],
                        "Enabled": True,
                        "UserStatus": "CONFIRMED",
                        "UserAttributes": [
                            {"Name": "sub", "Value": bound[3]},
                            {"Name": "email_verified", "Value": "true"},
                        ],
                        "UserMFASettingList": [],
                    },
                    parameters,
                )
            admin.admin_user_global_sign_out(**parameters)
            if uncertain:
                with pytest.raises(ClientError):
                    admin.admin_delete_software_token(**parameters)
            else:
                admin.admin_delete_software_token(**parameters)
                remote = admin.admin_get_user(**parameters)
                attributes = {row["Name"]: row["Value"] for row in remote["UserAttributes"]}
                assert remote["Username"] == bound[4] and attributes["sub"] == bound[3]
                assert remote["Enabled"] and attributes["email_verified"] == "true"
                assert remote["UserMFASettingList"] == []
            stub.assert_no_pending_responses()
    finally:
        admin.close()
    if not uncertain:
        # Runbook release happens only after independently confirmed provider state.
        with db.transaction() as session:
            session.get(AuthAccount, graph["owner_id"], with_for_update=True)
            session.get(StaffIdentity, bound[0], with_for_update=True).status = "active"
        fake_cognito.begin_step = "MFA_SETUP"
        enrollment = auth_service.sign_in("owner@example.test", "initial-password-value")
        assert enrollment.body["challenge"] == "MFA_SETUP"
        completed = auth_service.challenge(enrollment.flow_handle, code="123456")
        assert auth_service.me(completed.session_handle).body["user"]["id"] == str(
            graph["owner_id"]
        )
    else:
        with pytest.raises(AuthError):
            auth_service.sign_in("owner@example.test", "initial-password-value")
    with pytest.raises(AuthError):
        auth_service.me(signed.session_handle)
    with pytest.raises(AuthError):
        auth_service.challenge(pending.flow_handle, code="123456")
    with db.transaction() as session:
        identity = session.get(StaffIdentity, bound[0])
        assert (
            identity.id,
            identity.user_id,
            identity.issuer,
            identity.subject,
            identity.provider_username,
        ) == bound
        assert identity.status == ("inactive" if uncertain else "active")
        assert session.get(StaffUser, graph["owner_id"]).status == "active"
        assert session.get(AuthAccount, graph["user_id"]).epoch == 7
        old = session.scalar(select(AuthSession).where(AuthSession.closed_at.is_not(None)))
        assert old.access_cipher is None and old.revoke_pending
