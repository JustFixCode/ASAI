-- Durable storage for bounded offline historical research output only.
BEGIN;
SET LOCAL search_path = asai, pg_catalog;

-- Deployment creates this NOLOGIN, non-inheriting capability role before this
-- migration.  Do not silently grant a role that can login, inherit authority,
-- administer roles/databases, replicate, bypass RLS, or act as superuser.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'asai_research_writer')
       AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'asai_research_writer'
                   AND (rolcanlogin OR rolinherit OR rolsuper OR rolcreaterole
                        OR rolcreatedb OR rolreplication OR rolbypassrls)) THEN
        RAISE EXCEPTION 'asai_research_writer is unsafe' USING ERRCODE = '55000';
    END IF;
END;
$$;

CREATE TABLE asai.research_run (
    input_sha256 text PRIMARY KEY,
    result jsonb NOT NULL,
    recorded_by name NOT NULL DEFAULT session_user,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (input_sha256 ~ '^[0-9a-f]{64}$'),
    CHECK (jsonb_typeof(result) = 'object'),
    CHECK (octet_length(result::text) <= 1048576)
);

CREATE FUNCTION asai._research_exact_object(p_value jsonb, p_keys text[])
RETURNS boolean LANGUAGE sql IMMUTABLE PARALLEL SAFE SET search_path = pg_catalog AS $$
    SELECT CASE WHEN jsonb_typeof(p_value) = 'object' THEN
        ARRAY(SELECT jsonb_object_keys(p_value) ORDER BY 1) IS NOT DISTINCT FROM p_keys
    ELSE false END
$$;
CREATE FUNCTION asai._research_digest(p_value jsonb)
RETURNS boolean LANGUAGE sql IMMUTABLE PARALLEL SAFE SET search_path = pg_catalog AS $$
    SELECT jsonb_typeof(p_value) = 'string' AND p_value #>> '{}' ~ '^[0-9a-f]{64}$'
$$;
CREATE FUNCTION asai._research_timestamp(p_value jsonb)
RETURNS boolean LANGUAGE sql IMMUTABLE PARALLEL SAFE SET search_path = pg_catalog AS $$
    SELECT jsonb_typeof(p_value) = 'string' AND p_value #>> '{}' ~ '^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d{1,6})?\+00:00$'
