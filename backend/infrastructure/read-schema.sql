-- Run only through an already authorized private database connection.
-- No business rows or credentials are selected. Errors stop psql via ON_ERROR_STOP.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '15s';
SET LOCAL lock_timeout = '3s';
SELECT jsonb_build_object(
  'database', current_database(),
  'database_user', current_user,
  'observed_at', transaction_timestamp(),
  'transaction_read_only', current_setting('transaction_read_only'),
  'server_version', current_setting('server_version'),
  'alembic_revisions', (SELECT jsonb_agg(version_num ORDER BY version_num)
                        FROM public.alembic_version),
  'tables', (SELECT jsonb_agg(jsonb_build_object(
      'name', c.relname, 'owner', pg_get_userbyid(c.relowner),
      'row_security', c.relrowsecurity, 'force_row_security', c.relforcerowsecurity,
      'columns', (SELECT jsonb_agg(jsonb_build_object(
          'name', a.attname, 'type', format_type(a.atttypid, a.atttypmod),
          'not_null', a.attnotnull, 'generated', a.attgenerated
        ) ORDER BY a.attnum)
        FROM pg_attribute a WHERE a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped),
      'runtime_privileges', (SELECT jsonb_object_agg(p, CASE WHEN r.oid IS NULL THEN NULL
          ELSE has_table_privilege(r.oid, c.oid, p) END)
        FROM unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER']) p
        LEFT JOIN pg_roles r ON r.rolname='fitfinity_app')
    ) ORDER BY c.relname)
    FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname='public' AND c.relkind IN ('r','p')),
  'constraints', (SELECT jsonb_agg(jsonb_build_object(
      'table', c.relname, 'name', k.conname, 'type', k.contype,
      'validated', k.convalidated, 'definition', pg_get_constraintdef(k.oid)
    ) ORDER BY c.relname,k.conname)
    FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
    JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public'),
  'triggers', (SELECT jsonb_agg(jsonb_build_object(
      'table', c.relname, 'name', t.tgname, 'enabled', t.tgenabled,
      'definition', pg_get_triggerdef(t.oid)
    ) ORDER BY c.relname,t.tgname)
    FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
    JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname='public' AND NOT t.tgisinternal),
  'indexes', (SELECT jsonb_agg(jsonb_build_object(
      'table', c.relname, 'name', idx.relname, 'valid', i.indisvalid, 'ready', i.indisready,
      'definition', pg_get_indexdef(i.indexrelid)
    ) ORDER BY c.relname,idx.relname)
    FROM pg_index i JOIN pg_class c ON c.oid=i.indrelid
    JOIN pg_class idx ON idx.oid=i.indexrelid JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname='public'),
  'roles', (SELECT jsonb_agg(jsonb_build_object(
      'name', rolname, 'superuser', rolsuper, 'create_role', rolcreaterole,
      'create_database', rolcreatedb, 'bypass_row_security', rolbypassrls
    ) ORDER BY rolname)
    FROM pg_roles WHERE rolname IN ('fitfinity_app','fitfinity_migrator'))
);
ROLLBACK;
