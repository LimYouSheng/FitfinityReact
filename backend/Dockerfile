FROM rust:1.91.1-slim-trixie AS adapter-build
WORKDIR /adapter
ADD --checksum=sha256:d73f583f25b350af24072d0debcda9b9b44d651387685a9278c4e9f9f5c7104b https://codeload.github.com/aws/aws-lambda-web-adapter/tar.gz/dae48cbe1c2c90607df64e61e223f71710e8b894 /adapter/source.tar.gz
RUN test "$(uname -m)" = x86_64 \
    && apt-get update \
    && apt-get install -y --no-install-recommends musl-tools \
    && rm -rf /var/lib/apt/lists/* \
    && rustup target add x86_64-unknown-linux-musl \
    && tar -xzf source.tar.gz --strip-components=1 \
    && LAMBDA_RUNTIME_USER_AGENT=aws-lambda-rust/aws-lambda-adapter/1.0.1 \
       cargo build --locked --release --bin lambda-adapter --target x86_64-unknown-linux-musl

FROM python:3.12.16-slim-trixie AS application

# Refresh Debian security fixes before installing the locked Python dependencies.
# Fail the build if the critical Perl/OpenSSL fixes reviewed on 2026-09-22
# are unavailable. Other findings still require a scan of the resulting digest.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && dpkg --compare-versions "$(dpkg-query -W -f='${Version}' perl-base)" ge '5.40.1-6+deb13u1' \
    && dpkg --compare-versions "$(dpkg-query -W -f='${Version}' libssl3t64)" ge '3.5.7-1~deb13u2' \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    AWS_LWA_PORT=8080 \
    AWS_LWA_READINESS_CHECK_PATH=/health/live \
    AWS_LWA_READINESS_CHECK_HEALTHY_STATUS=200
WORKDIR /app

COPY requirements.lock /app/requirements.lock
RUN python -m pip install --no-cache-dir --require-hashes -r requirements.lock \
    && groupadd --gid 10001 fitfinity \
    && useradd --uid 10001 --gid 10001 --no-create-home fitfinity
COPY app /app/app
COPY alembic.ini /app/alembic.ini
COPY migrations /app/migrations
COPY infrastructure/read-schema.sql /app/infrastructure/read-schema.sql

USER 10001:10001
EXPOSE 8080
CMD ["python", "-m", "uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--no-access-log", "--no-proxy-headers"]

FROM application AS runtime
COPY --from=adapter-build /adapter/target/x86_64-unknown-linux-musl/release/lambda-adapter /opt/extensions/lambda-adapter
COPY --from=adapter-build /adapter/LICENSE /adapter/NOTICE /usr/share/doc/lambda-web-adapter/

FROM application AS test
ENV RUFF_CACHE_DIR=/tmp/ruff-cache
USER root
COPY requirements-test.lock /app/requirements-test.lock
RUN python -m pip install --no-cache-dir --require-hashes -r requirements-test.lock
COPY pyproject.toml /app/pyproject.toml
# Infrastructure verification reads the same Compose definition used by its caller.
COPY compose.yaml /app/compose.yaml
COPY Dockerfile /app/Dockerfile
COPY tests /app/tests
COPY scripts /app/scripts
COPY contracts /app/contracts
COPY infrastructure /app/infrastructure
USER 10001:10001
CMD ["python", "scripts/verify.py"]
