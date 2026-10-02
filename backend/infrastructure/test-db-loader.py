"""Accept only the hash-pinned bootstrap source through a private Lambda Invoke."""

import hashlib
import json
import re
import sys

import uvicorn
from fastapi import FastAPI, Request

SOURCE_SHA256 = None
app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)


@app.get("/health/live")
def health():
    return {"status": "ok"}


@app.post("/events")
async def run(request: Request):
    nonce = None
    try:
        raw = await request.body()
        if len(raw) > 49152:
            raise ValueError("envelope size")
        event = json.loads(raw)
        candidate = event.get("nonce")
        if isinstance(candidate, str) and re.fullmatch(r"[a-f0-9]{32}", candidate):
            nonce = candidate
        source = event.pop("bootstrap_source").encode("utf-8")
        if len(source) > 32768 or hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
            raise ValueError("source verification")
        body = json.dumps(event).encode()
        if len(body) > 256:
            raise ValueError("request size")

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        namespace = {"__name__": "fitfinity_db_bootstrap"}
        exec(compile(source, "fitfinity_db_bootstrap", "exec"), namespace)
        return await namespace["run"](Request(request.scope, receive))
    except Exception as error:
        return {
            "ok": False,
            "nonce": nonce,
            "stage": "bootstrap_transport",
            "error_type": type(error).__name__,
            "sqlstate": None,
        }


if __name__ == "__main__":
    SOURCE_SHA256 = sys.argv[1]
    uvicorn.run(
        app, host="0.0.0.0", port=8080, access_log=False, log_level="error", proxy_headers=False
    )
