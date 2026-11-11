\set ON_ERROR_STOP on
-- Run only against a disposable database immediately after 001_foundation.sql.
-- The final ROLLBACK leaves no test data or latch behind.
BEGIN;
SET LOCAL search_path = asai, pg_catalog;

DO $$
DECLARE
    v_entry_id bigint;
    v_retry_id bigint;
    v_event_id bigint;
    v_state asai.safety_state;
BEGIN
    SELECT state INTO v_state FROM asai.safety_control WHERE singleton;
    IF v_state IS DISTINCT FROM 'ALIVE' OR EXISTS (SELECT 1 FROM asai.journal_entry) THEN
        RAISE EXCEPTION 'test requires an empty, ALIVE ASAI schema' USING ERRCODE = '55000';
    END IF;

    v_entry_id := asai.post_journal(
        'invariant-test-funding-001',
        'Invariant test funding',
        '[
          {"account_code":"Asset:Cash", "currency":"USD", "side":"DEBIT", "amount":"100.00000000"},
          {"account_code":"Equity:Capital", "currency":"USD", "side":"CREDIT", "amount":"100.00000000"}
        ]'::jsonb,
        'FUNDING'
    );
    IF (SELECT count(*) FROM asai.journal_line WHERE entry_id = v_entry_id) <> 2 THEN
        RAISE EXCEPTION 'expected exactly two journal lines';
    END IF;

    -- A semantically identical JSONB retry is safe and returns the original entry.
    v_retry_id := asai.post_journal(
        'invariant-test-funding-001',
        'Invariant test funding',
        '[
          {"amount":100.00000000,"side":"DEBIT","currency":"USD","account_code":"Asset:Cash"},
          {"side":"CREDIT","account_code":"Equity:Capital","amount":100,"currency":"USD"}
        ]'::jsonb,
        'FUNDING'
    );
    IF v_retry_id <> v_entry_id OR (SELECT count(*) FROM asai.journal_entry) <> 1 THEN
        RAISE EXCEPTION 'idempotent retry did not return exactly the original entry';
    END IF;

    BEGIN
        PERFORM asai.post_journal(
            'invariant-test-funding-001', 'Changed request must fail',
            '[
              {"account_code":"Asset:Cash", "currency":"USD", "side":"DEBIT", "amount":"100"},
              {"account_code":"Equity:Capital", "currency":"USD", "side":"CREDIT", "amount":"100"}
            ]'::jsonb, 'FUNDING'
        );
        RAISE EXCEPTION 'changed idempotency-key reuse unexpectedly succeeded';
    EXCEPTION WHEN SQLSTATE '22023' THEN
        NULL;
    END;

    BEGIN
        PERFORM asai.post_journal(
            'invariant-test-unbalanced-001', 'Unbalanced must fail',
            '[
              {"account_code":"Asset:Cash", "currency":"USD", "side":"DEBIT", "amount":"100"},
              {"account_code":"Equity:Capital", "currency":"USD", "side":"CREDIT", "amount":"99"}
            ]'::jsonb
        );
        RAISE EXCEPTION 'unbalanced entry unexpectedly succeeded';
    EXCEPTION WHEN SQLSTATE '22023' THEN
        NULL;
    END;

    BEGIN
        PERFORM asai.post_journal(
            'invariant-test-nan-001', 'NaN must fail',
            '[
              {"account_code":"Asset:Cash", "currency":"USD", "side":"DEBIT", "amount":"NaN"},
              {"account_code":"Equity:Capital", "currency":"USD", "side":"CREDIT", "amount":"NaN"}
            ]'::jsonb
        );
        RAISE EXCEPTION 'NaN amount unexpectedly succeeded';
    EXCEPTION WHEN SQLSTATE '22023' THEN
        NULL;
    END;

    -- Regression coverage: JSON arrays may not smuggle scalar/non-record lines.
    BEGIN
        PERFORM asai.post_journal(
            'invariant-test-non-object-001', 'Non-object line must fail',
            '[
              {"account_code":"Asset:Cash", "currency":"USD", "side":"DEBIT", "amount":"1"},
              1
            ]'::jsonb
        );
        RAISE EXCEPTION 'non-object journal line unexpectedly succeeded';
    EXCEPTION WHEN SQLSTATE '22023' THEN
        NULL;
    END;

    BEGIN
        UPDATE asai.journal_entry SET memo = 'tampered' WHERE entry_id = v_entry_id;
        RAISE EXCEPTION 'journal update unexpectedly succeeded';
    EXCEPTION WHEN SQLSTATE '55000' THEN
        NULL;
    END;

    PERFORM asai.latch_safety('KILLED', 'Invariant test kill latch');
    SELECT event_id INTO v_event_id FROM asai.safety_event ORDER BY event_id DESC LIMIT 1;
    IF (SELECT state FROM asai.safety_control WHERE singleton) <> 'KILLED'
       OR NOT (SELECT latched FROM asai.safety_control WHERE singleton) THEN
        RAISE EXCEPTION 'kill latch was not persisted';
    END IF;

    BEGIN
        UPDATE asai.safety_control SET state = 'ALIVE', latched = false, reason = NULL WHERE singleton;
        RAISE EXCEPTION 'safety latch reset unexpectedly succeeded';
    EXCEPTION WHEN SQLSTATE '55000' THEN
        NULL;
    END;

    BEGIN
        UPDATE asai.safety_event SET reason = 'tampered' WHERE event_id = v_event_id;
        RAISE EXCEPTION 'safety event update unexpectedly succeeded';
    EXCEPTION WHEN SQLSTATE '55000' THEN
        NULL;
    END;

    -- Existing idempotent retries remain readable/safe; a new posting is denied after a latch.
    IF asai.post_journal(
        'invariant-test-funding-001',
        'Invariant test funding',
        '[
          {"account_code":"Asset:Cash", "currency":"USD", "side":"DEBIT", "amount":"100"},
          {"account_code":"Equity:Capital", "currency":"USD", "side":"CREDIT", "amount":"100"}
        ]'::jsonb,
        'FUNDING'
    ) <> v_entry_id THEN
        RAISE EXCEPTION 'idempotent retry changed after latch';
    END IF;

    BEGIN
        PERFORM asai.post_journal(
            'invariant-test-after-kill-001', 'New posting must fail after kill',
            '[
              {"account_code":"Asset:Cash", "currency":"USD", "side":"DEBIT", "amount":"1"},
              {"account_code":"Equity:Capital", "currency":"USD", "side":"CREDIT", "amount":"1"}
            ]'::jsonb
        );
        RAISE EXCEPTION 'new posting unexpectedly succeeded after kill latch';
    EXCEPTION WHEN SQLSTATE '55000' THEN
        NULL;
    END;
END;
$$;

-- Defensive whole-ledger invariant: no persisted entry may be unbalanced by currency.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM asai.journal_line
        GROUP BY entry_id, currency
        HAVING COALESCE(sum(amount) FILTER (WHERE side = 'DEBIT'), 0)
            <> COALESCE(sum(amount) FILTER (WHERE side = 'CREDIT'), 0)
    ) THEN
        RAISE EXCEPTION 'stored journal balance invariant failed' USING ERRCODE = '23514';
    END IF;
END;
$$;

ROLLBACK;
