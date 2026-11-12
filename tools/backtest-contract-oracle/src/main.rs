//! Bounded, offline input-contract validation for backtest fixtures.
//!
//! The validator deliberately validates only the documented TSV contract. It
//! does not calculate indicators, submit orders, access a broker/network, or
//! infer that supplied bars represent complete market history.

mod validator;

use std::env;
use std::process::ExitCode;
use validator::{read_input, validate_text};

fn usage() -> &'static str {
    "usage: backtest-contract-oracle <fixture.tsv|->"
}

fn main() -> ExitCode {
    let mut arguments = env::args().skip(1);
    let Some(path) = arguments.next() else {
        eprintln!("{}", usage());
        return ExitCode::from(64);
    };
    if arguments.next().is_some() || path == "--help" || path == "-h" {
        eprintln!("{}", usage());
        return ExitCode::from(64);
    }
    match read_input(&path).and_then(|input| validate_text(&input)) {
        Ok(count) => {
            println!("VALID bars={count}");
            ExitCode::SUCCESS
        }
        Err(error) => {
            eprintln!("INVALID: {error}");
            ExitCode::from(2)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::validator::*;

    fn fixture(rows: &str) -> String {
        format!("{MAGIC}\n{METADATA_HEADER}\n200\t60\t1.250\n{BAR_HEADER}\n{rows}")
    }

    #[test]
    fn accepts_valid_bounded_fixture() {
        let input = fixture("80\t139\tASAI\t10.00\t10.50\n140\t199\tASAI\t10.50\t11.00\n");
        assert_eq!(validate_text(&input), Ok(2));
    }

    #[test]
    fn accepts_leading_zero_decimal_and_negative_epoch() {
        let input = fixture("-120\t-61\tA-1\t000.001\t1\n-60\t-1\tA-1\t1\t2\n");
        assert_eq!(validate_text(&input), Ok(2));
    }

    #[test]
    fn accepts_exact_decimal_value_and_precision_boundaries() {
        let mut input = fixture("100\t159\tASAI\t1000000000.000000000000000000\t1\n");
        input = input.replacen(
            "200\t60\t1.250",
            "200\t60\t1000000000.000000000000000000",
            1,
        );
        assert_eq!(validate_text(&input), Ok(1));
    }

    #[test]
    fn rejects_malformed_adversarial_fields() {
        for (name, rows) in [
            ("float exponent", "100\t159\tASAI\t1e3\t1\n"),
            ("too precise", "100\t159\tASAI\t0.0000000000000000001\t1\n"),
            (
                "decimal exceeds numeric bound",
                "100\t159\tASAI\t1000000000.000000000000000001\t1\n",
            ),
            ("zero quantity", "100\t159\tASAI\t1\t1\n"),
            ("lowercase symbol", "100\t159\tasai\t1\t1\n"),
            ("overlong symbol", "100\t159\tABCDEFGHIJKLMNOPQ\t1\t1\n"),
            (
                "timestamp overflow",
                "999999999999999999999\t159\tASAI\t1\t1\n",
            ),
        ] {
            let mut input = fixture(rows);
            if name == "zero quantity" {
                input = input.replacen("200\t60\t1.250", "200\t60\t0", 1);
            }
            assert!(validate_text(&input).is_err(), "{name}");
        }
    }

    #[test]
    fn rejects_checked_timestamp_duration_overflow() {
        let mut input = fixture("-9223372036854775808\t9223372036854775807\tASAI\t1\t1\n");
        input = input.replacen("200\t60\t1.250", "9223372036854775807\t60\t1.250", 1);
        assert!(validate_text(&input).is_err());
    }

    #[test]
    fn rejects_order_overlap_duration_gap_symbol_and_lookahead() {
        for rows in [
            "100\t159\tASAI\t1\t1\n159\t218\tASAI\t1\t1\n",
            "100\t159\tASAI\t1\t1\n160\t220\tASAI\t1\t1\n",
            "100\t159\tASAI\t1\t1\n221\t280\tASAI\t1\t1\n",
            "100\t159\tASAI\t1\t1\n160\t219\tOTHER\t1\t1\n",
            "100\t201\tASAI\t1\t1\n",
        ] {
            assert!(validate_text(&fixture(rows)).is_err());
        }
    }

    #[test]
    fn rejects_structure_and_size_contract_violations() {
        assert!(validate_text("bad").is_err());
        assert!(validate_text(&fixture("\n")).is_err());
        assert!(validate_text(&fixture("100\t159\tASAI\t1\t1\textra\n")).is_err());
        let rows = (0..=MAX_BARS)
            .map(|index| format!("{}\t{}\tASAI\t1\t1", index * 2, index * 2 + 1))
            .collect::<Vec<_>>()
            .join("\n");
        assert!(validate_text(&fixture(&format!("{rows}\n"))).is_err());
    }

    #[test]
    fn permits_one_final_lf_but_rejects_a_blank_final_row() {
        let row = "100\t159\tASAI\t1\t1";
        assert_eq!(validate_text(&fixture(&format!("{row}\n"))), Ok(1));
        assert!(validate_text(&fixture(&format!("{row}\n\n"))).is_err());
    }

    #[test]
    fn limited_reader_rejects_an_oversized_stream() {
        use std::io::Cursor;

        assert_eq!(
            read_limited_input(Cursor::new(vec![b'x'; MAX_INPUT_BYTES]), "test"),
            Ok("x".repeat(MAX_INPUT_BYTES))
        );
        assert_eq!(
            read_limited_input(Cursor::new(vec![b'x'; MAX_INPUT_BYTES + 1]), "test"),
            Err("input exceeds 4 MiB bound".to_string())
        );
    }
}
