-- Supplemental disposable-database least-privilege test.
-- The CI workflow creates these NOLOGIN roles before applying 001/002 so the
-- migrations' conditional grants are exercised. This file never creates roles,
-- changes ownership, or grants privileges; it verifies effective grants only.
--
-- Scope: this checks every ordinary/partitioned/foreign table, view, and
-- materialized view currently in schema asai for PostgreSQL's seven relation
-- privileges (SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER).
-- Sequences are checked separately for SELECT, USAGE, and UPDATE. It does not
-- claim to constrain an owner, a superuser, or a role deliberately granted DML:
-- those are trusted deployment principals and must be controlled separately.
--
-- SET ROLE changes current_user, but not session_user. Catalog assertions name
-- each constrained role explicitly and execution checks use SET ROLE, so the
-- superuser/session_user that runs this disposable test is never mistaken for
-- an application principal. asai.internal_write is caller-settable custom GUC
-- state, not a privilege boundary: no role can turn it into table rights.
--
-- 002 currently leaves PUBLIC EXECUTE only on its three non-SECURITY-DEFINER
-- trigger helpers created after its broad revoke. That is deliberately checked
-- as a narrow compatibility fact below; it is not treated as authority to read
-- or write ASAI relations.

BEGIN;

-- Catalog checks establish the intended grant matrix without relying on the
-- migration owner or test runner for an authorization decision.
DO $$
DECLARE
    v_role name;
    v_member name;
    v_function regprocedure;
    v_relation record;
    v_privilege text;
    v_expected boolean;
    v_roles constant name[] := ARRAY[
        'asai_poster', 'asai_safety_operator', 'asai_reader',
        'asai_order_operator', 'asai_noaccess'
    ];
    v_relation_privileges constant text[] := ARRAY[
        'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'
    ];
    v_sequence_privileges constant text[] := ARRAY['SELECT', 'USAGE', 'UPDATE'];
