# backtest-contract-oracle

A small **offline, read-only** Rust command-line validator for a deliberately narrow historical-backtest fixture contract. It uses the Rust standard library only; it has no dependencies, network access, broker integration, live-state access, order submission, or output-file writes.

## Usage

```sh
cargo run --locked -- fixture.tsv
# or
cat fixture.tsv | cargo run --locked -- -
```

It prints `VALID bars=N` on success. Invalid input prints a precise diagnostic to stderr and exits `2`; usage errors exit `64`.

## Exact TSV contract (v1)

Input must be ASCII, at most 4 MiB, and have lines no longer than 1024 bytes. CRLF, blank rows, comments, and extra fields are rejected. One final LF is permitted.

```text
# backtest-contract-oracle-v1
as_of_epoch_seconds<TAB>max_gap_seconds<TAB>quantity
<signed i64 seconds><TAB><integer 0..31536000><TAB><positive decimal>
open_epoch_seconds<TAB>close_epoch_seconds<TAB>symbol<TAB>open<TAB>close
<bar row>...
```

* Timestamps are **signed 64-bit Unix epoch seconds**; fractional timestamps and ISO-8601 text are not accepted. `close_epoch_seconds <= as_of_epoch_seconds` is required.
* `quantity`, `open`, and `close` are unsigned ASCII base-10 decimals: no signs, exponent notation, whitespace, `NaN`, or infinity; at most 18 digits after the decimal point; strictly greater than zero; and no greater than `1000000000`.
* `symbol` is 1–16 ASCII characters matching `[A-Z0-9][A-Z0-9._-]{0,15}`.
* There must be 1–10,000 bars. Bars must have one symbol, a positive common integer-second duration, increasing non-overlapping intervals with each next open **strictly after** the previous close, and a positive inter-bar gap no larger than `max_gap_seconds`.

The validator parses all integers with checked `i64` conversion and computes durations/gaps with checked subtraction. Decimal validation is lexical deliberately, retaining precision without float rounding or numeric overflow.

## Relationship to `strategy/backtest.py`

This tool mirrors the bounded shape checks that can be represented by this TSV contract: a 10,000-bar maximum, one symbol, positive/equal bar durations, strict ordered non-overlap, configured gaps capped at 31,536,000 seconds, positive values with at most 18 decimal places and an absolute bound of 1,000,000,000, and an `as_of` cutoff.

It is **not a proof of full Python-engine equivalence**: the Python engine accepts timezone-aware `datetime` values with microseconds and uses `Decimal`, while this fixture format intentionally permits only whole Unix seconds and lexical unsigned decimals. It also does not validate strategy windows, cash/position/fee/slippage configuration, execute SMA logic, generate signals, simulate fills, calculate equity/provenance, establish source-data authenticity, or prove that a valid fixture contains no future knowledge. The `as_of` and explicit intervals only constrain the data submitted to this tool.

A permitted gap is still incomplete supplied history, not evidence of continuous market coverage.

## Tests

`cargo test --locked` covers valid input plus malformed and adversarial decimal syntax, overflowed timestamps, lower-case symbols, zero quantity, overlap/touching intervals, unequal duration, excessive gaps, mixed symbols, `as_of` violations, malformed TSV, and over-10,000 bars.
