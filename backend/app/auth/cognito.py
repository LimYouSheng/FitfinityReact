"""Confidential Cognito client. Token APIs are unsigned; no runtime IAM admin powers."""

import base64
import hashlib
import hmac

import boto3
from botocore import UNSIGNED
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.auth.errors import AuthError, unavailable


class Cognito:
    def __init__(self, settings, client=None):
        self.client_id = settings.cognito_client_id
        self._secret = settings.cognito_client_secret.get_secret_value()
        self.client = client or boto3.client(
            "cognito-idp",
            region_name="ap-southeast-1",
            config=Config(
                signature_version=UNSIGNED,
                connect_timeout=2,
                read_timeout=3,
                retries={"total_max_attempts": 1},
                max_pool_connections=2,
            ),
        )

    def _hash(self, username):
        return base64.b64encode(
            hmac.new(
                self._secret.encode(), (username + self.client_id).encode(), hashlib.sha256
            ).digest()
        ).decode()

    def _call(self, operation, **params):
        try:
            return getattr(self.client, operation)(**params)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in {
                "TooManyRequestsException",
                "LimitExceededException",
                "TooManyFailedAttemptsException",
            }:
                raise AuthError(
                    "AUTH_RATE_LIMITED", "Too many attempts. Try again later.", 429
                ) from None
            if code in {
                "CodeMismatchException",
                "ExpiredCodeException",
                "EnableSoftwareTokenMFAException",
            }:
                raise AuthError("INVALID_CODE", "The code is invalid or expired.", 400) from None
            if code in {"InvalidPasswordException", "PasswordHistoryPolicyViolationException"}:
                raise AuthError(
                    "PASSWORD_POLICY",
                    "Choose a different password that meets the requirements.",
                    422,
                ) from None
            if code in {
                "NotAuthorizedException",
                "UserNotFoundException",
                "UserNotConfirmedException",
                "PasswordResetRequiredException",
            }:
                raise AuthError() from None
            raise unavailable() from None
        except BotoCoreError:
            raise unavailable() from None

    def begin(self, username, password):
        return self._call(
            "initiate_auth",
            ClientId=self.client_id,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={
                "USERNAME": username,
                "PASSWORD": password,
                "SECRET_HASH": self._hash(username),
            },
        )

    def answer(self, username, step, state, answer):
        fields = {"USERNAME": username, "SECRET_HASH": self._hash(username)}
        if step == "SOFTWARE_TOKEN_MFA":
            fields["SOFTWARE_TOKEN_MFA_CODE"] = answer
        elif step == "NEW_PASSWORD_REQUIRED":
            fields["NEW_PASSWORD"] = answer
        elif step != "MFA_SETUP":
            raise AuthError()
        return self._call(
            "respond_to_auth_challenge",
            ClientId=self.client_id,
            ChallengeName=step,
            Session=state,
            ChallengeResponses=fields,
        )

    def associate(self, state):
        return self._call("associate_software_token", Session=state)

    def verify_totp(self, state, code):
        result = self._call("verify_software_token", Session=state, UserCode=code)
        if result.get("Status") != "SUCCESS" or not result.get("Session"):
            raise AuthError("INVALID_CODE", "The code is invalid or expired.", 400)
        return result["Session"]

    def user(self, access):
        return self._call("get_user", AccessToken=access)

    def refresh(self, refresh):
        return self._call(
            "get_tokens_from_refresh_token",
            ClientId=self.client_id,
            ClientSecret=self._secret,
            RefreshToken=refresh,
        )

    def revoke(self, refresh):
        return self._call(
            "revoke_token", ClientId=self.client_id, ClientSecret=self._secret, Token=refresh
        )

    def change_password(self, access, current, proposed):
        return self._call(
            "change_password",
            AccessToken=access,
            PreviousPassword=current,
            ProposedPassword=proposed,
        )

    def forgot(self, username):
        return self._call(
            "forgot_password",
            ClientId=self.client_id,
            Username=username,
            SecretHash=self._hash(username),
        )

    def reset(self, username, code, password):
        return self._call(
            "confirm_forgot_password",
            ClientId=self.client_id,
            Username=username,
            SecretHash=self._hash(username),
            ConfirmationCode=code,
            Password=password,
        )

    def close(self):
        self.client.close()