BEGIN
    FOREACH v_role IN ARRAY v_roles LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_roles
            WHERE rolname = v_role
              AND NOT rolcanlogin
              AND NOT rolinherit
              AND NOT rolsuper
              AND NOT rolcreaterole
              AND NOT rolcreatedb
              AND NOT rolreplication
              AND NOT rolbypassrls
        ) THEN
            RAISE EXCEPTION 'required constrained role % is missing or unsafe', v_role;
        END IF;

        -- A capability role must neither inherit nor SET ROLE to another role.
        SELECT parent.rolname INTO v_member
        FROM pg_auth_members AS membership
        JOIN pg_roles AS member ON member.oid = membership.member
        JOIN pg_roles AS parent ON parent.oid = membership.roleid
        WHERE member.rolname = v_role
        LIMIT 1;
        IF FOUND THEN
            RAISE EXCEPTION 'constrained role % is unexpectedly a member of %', v_role, v_member;
        END IF;

        -- Constrained roles are never schema/object owners, which would bypass
        -- ACL checks. Check schema, all ASAI relation kinds, functions, and types.
        IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'asai' AND nspowner = v_role::regrole)
           OR EXISTS (SELECT 1 FROM pg_class AS c JOIN pg_namespace AS n ON n.oid = c.relnamespace
                      WHERE n.nspname = 'asai' AND c.relowner = v_role::regrole)
           OR EXISTS (SELECT 1 FROM pg_proc AS p JOIN pg_namespace AS n ON n.oid = p.pronamespace
                      WHERE n.nspname = 'asai' AND p.proowner = v_role::regrole)
           OR EXISTS (SELECT 1 FROM pg_type AS t JOIN pg_namespace AS n ON n.oid = t.typnamespace
                      WHERE n.nspname = 'asai' AND t.typowner = v_role::regrole) THEN
            RAISE EXCEPTION 'constrained role % unexpectedly owns an ASAI object', v_role;
        END IF;
    END LOOP;

    IF has_schema_privilege('public', 'asai', 'USAGE')
       OR has_schema_privilege('asai_noaccess', 'asai', 'USAGE') THEN
        RAISE EXCEPTION 'PUBLIC or no-access role unexpectedly has schema usage';
    END IF;
    IF NOT has_schema_privilege('asai_poster', 'asai', 'USAGE')
       OR NOT has_schema_privilege('asai_safety_operator', 'asai', 'USAGE')
       OR NOT has_schema_privilege('asai_reader', 'asai', 'USAGE')
       OR NOT has_schema_privilege('asai_order_operator', 'asai', 'USAGE') THEN
        RAISE EXCEPTION 'an intended application role lacks schema usage';
    END IF;

    -- Every relation is checked, not merely the base tables named in an example.
    FOR v_relation IN
        SELECT c.oid, c.relname
        FROM pg_class AS c
        JOIN pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = 'asai' AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
    LOOP
        FOREACH v_role IN ARRAY v_roles LOOP
            FOREACH v_privilege IN ARRAY v_relation_privileges LOOP
                v_expected := v_role = 'asai_reader'
                    AND v_privilege = 'SELECT'
                    AND v_relation.relname IN (
                        'v_journal_lines', 'v_account_balance', 'safety_control',
                        'safety_event', 'paper_order', 'paper_order_event'
                    );
                IF has_table_privilege(v_role, v_relation.oid, v_privilege) IS DISTINCT FROM v_expected THEN
                    RAISE EXCEPTION 'unexpected % privilege for role % on relation %',
                        v_privilege, v_role, v_relation.relname;
                END IF;
            END LOOP;
        END LOOP;
        -- PUBLIC must not be the indirect source of any relation privilege.
        FOREACH v_privilege IN ARRAY v_relation_privileges LOOP
            IF has_table_privilege('public', v_relation.oid, v_privilege) THEN
                RAISE EXCEPTION 'PUBLIC unexpectedly has % on relation %', v_privilege, v_relation.relname;
            END IF;
        END LOOP;
    END LOOP;

    -- Identity sequences are independent ACL-bearing relations; no constrained
    -- role (including the reader) may obtain values or change/read their state.
    FOR v_relation IN
        SELECT c.oid, c.relname
        FROM pg_class AS c JOIN pg_namespace AS n ON n.oid = c.relnamespace
        WHERE n.nspname = 'asai' AND c.relkind = 'S'
    LOOP
        FOREACH v_role IN ARRAY v_roles LOOP
            FOREACH v_privilege IN ARRAY v_sequence_privileges LOOP
                IF has_sequence_privilege(v_role, v_relation.oid, v_privilege) THEN
                    RAISE EXCEPTION 'role % unexpectedly has % on sequence %',
                        v_role, v_privilege, v_relation.relname;
                END IF;
            END LOOP;
        END LOOP;
        FOREACH v_privilege IN ARRAY v_sequence_privileges LOOP
            IF has_sequence_privilege('public', v_relation.oid, v_privilege) THEN
                RAISE EXCEPTION 'PUBLIC unexpectedly has % on sequence %', v_privilege, v_relation.relname;
            END IF;
        END LOOP;
    END LOOP;

    -- Only the designated operational entry points may be executable, and only
    -- by their respective capability role.
    FOREACH v_role IN ARRAY v_roles LOOP
        FOREACH v_function IN ARRAY ARRAY[
            'asai.post_journal(text,text,jsonb,asai.entry_type)'::regprocedure,
            'asai.latch_safety(asai.safety_state,text)'::regprocedure,
            'asai.create_paper_order(text,text,text,asai.paper_order_side,asai.paper_order_type,numeric,numeric)'::regprocedure,
            'asai.record_paper_order_transition(bigint,asai.paper_order_state,text)'::regprocedure,
            'asai.begin_paper_submission(bigint,text)'::regprocedure,
            'asai.mark_paper_submission_timeout(bigint,text)'::regprocedure
        ] LOOP
            v_expected := (v_role = 'asai_poster' AND v_function =
                    'asai.post_journal(text,text,jsonb,asai.entry_type)'::regprocedure)
                OR (v_role = 'asai_safety_operator' AND v_function =
                    'asai.latch_safety(asai.safety_state,text)'::regprocedure)
                OR (v_role = 'asai_order_operator' AND v_function IN (
                    'asai.create_paper_order(text,text,text,asai.paper_order_side,asai.paper_order_type,numeric,numeric)'::regprocedure,
                    'asai.record_paper_order_transition(bigint,asai.paper_order_state,text)'::regprocedure,
                    'asai.begin_paper_submission(bigint,text)'::regprocedure,
                    'asai.mark_paper_submission_timeout(bigint,text)'::regprocedure
                ));
            IF has_function_privilege(v_role, v_function, 'EXECUTE') IS DISTINCT FROM v_expected THEN
                RAISE EXCEPTION 'unexpected EXECUTE grant for role % on %', v_role, v_function;
            END IF;
        END LOOP;
    END LOOP;

    IF EXISTS (
        SELECT 1
        FROM pg_proc AS p JOIN pg_namespace AS n ON n.oid = p.pronamespace
        WHERE n.nspname = 'asai'
          AND has_function_privilege('public', p.oid, 'EXECUTE')
          AND (p.prosecdef OR p.oid::regprocedure NOT IN (
              'asai._reject_paper_history_mutation()'::regprocedure,
              'asai._guard_paper_order_write()'::regprocedure,
              'asai._guard_paper_order_event_insert()'::regprocedure
          ))
    ) THEN
        RAISE EXCEPTION 'PUBLIC EXECUTE is not limited to non-security-definer 002 trigger helpers';
    END IF;
