-- ASAI PostgreSQL foundation: append-only, double-entry journal.
-- Apply once, as the dedicated schema owner, with psql -v ON_ERROR_STOP=1.
-- This migration intentionally creates no broker, order-routing, credential, or network capability.

BEGIN;

CREATE SCHEMA IF NOT EXISTS asai;
REVOKE ALL ON SCHEMA asai FROM PUBLIC;
SET LOCAL search_path = asai, pg_catalog;

CREATE TYPE asai.safety_state AS ENUM ('ALIVE', 'HALTED', 'KILLED', 'DEAD');
CREATE TYPE asai.entry_type AS ENUM ('GENERAL', 'FUNDING', 'EXPENSE', 'ADJUSTMENT');
CREATE TYPE asai.posting_side AS ENUM ('DEBIT', 'CREDIT');

CREATE TABLE asai.ledger_account (
    account_code text PRIMARY KEY,
    account_name text NOT NULL,
    enabled boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (account_code ~ '^[A-Z][A-Za-z0-9:_-]{2,127}$'),
    CHECK (btrim(account_name) <> '')
);

-- The only mutable control record. Its state may only move away from ALIVE.
CREATE TABLE asai.safety_control (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    state asai.safety_state NOT NULL DEFAULT 'ALIVE',
    latched boolean NOT NULL DEFAULT false,
    reason text,
    changed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK ((state = 'ALIVE' AND NOT latched AND reason IS NULL)
        OR (state <> 'ALIVE' AND latched AND btrim(reason) <> ''))
);

