"""Typed session compensation evidence; original domain history remains immutable."""

from alembic import op

revision = "20261024_0045"
down_revision = "20261024_0044"
branch_labels = None
depends_on = None

UPGRADE_SQL = r"""

CREATE TABLE session_mutations (
    operation VARCHAR(64) NOT NULL,
    request_key UUID NOT NULL,
    actor_role VARCHAR(16) NOT NULL,
    trainer_id UUID,
    message_id UUID NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_xid TEXT DEFAULT pg_current_xact_id()::text NOT NULL,
    actor_id UUID NOT NULL,
    actor_name VARCHAR(200) NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_session_mutations PRIMARY KEY (id),
    CONSTRAINT uq_session_mutations_actor_id_operation_request_key UNIQUE (actor_id, operation,
    request_key),
    CONSTRAINT ck_session_mutations_actor_role_values CHECK (actor_role IN ('owner', 'admin',
    'trainer')),
    CONSTRAINT fk_session_mutations_trainer_id_trainers FOREIGN KEY(trainer_id) REFERENCES
    trainers (id),
    CONSTRAINT uq_session_mutations_message_id UNIQUE (message_id),
    CONSTRAINT fk_session_mutations_message_id_messages FOREIGN KEY(message_id) REFERENCES
    messages (id),
    CONSTRAINT fk_session_mutations_actor_id_staff_users FOREIGN KEY(actor_id) REFERENCES
    staff_users (id),
    CONSTRAINT ck_session_mutations_actor_name_required CHECK (length(btrim(actor_name)) > 0)
)

;
CREATE INDEX ix_session_mutations_actor_id ON session_mutations (actor_id);

CREATE TABLE mutation_change_requests (
    kind VARCHAR(32) NOT NULL,
    trainer_id UUID NOT NULL,
    client_id UUID,
    purchase_id UUID,
    session_id UUID,
    status VARCHAR(16) NOT NULL,
    mutation_id UUID NOT NULL,
    entity_id UUID NOT NULL,
    side VARCHAR(8) NOT NULL,
    version INTEGER NOT NULL,
    CONSTRAINT pk_mutation_change_requests PRIMARY KEY (mutation_id, entity_id, side),
    CONSTRAINT ck_mutation_change_requests_side_values CHECK (side IN ('before', 'after')),
    CONSTRAINT fk_mutation_change_requests_mutation_id_session_mutations FOREIGN
    KEY(mutation_id) REFERENCES session_mutations (id),
    CONSTRAINT ck_mutation_change_requests_positive_version CHECK (version > 0)
)

;

CREATE TABLE mutation_clients (
    trainer_id UUID NOT NULL,
    status VARCHAR(16) NOT NULL,
    lifecycle_event_id UUID,
    mutation_id UUID NOT NULL,
    entity_id UUID NOT NULL,
    side VARCHAR(8) NOT NULL,
    version INTEGER NOT NULL,
    CONSTRAINT pk_mutation_clients PRIMARY KEY (mutation_id, entity_id, side),
    CONSTRAINT ck_mutation_clients_side_values CHECK (side IN ('before', 'after')),
    CONSTRAINT fk_mutation_clients_mutation_id_session_mutations FOREIGN KEY(mutation_id)
    REFERENCES session_mutations (id),
    CONSTRAINT ck_mutation_clients_positive_version CHECK (version > 0)
)

;

CREATE TABLE mutation_exercise_plan_details (
    plan_item_id UUID NOT NULL,
    detail_key VARCHAR(200) NOT NULL,
    position INTEGER NOT NULL,
    value TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    mutation_id UUID NOT NULL,
    entity_id UUID NOT NULL,
    side VARCHAR(8) NOT NULL,
    version INTEGER NOT NULL,
    CONSTRAINT pk_mutation_exercise_plan_details PRIMARY KEY (mutation_id, entity_id, side),
    CONSTRAINT ck_mutation_exercise_plan_details_side_values CHECK (side IN ('before', 'after')),
    CONSTRAINT fk_mutation_exercise_plan_details_mutation_id_session_mutations FOREIGN
    KEY(mutation_id) REFERENCES session_mutations (id),
    CONSTRAINT ck_mutation_exercise_plan_details_positive_version CHECK (version > 0)
)

;

CREATE TABLE mutation_exercise_plan_items (
    session_id UUID NOT NULL,
    exercise_id UUID,
    position INTEGER,
    retired_at TIMESTAMP WITH TIME ZONE,
    name VARCHAR(200) NOT NULL,
    weight VARCHAR(100) NOT NULL,
    reps VARCHAR(100) NOT NULL,
    rounds VARCHAR(100) NOT NULL,
    rest VARCHAR(100) NOT NULL,
    notes TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    mutation_id UUID NOT NULL,
    entity_id UUID NOT NULL,
    side VARCHAR(8) NOT NULL,
    version INTEGER NOT NULL,
    CONSTRAINT pk_mutation_exercise_plan_items PRIMARY KEY (mutation_id, entity_id, side),
    CONSTRAINT ck_mutation_exercise_plan_items_side_values CHECK (side IN ('before', 'after')),
    CONSTRAINT fk_mutation_exercise_plan_items_mutation_id_session_mutations FOREIGN
    KEY(mutation_id) REFERENCES session_mutations (id),
    CONSTRAINT ck_mutation_exercise_plan_items_positive_version CHECK (version > 0)
)

;

CREATE TABLE mutation_exercise_results (
    session_id UUID NOT NULL,
    plan_item_id UUID,
    name VARCHAR(200) NOT NULL,
    load_kg NUMERIC(9, 4) NOT NULL,
    reps INTEGER NOT NULL,
    sets INTEGER NOT NULL,
    retired_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    mutation_id UUID NOT NULL,
    entity_id UUID NOT NULL,
    side VARCHAR(8) NOT NULL,
    version INTEGER NOT NULL,
    CONSTRAINT pk_mutation_exercise_results PRIMARY KEY (mutation_id, entity_id, side),
    CONSTRAINT ck_mutation_exercise_results_side_values CHECK (side IN ('before', 'after')),
    CONSTRAINT fk_mutation_exercise_results_mutation_id_session_mutations FOREIGN
    KEY(mutation_id) REFERENCES session_mutations (id),
    CONSTRAINT ck_mutation_exercise_results_positive_version CHECK (version > 0)
)

;

CREATE TABLE mutation_media_assets (
    session_id UUID,
    original_session_id UUID,
    original_plan_item_id UUID,
    status VARCHAR(16) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE,
    mutation_id UUID NOT NULL,
    entity_id UUID NOT NULL,
    side VARCHAR(8) NOT NULL,
    version INTEGER NOT NULL,
    CONSTRAINT pk_mutation_media_assets PRIMARY KEY (mutation_id, entity_id, side),
    CONSTRAINT ck_mutation_media_assets_side_values CHECK (side IN ('before', 'after')),
    CONSTRAINT fk_mutation_media_assets_mutation_id_session_mutations FOREIGN KEY(mutation_id)
    REFERENCES session_mutations (id),
    CONSTRAINT ck_mutation_media_assets_positive_version CHECK (version > 0)
)

;

CREATE TABLE mutation_package_purchases (
    client_id UUID NOT NULL,
    trainer_id UUID NOT NULL,
    status VARCHAR(16) NOT NULL,
    lifecycle_event_id UUID,
    mutation_id UUID NOT NULL,
    entity_id UUID NOT NULL,
    side VARCHAR(8) NOT NULL,
    version INTEGER NOT NULL,
    CONSTRAINT pk_mutation_package_purchases PRIMARY KEY (mutation_id, entity_id, side),
    CONSTRAINT ck_mutation_package_purchases_side_values CHECK (side IN ('before', 'after')),
    CONSTRAINT fk_mutation_package_purchases_mutation_id_session_mutations FOREIGN
    KEY(mutation_id) REFERENCES session_mutations (id),
    CONSTRAINT ck_mutation_package_purchases_positive_version CHECK (version > 0)
)

;

CREATE TABLE mutation_purchase_schedule_slots (
    purchase_id UUID NOT NULL,
    weekday INTEGER NOT NULL,
    starts_at TIME WITHOUT TIME ZONE NOT NULL,
    ends_at TIME WITHOUT TIME ZONE NOT NULL,
    mutation_id UUID NOT NULL,
    entity_id UUID NOT NULL,
    side VARCHAR(8) NOT NULL,
    version INTEGER NOT NULL,
    CONSTRAINT pk_mutation_purchase_schedule_slots PRIMARY KEY (mutation_id, entity_id, side),
    CONSTRAINT ck_mutation_purchase_schedule_slots_side_values CHECK (side IN ('before', 'after')),
    CONSTRAINT fk_mutation_purchase_schedule_slots_mutation_id_session_02ef FOREIGN
    KEY(mutation_id) REFERENCES session_mutations (id),
    CONSTRAINT ck_mutation_purchase_schedule_slots_positive_version CHECK (version > 0)
)

;

CREATE TABLE mutation_scopes (
    mutation_id UUID NOT NULL,
    client_id UUID,
    trainer_id UUID,
    session_id UUID,
    sha256 VARCHAR(64) NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_mutation_scopes PRIMARY KEY (id),
    CONSTRAINT ck_mutation_scopes_one_target
    CHECK (num_nonnulls(client_id, trainer_id, session_id) = 1),
    CONSTRAINT ck_mutation_scopes_scope_digest CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT fk_mutation_scopes_mutation_id_session_mutations FOREIGN KEY(mutation_id)
    REFERENCES session_mutations (id),
    CONSTRAINT fk_mutation_scopes_client_id_clients FOREIGN KEY(client_id) REFERENCES clients (id),
    CONSTRAINT fk_mutation_scopes_trainer_id_trainers FOREIGN KEY(trainer_id) REFERENCES
    trainers (id)
)

;
CREATE INDEX ix_mutation_scopes_mutation_id ON mutation_scopes (mutation_id);

CREATE TABLE mutation_staff_users (
    role VARCHAR(16) NOT NULL,
    status VARCHAR(16) NOT NULL,
    mutation_id UUID NOT NULL,
    entity_id UUID NOT NULL,
    side VARCHAR(8) NOT NULL,
    version INTEGER NOT NULL,
    CONSTRAINT pk_mutation_staff_users PRIMARY KEY (mutation_id, entity_id, side),
    CONSTRAINT ck_mutation_staff_users_side_values CHECK (side IN ('before', 'after')),
    CONSTRAINT fk_mutation_staff_users_mutation_id_session_mutations FOREIGN KEY(mutation_id)
    REFERENCES session_mutations (id),
    CONSTRAINT ck_mutation_staff_users_positive_version CHECK (version > 0)
)

;

CREATE TABLE mutation_trainers (
    user_id UUID,
    status VARCHAR(16) NOT NULL,
    mutation_id UUID NOT NULL,
    entity_id UUID NOT NULL,
    side VARCHAR(8) NOT NULL,
    version INTEGER NOT NULL,
    CONSTRAINT pk_mutation_trainers PRIMARY KEY (mutation_id, entity_id, side),
    CONSTRAINT ck_mutation_trainers_side_values CHECK (side IN ('before', 'after')),
    CONSTRAINT fk_mutation_trainers_mutation_id_session_mutations FOREIGN KEY(mutation_id)
    REFERENCES session_mutations (id),
    CONSTRAINT ck_mutation_trainers_positive_version CHECK (version > 0)
)

;

CREATE TABLE mutation_training_sessions (
    client_id UUID NOT NULL,
    purchase_id UUID NOT NULL,
    trainer_id UUID NOT NULL,
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
    mutation_id UUID NOT NULL,
    entity_id UUID NOT NULL,
    side VARCHAR(8) NOT NULL,
    version INTEGER NOT NULL,
    CONSTRAINT pk_mutation_training_sessions PRIMARY KEY (mutation_id, entity_id, side),
    CONSTRAINT ck_mutation_training_sessions_side_values CHECK (side IN ('before', 'after')),
    CONSTRAINT fk_mutation_training_sessions_mutation_id_session_mutations FOREIGN
    KEY(mutation_id) REFERENCES session_mutations (id),
    CONSTRAINT ck_mutation_training_sessions_positive_version CHECK (version > 0)
)

;

CREATE TABLE session_mutation_undos (
    mutation_id UUID NOT NULL,
    request_key UUID NOT NULL,
    request_sha256 VARCHAR(64) NOT NULL,
    message_id UUID NOT NULL,
    result JSONB NOT NULL,
    created_xid TEXT DEFAULT pg_current_xact_id()::text NOT NULL,
    actor_id UUID NOT NULL,
    actor_name VARCHAR(200) NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_session_mutation_undos PRIMARY KEY (id),
    CONSTRAINT uq_session_mutation_undos_actor_id_request_key UNIQUE (actor_id, request_key),
    CONSTRAINT ck_session_mutation_undos_request_digest CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT uq_session_mutation_undos_mutation_id UNIQUE (mutation_id),
    CONSTRAINT fk_session_mutation_undos_mutation_id_session_mutations FOREIGN KEY(mutation_id)
    REFERENCES session_mutations (id),
    CONSTRAINT fk_session_mutation_undos_message_id_messages FOREIGN KEY(message_id) REFERENCES
    messages (id),
    CONSTRAINT fk_session_mutation_undos_actor_id_staff_users FOREIGN KEY(actor_id) REFERENCES
    staff_users (id),
    CONSTRAINT ck_session_mutation_undos_actor_name_required CHECK (length(btrim(actor_name)) > 0)
)

;
CREATE INDEX ix_session_mutation_undos_actor_id ON session_mutation_undos (actor_id);
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON session_mutations FOR EACH ROW EXECUTE
    FUNCTION ff_immutable();

CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON session_mutation_undos FOR EACH ROW
    EXECUTE FUNCTION ff_immutable();

CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON mutation_change_requests FOR EACH ROW
    EXECUTE FUNCTION ff_immutable();

CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON mutation_clients FOR EACH ROW EXECUTE
    FUNCTION ff_immutable();

CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON mutation_exercise_plan_details FOR EACH
    ROW EXECUTE FUNCTION ff_immutable();

CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON mutation_exercise_plan_items FOR EACH
    ROW EXECUTE FUNCTION ff_immutable();

CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON mutation_exercise_results FOR EACH ROW
    EXECUTE FUNCTION ff_immutable();

CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON mutation_media_assets FOR EACH ROW
    EXECUTE FUNCTION ff_immutable();

CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON mutation_package_purchases FOR EACH ROW
    EXECUTE FUNCTION ff_immutable();

CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON mutation_purchase_schedule_slots FOR
    EACH ROW EXECUTE FUNCTION ff_immutable();

CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON mutation_scopes FOR EACH ROW EXECUTE
    FUNCTION ff_immutable();

CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON mutation_staff_users FOR EACH ROW
    EXECUTE FUNCTION ff_immutable();

CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON mutation_trainers FOR EACH ROW EXECUTE
    FUNCTION ff_immutable();

CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON mutation_training_sessions FOR EACH ROW
    EXECUTE FUNCTION ff_immutable();
CREATE TRIGGER ff_actor BEFORE INSERT ON session_mutations FOR EACH ROW EXECUTE FUNCTION ff_actor();
CREATE TRIGGER ff_actor BEFORE INSERT ON session_mutation_undos FOR EACH ROW EXECUTE FUNCTION
    ff_actor();

CREATE FUNCTION ff_mutation_snapshot() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM session_mutations WHERE id=NEW.mutation_id
   AND created_xid=pg_current_xact_id()::text) THEN
  RAISE EXCEPTION 'Mutation snapshots must accompany the original command' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER ff_mutation_snapshot BEFORE INSERT ON mutation_change_requests FOR EACH ROW
    EXECUTE FUNCTION ff_mutation_snapshot();
CREATE TRIGGER ff_mutation_snapshot BEFORE INSERT ON mutation_clients FOR EACH ROW EXECUTE
    FUNCTION ff_mutation_snapshot();
CREATE TRIGGER ff_mutation_snapshot BEFORE INSERT ON mutation_exercise_plan_details FOR EACH
    ROW EXECUTE FUNCTION ff_mutation_snapshot();
CREATE TRIGGER ff_mutation_snapshot BEFORE INSERT ON mutation_exercise_plan_items FOR EACH ROW
    EXECUTE FUNCTION ff_mutation_snapshot();
CREATE TRIGGER ff_mutation_snapshot BEFORE INSERT ON mutation_exercise_results FOR EACH ROW
    EXECUTE FUNCTION ff_mutation_snapshot();
CREATE TRIGGER ff_mutation_snapshot BEFORE INSERT ON mutation_media_assets FOR EACH ROW EXECUTE
    FUNCTION ff_mutation_snapshot();
CREATE TRIGGER ff_mutation_snapshot BEFORE INSERT ON mutation_package_purchases FOR EACH ROW
    EXECUTE FUNCTION ff_mutation_snapshot();
CREATE TRIGGER ff_mutation_snapshot BEFORE INSERT ON mutation_purchase_schedule_slots FOR EACH
    ROW EXECUTE FUNCTION ff_mutation_snapshot();
CREATE TRIGGER ff_mutation_snapshot BEFORE INSERT ON mutation_scopes FOR EACH ROW EXECUTE
    FUNCTION ff_mutation_snapshot();
CREATE TRIGGER ff_mutation_snapshot BEFORE INSERT ON mutation_staff_users FOR EACH ROW EXECUTE
    FUNCTION ff_mutation_snapshot();
CREATE TRIGGER ff_mutation_snapshot BEFORE INSERT ON mutation_trainers FOR EACH ROW EXECUTE
    FUNCTION ff_mutation_snapshot();
CREATE TRIGGER ff_mutation_snapshot BEFORE INSERT ON mutation_training_sessions FOR EACH ROW
    EXECUTE FUNCTION ff_mutation_snapshot();

CREATE FUNCTION ff_mutation_undo() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM session_mutations WHERE id=NEW.mutation_id
   AND expires_at>clock_timestamp()) THEN
  RAISE EXCEPTION 'Undo window expired' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER ff_mutation_undo BEFORE INSERT ON session_mutation_undos
 FOR EACH ROW EXECUTE FUNCTION ff_mutation_undo();
CREATE OR REPLACE FUNCTION ff_retired_plan() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF OLD.retired_at IS NOT NULL AND NOT EXISTS (
  SELECT 1 FROM mutation_exercise_plan_items b
  JOIN mutation_exercise_plan_items a ON a.mutation_id=b.mutation_id
    AND a.entity_id=b.entity_id AND a.side='after'
  JOIN session_mutation_undos u ON u.mutation_id=b.mutation_id
  WHERE b.entity_id=OLD.id AND b.side='before'
    AND u.created_xid=pg_current_xact_id()::text
    AND to_jsonb(NEW) @> (to_jsonb(b)-ARRAY['mutation_id','entity_id','side','version'])
    AND to_jsonb(OLD) @> (to_jsonb(a)-ARRAY['mutation_id','entity_id','side','version'])
 ) THEN RAISE EXCEPTION 'Retired exercise evidence is immutable' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;
CREATE FUNCTION ff_detail_restore_version() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='UPDATE' THEN
  IF NEW.version<>OLD.version+1 OR NEW.id<>OLD.id OR NEW.created_at<>OLD.created_at THEN
   RAISE EXCEPTION 'version or identity mismatch' USING ERRCODE='23514';
  END IF;
  NEW.updated_at:=clock_timestamp();
 ELSIF NEW.version=1 THEN
  NEW.created_at:=transaction_timestamp(); NEW.updated_at:=NEW.created_at;
 ELSE
  IF NOT EXISTS(SELECT 1 FROM mutation_exercise_plan_details b
    JOIN session_mutation_undos u ON u.mutation_id=b.mutation_id
    WHERE b.entity_id=NEW.id AND b.side='before'
      AND u.created_xid=pg_current_xact_id()::text
      AND NEW.version=b.version+1
      AND to_jsonb(NEW) @> (to_jsonb(b)-ARRAY['mutation_id','entity_id','side','version'])
      AND NOT EXISTS(SELECT 1 FROM mutation_exercise_plan_details a WHERE
    a.mutation_id=b.mutation_id
        AND a.entity_id=b.entity_id AND a.side='after')) THEN
   RAISE EXCEPTION 'Restoring details requires exact atomic Undo evidence' USING ERRCODE='23514';
  END IF;
  NEW.updated_at:=clock_timestamp();
 END IF;
 RETURN NEW;
END $$;
DROP TRIGGER ff_version ON exercise_plan_details;
CREATE TRIGGER ff_version BEFORE INSERT OR UPDATE ON exercise_plan_details
 FOR EACH ROW EXECUTE FUNCTION ff_detail_restore_version();

"""

