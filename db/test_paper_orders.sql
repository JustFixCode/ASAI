\set ON_ERROR_STOP on
-- Run only against a disposable database after 001_foundation.sql and 002_paper_orders.sql.
-- The final ROLLBACK leaves no order data or safety latch behind.
BEGIN;
SET LOCAL search_path = asai, pg_catalog;

DO $$
DECLARE
    v_order_id bigint;
    v_retry_id bigint;
    v_limit_order_id bigint;
BEGIN
    IF (SELECT state FROM asai.safety_control WHERE singleton) IS DISTINCT FROM 'ALIVE'
       OR EXISTS (SELECT 1 FROM asai.paper_order) THEN
        RAISE EXCEPTION 'test requires an empty, ALIVE ASAI schema' USING ERRCODE = '55000';
    END IF;

    -- Creation succeeds only as a PAPER order, and an identical request is idempotent.
    v_order_id := asai.create_paper_order(
        'paper-test-request-001', 'paper-test-client-001', 'AAPL', 'BUY', 'MARKET', 2.00000000
    );
    v_retry_id := asai.create_paper_order(
        'paper-test-request-001', 'paper-test-client-001', 'AAPL', 'BUY', 'MARKET', 2.00000000
    );
    IF v_retry_id <> v_order_id OR (SELECT count(*) FROM asai.paper_order) <> 1
       OR (SELECT venue FROM asai.paper_order WHERE order_id = v_order_id) <> 'PAPER'
       OR (SELECT state FROM asai.paper_order WHERE order_id = v_order_id) <> 'INTENDED'
       OR (SELECT count(*) FROM asai.paper_order_event WHERE order_id = v_order_id) <> 1 THEN
        RAISE EXCEPTION 'paper-order create/idempotence invariant failed';
    END IF;

    -- Guard capability must not leak from a guarded function to caller SQL in this transaction.
    BEGIN
        UPDATE asai.paper_order SET state = 'ACCEPTED' WHERE order_id = v_order_id;
        RAISE EXCEPTION 'guarded create leaked direct state-write capability';
    EXCEPTION WHEN SQLSTATE '55000' THEN NULL;
    END;
    BEGIN
        INSERT INTO asai.paper_order_event(order_id, event_no, from_state, to_state, reason)
        VALUES (v_order_id, 2, 'INTENDED', 'ACCEPTED', 'forged direct event');
        RAISE EXCEPTION 'guarded create leaked direct event-write capability';
    EXCEPTION WHEN SQLSTATE '55000' THEN NULL;
    END;

    -- Same request identity cannot be changed.
    BEGIN
        PERFORM asai.create_paper_order(
            'paper-test-request-001', 'paper-test-client-001', 'MSFT', 'BUY', 'MARKET', 2.00000000
        );
        RAISE EXCEPTION 'changed request identity unexpectedly succeeded';
    EXCEPTION WHEN SQLSTATE '22023' THEN NULL;
    END;

    -- A client order ID can never identify two intents.
    BEGIN
        PERFORM asai.create_paper_order(
            'paper-test-request-002', 'paper-test-client-001', 'MSFT', 'SELL', 'MARKET', 1.00000000
        );
        RAISE EXCEPTION 'duplicate client order ID unexpectedly succeeded';
    EXCEPTION WHEN SQLSTATE '23505' THEN NULL;
    END;

    -- Paper-only schema rejects attempts to express an invalid venue through direct DML.
    BEGIN
        INSERT INTO asai.paper_order(request_id, client_order_id, venue, symbol, side, order_type, quantity)
        VALUES ('paper-test-direct-venue', 'paper-test-direct-venue', 'LIVE', 'AAPL', 'BUY', 'MARKET', 1);
        RAISE EXCEPTION 'direct live-venue insertion unexpectedly succeeded';
    EXCEPTION WHEN SQLSTATE '55000' THEN NULL;
    END;

    -- Invalid lifecycle jumps fail closed.
    BEGIN
        PERFORM asai.record_paper_order_transition(v_order_id, 'FILLED', 'cannot fill an unattempted order');
        RAISE EXCEPTION 'invalid lifecycle transition unexpectedly succeeded';
    EXCEPTION WHEN SQLSTATE '22023' THEN NULL;
    END;

    -- A simulated submission attempt records no broker action. A timeout becomes UNKNOWN.
    PERFORM asai.begin_paper_submission(v_order_id, 'simulation attempt started');
    PERFORM asai.mark_paper_submission_timeout(v_order_id, 'simulated response timeout; status ambiguous');
    IF (SELECT state FROM asai.paper_order WHERE order_id = v_order_id) <> 'SUBMISSION_UNKNOWN' THEN
        RAISE EXCEPTION 'submission timeout did not enter SUBMISSION_UNKNOWN';
    END IF;
    BEGIN
        UPDATE asai.paper_order SET state = 'ACCEPTED' WHERE order_id = v_order_id;
        RAISE EXCEPTION 'guarded transition leaked direct state-write capability';
    EXCEPTION WHEN SQLSTATE '55000' THEN NULL;
    END;

    -- UNKNOWN is deliberately non-retryable: it may be reconciled/cancelled, never resubmitted.
    BEGIN
        PERFORM asai.begin_paper_submission(v_order_id, 'automatic retry must be denied');
        RAISE EXCEPTION 'UNKNOWN paper order unexpectedly resubmitted';
    EXCEPTION WHEN SQLSTATE '22023' THEN NULL;
    END;
    IF (SELECT state FROM asai.paper_order WHERE order_id = v_order_id) <> 'SUBMISSION_UNKNOWN' THEN
        RAISE EXCEPTION 'retry denial changed UNKNOWN order state';
    END IF;

    -- Append-only intent and history reject mutation/deletion even by a role with table DML.
    BEGIN
        UPDATE asai.paper_order SET symbol = 'MSFT' WHERE order_id = v_order_id;
        RAISE EXCEPTION 'paper-order intent update unexpectedly succeeded';
    EXCEPTION WHEN SQLSTATE '55000' THEN NULL;
    END;
    BEGIN
        UPDATE asai.paper_order_event SET reason = 'tampered' WHERE order_id = v_order_id AND event_no = 1;
        RAISE EXCEPTION 'paper-order event update unexpectedly succeeded';
    EXCEPTION WHEN SQLSTATE '55000' THEN NULL;
    END;
    BEGIN
        DELETE FROM asai.paper_order_event WHERE order_id = v_order_id AND event_no = 1;
        RAISE EXCEPTION 'paper-order event delete unexpectedly succeeded';
    EXCEPTION WHEN SQLSTATE '55000' THEN NULL;
    END;
    BEGIN
        TRUNCATE asai.paper_order_event;
        RAISE EXCEPTION 'paper-order event truncate unexpectedly succeeded';
    EXCEPTION WHEN SQLSTATE '55000' THEN NULL;
    END;

    -- A valid explicit reconciliation transition remains possible from UNKNOWN.
    PERFORM asai.record_paper_order_transition(v_order_id, 'REJECTED', 'manual paper reconciliation found rejection');
    IF (SELECT state FROM asai.paper_order WHERE order_id = v_order_id) <> 'REJECTED'
       OR (SELECT count(*) FROM asai.paper_order_event WHERE order_id = v_order_id) <> 4 THEN
        RAISE EXCEPTION 'explicit reconciliation did not append exactly one event';
    END IF;

    -- Limit-order constraints are also enforced as part of immutable intent creation.
    v_limit_order_id := asai.create_paper_order(
        'paper-test-request-003', 'paper-test-client-003', 'MSFT', 'SELL', 'LIMIT', 1.25000000, 500.00000000
    );
    IF (SELECT limit_price FROM asai.paper_order WHERE order_id = v_limit_order_id) <> 500.00000000 THEN
        RAISE EXCEPTION 'valid limit paper order was not stored';
    END IF;
    BEGIN
        PERFORM asai.create_paper_order(
            'paper-test-request-004', 'paper-test-client-004', 'MSFT', 'SELL', 'LIMIT', 1.00000000
        );
        RAISE EXCEPTION 'limit order without limit price unexpectedly succeeded';
    EXCEPTION WHEN SQLSTATE '22023' THEN NULL;
    END;
    BEGIN
        PERFORM asai.record_paper_order_transition(v_limit_order_id, NULL, 'NULL state must be rejected explicitly');
        RAISE EXCEPTION 'NULL lifecycle state unexpectedly succeeded';
    EXCEPTION WHEN SQLSTATE '22023' THEN NULL;
    END;
END;
$$;

-- Kill/death latch integration: no new intent or submission attempt may start after a latch.
DO $$
DECLARE
    v_pre_latch_order_id bigint;
BEGIN
    v_pre_latch_order_id := asai.create_paper_order(
        'paper-test-request-005', 'paper-test-client-005', 'NVDA', 'BUY', 'MARKET', 1.00000000
    );
    PERFORM asai.latch_safety('KILLED', 'paper-order test kill latch');

    BEGIN
        PERFORM asai.create_paper_order(
            'paper-test-request-after-kill', 'paper-test-client-after-kill', 'TSLA', 'BUY', 'MARKET', 1.00000000
        );
        RAISE EXCEPTION 'new paper intent unexpectedly succeeded after kill latch';
    EXCEPTION WHEN SQLSTATE '55000' THEN NULL;
    END;
    BEGIN
        PERFORM asai.begin_paper_submission(v_pre_latch_order_id, 'must not start after kill latch');
        RAISE EXCEPTION 'paper submission attempt unexpectedly succeeded after kill latch';
    EXCEPTION WHEN SQLSTATE '55000' THEN NULL;
    END;
END;
$$;

ROLLBACK;