$$;
CREATE FUNCTION asai._research_decimal(p_value jsonb)
RETURNS boolean LANGUAGE sql IMMUTABLE PARALLEL SAFE SET search_path = pg_catalog AS $$
    SELECT jsonb_typeof(p_value) = 'string' AND octet_length(p_value #>> '{}') <= 128
       AND p_value #>> '{}' ~ '^-?(0|[1-9][0-9]*)(\.[0-9]+)?$'
$$;

CREATE FUNCTION asai._reject_research_history_mutation()
RETURNS trigger LANGUAGE plpgsql SET search_path = asai, pg_catalog, pg_temp AS $$
BEGIN RAISE EXCEPTION 'ASAI research history is append-only' USING ERRCODE = '55000'; END;
$$;
CREATE TRIGGER research_run_no_update_delete BEFORE UPDATE OR DELETE ON asai.research_run
FOR EACH ROW EXECUTE FUNCTION asai._reject_research_history_mutation();
CREATE TRIGGER research_run_no_truncate BEFORE TRUNCATE ON asai.research_run
FOR EACH STATEMENT EXECUTE FUNCTION asai._reject_research_history_mutation();

-- Receipt only: p_input_sha256 is writer-supplied and is not recomputed from the
-- original input.  A changed engine result under the same supplied key conflicts.
CREATE FUNCTION asai.record_research_run(p_input_sha256 text, p_result jsonb)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER
SET search_path = asai, pg_catalog, pg_temp AS $$
DECLARE
    v_existing jsonb;
    v_disclaimers constant jsonb := '["Historical bars are untrusted caller-supplied fixtures; acceptance does not establish that prices, timestamps, or history are real, complete, or suitable.","The caller-supplied as_of cutoff only constrains this deterministic simulation; it does not independently verify that any bar is genuinely past, closed, timely, complete, or suitable.","Results are deterministic analysis of supplied data, not a forecast, recommendation, validation of a strategy, or financial advice.","No network, credentials, broker, trading, order submission, control, risk, or manifest override path is used; simulated orders are not real orders.","Optional research text is captured as inert untrusted evidence only and has no execution, control, risk, or configuration authority."]'::jsonb;
    v_gap_warning constant text := 'Supplied history contains permitted inter-bar gaps; it is incomplete and does not establish continuous market coverage.';
BEGIN
    IF p_input_sha256 IS NULL OR p_input_sha256 !~ '^[0-9a-f]{64}$' THEN RAISE EXCEPTION 'input_sha256 must be a lowercase SHA-256 digest' USING ERRCODE = '22023'; END IF;
    IF p_result IS NULL OR jsonb_typeof(p_result) <> 'object' OR octet_length(p_result::text) > 1048576 THEN RAISE EXCEPTION 'result must be a bounded JSON object' USING ERRCODE = '22023'; END IF;
    IF NOT asai._research_exact_object(p_result, ARRAY['configuration_sha256','dataset_sha256','input_sha256','mode','provenance','research_document','simulation','trust_disclaimers']) THEN RAISE EXCEPTION 'result does not match research CLI contract' USING ERRCODE = '22023'; END IF;
    IF NOT (
        jsonb_typeof(p_result->'mode') = 'string' AND p_result->>'mode' = 'OFFLINE_HISTORICAL_ANALYSIS_ONLY'
        AND asai._research_digest(p_result->'dataset_sha256') AND asai._research_digest(p_result->'configuration_sha256')
        AND asai._research_digest(p_result->'input_sha256') AND p_result->>'input_sha256' = p_input_sha256
        AND p_result->'trust_disclaimers' = v_disclaimers
        AND (p_result->'research_document' = 'null'::jsonb OR (asai._research_exact_object(p_result->'research_document', ARRAY['content_sha256','risk_authority','untrusted']) AND asai._research_digest(p_result->'research_document'->'content_sha256') AND p_result->'research_document'->'untrusted' = 'true'::jsonb AND p_result->'research_document'->'risk_authority' = 'false'::jsonb))
        AND asai._research_exact_object(p_result->'provenance', ARRAY['as_of','engine_provenance_sha256','status'])
        AND asai._research_timestamp(p_result->'provenance'->'as_of') AND asai._research_digest(p_result->'provenance'->'engine_provenance_sha256')
        AND p_result->'provenance'->>'status' IN ('COMPLETED','COMPLETED_WITH_REJECTIONS','COMPLETED_WITH_UNFILLED','COMPLETED_WITH_REJECTIONS_AND_UNFILLED')
        AND asai._research_exact_object(p_result->'simulation', ARRAY['equity','final_cash','final_equity','final_position','orders','provenance','status','symbol','warnings'])
        AND jsonb_typeof(p_result->'simulation'->'symbol') = 'string' AND p_result->'simulation'->>'symbol' ~ '^[A-Z0-9][A-Z0-9._-]{0,15}$'
        AND asai._research_digest(p_result->'simulation'->'provenance')
        AND p_result->'simulation'->>'status' IN ('COMPLETED','COMPLETED_WITH_REJECTIONS','COMPLETED_WITH_UNFILLED','COMPLETED_WITH_REJECTIONS_AND_UNFILLED')
        AND asai._research_decimal(p_result->'simulation'->'final_cash') AND asai._research_decimal(p_result->'simulation'->'final_position') AND asai._research_decimal(p_result->'simulation'->'final_equity')
        AND jsonb_typeof(p_result->'simulation'->'orders') = 'array' AND jsonb_array_length(p_result->'simulation'->'orders') <= 10000
        AND NOT EXISTS (SELECT 1 FROM jsonb_array_elements(p_result->'simulation'->'orders') o(value) WHERE NOT (asai._research_exact_object(o.value, ARRAY['fee','fill_price','fill_timestamp','quantity','reason','side','signal_timestamp','status']) AND asai._research_timestamp(o.value->'signal_timestamp') AND o.value->>'side' IN ('BUY','SELL') AND o.value->>'status' IN ('FILLED','REJECTED_INSUFFICIENT_CASH','REJECTED_POSITION_LIMIT','REJECTED_NEGATIVE_CASH','UNFILLED_END_OF_DATA') AND asai._research_decimal(o.value->'quantity') AND ((o.value->>'status' = 'UNFILLED_END_OF_DATA' AND o.value->'fill_timestamp' = 'null'::jsonb AND o.value->'fill_price' = 'null'::jsonb AND o.value->'fee' = 'null'::jsonb AND o.value->>'reason' = 'no next documented bar open exists for an auditable fill') OR (o.value->>'status' <> 'UNFILLED_END_OF_DATA' AND asai._research_timestamp(o.value->'fill_timestamp') AND asai._research_decimal(o.value->'fill_price') AND asai._research_decimal(o.value->'fee') AND o.value->>'reason' = CASE o.value->>'status' WHEN 'FILLED' THEN 'documented next-bar open fill after closed-bar signal' WHEN 'REJECTED_INSUFFICIENT_CASH' THEN 'cash cannot cover fill and fee' WHEN 'REJECTED_POSITION_LIMIT' THEN 'max long position would be exceeded' WHEN 'REJECTED_NEGATIVE_CASH' THEN 'sale would make cash negative' END))) IS TRUE)
        AND jsonb_typeof(p_result->'simulation'->'equity') = 'array' AND jsonb_array_length(p_result->'simulation'->'equity') BETWEEN 1 AND 10000
        AND NOT EXISTS (SELECT 1 FROM jsonb_array_elements(p_result->'simulation'->'equity') e(value) WHERE NOT (asai._research_exact_object(e.value, ARRAY['cash','close','equity','position','timestamp']) AND asai._research_timestamp(e.value->'timestamp') AND asai._research_decimal(e.value->'cash') AND asai._research_decimal(e.value->'position') AND asai._research_decimal(e.value->'close') AND asai._research_decimal(e.value->'equity')) IS TRUE)
        AND jsonb_typeof(p_result->'simulation'->'warnings') = 'array' AND (p_result->'simulation'->'warnings' = '[]'::jsonb OR p_result->'simulation'->'warnings' = jsonb_build_array(v_gap_warning))
    ) IS TRUE THEN RAISE EXCEPTION 'result is not bounded offline historical analysis output' USING ERRCODE = '22023'; END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(p_input_sha256, 0));
    SELECT result INTO v_existing FROM asai.research_run WHERE input_sha256 = p_input_sha256;
    IF FOUND THEN IF v_existing <> p_result THEN RAISE EXCEPTION 'input_sha256 was reused with a different result' USING ERRCODE = '22023'; END IF; RETURN p_input_sha256; END IF;
    INSERT INTO asai.research_run(input_sha256, result) VALUES (p_input_sha256, p_result);
    RETURN p_input_sha256;
END;
$$;

REVOKE ALL ON asai.research_run FROM PUBLIC;
REVOKE ALL ON FUNCTION asai._reject_research_history_mutation() FROM PUBLIC;
REVOKE ALL ON FUNCTION asai._research_exact_object(jsonb,text[]) FROM PUBLIC;
REVOKE ALL ON FUNCTION asai._research_digest(jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION asai._research_timestamp(jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION asai._research_decimal(jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION asai.record_research_run(text, jsonb) FROM PUBLIC;
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'asai_research_writer') THEN
        GRANT USAGE ON SCHEMA asai TO asai_research_writer;
        GRANT EXECUTE ON FUNCTION asai.record_research_run(text, jsonb) TO asai_research_writer;
    END IF;
END; $$;
COMMIT;
