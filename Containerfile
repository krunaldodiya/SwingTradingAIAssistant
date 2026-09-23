# Linux x86_64 local distribution. The build context contains only the exact
# application wheel and uv.lock-exported, hash-checked runtime requirements.
FROM python:3.11.16-slim-bookworm@sha256:4b4c524dc3dce996864e030c7bd9c6b0e517597189fee48f48e05b499442444b AS builder

COPY --from=ghcr.io/astral-sh/uv:0.9.24@sha256:e4bc0bb4310505e7104f06430c0a2271a58f60a756a3b2c287bb409890081b2a /uv /bin/uv
COPY requirements.txt /tmp/requirements.txt
COPY *.whl /tmp/

ARG APP_VERSION
ARG WHEEL_SHA256
RUN set -- /tmp/*.whl && \
    test "$#" -eq 1 && \
    if [ "$(sha256sum "$1" | cut -d ' ' -f 1)" != "$WHEEL_SHA256" ]; then echo "wheel digest mismatch" >&2; exit 1; fi && \
    export UV_LINK_MODE=copy && \
    uv venv --python /usr/local/bin/python /opt/app && \
    uv pip install --python /opt/app/bin/python --require-hashes -r /tmp/requirements.txt && \
    uv pip install --python /opt/app/bin/python --no-deps /tmp/*.whl && \
    /opt/app/bin/python -c "from importlib.metadata import version; assert version('swing-trading-ai-assistant') == '$APP_VERSION'" && \
    /opt/app/bin/market-data --help >/dev/null

FROM python:3.11.16-slim-bookworm@sha256:4b4c524dc3dce996864e030c7bd9c6b0e517597189fee48f48e05b499442444b

ARG APP_VERSION
ARG SOURCE_REVISION
ARG WHEEL_SHA256
ARG REQUIREMENTS_SHA256
LABEL org.opencontainers.image.title="SwingTradingAIAssistant" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${SOURCE_REVISION}" \
      org.opencontainers.image.source="https://github.com/krunaldodiya/SwingTradingAIAssistant" \
      org.swingtradingaiassistant.wheel.sha256="${WHEEL_SHA256}" \
      org.swingtradingaiassistant.requirements.sha256="${REQUIREMENTS_SHA256}"

RUN groupadd --gid 10001 app && \
    useradd --uid 10001 --gid app --create-home --home-dir /home/app app
COPY --from=builder /opt/app /opt/app

ENV PATH="/opt/app/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /home/app
USER 10001:10001
ENTRYPOINT ["market-data"]