END;
$$;

-- Execute as the constrained role, not as the migration owner. SQLSTATE 42501 is
-- required for authorization denials; trigger/business-rule failures are not
-- treated as privilege enforcement.
SET ROLE asai_poster;
SELECT asai.post_journal(
    'role-test-journal-001',
    'least-privilege test posting',
    '[
      {"account_code":"Asset:Cash","currency":"USD","side":"DEBIT","amount":"1.00"},
      {"account_code":"Equity:Capital","currency":"USD","side":"CREDIT","amount":"1.00"}
    ]'::jsonb,
    'GENERAL'::asai.entry_type
);
DO $$
BEGIN
    BEGIN
        EXECUTE 'SELECT * FROM asai.journal_entry';
        RAISE EXCEPTION 'poster unexpectedly read journal base table';
    EXCEPTION WHEN SQLSTATE '42501' THEN NULL;
    END;
    -- Any caller can set this custom GUC; it must still fail before a table
    -- guard runs because it conveys no UPDATE privilege.
    PERFORM set_config('asai.internal_write', 'on', true);
    BEGIN
        EXECUTE 'UPDATE asai.safety_control SET state = ''HALTED'' WHERE singleton';
        RAISE EXCEPTION 'poster turned caller-settable GUC into table write access';
    EXCEPTION WHEN SQLSTATE '42501' THEN NULL;
    END;
    PERFORM set_config('asai.internal_write', 'off', true);
    BEGIN
        PERFORM asai.latch_safety('HALTED'::asai.safety_state, 'unauthorized test');
        RAISE EXCEPTION 'poster unexpectedly executed safety latch';
    EXCEPTION WHEN SQLSTATE '42501' THEN NULL;
    END;
END;
$$;
RESET ROLE;