DOWNGRADE_SQL = r"""

DO $$ BEGIN IF EXISTS(SELECT 1 FROM session_mutations) THEN
 RAISE EXCEPTION 'Undo downgrade refused: retained compensation history exists' USING
    ERRCODE='23514';
END IF; END $$;
DROP TRIGGER ff_version ON exercise_plan_details;
CREATE TRIGGER ff_version BEFORE INSERT OR UPDATE ON exercise_plan_details FOR EACH ROW EXECUTE
    FUNCTION ff_version();
DROP FUNCTION ff_detail_restore_version();
CREATE OR REPLACE FUNCTION ff_retired_plan() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF OLD.retired_at IS NOT NULL THEN RAISE EXCEPTION 'Retired exercise evidence is immutable';
    END IF;
 RETURN NEW;
END $$;
DROP TABLE session_mutation_undos;
DROP TABLE mutation_training_sessions;
DROP TABLE mutation_trainers;
DROP TABLE mutation_staff_users;
DROP TABLE mutation_scopes;
DROP TABLE mutation_purchase_schedule_slots;
DROP TABLE mutation_package_purchases;
DROP TABLE mutation_media_assets;
DROP TABLE mutation_exercise_results;
DROP TABLE mutation_exercise_plan_items;
DROP TABLE mutation_exercise_plan_details;
DROP TABLE mutation_clients;
DROP TABLE mutation_change_requests;
DROP TABLE session_mutations;
DROP FUNCTION ff_mutation_snapshot();
DROP FUNCTION ff_mutation_undo();

"""


def upgrade():
    op.execute(UPGRADE_SQL)


def downgrade():
    op.execute(DOWNGRADE_SQL)
