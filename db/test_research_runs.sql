-- Disposable-database tests for 003_research_runs.sql.
-- The harness must create asai_research_writer as a constrained NOLOGIN role before
-- applying the migration; this test intentionally does not create or grant roles.

BEGIN;

-- Keep every accepted test receipt identical to the strict Python/SQL contract.
-- The individual negative cases below then alter a single bounded field.
CREATE FUNCTION pg_temp.research_result(p_key text)
RETURNS jsonb LANGUAGE sql IMMUTABLE AS $$
    SELECT jsonb_build_object(
        'mode', 'OFFLINE_HISTORICAL_ANALYSIS_ONLY',
        'simulation', jsonb_build_object(
            'symbol', 'TEST', 'orders', '[]'::jsonb,
            'equity', jsonb_build_array(jsonb_build_object(
                'timestamp', '2026-01-01T00:00:00+00:00', 'cash', '100',
                'position', '0', 'close', '1', 'equity', '100')),
            'final_cash', '100', 'final_position', '0', 'final_equity', '100',
            'provenance', p_key, 'status', 'COMPLETED', 'warnings', '[]'::jsonb),
        'provenance', jsonb_build_object(
            'as_of', '2026-01-01T00:00:00+00:00', 'status', 'COMPLETED',
            'engine_provenance_sha256', p_key),
        'dataset_sha256', repeat('b', 64), 'configuration_sha256', repeat('c', 64),
        'input_sha256', p_key, 'research_document', 'null'::jsonb,
        'trust_disclaimers', jsonb_build_array(
            'Historical bars are untrusted caller-supplied fixtures; acceptance does not establish that prices, timestamps, or history are real, complete, or suitable.',
            'The caller-supplied as_of cutoff only constrains this deterministic simulation; it does not independently verify that any bar is genuinely past, closed, timely, complete, or suitable.',
            'Results are deterministic analysis of supplied data, not a forecast, recommendation, validation of a strategy, or financial advice.',
            'No network, credentials, broker, trading, order submission, control, risk, or manifest override path is used; simulated orders are not real orders.',
            'Optional research text is captured as inert untrusted evidence only and has no execution, control, risk, or configuration authority.'))
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_roles
        WHERE rolname = 'asai_research_writer'
          AND NOT rolcanlogin AND NOT rolinherit AND NOT rolsuper
          AND NOT rolcreaterole AND NOT rolcreatedb AND NOT rolreplication
          AND NOT rolbypassrls
    ) THEN
        RAISE EXCEPTION 'asai_research_writer is missing or unsafe';
    END IF;
    IF NOT has_schema_privilege('asai_research_writer', 'asai', 'USAGE')
       OR NOT has_function_privilege('asai_research_writer',
            'asai.record_research_run(text,jsonb)'::regprocedure, 'EXECUTE') THEN
        RAISE EXCEPTION 'research writer lacks its sole capability';
    END IF;
    IF has_table_privilege('asai_research_writer', 'asai.research_run', 'SELECT')
       OR has_table_privilege('asai_research_writer', 'asai.research_run', 'INSERT')
       OR has_table_privilege('asai_research_writer', 'asai.research_run', 'UPDATE')
       OR has_table_privilege('asai_research_writer', 'asai.research_run', 'DELETE')
       OR has_table_privilege('asai_research_writer', 'asai.research_run', 'TRUNCATE')
       OR has_function_privilege('asai_research_writer',
            'asai.post_journal(text,text,jsonb,asai.entry_type)'::regprocedure, 'EXECUTE')
       OR has_function_privilege('asai_research_writer',
            'asai.create_paper_order(text,text,text,asai.paper_order_side,asai.paper_order_type,numeric,numeric)'::regprocedure, 'EXECUTE') THEN
        RAISE EXCEPTION 'research writer has history or execution authority';
    END IF;
END;
$$;

SET ROLE asai_research_writer;

SELECT asai.record_research_run(
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    pg_temp.research_result('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')
) AS normal_insert;

-- Exact same JSON is an idempotent retry.
SELECT asai.record_research_run(
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    pg_temp.research_result('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')
) AS idempotent_retry;

DO $$
BEGIN
    BEGIN
        PERFORM asai.record_research_run(
            'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
            jsonb_set(pg_temp.research_result('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'),
                      '{simulation,status}', '"COMPLETED_WITH_UNFILLED"'::jsonb));
        RAISE EXCEPTION 'different result unexpectedly accepted for same digest';
    EXCEPTION WHEN SQLSTATE '22023' THEN NULL;
    END;
    BEGIN
        PERFORM asai.record_research_run(
            'not-a-digest',
            '{"mode":"OFFLINE_HISTORICAL_ANALYSIS_ONLY"}'::jsonb);
        RAISE EXCEPTION 'malformed result unexpectedly accepted';
    EXCEPTION WHEN SQLSTATE '22023' THEN NULL;
    END;
    BEGIN
        EXECUTE 'SELECT * FROM asai.research_run';
        RAISE EXCEPTION 'writer unexpectedly read research history';
    EXCEPTION WHEN SQLSTATE '42501' THEN NULL;
    END;
    BEGIN
        EXECUTE 'UPDATE asai.research_run SET result = result';
        RAISE EXCEPTION 'writer unexpectedly changed research history';
    EXCEPTION WHEN SQLSTATE '42501' THEN NULL;
    END;
    BEGIN
        EXECUTE 'DELETE FROM asai.research_run';
        RAISE EXCEPTION 'writer unexpectedly deleted research history';
    EXCEPTION WHEN SQLSTATE '42501' THEN NULL;
    END;
    BEGIN
        EXECUTE 'TRUNCATE asai.research_run';
        RAISE EXCEPTION 'writer unexpectedly truncated research history';
    EXCEPTION WHEN SQLSTATE '42501' THEN NULL;
    END;
    BEGIN
        EXECUTE 'SELECT asai.post_journal(''wrong-capability'', ''nope'', ''[]''::jsonb, ''GENERAL''::asai.entry_type)';
        RAISE EXCEPTION 'writer unexpectedly called journal function';
    EXCEPTION WHEN SQLSTATE '42501' THEN NULL;
    END;
