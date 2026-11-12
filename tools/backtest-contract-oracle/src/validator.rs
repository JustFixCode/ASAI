//! Parser and bounded-reader implementation for the offline fixture contract.

use std::fs;
use std::io::{self, Read};

pub(crate) const MAX_BARS: usize = 10_000;
pub(crate) const MAX_INPUT_BYTES: usize = 4 * 1024 * 1024;
const MAX_LINE_BYTES: usize = 1024;
const MAX_GAP_SECONDS: i64 = 31_536_000;
const MAX_DECIMAL_PLACES: usize = 18;
const MAX_ABS_WHOLE: &str = "1000000000";
pub(crate) const MAGIC: &str = "# backtest-contract-oracle-v1";
pub(crate) const METADATA_HEADER: &str = "as_of_epoch_seconds\tmax_gap_seconds\tquantity";
pub(crate) const BAR_HEADER: &str = "open_epoch_seconds\tclose_epoch_seconds\tsymbol\topen\tclose";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct Metadata {
    as_of: i64,
    max_gap: i64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct Bar<'a> {
    open: i64,
    close: i64,
    symbol: &'a str,
}

fn fail<T>(message: impl Into<String>) -> Result<T, String> {
    Err(message.into())
}

fn parse_i64(field: &str, line: usize, name: &str) -> Result<i64, String> {
    if field.is_empty()
        || !field
            .bytes()
            .all(|byte| byte.is_ascii_digit() || byte == b'-')
    {
        return fail(format!("line {line}: invalid {name}"));
    }
    if let Some(unsigned) = field.strip_prefix('-') {
        if unsigned.is_empty() || !unsigned.bytes().all(|byte| byte.is_ascii_digit()) {
            return fail(format!("line {line}: invalid {name}"));
        }
    } else if !field.bytes().all(|byte| byte.is_ascii_digit()) {
        return fail(format!("line {line}: invalid {name}"));
    }
    field
        .parse::<i64>()
        .map_err(|_| format!("line {line}: {name} is outside signed 64-bit range"))
}

fn parse_nonnegative_i64(
    field: &str,
    line: usize,
    name: &str,
    maximum: i64,
) -> Result<i64, String> {
    let value = parse_i64(field, line, name)?;
    if !(0..=maximum).contains(&value) {
        return fail(format!("line {line}: invalid {name}"));
    }
    Ok(value)
}

/// Validate a finite, unsigned base-10 decimal bounded by 1_000_000_000.
/// It is lexical by design: no floating-point conversion can overflow, round,
/// accept exponent notation, or erase decimal-place information.
fn validate_positive_decimal(field: &str, line: usize, name: &str) -> Result<(), String> {
    let mut parts = field.split('.');
    let whole = parts.next().unwrap_or_default();
    let fraction = parts.next();
    if parts.next().is_some()
        || whole.is_empty()
        || !whole.bytes().all(|byte| byte.is_ascii_digit())
        || fraction.is_some_and(|part| {
            part.is_empty()
                || part.len() > MAX_DECIMAL_PLACES
                || !part.bytes().all(|byte| byte.is_ascii_digit())
        })
    {
        return fail(format!("line {line}: invalid {name}"));
    }

    let whole_without_leading_zeroes = whole.trim_start_matches('0');
    let normalized_whole = if whole_without_leading_zeroes.is_empty() {
        "0"
    } else {
        whole_without_leading_zeroes
    };
    if normalized_whole.len() > MAX_ABS_WHOLE.len()
        || (normalized_whole.len() == MAX_ABS_WHOLE.len() && normalized_whole > MAX_ABS_WHOLE)
    {
        return fail(format!("line {line}: invalid {name}"));
    }
    if normalized_whole == MAX_ABS_WHOLE
        && fraction.is_some_and(|part| part.bytes().any(|byte| byte != b'0'))
    {
        return fail(format!("line {line}: invalid {name}"));
    }
    if whole.bytes().all(|byte| byte == b'0')
        && fraction.is_none_or(|part| part.bytes().all(|byte| byte == b'0'))
    {
        return fail(format!("line {line}: {name} must be positive"));
    }
    Ok(())
}

fn validate_symbol(field: &str, line: usize) -> Result<(), String> {
    let bytes = field.as_bytes();
    if !(1..=16).contains(&bytes.len())
        || !bytes[0].is_ascii_uppercase() && !bytes[0].is_ascii_digit()
        || !bytes[1..].iter().all(|byte| {
            byte.is_ascii_uppercase() || byte.is_ascii_digit() || matches!(byte, b'.' | b'_' | b'-')
        })
    {
        return fail(format!("line {line}: invalid symbol"));
    }
    Ok(())
}

fn split_exact(line: &str, line_number: usize, expected: usize) -> Result<Vec<&str>, String> {
    let fields: Vec<_> = line.split('\t').collect();
    if fields.len() != expected || fields.iter().any(|field| field.is_empty()) {
        return fail(format!(
            "line {line_number}: expected exactly {expected} non-empty tab-separated fields"
        ));
    }
    Ok(fields)
}

fn expected_line<'a>(
    lines: &mut impl Iterator<Item = (usize, &'a str)>,
    expected: &str,
) -> Result<(), String> {
    let Some((number, value)) = lines.next() else {
        return fail(format!("missing {expected}"));
    };
    if value.ends_with('\r') {
        return fail(format!("line {}: CRLF is not permitted", number + 1));
    }
    if value != expected {
        return fail(format!("line {}: expected {expected}", number + 1));
    }
    Ok(())
}

