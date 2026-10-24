"""Retain typed session identity/history while allowing reviewed package-session deletion."""

from alembic import op

revision = "20261024_0043"
down_revision = "20261024_0042"
branch_labels = None
depends_on = None

UPGRADE_SQL = r"""
CREATE TABLE session_identities (
	client_id UUID NOT NULL,
	purchase_id UUID NOT NULL,
	created_xid TEXT DEFAULT pg_current_xact_id()::text NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_session_identities PRIMARY KEY (id),
	CONSTRAINT uq_session_identities_id_purchase_id_client_id UNIQUE (id, purchase_id, client_id),
	CONSTRAINT fk_session_identities_purchase_id_client_id_package_purchases FOREIGN
  KEY(purchase_id, client_id) REFERENCES package_purchases (id, client_id),
	CONSTRAINT fk_session_identities_client_id_clients FOREIGN KEY(client_id)
    REFERENCES clients (id)
);

CREATE INDEX ix_session_identities_client_id ON session_identities (client_id);

CREATE INDEX ix_session_identities_purchase_id ON session_identities (purchase_id);

CREATE TABLE package_action_receipts (
	request_key UUID NOT NULL,
	request_sha256 VARCHAR(64) NOT NULL,
	operation VARCHAR(24) NOT NULL,
	client_id UUID NOT NULL,
	purchase_id UUID NOT NULL,
	client_version INTEGER NOT NULL,
	purchase_version INTEGER NOT NULL,
	message_id UUID,
	undo_expires_at TIMESTAMP WITH TIME ZONE,
	result JSONB NOT NULL,
	created_xid TEXT DEFAULT pg_current_xact_id()::text NOT NULL,
	actor_id UUID NOT NULL,
	actor_name VARCHAR(200) NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_package_action_receipts PRIMARY KEY (id),
	CONSTRAINT uq_package_action_receipts_actor_id_request_key UNIQUE (actor_id, request_key),
	CONSTRAINT fk_package_action_receipts_purchase_id_client_id_packag_d5ff FOREIGN
  KEY(purchase_id, client_id) REFERENCES package_purchases (id, client_id),
	CONSTRAINT ck_package_action_receipts_operation_values CHECK (operation IN ('deactivate',
  'delete_sessions')),
	CONSTRAINT ck_package_action_receipts_request_digest CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_package_action_receipts_reviewed_versions CHECK (client_version > 0 AND
  purchase_version > 0),
	CONSTRAINT ck_package_action_receipts_undo_scope CHECK (undo_expires_at IS NULL OR (operation =
  'delete_sessions' AND undo_expires_at > created_at)),
	CONSTRAINT fk_package_action_receipts_client_id_clients FOREIGN KEY(client_id) REFERENCES
  clients (id),
	CONSTRAINT uq_package_action_receipts_message_id UNIQUE (message_id),
	CONSTRAINT fk_package_action_receipts_message_id_messages FOREIGN KEY(message_id) REFERENCES
  messages (id),
	CONSTRAINT fk_package_action_receipts_actor_id_staff_users FOREIGN KEY(actor_id) REFERENCES
  staff_users (id),
	CONSTRAINT ck_package_action_receipts_actor_name_required CHECK (length(btrim(actor_name)) > 0)
);

CREATE INDEX ix_package_action_receipts_actor_id ON package_action_receipts (actor_id);

CREATE INDEX ix_package_action_receipts_client_id ON package_action_receipts (client_id);

CREATE INDEX ix_package_action_receipts_purchase_id ON package_action_receipts (purchase_id);

CREATE TABLE session_archives (
	action_id UUID NOT NULL,
	session_id UUID NOT NULL,
	client_id UUID NOT NULL,
	purchase_id UUID NOT NULL,
	trainer_id UUID NOT NULL,
	contents_sha256 VARCHAR(64) DEFAULT '' NOT NULL,
	original_version INTEGER NOT NULL,
	original_created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	original_updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	schedule_slot_id UUID,
	schedule_state VARCHAR(16) NOT NULL,
	session_number INTEGER,
	training_date DATE,
	starts_at TIME WITHOUT TIME ZONE,
	ends_at TIME WITHOUT TIME ZONE,
	status VARCHAR(16) NOT NULL,
	trainer_comments TEXT NOT NULL,
	client_summary TEXT NOT NULL,
	copied_from_session_id UUID,
	whatsapp_opened_at TIMESTAMP WITH TIME ZONE,
	whatsapp_open_count INTEGER NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_session_archives PRIMARY KEY (id),
	CONSTRAINT uq_session_archives_action_id_session_id UNIQUE (action_id, session_id),
	CONSTRAINT uq_session_archives_session_id_original_version UNIQUE
    (session_id, original_version),
	CONSTRAINT fk_session_archives_session_id_purchase_id_client_id_se_59e4 FOREIGN KEY(session_id,
  purchase_id, client_id) REFERENCES session_identities (id, purchase_id, client_id),
	CONSTRAINT fk_session_archives_schedule_slot_id_purchase_id_purcha_deaf FOREIGN
  KEY(schedule_slot_id, purchase_id) REFERENCES purchase_schedule_slots (id, purchase_id),
	CONSTRAINT ck_session_archives_status_values CHECK (status IN ('scheduled', 'planned')),
	CONSTRAINT ck_session_archives_schedule_state_values CHECK
    (schedule_state IN ('booked', 'open')),
	CONSTRAINT ck_session_archives_contents_digest CHECK (contents_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_session_archives_snapshot_versions CHECK (original_version > 0 AND
  whatsapp_open_count >= 0),
	CONSTRAINT ck_session_archives_snapshot_booking CHECK ((schedule_state = 'open' AND
  num_nonnulls(session_number, training_date, starts_at, ends_at, schedule_slot_id) = 0) OR
  (schedule_state = 'booked' AND session_number BETWEEN 1 AND 365 AND training_date IS NOT NULL
  AND starts_at IS NOT NULL AND ends_at IS NOT NULL AND starts_at < ends_at)),
	CONSTRAINT fk_session_archives_action_id_package_action_receipts FOREIGN KEY(action_id)
  REFERENCES package_action_receipts (id),
	CONSTRAINT fk_session_archives_trainer_id_trainers FOREIGN KEY(trainer_id) REFERENCES trainers
  (id),
	CONSTRAINT fk_session_archives_copied_from_session_id_session_identities FOREIGN
  KEY(copied_from_session_id) REFERENCES session_identities (id)
);

CREATE INDEX ix_session_archives_action_id ON session_archives (action_id);

CREATE INDEX ix_session_archives_session_id ON session_archives (session_id);

CREATE TABLE package_deletion_undos (
	action_id UUID NOT NULL,
	request_key UUID NOT NULL,
	request_sha256 VARCHAR(64) NOT NULL,
	message_id UUID NOT NULL,
	result JSONB NOT NULL,
	created_xid TEXT DEFAULT pg_current_xact_id()::text NOT NULL,
	actor_id UUID NOT NULL,
	actor_name VARCHAR(200) NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_package_deletion_undos PRIMARY KEY (id),
	CONSTRAINT uq_package_deletion_undos_actor_id_request_key UNIQUE (actor_id, request_key),
	CONSTRAINT ck_package_deletion_undos_request_digest CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT uq_package_deletion_undos_action_id UNIQUE (action_id),
	CONSTRAINT fk_package_deletion_undos_action_id_package_action_receipts FOREIGN KEY(action_id)
  REFERENCES package_action_receipts (id),
	CONSTRAINT fk_package_deletion_undos_message_id_messages FOREIGN KEY(message_id) REFERENCES
  messages (id),
	CONSTRAINT fk_package_deletion_undos_actor_id_staff_users FOREIGN KEY(actor_id) REFERENCES
  staff_users (id),
	CONSTRAINT ck_package_deletion_undos_actor_name_required CHECK (length(btrim(actor_name)) > 0)
);

CREATE INDEX ix_package_deletion_undos_actor_id ON package_deletion_undos (actor_id);

CREATE FUNCTION ff_session_contents(target uuid) RETURNS text LANGUAGE sql STABLE AS $$
 SELECT encode(sha256(convert_to(jsonb_build_object(
  'plans', (SELECT coalesce(jsonb_agg(to_jsonb(p) ORDER BY p.id), '[]'::jsonb)
            FROM exercise_plan_items p WHERE p.session_id=target),
  'details', (SELECT coalesce(jsonb_agg(to_jsonb(d) ORDER BY d.id), '[]'::jsonb)
              FROM exercise_plan_details d JOIN exercise_plan_items p ON p.id=d.plan_item_id
              WHERE p.session_id=target),
  'results', (SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY r.id), '[]'::jsonb)
              FROM exercise_results r WHERE r.session_id=target)
 )::text, 'UTF8')), 'hex')
$$;
INSERT INTO session_identities(id, created_at, client_id, purchase_id)
SELECT id, created_at, client_id, purchase_id FROM training_sessions;

CREATE FUNCTION ff_session_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO session_identities(id, created_at, client_id, purchase_id)
  VALUES(NEW.id, transaction_timestamp(), NEW.client_id, NEW.purchase_id)
  ON CONFLICT(id) DO NOTHING;
  RETURN NEW;
END $$;
CREATE TRIGGER ff_session_identity BEFORE INSERT ON training_sessions
FOR EACH ROW EXECUTE FUNCTION ff_session_identity();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON session_identities
FOR EACH ROW EXECUTE FUNCTION ff_immutable();
ALTER TABLE training_sessions ADD CONSTRAINT fk_training_sessions_identity
FOREIGN KEY(id,purchase_id,client_id) REFERENCES session_identities(id,purchase_id,client_id);

-- Existing constraint names can differ between generated and handwritten migrations.
-- Restrict the rewrite to reviewed history owners, preserving composite scope and options.
DO $history$
DECLARE item record;
BEGIN
  FOR item IN SELECT c.conname, c.conrelid::regclass AS owner, pg_get_constraintdef(c.oid) AS
  definition
  FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid
  WHERE c.contype='f' AND c.confrelid='training_sessions'::regclass
    AND t.relname IN ('session_booking_receipts','session_postponement_receipts',
      'session_change_receipts','session_plan_receipts','session_outcome_receipts',
      'session_summary_receipts','session_handoff_receipts','change_requests',
      'messages','session_events','training_sessions','exercise_plan_items',
      'exercise_results','assignment_changes')
  LOOP
    EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I', item.owner, item.conname);
    EXECUTE format('ALTER TABLE %s ADD CONSTRAINT %I %s', item.owner, item.conname,
      replace(item.definition, 'REFERENCES training_sessions(', 'REFERENCES session_identities('));
  END LOOP;
END $history$;

CREATE TRIGGER ff_actor BEFORE INSERT ON package_action_receipts
FOR EACH ROW EXECUTE FUNCTION ff_actor();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON package_action_receipts
FOR EACH ROW EXECUTE FUNCTION ff_immutable();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON session_archives
FOR EACH ROW EXECUTE FUNCTION ff_immutable();
CREATE TRIGGER ff_actor BEFORE INSERT ON package_deletion_undos
FOR EACH ROW EXECUTE FUNCTION ff_actor();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON package_deletion_undos
FOR EACH ROW EXECUTE FUNCTION ff_immutable();

CREATE FUNCTION ff_session_archive() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE original training_sessions%ROWTYPE; action package_action_receipts%ROWTYPE; field text;
BEGIN
  SELECT * INTO STRICT original FROM training_sessions WHERE id=NEW.session_id FOR UPDATE;
  SELECT * INTO STRICT action FROM package_action_receipts WHERE id=NEW.action_id;
  NEW.contents_sha256 := ff_session_contents(NEW.session_id);
  IF action.created_xid <> pg_current_xact_id()::text
     OR NOT (action.result->'deletedSessionIds' ? NEW.session_id::text) THEN
    RAISE EXCEPTION 'Archive must be part of its original deletion command' USING ERRCODE='23514';
  END IF;
  IF (action.client_id,action.purchase_id) IS DISTINCT FROM
  (original.client_id,original.purchase_id)
     OR NEW.original_version <> original.version
     OR NEW.original_created_at <> original.created_at
     OR NEW.original_updated_at <> original.updated_at THEN
    RAISE EXCEPTION 'Archive requires the exact reviewed live session' USING ERRCODE='23514';
  END IF;
  FOREACH field IN ARRAY ARRAY['client_id','purchase_id','trainer_id','schedule_slot_id',
    'schedule_state','session_number','training_date','starts_at','ends_at','status',

  'trainer_comments','client_summary','copied_from_session_id','whatsapp_opened_at','whatsapp_open_count']
  LOOP
    IF to_jsonb(NEW)->field IS DISTINCT FROM to_jsonb(original)->field THEN
      RAISE EXCEPTION 'Archive differs from live session: %', field USING ERRCODE='23514';
    END IF;
  END LOOP;
  RETURN NEW;
END $$;
CREATE TRIGGER ff_session_archive BEFORE INSERT ON session_archives
FOR EACH ROW EXECUTE FUNCTION ff_session_archive();

CREATE FUNCTION ff_package_deletion_undo() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE action package_action_receipts%ROWTYPE;
BEGIN
  SELECT * INTO STRICT action FROM package_action_receipts WHERE id=NEW.action_id;
  IF action.operation <> 'delete_sessions' OR action.undo_expires_at IS NULL
     OR action.undo_expires_at <= clock_timestamp()
     OR NOT EXISTS (SELECT 1 FROM session_archives WHERE action_id=action.id) THEN
    RAISE EXCEPTION 'Package action is not reversible' USING ERRCODE='23514';
  END IF;
  NEW.created_xid := pg_current_xact_id()::text;
  RETURN NEW;
END $$;
CREATE TRIGGER ff_package_deletion_undo BEFORE INSERT ON package_deletion_undos
FOR EACH ROW EXECUTE FUNCTION ff_package_deletion_undo();

-- Restoring an old UUID must never reset its version or creation time.
CREATE FUNCTION ff_training_session_version() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE archive session_archives%ROWTYPE; field text;
BEGIN
  IF TG_OP='UPDATE' THEN
    IF NEW.version <> OLD.version+1 OR NEW.id <> OLD.id OR NEW.created_at <> OLD.created_at THEN
      RAISE EXCEPTION 'version or identity mismatch' USING ERRCODE='23514';
    END IF;
    NEW.updated_at := clock_timestamp();
    RETURN NEW;
  END IF;
  SELECT * INTO archive FROM session_archives WHERE session_id=NEW.id
    ORDER BY original_version DESC LIMIT 1;
  IF archive.id IS NULL THEN
    IF NEW.version <> 1 OR NOT EXISTS (SELECT 1 FROM session_identities
      WHERE id=NEW.id AND created_xid=pg_current_xact_id()::text) THEN
      RAISE EXCEPTION 'initial version or reused session identity is invalid' USING ERRCODE='23514';
    END IF;
    NEW.created_at := transaction_timestamp(); NEW.updated_at := NEW.created_at;
    RETURN NEW;
  END IF;
  IF ff_session_contents(NEW.id) <> archive.contents_sha256
     OR (archive.schedule_state='booked' AND archive.training_date + archive.starts_at
         <= (clock_timestamp() AT TIME ZONE 'Asia/Singapore')) THEN
    RAISE EXCEPTION 'Archived session changed or has started' USING ERRCODE='23514';
  END IF;
  IF NEW.version <> archive.original_version+1 OR NEW.created_at <> archive.original_created_at
     OR NOT EXISTS (SELECT 1 FROM package_deletion_undos
       WHERE action_id=archive.action_id AND created_xid=pg_current_xact_id()::text) THEN
    RAISE EXCEPTION 'Restoration requires current atomic Undo evidence and increasing version'
      USING ERRCODE='23514';
  END IF;
  FOREACH field IN ARRAY ARRAY['client_id','purchase_id','trainer_id','schedule_slot_id',
    'schedule_state','session_number','training_date','starts_at','ends_at','status',

  'trainer_comments','client_summary','copied_from_session_id','whatsapp_opened_at','whatsapp_open_count']
  LOOP
    IF to_jsonb(NEW)->field IS DISTINCT FROM to_jsonb(archive)->field THEN
      RAISE EXCEPTION 'Restoration differs from archived session: %', field USING ERRCODE='23514';
    END IF;
  END LOOP;
  NEW.updated_at := clock_timestamp();
  RETURN NEW;
END $$;
DROP TRIGGER ff_version ON training_sessions;
CREATE TRIGGER ff_version BEFORE INSERT OR UPDATE ON training_sessions
FOR EACH ROW EXECUTE FUNCTION ff_training_session_version();
CREATE OR REPLACE FUNCTION ff_session_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE purchase package_purchases%ROWTYPE;
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status IN ('completed', 'cancelled') OR
       OLD.training_date + OLD.starts_at <= (clock_timestamp() AT TIME ZONE 'Asia/Singapore') OR
       EXISTS (SELECT 1 FROM acknowledgements WHERE session_id=OLD.id) OR
       EXISTS (SELECT 1 FROM credit_debits WHERE session_id=OLD.id) OR
       (NOT EXISTS (SELECT 1 FROM session_archives a JOIN package_action_receipts p
           ON p.id=a.action_id WHERE a.session_id=OLD.id AND a.original_version=OLD.version
           AND p.created_xid=pg_current_xact_id()::text) AND (
         EXISTS (SELECT 1 FROM session_events WHERE session_id=OLD.id) OR
         EXISTS (SELECT 1 FROM exercise_plan_items WHERE session_id=OLD.id) OR
         EXISTS (SELECT 1 FROM exercise_results WHERE session_id=OLD.id) OR
         EXISTS (SELECT 1 FROM session_booking_receipts WHERE session_id=OLD.id) OR
         EXISTS (SELECT 1 FROM session_postponement_receipts WHERE session_id=OLD.id) OR
         EXISTS (SELECT 1 FROM session_change_receipts WHERE session_id=OLD.id) OR
         EXISTS (SELECT 1 FROM session_plan_receipts WHERE session_id=OLD.id) OR
         EXISTS (SELECT 1 FROM session_outcome_receipts WHERE session_id=OLD.id) OR
         EXISTS (SELECT 1 FROM session_summary_receipts WHERE session_id=OLD.id) OR
         EXISTS (SELECT 1 FROM session_handoff_receipts WHERE session_id=OLD.id) OR
         EXISTS (SELECT 1 FROM change_requests WHERE session_id=OLD.id) OR
         EXISTS (SELECT 1 FROM messages WHERE session_id=OLD.id) OR
         EXISTS (SELECT 1 FROM assignment_changes WHERE session_id=OLD.id) OR
         EXISTS (SELECT 1 FROM training_sessions WHERE copied_from_session_id=OLD.id))) THEN
      RAISE EXCEPTION 'session contains retained history or is no longer future' USING
    ERRCODE='23514'; END IF;
    RETURN OLD;
  END IF;
  IF TG_OP='UPDATE' AND NEW.session_number IS DISTINCT FROM OLD.session_number
     AND NEW.schedule_state=OLD.schedule_state AND NEW.session_number IS DISTINCT FROM (
       SELECT position FROM (
         SELECT id, row_number() OVER (ORDER BY training_date, starts_at, id) AS position
         FROM training_sessions WHERE purchase_id=NEW.purchase_id AND schedule_state='booked'
       ) numbered WHERE id=NEW.id
     ) THEN
    RAISE EXCEPTION 'immutable field: training_sessions.session_number' USING ERRCODE='23514';
  END IF;
  SELECT * INTO STRICT purchase FROM package_purchases WHERE id=NEW.purchase_id FOR UPDATE;
  IF (TG_OP='INSERT' OR (TG_OP='UPDATE' AND NEW.purchase_id IS DISTINCT FROM OLD.purchase_id))
    AND (SELECT count(*) FROM training_sessions WHERE purchase_id=NEW.purchase_id)
        >= purchase.total_sessions THEN
    RAISE EXCEPTION 'session count exceeds purchased capacity' USING ERRCODE='23514'; END IF;
  IF NEW.session_number > purchase.total_sessions THEN
    RAISE EXCEPTION 'session number exceeds purchased capacity' USING ERRCODE='23514'; END IF;
  IF TG_OP = 'INSERT' AND NOT EXISTS (SELECT 1 FROM session_archives a
    JOIN package_deletion_undos u ON u.action_id=a.action_id
    WHERE a.session_id=NEW.id AND u.created_xid=pg_current_xact_id()::text)
    AND (NEW.training_date < purchase.start_date OR NEW.training_date >
    purchase.end_date) THEN
    RAISE EXCEPTION 'generated session is outside purchase validity' USING ERRCODE='23514'; END IF;
  IF TG_OP = 'UPDATE' AND OLD.status = 'completed' AND
     (NEW.status, NEW.training_date, NEW.starts_at, NEW.ends_at, NEW.trainer_id) IS DISTINCT FROM
     (OLD.status, OLD.training_date, OLD.starts_at, OLD.ends_at, OLD.trainer_id) THEN
    RAISE EXCEPTION 'completed session scheduling is retained evidence' USING ERRCODE='23514'; END
    IF;
  RETURN NEW;
END $$;

"""