SET ROLE asai_order_operator;
SELECT asai.create_paper_order(
    'role-test-paper-request-001',
    'role-test-paper-client-001',
    'MSFT',
    'BUY'::asai.paper_order_side,
    'MARKET'::asai.paper_order_type,
    1.00000000,
    NULL
);
DO $$
BEGIN
    BEGIN
        EXECUTE 'SELECT * FROM asai.paper_order';
        RAISE EXCEPTION 'order operator unexpectedly read paper-order base table';
    EXCEPTION WHEN SQLSTATE '42501' THEN NULL;
    END;
    BEGIN
        PERFORM asai.post_journal('role-test-denied', 'denied', '[]'::jsonb, 'GENERAL'::asai.entry_type);
        RAISE EXCEPTION 'order operator unexpectedly executed posting function';
    EXCEPTION WHEN SQLSTATE '42501' THEN NULL;
    END;
END;
$$;
RESET ROLE;

SET ROLE asai_reader;
DO $$
BEGIN
    IF (SELECT count(*) FROM asai.v_journal_lines) <> 2
       OR (SELECT count(*) FROM asai.paper_order) <> 1
       OR (SELECT venue FROM asai.paper_order LIMIT 1) <> 'PAPER' THEN
        RAISE EXCEPTION 'reader cannot observe expected paper-only test state';
    END IF;
    BEGIN
        EXECUTE 'SELECT * FROM asai.journal_entry';
        RAISE EXCEPTION 'reader unexpectedly read journal base table';
    EXCEPTION WHEN SQLSTATE '42501' THEN NULL;
    END;
    BEGIN
        PERFORM asai.create_paper_order(
            'role-test-reader-denied', 'role-test-reader-denied', 'MSFT',
            'BUY'::asai.paper_order_side, 'MARKET'::asai.paper_order_type, 1, NULL
        );
        RAISE EXCEPTION 'reader unexpectedly created paper order';
    EXCEPTION WHEN SQLSTATE '42501' THEN NULL;
    END;
END;
$$;
RESET ROLE;

SET ROLE asai_noaccess;
DO $$
BEGIN
    BEGIN
        EXECUTE 'SELECT * FROM asai.safety_control';
        RAISE EXCEPTION 'no-access role unexpectedly read safety control';
    EXCEPTION WHEN SQLSTATE '42501' THEN NULL;
    END;
    BEGIN
        EXECUTE 'SELECT asai.latch_safety(''HALTED''::asai.safety_state, ''unauthorized test'')';
        RAISE EXCEPTION 'no-access role unexpectedly executed safety latch';
    EXCEPTION WHEN SQLSTATE '42501' THEN NULL;
    END;
END;
$$;
RESET ROLE;

-- The sole intended safety operator can latch, but still cannot read or write its
-- base table directly. Once latched, previously authorized order creation must
-- fail closed. The paper-only row above is the test's concrete non-live check;
-- this schema has no broker/network execution capability to test.
SET ROLE asai_safety_operator;
SELECT asai.latch_safety('HALTED'::asai.safety_state, 'least-privilege test latch');
DO $$
BEGIN
    BEGIN
        EXECUTE 'UPDATE asai.safety_control SET state = ''ALIVE'' WHERE singleton';
        RAISE EXCEPTION 'safety operator unexpectedly wrote safety control directly';
    EXCEPTION WHEN SQLSTATE '42501' THEN NULL;
    END;
    BEGIN
        EXECUTE 'SELECT * FROM asai.safety_control';
        RAISE EXCEPTION 'safety operator unexpectedly read safety control directly';
    EXCEPTION WHEN SQLSTATE '42501' THEN NULL;
    END;
END;
$$;
RESET ROLE;

SET ROLE asai_order_operator;
DO $$
BEGIN
    BEGIN
        PERFORM asai.create_paper_order(
            'role-test-after-latch', 'role-test-after-latch', 'NVDA',
            'BUY'::asai.paper_order_side, 'MARKET'::asai.paper_order_type, 1, NULL
        );
        RAISE EXCEPTION 'latched system unexpectedly accepted a paper order';
    EXCEPTION WHEN SQLSTATE '55000' THEN NULL;
    END;
END;
$$;
RESET ROLE;

ROLLBACK;
