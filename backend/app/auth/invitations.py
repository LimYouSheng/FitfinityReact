"""Narrow signed Cognito provisioning; no password/token ever enters an API response."""

from html import escape

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.auth.errors import AuthError


class CognitoInvitations:
    def __init__(self, settings, client=None):
        self.settings = settings
        self.client = client

    def _call(self, operation, **values):
        if self.client is None:
            self.client = boto3.client(
                "cognito-idp",
                region_name="ap-southeast-1",
                endpoint_url="https://cognito-idp.ap-southeast-1.amazonaws.com",
                verify=True,
                config=Config(
                    connect_timeout=2,
                    read_timeout=3,
                    retries={"total_max_attempts": 1},
                    max_pool_connections=2,
                ),
            )
        return getattr(self.client, operation)(UserPoolId=self.settings.cognito_pool_id, **values)

    def check_configuration(self):
        """No invitation before its pool schema and actual email link are configured."""
        try:
            pool = self._call("describe_user_pool")["UserPool"]
            marker = next(
                (a for a in pool.get("SchemaAttributes", []) if a.get("Name") == "custom:staff_id"),
                {},
            )
            config = pool.get("AdminCreateUserConfig", {})
            message = config.get("InviteMessageTemplate", {}).get("EmailMessage", "")
            if (
                marker.get("Mutable") is not False
                or marker.get("AttributeDataType") != "String"
                or config.get("AllowAdminCreateUserOnly") is not True
                or f'href="{escape(self.settings.staff_portal_url, quote=True)}"' not in message
                or "{username}" not in message
                or "{####}" not in message
            ):
                raise ValueError("Invalid invitation configuration")
        except (BotoCoreError, ClientError, KeyError, ValueError, TypeError):
            raise AuthError(
                "INVITATIONS_UNAVAILABLE", "Staff invitations are not ready. Contact support.", 503
            ) from None

    @staticmethod
    def validate(remote, user_id, email):
        attributes = {
            a["Name"]: a["Value"]
            for a in remote.get("UserAttributes", remote.get("Attributes", []))
        }
        if (
            attributes.get("custom:staff_id") != str(user_id)
            or attributes.get("email") != email
            or attributes.get("email_verified") != "true"
            or not attributes.get("sub")
            or not remote.get("Username")
            or remote.get("Enabled") is not True
        ):
            raise AuthError(
                "STAFF_IDENTITY_CONFLICT",
                "This email cannot be linked automatically. Contact support.",
                409,
            )
        return {
            "subject": attributes["sub"],
            "username": remote["Username"],
            "status": remote.get("UserStatus"),
        }

    def ensure(self, user_id, name, email):
        try:
            try:
                remote = self._call("admin_get_user", Username=email)
            except ClientError as error:
                if error.response.get("Error", {}).get("Code") != "UserNotFoundException":
                    raise
                remote = self._call(
                    "admin_create_user",
                    Username=email,
                    MessageAction="SUPPRESS",
                    ForceAliasCreation=False,
                    DesiredDeliveryMediums=["EMAIL"],
                    UserAttributes=[
                        {"Name": "email", "Value": email},
                        {"Name": "email_verified", "Value": "true"},
                        {"Name": "name", "Value": name},
                        {"Name": "custom:staff_id", "Value": str(user_id)},
                    ],
                )["User"]
            return self.validate(remote, user_id, email)
        except (BotoCoreError, ClientError, KeyError, TypeError):
            raise AuthError(
                "INVITATION_RETRY", "Account setup is incomplete. Retry with the same details.", 503
            ) from None

    def send(self, user_id, email):
        # A previously completed account must never have its credentials reset by a retry.
        try:
            remote = self._call("admin_get_user", Username=email)
            identity = self.validate(remote, user_id, email)
            if identity["status"] != "FORCE_CHANGE_PASSWORD":
                return False
            self._call(
                "admin_create_user",
                Username=identity["username"],
                MessageAction="RESEND",
                DesiredDeliveryMediums=["EMAIL"],
                ForceAliasCreation=False,
            )
            return True
        except (BotoCoreError, ClientError, KeyError, TypeError):
            raise AuthError(
                "INVITATION_DELIVERY_UNKNOWN", "Invitation delivery could not be confirmed.", 503
            ) from None

    def close(self):
        if self.client is not None:
            self.client.close()