DOWNGRADE_SQL = r"""

DO $guard$
BEGIN
 IF EXISTS(SELECT 1 FROM package_action_receipts)
    OR EXISTS(SELECT 1 FROM session_archives)
    OR EXISTS(SELECT 1 FROM package_deletion_undos)
    OR EXISTS(SELECT 1 FROM session_identities i
              WHERE NOT EXISTS(SELECT 1 FROM training_sessions s WHERE s.id=i.id)) THEN
   RAISE EXCEPTION 'Package archive downgrade refused: retained deletion evidence exists';
 END IF;
END;
$guard$;
ALTER TABLE training_sessions DROP CONSTRAINT fk_training_sessions_identity;
DO $history$
DECLARE item record;
BEGIN
 FOR item IN SELECT c.conname, c.conrelid::regclass AS owner,
   pg_get_constraintdef(c.oid) AS definition
 FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid
 WHERE c.contype='f' AND c.confrelid='session_identities'::regclass
   AND t.relname NOT IN ('session_archives')
 LOOP
   EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I', item.owner, item.conname);
   EXECUTE format('ALTER TABLE %s ADD CONSTRAINT %I %s', item.owner, item.conname,
     replace(item.definition, 'REFERENCES session_identities(', 'REFERENCES training_sessions('));
 END LOOP;
END $history$;
DROP TRIGGER ff_session_identity ON training_sessions;
DROP FUNCTION ff_session_identity();
DROP TRIGGER ff_version ON training_sessions;
CREATE TRIGGER ff_version BEFORE INSERT OR UPDATE ON training_sessions
 FOR EACH ROW EXECUTE FUNCTION ff_version();
DROP FUNCTION ff_training_session_version();
DROP TABLE package_archived_media;
DROP TABLE package_action_requests;
DROP FUNCTION ff_package_archive_links();
DROP TABLE package_deletion_undos;
DROP TABLE session_archives;
DROP TABLE package_action_receipts;
DROP TABLE session_identities;
DROP FUNCTION ff_package_deletion_undo();
DROP FUNCTION ff_session_archive();
DROP FUNCTION ff_session_contents(uuid);
CREATE OR REPLACE FUNCTION ff_session_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE purchase package_purchases%ROWTYPE;
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status IN ('completed', 'cancelled') OR
       OLD.training_date + OLD.starts_at <= (clock_timestamp() AT TIME ZONE 'Asia/Singapore') OR
       EXISTS (SELECT 1 FROM acknowledgements WHERE session_id=OLD.id) OR
       EXISTS (SELECT 1 FROM credit_debits WHERE session_id=OLD.id) OR
       EXISTS (SELECT 1 FROM session_events WHERE session_id=OLD.id) THEN
      RAISE EXCEPTION 'session contains retained history or is no longer future' USING
    ERRCODE='23514'; END IF;
    RETURN OLD;
  END IF;
  IF TG_OP='UPDATE' AND NEW.session_number IS DISTINCT FROM OLD.session_number
     AND NEW.schedule_state=OLD.schedule_state AND NEW.session_number IS DISTINCT FROM (
       SELECT position FROM (
         SELECT id, row_number() OVER (ORDER BY training_date, starts_at, id) AS position
         FROM training_sessions WHERE purchase_id=NEW.purchase_id AND schedule_state='booked'
       ) numbered WHERE id=NEW.id
     ) THEN
    RAISE EXCEPTION 'immutable field: training_sessions.session_number' USING ERRCODE='23514';
  END IF;
  SELECT * INTO STRICT purchase FROM package_purchases WHERE id=NEW.purchase_id FOR UPDATE;
  IF (TG_OP='INSERT' OR (TG_OP='UPDATE' AND NEW.purchase_id IS DISTINCT FROM OLD.purchase_id))
    AND (SELECT count(*) FROM training_sessions WHERE purchase_id=NEW.purchase_id)
        >= purchase.total_sessions THEN
    RAISE EXCEPTION 'session count exceeds purchased capacity' USING ERRCODE='23514'; END IF;
  IF NEW.session_number > purchase.total_sessions THEN
    RAISE EXCEPTION 'session number exceeds purchased capacity' USING ERRCODE='23514'; END IF;
  IF TG_OP = 'INSERT' AND (NEW.training_date < purchase.start_date OR NEW.training_date >
    purchase.end_date) THEN
    RAISE EXCEPTION 'generated session is outside purchase validity' USING ERRCODE='23514'; END IF;
  IF TG_OP = 'UPDATE' AND OLD.status = 'completed' AND
     (NEW.status, NEW.training_date, NEW.starts_at, NEW.ends_at, NEW.trainer_id) IS DISTINCT FROM
     (OLD.status, OLD.training_date, OLD.starts_at, OLD.ends_at, OLD.trainer_id) THEN
    RAISE EXCEPTION 'completed session scheduling is retained evidence' USING ERRCODE='23514'; END
    IF;
  RETURN NEW;
END $$;

"""


