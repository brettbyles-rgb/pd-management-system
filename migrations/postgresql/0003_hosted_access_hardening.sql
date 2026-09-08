BEGIN;

-- The application connects as this role. Login is enabled and its password is
-- set separately in the secret-management workflow, never in source control.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pd_management_reader') THEN
        CREATE ROLE pd_management_reader
            NOLOGIN
            NOSUPERUSER
            NOCREATEDB
            NOCREATEROLE
            NOINHERIT
            NOREPLICATION
            NOBYPASSRLS;
    END IF;
END
$$;

-- Supabase's Data API roles and PostgreSQL's implicit PUBLIC role must not be
-- able to read this proof-of-concept schema directly.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM PUBLIC, anon, authenticated;
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC, anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    REVOKE ALL PRIVILEGES ON TABLES FROM PUBLIC, anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    REVOKE ALL PRIVILEGES ON SEQUENCES FROM PUBLIC, anon, authenticated;

-- Cover the migration ledger and any future table already present when this
-- migration runs. The application role receives an explicit SELECT-only policy.
DO $$
DECLARE
    item record;
BEGIN
    FOR item IN
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'public'
    LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', item.tablename);

        IF NOT EXISTS (
            SELECT 1
            FROM pg_policies
            WHERE schemaname = 'public'
              AND tablename = item.tablename
              AND policyname = 'pd_management_reader_select'
        ) THEN
            EXECUTE format(
                'CREATE POLICY pd_management_reader_select ON public.%I FOR SELECT TO pd_management_reader USING (true)',
                item.tablename
            );
        END IF;
    END LOOP;
END
$$;

-- Views execute with the caller's permissions so they cannot bypass RLS using
-- their owner's postgres privileges.
DO $$
DECLARE
    item record;
BEGIN
    FOR item IN
        SELECT viewname
        FROM pg_views
        WHERE schemaname = 'public'
    LOOP
        EXECUTE format(
            'ALTER VIEW public.%I SET (security_invoker = true)',
            item.viewname
        );
    END LOOP;
END
$$;

GRANT CONNECT ON DATABASE postgres TO pd_management_reader;
GRANT USAGE ON SCHEMA public TO pd_management_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO pd_management_reader;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
    GRANT SELECT ON TABLES TO pd_management_reader;

COMMIT;
