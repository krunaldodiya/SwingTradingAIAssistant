import pytest
from credentials_fixture import TEST_API, TEST_CLIENT, TEST_MPIN, TEST_TOTP

from swing_trading_ai_assistant.portfolio.angel_one import (
    AngelOneClient,
    AngelOneCredentials,
)
from swing_trading_ai_assistant.portfolio.brokers import (
    SUPPORTED_BROKERS,
    BrokerAdapter,
    BrokerConnector,
    adapter_for,
    open_connector,
)
from swing_trading_ai_assistant.portfolio.errors import PortfolioError


def test_only_angel_one_is_registered() -> None:
    assert {"ANGEL_ONE"} == SUPPORTED_BROKERS
    assert adapter_for("ANGEL_ONE").credential_suffixes == (
        "API_KEY",
        "CLIENT_CODE",
        "PIN",
        "TOTP_SECRET",
    )


def test_unsupported_broker_fails_closed() -> None:
    with pytest.raises(PortfolioError) as error:
        open_connector("UPSTOX", "UPSTOX_MAIN")
    assert error.value.code == "BROKER_UNSUPPORTED"


def test_adapter_verify_and_credential_names() -> None:
    class FakeClient:
        authenticated_client_code = None

        def __init__(self) -> None:
            self.logged_in = False

        def login(self) -> None:
            self.logged_in = True

    client = FakeClient()
    adapter = BrokerAdapter(
        broker="TEST",
        credential_suffixes=("API_KEY", "CLIENT_CODE"),
        open=lambda prefix, environ: ("IDENTITY", client),
    )
    assert adapter.verify("PREFIX") == "IDENTITY"
    assert client.logged_in
    assert adapter.missing_credentials("PREFIX", {}) == (
        "PREFIX_API_KEY",
        "PREFIX_CLIENT_CODE",
    )


def test_angel_one_satisfies_the_connector_protocol() -> None:
    client = AngelOneClient(
        AngelOneCredentials(
            api_key=TEST_API,
            client_code=TEST_CLIENT,
            pin=TEST_MPIN,
            totp_secret=TEST_TOTP,
        ),
        environ={},
    )
    assert isinstance(client, BrokerConnector)
    assert client.broker == "ANGEL_ONE"
    assert client.capabilities == frozenset(
        {"holdings", "positions", "orders", "trades", "gtt"}
    )