UPGRADE_SQL += r"""

CREATE TABLE package_archived_media (
    archive_id UUID NOT NULL,
    media_id UUID NOT NULL,
    original_version INTEGER NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_package_archived_media PRIMARY KEY (id),
    CONSTRAINT uq_package_archived_media_archive_id_media_id UNIQUE (archive_id, media_id),
    CONSTRAINT ck_package_archived_media_original_version CHECK (original_version > 0),
    CONSTRAINT fk_package_archived_media_archive_id_session_archives FOREIGN KEY(archive_id)
REFERENCES session_archives (id),
    CONSTRAINT fk_package_archived_media_media_id_media_assets FOREIGN KEY(media_id) REFERENCES
media_assets (id)
)

;

CREATE TABLE package_action_requests (
    action_id UUID NOT NULL,
    request_id UUID NOT NULL,
    resolved_version INTEGER NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_package_action_requests PRIMARY KEY (id),
    CONSTRAINT uq_package_action_requests_action_id_request_id UNIQUE (action_id, request_id),
    CONSTRAINT ck_package_action_requests_resolved_version CHECK (resolved_version > 0),
    CONSTRAINT fk_package_action_requests_action_id_package_action_receipts FOREIGN
KEY(action_id) REFERENCES package_action_receipts (id),
    CONSTRAINT fk_package_action_requests_request_id_change_requests FOREIGN KEY(request_id)
REFERENCES change_requests (id)
)

;
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON package_archived_media
FOR EACH ROW EXECUTE FUNCTION ff_immutable();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON package_action_requests
FOR EACH ROW EXECUTE FUNCTION ff_immutable();
CREATE FUNCTION ff_package_archive_links() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_TABLE_NAME='package_archived_media' THEN
  IF NOT EXISTS (SELECT 1 FROM session_archives a
    JOIN package_action_receipts r ON r.id=a.action_id
    JOIN media_assets m ON m.id=NEW.media_id
    WHERE a.id=NEW.archive_id AND m.session_id=a.session_id
      AND m.status='ready' AND m.version=NEW.original_version
      AND r.created_xid=pg_current_xact_id()::text) THEN
    RAISE EXCEPTION 'Original media archive link is invalid' USING ERRCODE='23514';
  END IF;
 ELSE
  IF NOT EXISTS (SELECT 1 FROM package_action_receipts a
    JOIN change_requests r ON r.id=NEW.request_id
    JOIN session_archives s ON s.action_id=a.id AND s.session_id=r.session_id
    WHERE a.id=NEW.action_id AND r.status='rejected' AND r.version=NEW.resolved_version
      AND a.created_xid=pg_current_xact_id()::text) THEN
    RAISE EXCEPTION 'Resolved request archive link is invalid' USING ERRCODE='23514';
  END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER ff_archive_link BEFORE INSERT ON package_archived_media
FOR EACH ROW EXECUTE FUNCTION ff_package_archive_links();
CREATE TRIGGER ff_archive_link BEFORE INSERT ON package_action_requests
FOR EACH ROW EXECUTE FUNCTION ff_package_archive_links();

"""


def upgrade():
    op.execute(UPGRADE_SQL)


def downgrade():
    op.execute(DOWNGRADE_SQL)
