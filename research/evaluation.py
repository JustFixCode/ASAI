"""Offline deterministic evaluation of caller-supplied backtest evidence.

This research-only module consumes an already-produced ``BacktestResult``. It
has no market-data, filesystem, network, credentials, broker, execution, or
control capability. Its evidence gate is not trading approval and makes no
claim that supplied data is authentic or that results are profitable.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
import hashlib
import json

from strategy.backtest import BacktestResult, EquityPoint, HistoricalOrder

D = Decimal
_MAX_POINTS = 10_000
_MAX_ORDERS = 10_000
_MAX_ABS_VALUE = D("1000000000")
_MAX_DECIMAL_PLACES = 18
_PRECISION = 100
_MAX_TEXT_LENGTH = 512
_ORDER_STATUSES = frozenset({"FILLED", "REJECTED_INSUFFICIENT_CASH", "REJECTED_POSITION_LIMIT", "REJECTED_NEGATIVE_CASH", "UNFILLED_END_OF_DATA"})
_RESULT_STATUSES = frozenset({"COMPLETED", "COMPLETED_WITH_REJECTIONS", "COMPLETED_WITH_UNFILLED", "COMPLETED_WITH_REJECTIONS_AND_UNFILLED"})


class EvaluationInputError(ValueError):
    """Raised for malformed, tampered, or ambiguous backtest evidence."""


@dataclass(frozen=True)
class _DatasetBinding:
    """Validated untrusted dataset assertions included in an evaluation hash."""

    digest: str
    adjustment_status: str
    provenance: tuple[str, str, str, str, str]


def _timestamp(value: object, name: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise EvaluationInputError(f"{name} must be an aware UTC datetime")
    return value.astimezone(timezone.utc)


def _number(value: object, name: str, *, nonnegative: bool = False) -> Decimal:
    if type(value) is not Decimal or not value.is_finite() or value.as_tuple().exponent < -_MAX_DECIMAL_PLACES or abs(value) > _MAX_ABS_VALUE:
        raise EvaluationInputError(f"invalid {name}")
    if nonnegative and value < 0:
        raise EvaluationInputError(f"invalid {name}")
    return value


def _decimal_math(operation, name: str) -> Decimal:
    try:
        with localcontext() as context:
            context.prec = _PRECISION
            # Return and drawdown divisions can be non-terminating. Do not
            # inherit a caller's rounding mode when making them reproducible.
            context.rounding = ROUND_HALF_EVEN
            value = operation()
    except (InvalidOperation, OverflowError, ValueError, ZeroDivisionError) as exc:
        raise EvaluationInputError(f"invalid {name} arithmetic") from exc
    if not value.is_finite() or abs(value) > _MAX_ABS_VALUE:
        raise EvaluationInputError(f"invalid {name} arithmetic")
    return value


def _text(value: object, name: str) -> str:
    if type(value) is not str or not value or len(value) > _MAX_TEXT_LENGTH or "\x00" in value or "\n" in value or "\r" in value:
        raise EvaluationInputError(f"invalid {name}")
    return value


def _expected_status(orders: tuple[HistoricalOrder, ...]) -> str:
    rejected = any(order.status.startswith("REJECTED_") for order in orders)
    unfilled = any(order.status == "UNFILLED_END_OF_DATA" for order in orders)
    return "COMPLETED_WITH_REJECTIONS_AND_UNFILLED" if rejected and unfilled else "COMPLETED_WITH_REJECTIONS" if rejected else "COMPLETED_WITH_UNFILLED" if unfilled else "COMPLETED"


@dataclass(frozen=True)
class EvidenceThresholds:
    """Explicit caller-selected research criteria; none authorizes trading."""

    min_equity_points: int
    min_filled_orders: int
    min_total_return: Decimal
    max_drawdown: Decimal

    def __post_init__(self) -> None:
        if type(self.min_equity_points) is not int or not (1 <= self.min_equity_points <= _MAX_POINTS):
            raise EvaluationInputError("invalid min_equity_points")
        if type(self.min_filled_orders) is not int or not (0 <= self.min_filled_orders <= _MAX_ORDERS):
            raise EvaluationInputError("invalid min_filled_orders")
        _number(self.min_total_return, "min_total_return")
        drawdown = _number(self.max_drawdown, "max_drawdown", nonnegative=True)
        if drawdown > D("1"):
            raise EvaluationInputError("invalid max_drawdown")


@dataclass(frozen=True)
class BacktestEvidenceStats:
    equity_points: int
    filled_orders: int
    rejected_orders: int
    unfilled_orders: int
    start_equity: Decimal
    final_equity: Decimal
    total_return: Decimal | None
    max_drawdown: Decimal | None


@dataclass(frozen=True)
class EvidenceEvaluation:
    """A reproducible research finding, never an execution decision."""

    as_of: datetime
    source_provenance: str
    evaluation_hash: str
    stats: BacktestEvidenceStats
    classification: str
    unmet_criteria: tuple[str, ...]
    warnings: tuple[str, ...]


def _settings(value: object) -> EvidenceThresholds:
    if type(value) is not EvidenceThresholds:
        raise EvaluationInputError("invalid thresholds")
    return EvidenceThresholds(value.min_equity_points, value.min_filled_orders, value.min_total_return, value.max_drawdown)


def _result(value: object, as_of: datetime) -> tuple[BacktestResult, tuple[EquityPoint, ...], tuple[HistoricalOrder, ...], _DatasetBinding | None]:
    # Import lazily so ordinary legacy BacktestResult callers keep the original
    # evaluator interface without creating a module-level dependency cycle.
    from research.historical_dataset import DatasetBacktestResult, HistoricalDatasetError, dataset_digest

    binding: _DatasetBinding | None = None
    dataset = None
    if type(value) is DatasetBacktestResult:
        try:
            actual_digest = dataset_digest(value.dataset)
        except HistoricalDatasetError as exc:
            raise EvaluationInputError("invalid dataset-bound result") from exc
        if type(value.dataset_digest) is not str or value.dataset_digest != actual_digest:
            raise EvaluationInputError("dataset digest does not match dataset-bound result")
        dataset = value.dataset
        binding = _DatasetBinding(actual_digest, dataset.adjustment_status,
                                  (dataset.provenance.source_id, dataset.provenance.source_kind,
                                   dataset.provenance.source_label, dataset.provenance.source_reference,
                                   dataset.provenance.asserted_captured_at.isoformat()))
        value = value.backtest
    if type(value) is not BacktestResult:
        raise EvaluationInputError("invalid backtest result")
    if type(value.symbol) is not str or not value.symbol or len(value.symbol) > _MAX_TEXT_LENGTH:
        raise EvaluationInputError("invalid result symbol")
    if type(value.provenance) is not str or len(value.provenance) != 64 or any(char not in "0123456789abcdef" for char in value.provenance):
        raise EvaluationInputError("invalid result provenance")
    if type(value.equity) is not tuple or not value.equity or len(value.equity) > _MAX_POINTS:
        raise EvaluationInputError("equity must contain 1 to 10000 points")
    if type(value.orders) is not tuple or len(value.orders) > _MAX_ORDERS:
        raise EvaluationInputError("invalid orders")

    points: list[EquityPoint] = []
    previous: datetime | None = None
    for point in value.equity:
        if type(point) is not EquityPoint:
            raise EvaluationInputError("invalid equity point")
        timestamp = _timestamp(point.timestamp, "equity timestamp")
        if timestamp > as_of:
            raise EvaluationInputError("equity timestamp is after as_of")
        if previous is not None and timestamp <= previous:
            raise EvaluationInputError("equity timestamps must be strictly chronological")
        cash = _number(point.cash, "equity cash")
        position = _number(point.position, "equity position", nonnegative=True)
        close = _number(point.close, "equity close", nonnegative=True)
        equity = _number(point.equity, "equity value")
        expected = _decimal_math(lambda: cash + position * close, "equity value")
        if equity != expected:
            raise EvaluationInputError("equity point is internally inconsistent")
        points.append(EquityPoint(timestamp, cash, position, close, equity))
        previous = timestamp

    observation_times = {point.timestamp for point in points}
    orders: list[HistoricalOrder] = []
    execution_times: list[datetime] = []
    for order in value.orders:
        if type(order) is not HistoricalOrder:
            raise EvaluationInputError("invalid order")
        signal = _timestamp(order.signal_timestamp, "order signal timestamp")
        if signal > as_of:
            raise EvaluationInputError("order signal timestamp is after as_of")
        if signal not in observation_times:
            raise EvaluationInputError("order signal timestamp is not an equity observation")
        if type(order.side) is not str or type(order.status) is not str or order.side not in ("BUY", "SELL") or order.status not in _ORDER_STATUSES:
            raise EvaluationInputError("invalid order")
        quantity = _number(order.quantity, "order quantity", nonnegative=True)
        if quantity <= 0:
            raise EvaluationInputError("invalid order quantity")
        reason = _text(order.reason, "order reason")
        if order.status == "UNFILLED_END_OF_DATA":
            if order.fill_timestamp is not None or order.fill_price is not None or order.fee is not None:
                raise EvaluationInputError("unfilled order has fill fields")
            orders.append(HistoricalOrder(signal, None, order.side, quantity, order.status, None, None, reason))
            continue
        if order.status == "REJECTED_POSITION_LIMIT":
            # This is rejected before a fill is attempted, so the engine has no
            # execution timestamp, price, or fee to report.
            if order.fill_timestamp is not None or order.fill_price is not None or order.fee is not None:
                raise EvaluationInputError("position-limit rejection has fill fields")
            orders.append(HistoricalOrder(signal, None, order.side, quantity, order.status, None, None, reason))
            continue
        # Filled orders and cash-related rejected execution attempts carry the
        # documented later open, attempted price, and fee.
        if order.fill_timestamp is None or order.fill_price is None or order.fee is None:
            raise EvaluationInputError("executed order is missing fill fields")
        fill = _timestamp(order.fill_timestamp, "order fill timestamp")
        if fill <= signal or fill > as_of:
            raise EvaluationInputError("executed order timestamps are invalid")
        price = _number(order.fill_price, "order fill price", nonnegative=True)
        fee = _number(order.fee, "order fee", nonnegative=True)
        if price <= 0:
            raise EvaluationInputError("invalid order fill price")
        execution_times.append(fill)
        orders.append(HistoricalOrder(signal, fill, order.side, quantity, order.status, price, fee, reason))

    if execution_times and max(execution_times) > points[-1].timestamp:
        raise EvaluationInputError("order execution is after final equity observation")
    final = points[-1]
    if (_number(value.final_cash, "final cash") != final.cash or _number(value.final_position, "final position", nonnegative=True) != final.position or _number(value.final_equity, "final equity") != final.equity):
        raise EvaluationInputError("final result fields do not match final equity")
    normalized_orders = tuple(orders)
    if type(value.status) is not str or value.status not in _RESULT_STATUSES or value.status != _expected_status(normalized_orders):
        raise EvaluationInputError("result status does not match orders")
    if type(value.warnings) is not tuple:
        raise EvaluationInputError("invalid result warnings")
    source_warnings = tuple(_text(warning, "result warning") for warning in value.warnings)
    source = BacktestResult(value.symbol, normalized_orders, tuple(points), final.cash, final.position, final.equity,
                            value.provenance, value.status, source_warnings)
    if dataset is not None:
        if source.symbol != dataset.symbol:
            raise EvaluationInputError("dataset-bound result symbol does not match dataset")
        if dataset.as_of > as_of:
            raise EvaluationInputError("dataset as_of is after evaluation as_of")
        if len(points) != len(dataset.bars):
            raise EvaluationInputError("dataset-bound result has dropped or extra equity observations")
        for point, bar in zip(points, dataset.bars, strict=True):
            if point.timestamp != bar.close_timestamp:
                raise EvaluationInputError("dataset-bound equity timestamp does not match dataset bar")
            if point.close != bar.close:
                raise EvaluationInputError("dataset-bound equity close does not match dataset bar")
        bar_opens = {bar.open_timestamp for bar in dataset.bars}
        for order in normalized_orders:
            if order.fill_timestamp is not None and order.fill_timestamp not in bar_opens:
                raise EvaluationInputError("dataset-bound order fill timestamp does not match dataset bar")
    return source, tuple(points), normalized_orders, binding


def _digest(result: BacktestResult, points: tuple[EquityPoint, ...], orders: tuple[HistoricalOrder, ...], thresholds: EvidenceThresholds, as_of: datetime, dataset_binding: _DatasetBinding | None) -> str:
    payload = {
        "engine": "offline-backtest-evidence-v1", "as_of": as_of.isoformat(), "symbol": result.symbol,
        "source_provenance": result.provenance, "result_status": result.status, "result_warnings": list(result.warnings),
        "dataset_binding": None if dataset_binding is None else {
            "digest": dataset_binding.digest, "adjustment_status": dataset_binding.adjustment_status,
            "provenance_assertions": list(dataset_binding.provenance),
        },
        "thresholds": [thresholds.min_equity_points, thresholds.min_filled_orders, str(thresholds.min_total_return), str(thresholds.max_drawdown)],
        "equity": [[point.timestamp.isoformat(), str(point.cash), str(point.position), str(point.close), str(point.equity)] for point in points],
        "orders": [[order.signal_timestamp.isoformat(), order.fill_timestamp.isoformat() if order.fill_timestamp else None, order.side, str(order.quantity), order.status, str(order.fill_price) if order.fill_price is not None else None, str(order.fee) if order.fee is not None else None, order.reason] for order in orders],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")).hexdigest()


def evaluate_backtest(result: BacktestResult, thresholds: EvidenceThresholds, *, as_of: datetime) -> EvidenceEvaluation:
    """Evaluate supplied historical evidence at an explicit UTC cutoff.

    Point-in-time checks reject equity or order facts after ``as_of`` and reject
    order executions that are not strictly later than their signals. A passing
    result only means stated research thresholds were met; it is never approval
    to trade, a profitability claim, or validation of caller-supplied data.
    """
    cutoff = _timestamp(as_of, "as_of")
    settings = _settings(thresholds)
    source, points, orders, dataset_binding = _result(result, cutoff)
    start, final = points[0].equity, points[-1].equity
    final_timestamp = points[-1].timestamp
    total_return: Decimal | None = None
    drawdown: Decimal | None = None
    warnings = ["Caller-supplied backtest data and provenance are unverified; this is not evidence of authentic data or profitability.", "Research-only evidence evaluation; it has no execution or trading authority.", "start_equity is the first recorded equity observation, not a verified initial-capital value."]
    if final_timestamp < cutoff:
        warnings.append("The final equity observation predates as_of; this is a stale historical report at the requested cutoff.")
    if source.warnings:
        warnings.append("The supplied backtest reports limitations; those caller-supplied limitations are included in the evaluation hash and do not establish authentic or continuous history.")
    if dataset_binding is not None:
        warnings.append("The evaluation hash binds the supplied dataset digest, adjustment status, and provenance assertions; they remain unverified. The wrapper cannot authenticate the dataset and cannot prove that caller-supplied result values were derived from it.")
    if start <= 0 or any(point.equity <= 0 for point in points):
        warnings.append("Return and drawdown are not applicable because supplied equity is zero or negative.")
    elif len(points) < 2:
        warnings.append("Return and drawdown are not applicable with fewer than two equity observations; zero drawdown would not be meaningful.")
    else:
        total_return = _decimal_math(lambda: (final - start) / start, "total return")
        peak = points[0].equity
        drawdowns = []
        for point in points:
            peak = max(peak, point.equity)
            drawdowns.append(_decimal_math(lambda point=point, peak=peak: (peak - point.equity) / peak, "drawdown"))
        drawdown = max(drawdowns)
    filled = sum(order.status == "FILLED" for order in orders)
    rejected = sum(order.status.startswith("REJECTED_") for order in orders)
    unfilled = sum(order.status == "UNFILLED_END_OF_DATA" for order in orders)
    stats = BacktestEvidenceStats(len(points), filled, rejected, unfilled, start, final, total_return, drawdown)
    unmet: list[str] = []
    insufficient = False
    if len(points) < settings.min_equity_points:
        unmet.append("min_equity_points")
        insufficient = True
    if filled < settings.min_filled_orders:
        unmet.append("min_filled_orders")
        insufficient = True
    if total_return is None or drawdown is None:
        unmet.append("positive_equity_required_for_return_and_drawdown")
        insufficient = True
    if not insufficient:
        if total_return < settings.min_total_return:
            unmet.append("min_total_return")
        if drawdown > settings.max_drawdown:
            unmet.append("max_drawdown")
    classification = "INSUFFICIENT_EVIDENCE" if insufficient else "RESEARCH_EVIDENCE_MET" if not unmet else "RESEARCH_EVIDENCE_NOT_MET"
    return EvidenceEvaluation(cutoff, source.provenance, _digest(source, points, orders, settings, cutoff, dataset_binding), stats, classification, tuple(unmet), tuple(warnings))
