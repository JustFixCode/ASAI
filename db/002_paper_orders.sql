-- ASAI paper-only order intent and lifecycle foundation.
-- Apply after 001_foundation.sql as the dedicated schema owner.
-- This migration contains no broker credentials, network calls, or live-venue capability.

BEGIN;
SET LOCAL search_path = asai, pg_catalog;

CREATE TYPE asai.paper_order_side AS ENUM ('BUY', 'SELL');
CREATE TYPE asai.paper_order_type AS ENUM ('MARKET', 'LIMIT');
CREATE TYPE asai.paper_order_state AS ENUM (
    'INTENDED',
    'SUBMISSION_ATTEMPTED',
    'SUBMISSION_UNKNOWN',
    'ACCEPTED',
    'PARTIALLY_FILLED',
    'FILLED',
    'REJECTED',
    'CANCEL_REQUESTED',
    'CANCELLED'
);

-- venue is deliberately not caller-controlled. Its single permitted value makes live routing
-- unrepresentable in this schema.
CREATE TABLE asai.paper_order (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id text NOT NULL UNIQUE CHECK (btrim(request_id) <> '' AND length(request_id) <= 200),
    client_order_id text NOT NULL UNIQUE CHECK (client_order_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'),
    venue text NOT NULL DEFAULT 'PAPER' CHECK (venue = 'PAPER'),
    symbol text NOT NULL CHECK (symbol ~ '^[A-Z][A-Z0-9._/-]{0,31}$'),
    side asai.paper_order_side NOT NULL,
    order_type asai.paper_order_type NOT NULL,
    quantity numeric(24,8) NOT NULL CHECK (quantity > 0 AND quantity::text NOT IN ('NaN', 'Infinity', '-Infinity')),
    limit_price numeric(24,8),
    state asai.paper_order_state NOT NULL DEFAULT 'INTENDED',
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (scale(quantity) <= 8),
    CHECK (limit_price IS NULL OR (limit_price > 0 AND scale(limit_price) <= 8
           AND limit_price::text NOT IN ('NaN', 'Infinity', '-Infinity'))),
    CHECK ((order_type = 'LIMIT' AND limit_price IS NOT NULL) OR (order_type = 'MARKET' AND limit_price IS NULL))
);
CREATE INDEX paper_order_state_idx ON asai.paper_order (state, created_at);

-- Every lifecycle fact is append-only. The event sequence is per order and starts at one.
CREATE TABLE asai.paper_order_event (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id bigint NOT NULL REFERENCES asai.paper_order(order_id) ON DELETE RESTRICT,
    event_no integer NOT NULL CHECK (event_no > 0),
    from_state asai.paper_order_state,
    to_state asai.paper_order_state NOT NULL,
    reason text NOT NULL CHECK (btrim(reason) <> '' AND length(reason) <= 2000),
    recorded_by name NOT NULL DEFAULT session_user,
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (order_id, event_no),
    CHECK ((event_no = 1 AND from_state IS NULL AND to_state = 'INTENDED')
        OR (event_no > 1 AND from_state IS NOT NULL))
);
CREATE INDEX paper_order_event_order_idx ON asai.paper_order_event (order_id, event_no);

CREATE FUNCTION asai._reject_paper_history_mutation()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = asai, pg_catalog
AS $$
BEGIN
    RAISE EXCEPTION 'ASAI paper-order history is append-only' USING ERRCODE = '55000';
END;
$$;

CREATE FUNCTION asai._guard_paper_order_write()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = asai, pg_catalog
AS $$
BEGIN
    IF NOT asai._internal_write_enabled() THEN
        RAISE EXCEPTION 'paper orders are managed only by ASAI guarded functions' USING ERRCODE = '55000';
    END IF;
    IF TG_OP = 'UPDATE' AND (
        NEW.order_id IS DISTINCT FROM OLD.order_id OR NEW.request_id IS DISTINCT FROM OLD.request_id
        OR NEW.client_order_id IS DISTINCT FROM OLD.client_order_id OR NEW.venue IS DISTINCT FROM OLD.venue
        OR NEW.symbol IS DISTINCT FROM OLD.symbol OR NEW.side IS DISTINCT FROM OLD.side
        OR NEW.order_type IS DISTINCT FROM OLD.order_type OR NEW.quantity IS DISTINCT FROM OLD.quantity
        OR NEW.limit_price IS DISTINCT FROM OLD.limit_price OR NEW.created_at IS DISTINCT FROM OLD.created_at
    ) THEN
        RAISE EXCEPTION 'paper-order intent is immutable' USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE FUNCTION asai._guard_paper_order_event_insert()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = asai, pg_catalog
AS $$
BEGIN
    IF NOT asai._internal_write_enabled() THEN
        RAISE EXCEPTION 'paper-order events are managed only by ASAI guarded functions' USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER paper_order_guard_insert_update
BEFORE INSERT OR UPDATE ON asai.paper_order
FOR EACH ROW EXECUTE FUNCTION asai._guard_paper_order_write();
CREATE TRIGGER paper_order_no_delete
BEFORE DELETE ON asai.paper_order
FOR EACH ROW EXECUTE FUNCTION asai._reject_paper_history_mutation();
CREATE TRIGGER paper_order_no_truncate
BEFORE TRUNCATE ON asai.paper_order
FOR EACH STATEMENT EXECUTE FUNCTION asai._reject_paper_history_mutation();
CREATE TRIGGER paper_order_event_guard_insert
BEFORE INSERT ON asai.paper_order_event
FOR EACH ROW EXECUTE FUNCTION asai._guard_paper_order_event_insert();
CREATE TRIGGER paper_order_event_no_update_delete
BEFORE UPDATE OR DELETE ON asai.paper_order_event
FOR EACH ROW EXECUTE FUNCTION asai._reject_paper_history_mutation();
CREATE TRIGGER paper_order_event_no_truncate
BEFORE TRUNCATE ON asai.paper_order_event
FOR EACH STATEMENT EXECUTE FUNCTION asai._reject_paper_history_mutation();

-- Create an immutable paper-order intent. A repeated request identity returns only the
-- identical original request; a client order ID may never name two intents.
CREATE FUNCTION asai.create_paper_order(
    p_request_id text,
    p_client_order_id text,
    p_symbol text,
    p_side asai.paper_order_side,
    p_order_type asai.paper_order_type,
    p_quantity numeric,
    p_limit_price numeric DEFAULT NULL
)
RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = asai, pg_catalog
AS $$
DECLARE
    v_order_id bigint;
    v_existing asai.paper_order%ROWTYPE;
    v_control asai.safety_control%ROWTYPE;
BEGIN
    IF btrim(COALESCE(p_request_id, '')) = '' OR length(p_request_id) > 200
       OR COALESCE(p_client_order_id, '') !~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$'
       OR COALESCE(p_symbol, '') !~ '^[A-Z][A-Z0-9._/-]{0,31}$'
       OR p_side IS NULL OR p_order_type IS NULL
       OR p_quantity IS NULL OR p_quantity <= 0 OR scale(p_quantity) > 8
       OR p_quantity::text IN ('NaN', 'Infinity', '-Infinity')
       OR (p_limit_price IS NOT NULL AND (p_limit_price <= 0 OR scale(p_limit_price) > 8
           OR p_limit_price::text IN ('NaN', 'Infinity', '-Infinity')))
       OR (p_order_type = 'LIMIT' AND p_limit_price IS NULL)
       OR (p_order_type = 'MARKET' AND p_limit_price IS NOT NULL) THEN
        RAISE EXCEPTION 'invalid paper-order intent' USING ERRCODE = '22023';
    END IF;

    PERFORM pg_advisory_xact_lock(hashtextextended('paper-request:' || p_request_id, 0));
    SELECT * INTO v_existing FROM asai.paper_order WHERE request_id = p_request_id;
    IF FOUND THEN
        IF v_existing.client_order_id IS DISTINCT FROM p_client_order_id
           OR v_existing.symbol IS DISTINCT FROM p_symbol OR v_existing.side IS DISTINCT FROM p_side
           OR v_existing.order_type IS DISTINCT FROM p_order_type OR v_existing.quantity IS DISTINCT FROM p_quantity
           OR v_existing.limit_price IS DISTINCT FROM p_limit_price THEN
            RAISE EXCEPTION 'request identity was reused with a different paper-order intent' USING ERRCODE = '22023';
        END IF;
        RETURN v_existing.order_id;
    END IF;

    -- Serialize new intents against a kill/death latch before writing any order state.
    SELECT * INTO v_control FROM asai.safety_control WHERE singleton FOR UPDATE;
    IF NOT FOUND OR v_control.state <> 'ALIVE' OR v_control.latched THEN
        RAISE EXCEPTION 'paper-order creation denied: safety control is latched (%)', COALESCE(v_control.state::text, 'MISSING')
            USING ERRCODE = '55000';
    END IF;

    -- Distinguish an idempotency conflict from an unrelated unique-index implementation detail.
    IF EXISTS (SELECT 1 FROM asai.paper_order WHERE client_order_id = p_client_order_id) THEN
        RAISE EXCEPTION 'client order ID is already bound to a different paper-order intent' USING ERRCODE = '23505';
    END IF;

    PERFORM set_config('asai.internal_write', 'on', true);
    INSERT INTO asai.paper_order(request_id, client_order_id, symbol, side, order_type, quantity, limit_price)
    VALUES (p_request_id, p_client_order_id, p_symbol, p_side, p_order_type, p_quantity, p_limit_price)
    RETURNING order_id INTO v_order_id;
    INSERT INTO asai.paper_order_event(order_id, event_no, from_state, to_state, reason)
    VALUES (v_order_id, 1, NULL, 'INTENDED', 'paper-only order intent created');
    -- Do not leave the guard-setting enabled for the caller's remaining transaction.
    PERFORM set_config('asai.internal_write', 'off', true);
    RETURN v_order_id;
END;
$$;

-- Record a valid lifecycle observation. This function cannot submit an order anywhere.
CREATE FUNCTION asai.record_paper_order_transition(
    p_order_id bigint,
    p_to_state asai.paper_order_state,
    p_reason text
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = asai, pg_catalog
AS $$
DECLARE
    v_order asai.paper_order%ROWTYPE;
    v_next_event_no integer;
BEGIN
    IF p_order_id IS NULL OR p_to_state IS NULL
       OR btrim(COALESCE(p_reason, '')) = '' OR length(p_reason) > 2000 THEN
        RAISE EXCEPTION 'order ID, target state, and a 1..2000 character reason are required' USING ERRCODE = '22023';
    END IF;
    SELECT * INTO v_order FROM asai.paper_order WHERE order_id = p_order_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'paper order does not exist' USING ERRCODE = '22023';
    END IF;

    IF NOT (
        (v_order.state = 'INTENDED' AND p_to_state IN ('SUBMISSION_ATTEMPTED', 'CANCELLED')) OR
        (v_order.state = 'SUBMISSION_ATTEMPTED' AND p_to_state IN ('SUBMISSION_UNKNOWN', 'ACCEPTED', 'REJECTED')) OR
        (v_order.state = 'SUBMISSION_UNKNOWN' AND p_to_state IN ('ACCEPTED', 'REJECTED', 'CANCEL_REQUESTED', 'CANCELLED')) OR
        (v_order.state = 'ACCEPTED' AND p_to_state IN ('PARTIALLY_FILLED', 'FILLED', 'CANCEL_REQUESTED')) OR
        (v_order.state = 'PARTIALLY_FILLED' AND p_to_state IN ('FILLED', 'CANCEL_REQUESTED')) OR
        (v_order.state = 'CANCEL_REQUESTED' AND p_to_state IN ('CANCELLED', 'PARTIALLY_FILLED', 'FILLED'))
    ) THEN
        RAISE EXCEPTION 'invalid paper-order transition: % to %', v_order.state, p_to_state USING ERRCODE = '22023';
    END IF;

    PERFORM set_config('asai.internal_write', 'on', true);
    UPDATE asai.paper_order SET state = p_to_state, updated_at = clock_timestamp() WHERE order_id = p_order_id;
    SELECT COALESCE(max(event_no), 0) + 1 INTO v_next_event_no FROM asai.paper_order_event WHERE order_id = p_order_id;
    INSERT INTO asai.paper_order_event(order_id, event_no, from_state, to_state, reason)
    VALUES (p_order_id, v_next_event_no, v_order.state, p_to_state, p_reason);
    -- Do not leave the guard-setting enabled for the caller's remaining transaction.
    PERFORM set_config('asai.internal_write', 'off', true);
END;
$$;

-- This only records a simulation lifecycle step. It has no broker/network implementation.
-- It is intentionally legal only from INTENDED; UNKNOWN can never be automatically resubmitted.
CREATE FUNCTION asai.begin_paper_submission(p_order_id bigint, p_reason text)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = asai, pg_catalog
AS $$
DECLARE
    v_control asai.safety_control%ROWTYPE;
BEGIN
    SELECT * INTO v_control FROM asai.safety_control WHERE singleton FOR UPDATE;
    IF NOT FOUND OR v_control.state <> 'ALIVE' OR v_control.latched THEN
        RAISE EXCEPTION 'paper submission attempt denied: safety control is latched (%)', COALESCE(v_control.state::text, 'MISSING')
            USING ERRCODE = '55000';
    END IF;
    PERFORM asai.record_paper_order_transition(p_order_id, 'SUBMISSION_ATTEMPTED', p_reason);
END;
$$;

CREATE FUNCTION asai.mark_paper_submission_timeout(p_order_id bigint, p_reason text)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = asai, pg_catalog
AS $$
BEGIN
    PERFORM asai.record_paper_order_transition(p_order_id, 'SUBMISSION_UNKNOWN', p_reason);
END;
$$;

REVOKE ALL ON asai.paper_order, asai.paper_order_event FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA asai FROM PUBLIC;
REVOKE ALL ON FUNCTION asai.create_paper_order(text, text, text, asai.paper_order_side, asai.paper_order_type, numeric, numeric) FROM PUBLIC;
REVOKE ALL ON FUNCTION asai.record_paper_order_transition(bigint, asai.paper_order_state, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION asai.begin_paper_submission(bigint, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION asai.mark_paper_submission_timeout(bigint, text) FROM PUBLIC;

-- Optional deployment grants. These are effective only after production roles, ownership,
-- membership, and database connection privileges are configured outside this migration.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'asai_order_operator') THEN
        GRANT USAGE ON SCHEMA asai TO asai_order_operator;
        GRANT EXECUTE ON FUNCTION asai.create_paper_order(text, text, text, asai.paper_order_side, asai.paper_order_type, numeric, numeric) TO asai_order_operator;
        GRANT EXECUTE ON FUNCTION asai.record_paper_order_transition(bigint, asai.paper_order_state, text) TO asai_order_operator;
        GRANT EXECUTE ON FUNCTION asai.begin_paper_submission(bigint, text) TO asai_order_operator;
        GRANT EXECUTE ON FUNCTION asai.mark_paper_submission_timeout(bigint, text) TO asai_order_operator;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'asai_reader') THEN
        GRANT USAGE ON SCHEMA asai TO asai_reader;
        GRANT SELECT ON asai.paper_order, asai.paper_order_event TO asai_reader;
    END IF;
END;
$$;

COMMIT;
