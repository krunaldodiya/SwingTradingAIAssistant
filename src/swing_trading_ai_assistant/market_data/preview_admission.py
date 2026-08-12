"""Product-owned admission policy for the first public preview."""

from __future__ import annotations

from dataclasses import dataclass

from .instruments import Instrument


@dataclass(frozen=True, slots=True)
class PreviewAdmissionPolicyV1:
    """Admit only the explicitly frozen first-preview instrument."""

    segment: str
    symbol: str

    def __post_init__(self) -> None:
        if type(self.segment) is not str or type(self.symbol) is not str:
            raise ValueError("invalid preview admission policy")
        if (self.segment, self.symbol) != ("NSE_EQ", "RELIANCE"):
            raise ValueError("unsupported preview admission policy")

    def admits(self, segment: object, symbol: object) -> bool:
        """Return whether an exact public identity is admitted."""
        return (
            type(segment) is str
            and type(symbol) is str
            and (
                segment,
                symbol,
            )
            == (self.segment, self.symbol)
        )

    def admits_instrument(self, instrument: Instrument) -> bool:
        """Confirm provider resolution retained the admitted equity identity."""
        return (
            type(instrument) is Instrument
            and instrument.segment == self.segment
            and instrument.symbol == self.symbol
            and instrument.instrument_type == "EQ"
            and instrument.exchange == "NSE"
            and instrument.isin is not None
        )
