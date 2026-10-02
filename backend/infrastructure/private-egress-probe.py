"Fixed HTTPS-only connectivity probe. No credentials, database calls or input URLs."

import http.client
import json


def read_https(host, path, limit):
    connection = http.client.HTTPSConnection(host, timeout=8)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        if response.status != 200:
            raise RuntimeError("Unexpected HTTPS status")
        body = response.read(limit + 1)
        if len(body) > limit:
            raise RuntimeError("Response too large")
        return body
    finally:
        connection.close()


def handler(event, context):
    keys = json.loads(
        read_https(
            "cognito-idp.ap-southeast-1.amazonaws.com",
            "/ap-southeast-1_La0Y3MXCj/.well-known/jwks.json",
            131072,
        )
    )["keys"]
    if not isinstance(keys, list) or not 1 <= len(keys) <= 8:
        raise RuntimeError("Invalid JWKS")
    address = read_https("checkip.amazonaws.com", "/", 128).decode("ascii").strip()
    if address != "52.77.93.192":
        raise RuntimeError("Egress address differs from accepted NAT")
    return {"https_verified": True, "jwks_key_count": len(keys), "egress_ip": address}
