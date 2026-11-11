"""Bounded offline SMA research runner; it cannot trade, fetch, or persist evidence."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any

from research.ingestion import ResearchIngestionError, capture_document, document_digest
from strategy import BacktestBar, BacktestConfig, BacktestInputError, SMAcrossoverStrategy, run_backtest

_MAX_INPUT_BYTES = 1_048_576
_MAX_TEXT = 128
_TOP_KEYS = frozenset(("schema_version", "as_of", "bars", "strategy", "config", "research_document"))
_BAR_KEYS = frozenset(("open_timestamp", "close_timestamp", "symbol", "open", "close"))
_STRATEGY_KEYS = frozenset(("type", "short_window", "long_window"))
_CONFIG_KEYS = frozenset(("initial_cash", "order_quantity", "max_position", "max_gap_seconds", "fee_bps", "slippage_bps"))


class ResearchCliError(ValueError):
    """Raised for unsafe, ambiguous, or unsupported offline research input."""


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise ResearchCliError("input contains duplicate JSON fields")
        output[key] = value
    return output


def _exact(value: object, keys: frozenset[str], name: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise ResearchCliError(f"invalid {name}")
    return value


def _no_symlink_path(path: Path) -> None:
    # Check every extant component before opening, so a symlinked parent is rejected too.
    absolute = path.absolute()
    for component in (absolute, *absolute.parents):
        try:
            if stat.S_ISLNK(os.lstat(component).st_mode):
                raise ResearchCliError("input path must not contain a symlink")
        except FileNotFoundError:
            continue


def _read_input(path: str | Path) -> dict[str, Any]:
    candidate = Path(path)
    _no_symlink_path(candidate)
    if not hasattr(os, "O_NOFOLLOW"):
        raise ResearchCliError("no-follow file support is required")
    try:
        fd = os.open(os.fspath(candidate), os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0))
    except OSError as exc:
        raise ResearchCliError("input must be a readable local regular file") from exc
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_INPUT_BYTES:
            raise ResearchCliError("input must be a bounded regular file")
        data = bytearray()
        while len(data) <= _MAX_INPUT_BYTES:
            block = os.read(fd, min(65_536, _MAX_INPUT_BYTES + 1 - len(data)))
            if not block:
                break
            data.extend(block)
        if len(data) > _MAX_INPUT_BYTES:
            raise ResearchCliError("input exceeds size limit")
        value = json.loads(bytes(data).decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ResearchCliError("invalid JSON numeric constant")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResearchCliError("input is not valid UTF-8 JSON") from exc
    finally:
        os.close(fd)
    if type(value) is not dict:
        raise ResearchCliError("input must be a JSON object")
    return value


def _decimal(value: object, name: str) -> Decimal:
    # Numeric JSON types risk binary conversion ambiguity; require exact decimal strings.
    if type(value) is not str or not value or len(value) > _MAX_TEXT:
        raise ResearchCliError(f"invalid {name}")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ResearchCliError(f"invalid {name}") from exc
    if not parsed.is_finite():
        raise ResearchCliError(f"invalid {name}")
    return parsed


def _timestamp(value: object, name: str = "bar timestamp") -> datetime:
    if type(value) is not str or not value or len(value) > 40:
        raise ResearchCliError(f"invalid {name}")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ResearchCliError(f"invalid {name}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None or parsed.isoformat() != value:
        raise ResearchCliError(f"{name} must be canonical ISO-8601 with timezone")
    return parsed


def _as_of(value: object) -> datetime:
    """Require an explicit, canonical UTC cutoff; never infer wall-clock time."""
    if type(value) is not str or not value or len(value) > 40:
        raise ResearchCliError("as_of must be canonical UTC ISO-8601")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ResearchCliError("as_of must be canonical UTC ISO-8601") from exc
    if (parsed.tzinfo is None or parsed.utcoffset() is None
            or parsed.utcoffset().total_seconds() != 0 or parsed.isoformat() != value):
        raise ResearchCliError("as_of must be canonical UTC ISO-8601")
    return parsed


def _bars(value: object) -> tuple[BacktestBar, ...]:
    if type(value) is not list or not value or len(value) > 10_000:
        raise ResearchCliError("bars must contain 1 to 10000 items")
    try:
        return tuple(BacktestBar(_timestamp(item["open_timestamp"], "bar open timestamp"),
                                 _timestamp(item["close_timestamp"], "bar close timestamp"), item["symbol"],
                                 _decimal(item["open"], "bar open"), _decimal(item["close"], "bar close"))
                     for raw in value for item in (_exact(raw, _BAR_KEYS, "bar"),))
    except (KeyError, TypeError, BacktestInputError, ResearchCliError) as exc:
        raise ResearchCliError("invalid historical bars") from exc


def _strategy(value: object) -> SMAcrossoverStrategy:
    raw = _exact(value, _STRATEGY_KEYS, "strategy")
    if raw["type"] != "sma_crossover" or type(raw["short_window"]) is not int or type(raw["long_window"]) is not int:
        raise ResearchCliError("strategy must explicitly configure integer SMA windows")
    try:
        return SMAcrossoverStrategy(raw["short_window"], raw["long_window"])
    except BacktestInputError as exc:
        raise ResearchCliError("invalid SMA strategy") from exc


def _config(value: object) -> BacktestConfig:
    raw = _exact(value, _CONFIG_KEYS, "config")
    if type(raw["max_gap_seconds"]) is not int:
        raise ResearchCliError("max_gap_seconds must be an integer")
    try:
        return BacktestConfig(*(_decimal(raw[key], key) for key in ("initial_cash", "order_quantity", "max_position")),
                              raw["max_gap_seconds"], *(_decimal(raw[key], key) for key in ("fee_bps", "slippage_bps")))
    except BacktestInputError as exc:
        raise ResearchCliError("invalid backtest configuration") from exc


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _json_value(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    return value


def run(input_path: str | Path) -> dict[str, Any]:
    """Run caller-supplied historical analysis only, returning JSON-safe simulation output."""
    raw = _read_input(input_path)
    required = _TOP_KEYS - {"research_document"}
    if type(raw) is not dict or not required.issubset(raw) or not set(raw).issubset(_TOP_KEYS):
        raise ResearchCliError("invalid research input")
    if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
        raise ResearchCliError("schema_version must be 1")
    as_of = _as_of(raw["as_of"])
    bars, strategy, config = _bars(raw["bars"]), _strategy(raw["strategy"]), _config(raw["config"])
    document = None
    if raw.get("research_document") is not None:
        try:
            document = capture_document(raw["research_document"])
        except ResearchIngestionError as exc:
            raise ResearchCliError("invalid untrusted research document") from exc
    try:
        result = run_backtest(bars, strategy, config, as_of=as_of)
    except BacktestInputError as exc:
        raise ResearchCliError("backtest rejected historical input") from exc
    dataset = [{"open_timestamp": bar.open_timestamp.isoformat(), "close_timestamp": bar.close_timestamp.isoformat(), "symbol": bar.symbol, "open": str(bar.open), "close": str(bar.close)} for bar in bars]
    settings = {"strategy": {"type": "sma_crossover", "short_window": strategy.short_window, "long_window": strategy.long_window},
                "config": {"initial_cash": str(config.initial_cash), "order_quantity": str(config.order_quantity), "max_position": str(config.max_position), "max_gap_seconds": config.max_gap_seconds, "fee_bps": str(config.fee_bps), "slippage_bps": str(config.slippage_bps)}}
    provenance = {"as_of": as_of.isoformat(), "status": result.status,
                  "engine_provenance_sha256": result.provenance}
    return {"mode": "OFFLINE_HISTORICAL_ANALYSIS_ONLY", "simulation": _json_value(asdict(result)),
            "provenance": provenance, "dataset_sha256": _digest(dataset),
            "configuration_sha256": _digest(settings),
            "input_sha256": _digest({"schema_version": 1, "as_of": as_of.isoformat(), "bars": dataset,
                                       **settings, "research_document": document_digest(document) if document else None}),
            "research_document": None if document is None else {"content_sha256": document_digest(document), "untrusted": True, "risk_authority": False},
            "trust_disclaimers": ["Historical bars are untrusted caller-supplied fixtures; acceptance does not establish that prices, timestamps, or history are real, complete, or suitable.", "The caller-supplied as_of cutoff only constrains this deterministic simulation; it does not independently verify that any bar is genuinely past, closed, timely, complete, or suitable.", "Results are deterministic analysis of supplied data, not a forecast, recommendation, validation of a strategy, or financial advice.", "No network, credentials, broker, trading, order submission, control, risk, or manifest override path is used; simulated orders are not real orders.", "Optional research text is captured as inert untrusted evidence only and has no execution, control, risk, or configuration authority."]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run bounded offline historical SMA analysis; never trades or fetches data.")
    parser.add_argument("input", help="local JSON research input (regular file, no symlinks)")
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.input), sort_keys=True, separators=(",", ":"), allow_nan=False))
    except ResearchCliError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