END;
$$;
RESET ROLE;

-- A SQL NULL from a JSON operator must never turn a failed check into a
-- pass. These payloads preserve the top-level shape but poison values/types.
DO $nulls$
DECLARE
    v_key constant text := 'ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff';
    v_result jsonb := pg_temp.research_result(v_key);
    v_bad jsonb;
BEGIN
    FOREACH v_bad IN ARRAY ARRAY[
        jsonb_set(v_result, '{dataset_sha256}', 'null'::jsonb),
        jsonb_set(v_result, '{mode}', 'true'::jsonb),
        jsonb_set(v_result, '{simulation,provenance}', 'null'::jsonb),
        jsonb_set(v_result, '{provenance,engine_provenance_sha256}', 'null'::jsonb)
    ] LOOP
        BEGIN
            PERFORM asai.record_research_run(v_key, v_bad);
            RAISE EXCEPTION 'JSON null/type confusion unexpectedly accepted';
        EXCEPTION WHEN SQLSTATE '22023' THEN NULL;
        END;
    END LOOP;
END;
$nulls$;

-- This input compresses well in PostgreSQL, but it exceeds the logical JSON
-- byte bound. pg_column_size() would not be a safe limit for this payload.
DO $size$
BEGIN
    BEGIN
        INSERT INTO asai.research_run(input_sha256, result)
        VALUES ('9999999999999999999999999999999999999999999999999999999999999999',
                jsonb_build_object('padding', repeat('x', 1048576)));
        RAISE EXCEPTION 'oversized compressed JSON unexpectedly persisted';
    EXCEPTION WHEN SQLSTATE '23514' THEN NULL;
    END;
END;
$size$;

DO $identity$
DECLARE
    v_recorded_by name;
BEGIN
    SELECT recorded_by INTO v_recorded_by
    FROM asai.research_run
    WHERE input_sha256 = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
    IF v_recorded_by IS DISTINCT FROM session_user THEN
        RAISE EXCEPTION 'research writer identity was not stored as session_user';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_proc p
        WHERE p.oid = 'asai.record_research_run(text,jsonb)'::regprocedure
          AND p.prosecdef
          AND p.proconfig @> ARRAY['search_path=asai, pg_catalog, pg_temp']
    ) THEN
        RAISE EXCEPTION 'security-definer research function lacks hardened search_path';
    END IF;
END;
$identity$;

-- Trigger protections remain effective even for the migration owner.  Superusers
-- and object owners remain PostgreSQL ACL/trigger-bypass deployment principals.
DO $$
BEGIN
    BEGIN
        UPDATE asai.research_run SET result = result
        WHERE input_sha256 = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
        RAISE EXCEPTION 'append-only update unexpectedly succeeded';
    EXCEPTION WHEN SQLSTATE '55000' THEN NULL;
    END;
    BEGIN
        DELETE FROM asai.research_run
        WHERE input_sha256 = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa';
        RAISE EXCEPTION 'append-only delete unexpectedly succeeded';
    EXCEPTION WHEN SQLSTATE '55000' THEN NULL;
    END;
END;
$$;

COMMIT;

-- The function insert participates in the caller transaction and rolls back cleanly.
BEGIN;
SET ROLE asai_research_writer;
SELECT asai.record_research_run(
    'dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd',
    pg_temp.research_result('dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd')
);
RESET ROLE;
ROLLBACK;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM asai.research_run
               WHERE input_sha256 = 'dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd') THEN
        RAISE EXCEPTION 'rolled-back research run persisted';
    END IF;
END;
$$;

-- A separate backend holds the same digest lock while the local retry waits.
-- dblink is a PostgreSQL contrib extension used only in this disposable test.
CREATE EXTENSION IF NOT EXISTS dblink;
DO $test$
DECLARE
    v_key constant text := 'eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee';
    v_result jsonb := pg_temp.research_result(v_key);
    v_started timestamptz;
    v_attempt integer;
BEGIN
    PERFORM dblink_connect('research_run_lock_test', format(
        'port=%s dbname=%s user=%s',
        current_setting('port'), current_database(), session_user));
    PERFORM dblink_send_query('research_run_lock_test', format(
        'BEGIN; SET ROLE asai_research_writer; SELECT asai.record_research_run(%L, %L::jsonb); SELECT pg_sleep(1); COMMIT;',
        v_key, v_result::text));
    FOR v_attempt IN 1..100 LOOP
        EXIT WHEN EXISTS (SELECT 1 FROM pg_locks
                          WHERE locktype = 'advisory' AND granted
                            AND pid <> pg_backend_pid());
        PERFORM pg_sleep(0.01);
    END LOOP;
    IF NOT EXISTS (SELECT 1 FROM pg_locks
                   WHERE locktype = 'advisory' AND granted
                     AND pid <> pg_backend_pid()) THEN
        RAISE EXCEPTION 'concurrent backend did not acquire research-run lock';
    END IF;
    v_started := clock_timestamp();
    PERFORM asai.record_research_run(v_key, v_result);
    IF clock_timestamp() - v_started < interval '500 milliseconds' THEN
        RAISE EXCEPTION 'same-key retry did not wait for concurrent transaction';
    END IF;
    PERFORM * FROM dblink_get_result('research_run_lock_test') AS result(status text);
    PERFORM dblink_disconnect('research_run_lock_test');
END;
$test$;
