"""Real S3-compatible IO on the owned Docker service, never an AWS endpoint."""

import os
from contextlib import contextmanager
from uuid import uuid4

import boto3
import pytest
from botocore.config import Config

from app.media_storage import MediaStorage


@contextmanager
def isolated_media(public_endpoint=None):
    endpoint = os.getenv("FITFINITY_TEST_MEDIA_ENDPOINT")
    if endpoint != "http://test-media:9000":
        raise RuntimeError("Media tests require the isolated Docker test-media service")
    if public_endpoint not in {None, endpoint, "http://127.0.0.1:4181"}:
        raise RuntimeError("Media signatures require the isolated browser storage endpoint")
    options = dict(
        region_name="us-east-1",
        aws_access_key_id="fitfinity-isolated-test",
        aws_secret_access_key="fitfinity-isolated-test-not-an-aws-secret",
        config=Config(
            signature_version="s3v4",
            proxies={},  # Only this fixed internal Compose hostname bypasses the external proxy.
            retries={"total_max_attempts": 1},
            s3={"addressing_style": "path"},
        ),
    )
    client = boto3.client("s3", endpoint_url=endpoint, **options)
    signing = (
        boto3.client("s3", endpoint_url=public_endpoint, **options)
        if public_endpoint and public_endpoint != endpoint
        else client
    )
    bucket = "fitfinity-test-" + uuid4().hex
    client.create_bucket(Bucket=bucket)
    store = MediaStorage(client, signing)
    try:
        client.put_bucket_cors(
            Bucket=bucket,
            CORSConfiguration={
                "CORSRules": [
                    {
                        "AllowedOrigins": ["http://127.0.0.1:4180"],
                        "AllowedMethods": ["GET", "PUT", "HEAD"],
                        "AllowedHeaders": [
                            "content-type",
                            "x-amz-checksum-sha256",
                            "if-none-match",
                            # Playwright adds this synthetic routing header to every request.
                            "x-fitfinity-browser-worker",
                        ],
                        "ExposeHeaders": ["Content-Length", "Content-Type", "Cache-Control"],
                    }
                ]
            },
        )
        yield store, bucket
    finally:
        for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket):
            for item in page.get("Contents", []):
                client.delete_object(Bucket=bucket, Key=item["Key"])
        client.delete_bucket(Bucket=bucket)
        store.close()


@pytest.fixture
def media_store():
    with isolated_media() as value:
        yield value
