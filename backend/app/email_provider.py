"""One SES submission per durable attempt; ambiguous responses must not auto-resend."""

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError


class DeliveryFailure(Exception):
    """Expose a non-sensitive category, never provider responses or recipient addresses."""

    def __init__(self, state, code):
        super().__init__(code)
        self.state, self.code = state, code


class SesEmail:
    def __init__(self, region, sender, configuration_set="", client=None):
        self.region, self.sender = region, sender
        self.configuration_set, self.client = configuration_set, client

    def send(self, recipient, content, delivery_id):
        """Return SES acceptance evidence, not a claim that the recipient received it."""
        if self.client is None:
            self.client = boto3.client(
                "sesv2",
                region_name=self.region,
                config=Config(
                    connect_timeout=2,
                    read_timeout=5,
                    retries={"total_max_attempts": 1},
                    max_pool_connections=1,
                ),
            )
        request = {
            "FromEmailAddress": self.sender,
            "Destination": {"ToAddresses": [recipient]},
            "Content": {
                "Simple": {
                    "Subject": {"Data": content.subject, "Charset": "UTF-8"},
                    "Body": {"Text": {"Data": content.text, "Charset": "UTF-8"}},
                }
            },
            "EmailTags": [{"Name": "delivery_id", "Value": str(delivery_id)}],
        }
        if self.configuration_set:
            request["ConfigurationSetName"] = self.configuration_set
        try:
            result = self.client.send_email(**request)
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code", "")
            if code in {"TooManyRequestsException", "ThrottlingException"}:
                raise DeliveryFailure("retry", "ses_throttled") from None
            status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)
            if 400 <= status < 500:
                raise DeliveryFailure("failed", "ses_rejected") from None
            raise DeliveryFailure("unknown", "ses_response_uncertain") from None
        except BotoCoreError:
            raise DeliveryFailure("unknown", "ses_transport_uncertain") from None
        identity = result.get("MessageId")
        if not isinstance(identity, str) or not identity:
            raise DeliveryFailure("unknown", "ses_acceptance_missing")
        return identity

    def close(self):
        if self.client is not None:
            self.client.close()