pub(crate) fn validate_text(input: &str) -> Result<usize, String> {
    if input.len() > MAX_INPUT_BYTES {
        return fail("input exceeds 4 MiB bound");
    }
    if !input.is_ascii() {
        return fail("input must be ASCII");
    }
    // split_terminator permits one final LF without retaining a Vec of every
    // line. This keeps parser overhead bounded by the input itself rather
    // than allowing millions of short lines to amplify memory use.
    let mut lines = input.split_terminator('\n').enumerate();
    expected_line(&mut lines, MAGIC)?;
    expected_line(&mut lines, METADATA_HEADER)?;

    let Some((metadata_line_index, metadata_line)) = lines.next() else {
        return fail("missing metadata row");
    };
    let metadata_line_number = metadata_line_index + 1;
    if metadata_line.len() > MAX_LINE_BYTES || metadata_line.ends_with('\r') {
        return fail(format!("line {metadata_line_number}: invalid metadata row"));
    }
    let metadata_fields = split_exact(metadata_line, metadata_line_number, 3)?;
    let metadata = Metadata {
        as_of: parse_i64(
            metadata_fields[0],
            metadata_line_number,
            "as_of_epoch_seconds",
        )?,
        max_gap: parse_nonnegative_i64(
            metadata_fields[1],
            metadata_line_number,
            "max_gap_seconds",
            MAX_GAP_SECONDS,
        )?,
    };
    validate_positive_decimal(metadata_fields[2], metadata_line_number, "quantity")?;

    expected_line(&mut lines, BAR_HEADER)?;
    let mut previous: Option<Bar<'_>> = None;
    let mut duration: Option<i64> = None;
    let mut first_symbol: Option<&str> = None;
    let mut count = 0_usize;
    for (index, value) in lines {
        let line_number = index + 1;
        if value.is_empty() {
            return fail(format!("line {line_number}: blank rows are not permitted"));
        }
        if value.len() > MAX_LINE_BYTES || value.ends_with('\r') {
            return fail(format!("line {line_number}: invalid bar row"));
        }
        count = count
            .checked_add(1)
            .ok_or_else(|| "bar count overflow".to_string())?;
        if count > MAX_BARS {
            return fail("bars must contain 1 to 10000 rows");
        }
        let fields = split_exact(value, line_number, 5)?;
        let bar = Bar {
            open: parse_i64(fields[0], line_number, "open_epoch_seconds")?,
            close: parse_i64(fields[1], line_number, "close_epoch_seconds")?,
            symbol: fields[2],
        };
        validate_symbol(bar.symbol, line_number)?;
        validate_positive_decimal(fields[3], line_number, "open")?;
        validate_positive_decimal(fields[4], line_number, "close")?;
        if bar.open >= bar.close {
            return fail(format!(
                "line {line_number}: open timestamp must precede close timestamp"
            ));
        }
        if bar.close > metadata.as_of {
            return fail(format!(
                "line {line_number}: close timestamp is later than as_of cutoff"
            ));
        }
        let bar_duration = bar
            .close
            .checked_sub(bar.open)
            .ok_or_else(|| format!("line {line_number}: timestamp duration overflow"))?;
        if let Some(expected_duration) = duration {
            if bar_duration != expected_duration {
                return fail(format!("line {line_number}: bars must have equal duration"));
            }
        } else {
            duration = Some(bar_duration);
        }
        if let Some(symbol) = first_symbol {
            if bar.symbol != symbol {
                return fail(format!(
                    "line {line_number}: bars must contain exactly one symbol"
                ));
            }
        } else {
            first_symbol = Some(bar.symbol);
        }
        if let Some(previous_bar) = previous {
            if bar.open <= previous_bar.close {
                return fail(format!("line {line_number}: intervals must be ordered, non-overlapping, and have open after previous close"));
            }
            let gap = bar
                .open
                .checked_sub(previous_bar.close)
                .ok_or_else(|| format!("line {line_number}: gap overflow"))?;
            if gap > metadata.max_gap {
                return fail(format!(
                    "line {line_number}: bar gap exceeds configured maximum"
                ));
            }
        }
        previous = Some(bar);
    }
    if count == 0 {
        return fail("bars must contain 1 to 10000 rows");
    }
    Ok(count)
}

pub(crate) fn read_limited_input(mut reader: impl Read, source: &str) -> Result<String, String> {
    let mut contents = String::new();
    reader
        .by_ref()
        .take((MAX_INPUT_BYTES + 1) as u64)
        .read_to_string(&mut contents)
        .map_err(|error| format!("cannot read {source} as UTF-8: {error}"))?;
    if contents.len() > MAX_INPUT_BYTES {
        return fail("input exceeds 4 MiB bound");
    }
    Ok(contents)
}

pub(crate) fn read_input(argument: &str) -> Result<String, String> {
    if argument == "-" {
        return read_limited_input(io::stdin(), "stdin");
    }
    // Open first and check metadata from the same handle; then enforce the
    // byte cap while reading. A path replacement after a pathname stat can no
    // longer turn the later read into an unbounded allocation.
    let file = fs::File::open(argument).map_err(|error| format!("cannot open input: {error}"))?;
    let metadata = file
        .metadata()
        .map_err(|error| format!("cannot stat input: {error}"))?;
    if !metadata.is_file() {
        return fail("input must be a regular file");
    }
    read_limited_input(file, "input")
}