CREATE TABLE asai.safety_event (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    state asai.safety_state NOT NULL,
    reason text NOT NULL CHECK (btrim(reason) <> ''),
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE asai.journal_entry (
    entry_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    idempotency_key text NOT NULL UNIQUE CHECK (btrim(idempotency_key) <> ''),
    entry_type asai.entry_type NOT NULL DEFAULT 'GENERAL',
    memo text NOT NULL CHECK (btrim(memo) <> ''),
    request_lines jsonb NOT NULL CHECK (jsonb_typeof(request_lines) = 'array'),
    posted_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE asai.journal_line (
    line_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entry_id bigint NOT NULL REFERENCES asai.journal_entry(entry_id) ON DELETE RESTRICT,
    line_no integer NOT NULL CHECK (line_no > 0),
    account_code text NOT NULL REFERENCES asai.ledger_account(account_code) ON DELETE RESTRICT,
    currency char(3) NOT NULL CHECK (currency = upper(currency) AND currency ~ '^[A-Z]{3}$'),
    side asai.posting_side NOT NULL,
    amount numeric(24,8) NOT NULL CHECK (amount > 0),
    UNIQUE (entry_id, line_no)
);
CREATE INDEX journal_line_entry_idx ON asai.journal_line (entry_id, line_no);
CREATE INDEX journal_line_account_currency_idx ON asai.journal_line (account_code, currency);

-- Read-only projections. Positive signed_amount is a debit, negative is a credit.
CREATE VIEW asai.v_journal_lines AS
SELECT e.entry_id, e.idempotency_key, e.entry_type, e.memo, e.posted_at,
       l.line_no, l.account_code, l.currency, l.side, l.amount,
       CASE WHEN l.side = 'DEBIT' THEN l.amount ELSE -l.amount END AS signed_amount
FROM asai.journal_entry AS e
JOIN asai.journal_line AS l ON l.entry_id = e.entry_id;

CREATE VIEW asai.v_account_balance AS
SELECT account_code, currency,
       sum(CASE WHEN side = 'DEBIT' THEN amount ELSE -amount END) AS signed_balance
FROM asai.journal_line
GROUP BY account_code, currency;

-- Used by guarded functions below. Ordinary application roles do not receive table DML.
CREATE FUNCTION asai._internal_write_enabled()
RETURNS boolean
LANGUAGE sql
STABLE
SET search_path = pg_catalog
AS $$
    SELECT current_setting('asai.internal_write', true) = 'on'
$$;

CREATE FUNCTION asai._reject_journal_mutation()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = asai, pg_catalog
AS $$
BEGIN
    RAISE EXCEPTION 'ASAI journal history is append-only'
        USING ERRCODE = '55000';
END;
$$;

CREATE TRIGGER journal_entry_no_update_delete
BEFORE UPDATE OR DELETE ON asai.journal_entry
FOR EACH ROW EXECUTE FUNCTION asai._reject_journal_mutation();

CREATE TRIGGER journal_line_no_update_delete
BEFORE UPDATE OR DELETE ON asai.journal_line
FOR EACH ROW EXECUTE FUNCTION asai._reject_journal_mutation();

CREATE FUNCTION asai._guard_safety_control()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = asai, pg_catalog
AS $$
BEGIN
    IF TG_OP = 'DELETE' OR NOT asai._internal_write_enabled() THEN
        RAISE EXCEPTION 'safety control is managed only by ASAI guarded functions'
            USING ERRCODE = '55000';
    END IF;
    IF OLD.singleton IS DISTINCT FROM NEW.singleton
       OR OLD.state <> 'ALIVE'
       OR NEW.state = 'ALIVE'
       OR NOT NEW.latched
       OR btrim(COALESCE(NEW.reason, '')) = '' THEN
        RAISE EXCEPTION 'invalid safety-state transition' USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER safety_control_guard
BEFORE UPDATE OR DELETE ON asai.safety_control
FOR EACH ROW EXECUTE FUNCTION asai._guard_safety_control();

CREATE TRIGGER safety_event_no_update_delete
BEFORE UPDATE OR DELETE ON asai.safety_event
FOR EACH ROW EXECUTE FUNCTION asai._reject_journal_mutation();

INSERT INTO asai.safety_control(singleton, state, latched, reason)
VALUES (true, 'ALIVE', false, NULL);

-- Minimal explicit chart. Extend it only through controlled administration before use.
INSERT INTO asai.ledger_account(account_code, account_name) VALUES
    ('Asset:Cash', 'Cash'),
    ('Asset:Receivable', 'Receivable'),
    ('Liability:Payable', 'Payable'),
    ('Equity:Capital', 'Capital'),
    ('Equity:RetainedEarnings', 'Retained earnings'),
    ('Income:General', 'General income'),
    ('Expense:General', 'General expense');

-- Atomically append a complete entry. p_lines is a JSON array of objects:
-- {"account_code":"Asset:Cash","currency":"USD","side":"DEBIT","amount":"10.00"}.
-- A repeated idempotency key returns the original entry only if memo, type, and JSON payload match exactly.
CREATE FUNCTION asai.post_journal(
    p_idempotency_key text,
    p_memo text,
    p_lines jsonb,
    p_entry_type asai.entry_type DEFAULT 'GENERAL'
)
RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = asai, pg_catalog
AS $$
DECLARE
    v_entry_id bigint;
    v_control asai.safety_control%ROWTYPE;
    v_count integer;
    v_bad_count integer;
BEGIN
    IF btrim(COALESCE(p_idempotency_key, '')) = '' OR length(p_idempotency_key) > 200 THEN
        RAISE EXCEPTION 'idempotency key must be 1..200 nonblank characters' USING ERRCODE = '22023';
    END IF;
    IF btrim(COALESCE(p_memo, '')) = '' OR length(p_memo) > 1000 THEN
        RAISE EXCEPTION 'memo must be 1..1000 nonblank characters' USING ERRCODE = '22023';
    END IF;
    IF p_lines IS NULL OR jsonb_typeof(p_lines) <> 'array' THEN
        RAISE EXCEPTION 'lines must be a JSON array' USING ERRCODE = '22023';
    END IF;

    -- Same key is serialized even before its first insert. Collision only serializes unrelated requests.
    PERFORM pg_advisory_xact_lock(hashtextextended(p_idempotency_key, 0));
    SELECT entry_id INTO v_entry_id
    FROM asai.journal_entry
    WHERE idempotency_key = p_idempotency_key;
    IF FOUND THEN
        IF EXISTS (
            SELECT 1 FROM asai.journal_entry
            WHERE entry_id = v_entry_id
              AND (memo <> p_memo OR entry_type <> p_entry_type OR request_lines <> p_lines)
        ) THEN
            RAISE EXCEPTION 'idempotency key was reused with a different request' USING ERRCODE = '22023';
        END IF;
        RETURN v_entry_id;
    END IF;

    -- This row lock serializes a safety latch against all first-time postings.
    SELECT * INTO v_control FROM asai.safety_control WHERE singleton FOR UPDATE;
    IF NOT FOUND OR v_control.state <> 'ALIVE' OR v_control.latched THEN
        RAISE EXCEPTION 'posting denied: safety control is latched (%)', COALESCE(v_control.state::text, 'MISSING')
            USING ERRCODE = '55000';
    END IF;

    SELECT count(*) INTO v_count FROM jsonb_array_elements(p_lines);
    IF v_count < 2 THEN
        RAISE EXCEPTION 'an entry requires at least two lines' USING ERRCODE = '22023';
    END IF;
    IF EXISTS (SELECT 1 FROM jsonb_array_elements(p_lines) AS x WHERE jsonb_typeof(x) <> 'object') THEN
        RAISE EXCEPTION 'every line must be a JSON object' USING ERRCODE = '22023';
    END IF;

    -- jsonb_to_recordset both validates shape and keeps all amount arithmetic in PostgreSQL numeric.
    WITH parsed AS (
        SELECT * FROM jsonb_to_recordset(p_lines) AS x(
            account_code text, currency text, side text, amount numeric
        )
    )
    SELECT count(*) FILTER (WHERE account_code IS NULL OR currency IS NULL OR side IS NULL OR amount IS NULL
                              OR account_code !~ '^[A-Z][A-Za-z0-9:_-]{2,127}$'
                              OR currency !~ '^[A-Z]{3}$'
                              OR side NOT IN ('DEBIT', 'CREDIT')
                              -- PostgreSQL numeric accepts special non-finite values on supported versions.
                              -- They are never valid money, even when comparison semantics say NaN/Infinity > 0.
                              OR amount::text IN ('NaN', 'Infinity', '-Infinity')
                              OR amount <= 0 OR scale(amount) > 8)
    INTO v_bad_count
    FROM parsed;
    IF v_bad_count > 0 THEN
        RAISE EXCEPTION 'line fields must be valid account_code, uppercase ISO-like currency, side, and positive amount (max 8 decimals)'
            USING ERRCODE = '22023';
    END IF;

    IF EXISTS (
        WITH parsed AS (
            SELECT * FROM jsonb_to_recordset(p_lines) AS x(account_code text, currency text, side text, amount numeric)
        ), sums AS (
            SELECT currency,
                   sum(amount) FILTER (WHERE side = 'DEBIT') AS debits,
                   sum(amount) FILTER (WHERE side = 'CREDIT') AS credits
            FROM parsed GROUP BY currency
        )
        SELECT 1 FROM sums WHERE COALESCE(debits, 0) <> COALESCE(credits, 0)
    ) THEN
        RAISE EXCEPTION 'entry is not balanced within each currency' USING ERRCODE = '22023';
    END IF;

    IF EXISTS (
        WITH parsed AS (
            SELECT DISTINCT account_code FROM jsonb_to_recordset(p_lines) AS x(account_code text, currency text, side text, amount numeric)
        )
        SELECT 1 FROM parsed p LEFT JOIN asai.ledger_account a USING (account_code)
        WHERE a.account_code IS NULL OR NOT a.enabled
    ) THEN
        RAISE EXCEPTION 'entry references a missing or disabled account' USING ERRCODE = '22023';
    END IF;

    INSERT INTO asai.journal_entry(idempotency_key, entry_type, memo, request_lines)
    VALUES (p_idempotency_key, p_entry_type, p_memo, p_lines)
    RETURNING entry_id INTO v_entry_id;

    INSERT INTO asai.journal_line(entry_id, line_no, account_code, currency, side, amount)
    SELECT v_entry_id, ord::integer, account_code, currency::char(3), side::asai.posting_side, amount
    FROM ROWS FROM (
        jsonb_to_recordset(p_lines) AS (
            account_code text, currency text, side text, amount numeric
        )
    ) WITH ORDINALITY AS x(account_code, currency, side, amount, ord);

    RETURN v_entry_id;
END;
$$;

CREATE FUNCTION asai.latch_safety(
    p_state asai.safety_state,
    p_reason text
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = asai, pg_catalog
AS $$
DECLARE
    v_control asai.safety_control%ROWTYPE;
BEGIN
    IF p_state = 'ALIVE' OR btrim(COALESCE(p_reason, '')) = '' OR length(p_reason) > 2000 THEN
        RAISE EXCEPTION 'latch requires HALTED, KILLED, or DEAD and a 1..2000 character reason' USING ERRCODE = '22023';
    END IF;
    SELECT * INTO v_control FROM asai.safety_control WHERE singleton FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'safety control record is missing' USING ERRCODE = '55000';
    END IF;
    IF v_control.state <> 'ALIVE' OR v_control.latched THEN
        RAISE EXCEPTION 'safety control is already latched as %', v_control.state USING ERRCODE = '55000';
    END IF;
    PERFORM set_config('asai.internal_write', 'on', true);
    UPDATE asai.safety_control
       SET state = p_state, latched = true, reason = p_reason, changed_at = clock_timestamp()
     WHERE singleton;
    INSERT INTO asai.safety_event(state, reason) VALUES (p_state, p_reason);
END;
$$;

-- Default-deny. The migration owner retains ownership; application access is function-only.
REVOKE ALL ON ALL TABLES IN SCHEMA asai FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA asai FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA asai FROM PUBLIC;

-- Optional least-privilege grants activate only if deployment roles already exist.
-- Create these NOLOGIN group roles outside this migration (requires CREATEROLE), then grant LOGIN roles into them.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'asai_poster') THEN
        GRANT USAGE ON SCHEMA asai TO asai_poster;
        GRANT EXECUTE ON FUNCTION asai.post_journal(text, text, jsonb, asai.entry_type) TO asai_poster;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'asai_safety_operator') THEN
        GRANT USAGE ON SCHEMA asai TO asai_safety_operator;
        GRANT EXECUTE ON FUNCTION asai.latch_safety(asai.safety_state, text) TO asai_safety_operator;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'asai_reader') THEN
        GRANT USAGE ON SCHEMA asai TO asai_reader;
        GRANT SELECT ON asai.v_journal_lines, asai.v_account_balance, asai.safety_control, asai.safety_event TO asai_reader;
    END IF;
END;
$$;

COMMIT;
