FROM python:3.12.14-slim-trixie AS runtime

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
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:1.0.1 /lambda-adapter /opt/extensions/lambda-adapter
COPY app /app/app
COPY alembic.ini /app/alembic.ini
COPY migrations /app/migrations

USER 10001:10001
EXPOSE 8080
CMD ["python", "-m", "uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--no-access-log", "--no-proxy-headers"]

FROM runtime AS test
ENV RUFF_CACHE_DIR=/tmp/ruff-cache
USER root
COPY requirements-test.lock /app/requirements-test.lock
RUN python -m pip install --no-cache-dir --require-hashes -r requirements-test.lock
COPY pyproject.toml /app/pyproject.toml
# Infrastructure verification reads the same Compose definition used by its caller.
COPY compose.yaml /app/compose.yaml
COPY tests /app/tests
COPY scripts /app/scripts
COPY contracts /app/contracts
COPY infrastructure /app/infrastructure
USER 10001:10001
CMD ["python", "scripts/verify.py"]
