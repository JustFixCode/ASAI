"""Deterministic, offline walk-forward evaluation for caller-supplied point-in-time data.

This module is research-only. It has no networking, model downloads, trading,
strategy, risk, broker, or order authority. The only model is an explicit
training-target mean baseline; it is not a claim of an ML implementation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
import hashlib
import json
from typing import Iterable

D = Decimal
_MAX_ROWS = 10_000
_MAX_WINDOWS = 1_000
_MAX_ABS_VALUE = D("1000000000")
_MAX_DECIMAL_PLACES = 18
_PRECISION = 80


class WalkForwardInputError(ValueError):
    """Raised for ambiguous, malformed, or unsafe offline research inputs."""


def _timestamp(value: object, name: str) -> datetime:
    # Exact type avoids invoking caller-defined datetime subclass behavior.
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise WalkForwardInputError(f"{name} must be an aware UTC datetime")
    return value.astimezone(timezone.utc)


def _number(value: object, name: str) -> Decimal:
    if type(value) is not Decimal or not value.is_finite() or value.as_tuple().exponent < -_MAX_DECIMAL_PLACES or abs(value) > _MAX_ABS_VALUE:
        raise WalkForwardInputError(f"invalid {name}")
    return value


@dataclass(frozen=True)
class PointInTimeObservation:
    """A feature known at ``feature_timestamp`` and a later realized outcome."""

    feature_timestamp: datetime
    target_timestamp: datetime
    feature: Decimal
    target: Decimal

    def __post_init__(self) -> None:
        if _timestamp(self.feature_timestamp, "feature_timestamp") >= _timestamp(self.target_timestamp, "target_timestamp"):
            raise WalkForwardInputError("feature_timestamp must precede target_timestamp")
        _number(self.feature, "feature")
        _number(self.target, "target")


@dataclass(frozen=True)
class WalkForwardConfig:
    """Expanding-window settings; ``purge_observations`` removes recent rows first."""

    initial_train_size: int
    test_size: int
    purge_observations: int = 0
    max_windows: int = _MAX_WINDOWS

    def __post_init__(self) -> None:
        if type(self.initial_train_size) is not int or not (2 <= self.initial_train_size <= _MAX_ROWS):
            raise WalkForwardInputError("invalid initial_train_size")
        if type(self.test_size) is not int or not (1 <= self.test_size <= _MAX_ROWS):
            raise WalkForwardInputError("invalid test_size")
        if type(self.purge_observations) is not int or not (0 <= self.purge_observations < _MAX_ROWS):
            raise WalkForwardInputError("invalid purge_observations")
        if type(self.max_windows) is not int or not (1 <= self.max_windows <= _MAX_WINDOWS):
            raise WalkForwardInputError("invalid max_windows")


@dataclass(frozen=True)
class BaselinePrediction:
    feature_timestamp: datetime
    target_timestamp: datetime
    prediction: Decimal
    actual: Decimal


@dataclass(frozen=True)
class OutOfSampleMetrics:
    count: int
    mean_absolute_error: Decimal
    root_mean_squared_error: Decimal
    mean_error: Decimal


@dataclass(frozen=True)
class WalkForwardWindow:
    train_feature_start: datetime
    train_feature_end: datetime
    test_feature_start: datetime
    test_feature_end: datetime
    train_size: int
    configured_purged_count: int
    temporal_purged_count: int
    baseline_mean: Decimal
    predictions: tuple[BaselinePrediction, ...]
    metrics: OutOfSampleMetrics


@dataclass(frozen=True)
class WalkForwardResult:
    as_of: datetime
    windows: tuple[WalkForwardWindow, ...]
    out_of_sample: tuple[BaselinePrediction, ...]
    metrics: OutOfSampleMetrics
    provenance: str
    model: str
    warnings: tuple[str, ...]


def _validate_config(config: object) -> WalkForwardConfig:
    if type(config) is not WalkForwardConfig:
        raise WalkForwardInputError("invalid configuration")
    return WalkForwardConfig(config.initial_train_size, config.test_size, config.purge_observations, config.max_windows)


def _collect(observations: Iterable[PointInTimeObservation], as_of: datetime) -> tuple[PointInTimeObservation, ...]:
    # Do not run arbitrary caller-controlled iterators in this offline evaluator.
    if type(observations) not in (tuple, list):
        raise WalkForwardInputError("observations must be a built-in tuple or list")
    supplied = tuple(observations)
    if len(supplied) > _MAX_ROWS or not supplied:
        raise WalkForwardInputError("observations must contain 1 to 10000 items")
    normalized: list[PointInTimeObservation] = []
    last_feature: datetime | None = None
    last_target: datetime | None = None
    for row in supplied:
        if type(row) is not PointInTimeObservation:
            raise WalkForwardInputError("invalid observation")
        feature_time = _timestamp(row.feature_timestamp, "feature_timestamp")
        target_time = _timestamp(row.target_timestamp, "target_timestamp")
        if feature_time >= target_time:
            raise WalkForwardInputError("feature_timestamp must precede target_timestamp")
        if target_time > as_of:
            raise WalkForwardInputError("target_timestamp is after as_of")
        if last_feature is not None and feature_time <= last_feature:
            raise WalkForwardInputError("feature timestamps must be strictly chronological")
        if last_target is not None and target_time <= last_target:
            raise WalkForwardInputError("target timestamps must be strictly chronological")
        normalized.append(PointInTimeObservation(feature_time, target_time, _number(row.feature, "feature"), _number(row.target, "target")))
        last_feature, last_target = feature_time, target_time
    return tuple(normalized)


def _mean(rows: tuple[PointInTimeObservation, ...]) -> Decimal:
    try:
        with localcontext() as context:
            context.prec = _PRECISION
            context.rounding = ROUND_HALF_EVEN
            result = sum((item.target for item in rows), D("0")) / D(len(rows))
    except (InvalidOperation, OverflowError) as exc:
        raise WalkForwardInputError("invalid baseline arithmetic") from exc
    if not result.is_finite() or abs(result) > _MAX_ABS_VALUE:
        raise WalkForwardInputError("invalid baseline arithmetic")
    return result


def _metrics(predictions: tuple[BaselinePrediction, ...]) -> OutOfSampleMetrics:
    if not predictions:
        raise WalkForwardInputError("no out-of-sample predictions")
    try:
        with localcontext() as context:
            context.prec = _PRECISION
            context.rounding = ROUND_HALF_EVEN
            errors = tuple(item.prediction - item.actual for item in predictions)
            count = D(len(errors))
            mae = sum((abs(error) for error in errors), D("0")) / count
            mse = sum((error * error for error in errors), D("0")) / count
            rmse = mse.sqrt()
            mean_error = sum(errors, D("0")) / count
    except (InvalidOperation, OverflowError) as exc:
        raise WalkForwardInputError("invalid metric arithmetic") from exc
    return OutOfSampleMetrics(len(predictions), mae, rmse, mean_error)


def _provenance(rows: tuple[PointInTimeObservation, ...], config: WalkForwardConfig, as_of: datetime) -> str:
    payload = {"engine": "offline-expanding-mean-baseline-v1", "as_of": as_of.isoformat(), "config": [config.initial_train_size, config.test_size, config.purge_observations, config.max_windows], "observations": [[row.feature_timestamp.isoformat(), row.target_timestamp.isoformat(), str(row.feature), str(row.target)] for row in rows]}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


def run_walk_forward(observations: Iterable[PointInTimeObservation], config: WalkForwardConfig, *, as_of: datetime) -> WalkForwardResult:
    """Evaluate a deterministic expanding mean baseline at an explicit UTC cutoff.

    Each prediction is made from targets whose availability timestamps are earlier
    than the first feature timestamp in its test window. Recent rows are first
    removed by the configured purge, then additionally purged until that temporal
    invariant holds. This is an evaluator, not a strategy or trading interface.
    """
    cutoff = _timestamp(as_of, "as_of")
    values, settings = _collect(observations, cutoff), _validate_config(config)
    first_test = settings.initial_train_size + settings.purge_observations
    if first_test >= len(values):
        raise WalkForwardInputError("insufficient observations after initial training and purge")
    windows: list[WalkForwardWindow] = []
    all_predictions: list[BaselinePrediction] = []
    skipped_for_test_label_separation = 0
    test_start = first_test
    while test_start < len(values) and len(windows) < settings.max_windows:
        test = values[test_start:min(test_start + settings.test_size, len(values))]
        candidate_end = test_start - settings.purge_observations
        train = values[:candidate_end]
        temporal_purged = 0
        while train and train[-1].target_timestamp >= test[0].feature_timestamp:
            train = train[:-1]
            temporal_purged += 1
        if len(train) < 2:
            raise WalkForwardInputError("purge leaves fewer than two chronologically safe training observations")
        baseline = _mean(train)
        predictions = tuple(BaselinePrediction(row.feature_timestamp, row.target_timestamp, baseline, row.target) for row in test)
        metrics = _metrics(predictions)
        windows.append(WalkForwardWindow(train[0].feature_timestamp, train[-1].feature_timestamp, test[0].feature_timestamp, test[-1].feature_timestamp, len(train), settings.purge_observations, temporal_purged, baseline, predictions, metrics))
        all_predictions.extend(predictions)
        next_test_start = test_start + len(test)
        # Keep target/label intervals in separate OOS folds. Otherwise a later
        # fold could evaluate observations before an earlier fold's labels exist.
        while (next_test_start < len(values)
               and values[next_test_start].feature_timestamp <= test[-1].target_timestamp):
            next_test_start += 1
            skipped_for_test_label_separation += 1
        test_start = next_test_start
    out_of_sample = tuple(all_predictions)
    warnings: list[str] = [
        "Features, targets, and timestamps are unverified caller-supplied assertions; this evaluator does not establish completeness, authenticity, or real-world availability.",
        "The as_of cutoff rejects later target timestamps but does not prove publication time or target finality.",
        "Metrics describe only the supplied offline evaluation and are not performance evidence, forecasts, investment advice, or trading recommendations.",
    ]
    if skipped_for_test_label_separation:
        warnings.append("Observations were omitted between windows to prevent overlapping out-of-sample label intervals.")
    if len(windows) == settings.max_windows and test_start < len(values):
        warnings.append("Evaluation stopped at max_windows; later observations were not evaluated.")
    return WalkForwardResult(cutoff, tuple(windows), out_of_sample, _metrics(out_of_sample), _provenance(values, settings, cutoff), "expanding training-target mean baseline (no ML model)", tuple(warnings))
