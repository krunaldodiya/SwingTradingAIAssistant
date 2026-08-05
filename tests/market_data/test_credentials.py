from __future__ import annotations

import pytest

from swing_trading_ai_assistant.market_data.credentials import (
    AccessToken,
    CredentialNotFoundError,
    EnvironmentAccessTokenProvider,
)


def test_access_token_never_reveals_secret_in_text_representations() -> None:
    token = AccessToken("super-secret-token")

    assert "super-secret-token" not in repr(token)
    assert "super-secret-token" not in str(token)
    assert token.reveal() == "super-secret-token"


def test_environment_provider_reads_the_configured_access_token() -> None:
    provider = EnvironmentAccessTokenProvider(
        environment={"UPSTOX_ACCESS_TOKEN": "  token-value  "}
    )

    token = provider.get_access_token()

    assert isinstance(token, AccessToken)
    assert token.reveal() == "token-value"


@pytest.mark.parametrize("environment", ({}, {"UPSTOX_ACCESS_TOKEN": "  "}))
def test_environment_provider_fails_safely_when_token_is_unavailable(
    environment: dict[str, str],
) -> None:
    provider = EnvironmentAccessTokenProvider(environment=environment)

    with pytest.raises(CredentialNotFoundError) as exc_info:
        provider.get_access_token()

    error = exc_info.value
    assert str(error) == "UPSTOX_ACCESS_TOKEN is not configured"
    assert error.__cause__ is None
    assert error.__context__ is None


def test_environment_provider_does_not_retain_a_mutable_environment_mapping() -> None:
    environment = {"UPSTOX_ACCESS_TOKEN": "first-token"}
    provider = EnvironmentAccessTokenProvider(environment=environment)
    environment["UPSTOX_ACCESS_TOKEN"] = "changed-token"  # noqa: S105 - test data

    assert provider.get_access_token().reveal() == "first-token"
