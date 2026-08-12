"""Point-in-time Nifty 50 admission for vendor-neutral public workflows."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

from .instruments import Instrument
from .universe_snapshot import Nifty50ConstituentV1, Nifty50UniverseSnapshotV1

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class EquityAdmissionPolicyV1(Protocol):
    """Small common boundary shared by preview and Nifty 50 workflows."""

    def admits(self, segment: object, symbol: object) -> bool: ...

    def admits_instrument(self, instrument: Instrument) -> bool: ...


@dataclass(frozen=True, slots=True)
class Nifty50AdmissionPolicyV1:
    """Bind selected historical aliases to exact point-in-time member ISINs."""

    universe_snapshot_sha256: str
    universe: Nifty50UniverseSnapshotV1
    selected_symbols: tuple[str, ...] | None = None
    _selected: tuple[Nifty50ConstituentV1, ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if (
            type(self.universe_snapshot_sha256) is not str
            or _DIGEST.fullmatch(self.universe_snapshot_sha256) is None
            or type(self.universe) is not Nifty50UniverseSnapshotV1
            or (
                self.selected_symbols is not None
                and (
                    type(self.selected_symbols) is not tuple
                    or not self.selected_symbols
                    or len(self.selected_symbols) > 50
                    or any(type(value) is not str for value in self.selected_symbols)
                    or len(set(self.selected_symbols)) != len(self.selected_symbols)
                )
            )
        ):
            raise ValueError("invalid Nifty 50 admission policy")
        requested = (
            {member.symbol for member in self.universe.constituents}
            if self.selected_symbols is None
            else set(self.selected_symbols)
        )
        selected = tuple(
            member
            for member in self.universe.constituents
            if member.symbol in requested
        )
        if len(selected) != len(requested):
            raise ValueError("selected symbol is not in the point-in-time Nifty 50")
        object.__setattr__(self, "_selected", selected)

    @property
    def ordered_symbols(self) -> tuple[str, ...]:
        """Return one deterministic ISIN-ordered execution list."""
        return tuple(member.symbol for member in self._selected)

    def admits(self, segment: object, symbol: object) -> bool:
        return (
            type(segment) is str
            and type(symbol) is str
            and segment == "NSE_EQ"
            and any(member.symbol == symbol for member in self._selected)
        )

    def admits_instrument(self, instrument: Instrument) -> bool:
        if type(instrument) is not Instrument:
            return False
        return any(
            instrument.segment == "NSE_EQ"
            and instrument.exchange == "NSE"
            and instrument.instrument_type == "EQ"
            and instrument.symbol == member.symbol
            and instrument.isin == member.isin
            for member in self._selected
        )
