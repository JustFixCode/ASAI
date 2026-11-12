"""Deterministic, in-memory contract for caller-supplied historical market bars.

This module has no network, filesystem, database, catalogue, broker, or execution
capability. It does not retrieve, authenticate, validate, or claim authenticity of
market data. Provenance and adjustment status are untrusted caller assertions.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import json
import re
from typing import Any, Iterable, Literal, Mapping

from strategy.backtest import BacktestBar, BacktestConfig, BacktestResult, SMAcrossoverStrategy, run_backtest

D = Decimal
SCHEMA_VERSION = 1
RECORD_TYPE = "untrusted_offline_historical_market_dataset"
MAX_BARS = 10_000
MAX_GAP_SECONDS = 31_536_000
_SOURCE_KINDS = frozenset({"caller_supplied_historical_data", "manual_market_export", "local_fixture"})
_ADJUSTMENT_STATUSES = frozenset({"UNKNOWN", "UNADJUSTED_UNVERIFIED", "ADJUSTED_UNVERIFIED"})
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_TEXT = re.compile(r"[^\x00\r\n]{1,256}\Z")


class HistoricalDatasetError(ValueError):
    """Raised when an untrusted offline dataset is malformed or ambiguous."""


@dataclass(frozen=True)
class DatasetProvenance:
    """Opaque caller assertions; never retrieval instructions or authenticity proof."""

    source_id: str
    source_kind: str
    source_label: str
    source_reference: str
    asserted_captured_at: datetime


@dataclass(frozen=True)
class HistoricalDataset:
    """An immutable bounded single-symbol closed-bar dataset with a stable digest."""

    schema_version: int
    record_type: str
    untrusted: bool
    authenticity_verified: bool
    adjustment_status: Literal["UNKNOWN", "UNADJUSTED_UNVERIFIED", "ADJUSTED_UNVERIFIED"]
    provenance: DatasetProvenance
    symbol: str
    as_of: datetime
    bar_duration_seconds: int
    bars: tuple[BacktestBar, ...]
    gap_seconds: tuple[int, ...]
    canonical_sha256: str


@dataclass(frozen=True)
class DatasetBacktestResult:
    """Immutable dataset-bound view of the existing engine result.

    ``backtest`` remains the unmodified legacy result, while ``dataset`` and
    ``dataset_digest`` explicitly retain the caller assertions that are not
    represented by bars alone. The delegated properties keep ordinary result
    consumers compatible without implying that those assertions are authentic
    or that this wrapper proves the result was derived from the dataset.
    """

    backtest: BacktestResult
    dataset: HistoricalDataset
    dataset_digest: str

    @property
    def symbol(self) -> str:
        return self.backtest.symbol

    @property
    def orders(self) -> tuple:
        return self.backtest.orders

    @property
    def equity(self) -> tuple:
        return self.backtest.equity

    @property
    def final_cash(self) -> Decimal:
        return self.backtest.final_cash

    @property
    def final_position(self) -> Decimal:
        return self.backtest.final_position

    @property
    def final_equity(self) -> Decimal:
        return self.backtest.final_equity

    @property
    def provenance(self) -> str:
        return self.backtest.provenance

    @property
    def status(self) -> str:
        return self.backtest.status

    @property
    def warnings(self) -> tuple[str, ...]:
        return self.backtest.warnings


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _utc(value: object, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise HistoricalDatasetError(f"{label} must be an aware UTC datetime")
    return value.astimezone(timezone.utc)


def _text(value: object, label: str) -> str:
    if type(value) is not str or not _TEXT.fullmatch(value):
        raise HistoricalDatasetError(f"invalid {label}")
    return value


def _provenance(value: object) -> DatasetProvenance:
    if type(value) is not DatasetProvenance:
        raise HistoricalDatasetError("invalid provenance")
    if type(value.source_id) is not str or not _IDENTIFIER.fullmatch(value.source_id):
        raise HistoricalDatasetError("invalid source_id")
    if type(value.source_kind) is not str or value.source_kind not in _SOURCE_KINDS:
        raise HistoricalDatasetError("invalid source_kind")
    return DatasetProvenance(value.source_id, value.source_kind, _text(value.source_label, "source_label"),
                             _text(value.source_reference, "source_reference"), _utc(value.asserted_captured_at, "asserted_captured_at"))


def _bar(value: object) -> BacktestBar:
    if type(value) is not BacktestBar:
        raise HistoricalDatasetError("invalid bar")
    try:
        opened = _utc(value.open_timestamp, "bar open_timestamp")
        closed = _utc(value.close_timestamp, "bar close_timestamp")
        # BacktestBar owns exact Decimal and symbol validation; construct a fresh copy
        # so a caller cannot rely on a frozen object mutated after construction.
        return BacktestBar(opened, closed, value.symbol, value.open, value.close)
    except ValueError as exc:
        raise HistoricalDatasetError(str(exc)) from exc


def _whole_seconds(value: timedelta, label: str) -> int:
    seconds = int(value.total_seconds())
    if value != timedelta(seconds=seconds) or seconds <= 0:
        raise HistoricalDatasetError(f"{label} must be a positive whole number of seconds")
    return seconds


def _collect_bars(values: object) -> tuple[BacktestBar, ...]:
    if isinstance(values, (str, bytes)):
        raise HistoricalDatasetError("bars must be a bounded iterable")
    try:
        iterator = iter(values)  # type: ignore[arg-type]
    except TypeError as exc:
        raise HistoricalDatasetError("bars must be a bounded iterable") from exc
    collected: list[BacktestBar] = []
    for _ in range(MAX_BARS + 1):
        try:
            candidate = next(iterator)
        except StopIteration:
            break
        except Exception as exc:
            # An untrusted iterator must not leak arbitrary failures through a
            # validation boundary or be treated as a partial authentic dataset.
            raise HistoricalDatasetError("bars iterable failed during validation") from exc
        collected.append(_bar(candidate))
    if not collected or len(collected) > MAX_BARS:
        raise HistoricalDatasetError("bars must contain 1 to 10000 items")
    return tuple(collected)


def _payload(dataset: HistoricalDataset) -> dict[str, Any]:
    return {
        "schema_version": dataset.schema_version,
        "record_type": dataset.record_type,
        "untrusted": dataset.untrusted,
        "authenticity_verified": dataset.authenticity_verified,
        "adjustment_status": dataset.adjustment_status,
        "provenance": {
            "source_id": dataset.provenance.source_id,
            "source_kind": dataset.provenance.source_kind,
            "source_label": dataset.provenance.source_label,
            "source_reference": dataset.provenance.source_reference,
            "asserted_captured_at": dataset.provenance.asserted_captured_at.isoformat(),
        },
        "symbol": dataset.symbol,
        "as_of": dataset.as_of.isoformat(),
        "bar_duration_seconds": dataset.bar_duration_seconds,
        "bars": [
            {"open_timestamp": bar.open_timestamp.isoformat(), "close_timestamp": bar.close_timestamp.isoformat(),
             "symbol": bar.symbol, "open": str(bar.open), "close": str(bar.close)}
            for bar in dataset.bars
        ],
        "gap_seconds": list(dataset.gap_seconds),
    }


def _validate(dataset: object) -> HistoricalDataset:
    if type(dataset) is not HistoricalDataset:
        raise HistoricalDatasetError("invalid dataset")
    if (type(dataset.schema_version) is not int or dataset.schema_version != SCHEMA_VERSION
            or type(dataset.record_type) is not str or dataset.record_type != RECORD_TYPE):
        raise HistoricalDatasetError("invalid dataset schema")
    if type(dataset.untrusted) is not bool or dataset.untrusted is not True or type(dataset.authenticity_verified) is not bool or dataset.authenticity_verified is not False:
        raise HistoricalDatasetError("datasets must remain untrusted and unauthenticated")
    if type(dataset.adjustment_status) is not str or dataset.adjustment_status not in _ADJUSTMENT_STATUSES:
        raise HistoricalDatasetError("invalid adjustment_status")
    provenance = _provenance(dataset.provenance)
    cutoff = _utc(dataset.as_of, "as_of")
    bars = _collect_bars(dataset.bars)
    symbol = bars[0].symbol
    duration: timedelta | None = None
    previous_close: datetime | None = None
    gaps: list[int] = []
    for bar in bars:
        if bar.symbol != symbol:
            raise HistoricalDatasetError("bars must contain exactly one symbol")
        if bar.close_timestamp > cutoff:
            raise HistoricalDatasetError("bar close_timestamp is later than as_of")
        interval = bar.close_timestamp - bar.open_timestamp
        if duration is None:
            duration = interval
        elif interval != duration:
            raise HistoricalDatasetError("bars must have equal duration")
        if previous_close is not None:
            if bar.open_timestamp <= previous_close:
                raise HistoricalDatasetError("bar chronology contains duplicate or overlapping intervals")
            seconds = _whole_seconds(bar.open_timestamp - previous_close, "bar gap")
            if seconds > MAX_GAP_SECONDS:
                raise HistoricalDatasetError("bar gap exceeds maximum")
            gaps.append(seconds)
        previous_close = bar.close_timestamp
    assert duration is not None
    duration_seconds = _whole_seconds(duration, "bar duration")
    if type(dataset.symbol) is not str or dataset.symbol != symbol:
        raise HistoricalDatasetError("dataset symbol does not match bars")
    if type(dataset.bar_duration_seconds) is not int or dataset.bar_duration_seconds != duration_seconds:
        raise HistoricalDatasetError("bar_duration_seconds does not match bars")
    if type(dataset.gap_seconds) is not tuple or dataset.gap_seconds != tuple(gaps):
        raise HistoricalDatasetError("gap_seconds does not match bars")
    clean = HistoricalDataset(SCHEMA_VERSION, RECORD_TYPE, True, False, dataset.adjustment_status, provenance,
                              symbol, cutoff, duration_seconds, bars, tuple(gaps), "0" * 64)
    digest = sha256(_canonical(_payload(clean)).encode("utf-8")).hexdigest()
    if type(dataset.canonical_sha256) is not str or dataset.canonical_sha256 != digest:
        raise HistoricalDatasetError("canonical_sha256 does not match dataset")
    return HistoricalDataset(SCHEMA_VERSION, RECORD_TYPE, True, False, dataset.adjustment_status, provenance,
                             symbol, cutoff, duration_seconds, bars, tuple(gaps), digest)


def build_historical_dataset(*, provenance: DatasetProvenance, adjustment_status: str, as_of: datetime,
                             bars: Iterable[BacktestBar]) -> HistoricalDataset:
    """Build a validated immutable dataset from caller-supplied in-memory closed bars."""
    source = _provenance(provenance)
    cutoff = _utc(as_of, "as_of")
    owned_bars = _collect_bars(bars)
    if type(adjustment_status) is not str or adjustment_status not in _ADJUSTMENT_STATUSES:
        raise HistoricalDatasetError("invalid adjustment_status")
    symbol = owned_bars[0].symbol
    duration = owned_bars[0].close_timestamp - owned_bars[0].open_timestamp
    duration_seconds = _whole_seconds(duration, "bar duration")
    gaps: list[int] = []
    for index, bar in enumerate(owned_bars):
        if bar.symbol != symbol:
            raise HistoricalDatasetError("bars have mixed symbols")
        if bar.close_timestamp > cutoff:
            raise HistoricalDatasetError("bar close_timestamp is later than as_of")
        if bar.close_timestamp - bar.open_timestamp != duration:
            raise HistoricalDatasetError("bars must have equal duration")
        if index:
            previous = owned_bars[index - 1]
            if bar.open_timestamp <= previous.close_timestamp:
                raise HistoricalDatasetError("bar chronology contains duplicate or overlapping intervals")
            gap = _whole_seconds(bar.open_timestamp - previous.close_timestamp, "bar gap")
            if gap > MAX_GAP_SECONDS:
                raise HistoricalDatasetError("bar gap exceeds maximum")
            gaps.append(gap)
    gaps = tuple(gaps)
    provisional = HistoricalDataset(SCHEMA_VERSION, RECORD_TYPE, True, False, adjustment_status, source, symbol,
                                    cutoff, duration_seconds, owned_bars, gaps, "0" * 64)
    digest = sha256(_canonical(_payload(provisional)).encode("utf-8")).hexdigest()
    return _validate(HistoricalDataset(SCHEMA_VERSION, RECORD_TYPE, True, False, adjustment_status, source, symbol,
                                       cutoff, duration_seconds, owned_bars, gaps, digest))


def dataset_digest(dataset: HistoricalDataset) -> str:
    """Return the canonical reproducibility digest after revalidating every field."""
    return _validate(dataset).canonical_sha256


def to_backtest_bars(dataset: HistoricalDataset) -> tuple[BacktestBar, ...]:
    """Return owned bars suitable for ``strategy.backtest.run_backtest``."""
    return _validate(dataset).bars


def run_dataset_backtest(dataset: HistoricalDataset, strategy: SMAcrossoverStrategy,
                         config: BacktestConfig) -> DatasetBacktestResult:
    """Run the existing engine while retaining this dataset's untrusted assertions.

    The returned binding is reproducible, but cannot authenticate caller-supplied
    bars or provenance assertions.
    """
    clean = _validate(dataset)
    result = run_backtest(clean.bars, strategy, config, as_of=clean.as_of)
    return DatasetBacktestResult(result, clean, clean.canonical_sha256)


__all__ = ["SCHEMA_VERSION", "RECORD_TYPE", "MAX_BARS", "DatasetProvenance", "HistoricalDataset", "DatasetBacktestResult",
           "HistoricalDatasetError", "build_historical_dataset", "dataset_digest", "to_backtest_bars",
           "run_dataset_backtest"]
