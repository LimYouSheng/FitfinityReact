"""Preserve original private library saves across direct upload and response loss."""

from alembic import op

revision = "20261024_0041"
down_revision = "20261024_0040"
branch_labels = None
depends_on = None

UPGRADE_SQL = r"""

CREATE TABLE library_save_intents (
  request_key UUID NOT NULL,
  request_sha256 VARCHAR(64) NOT NULL,
  exercise_id UUID NOT NULL,
  expected_version INTEGER,
  name VARCHAR(180) NOT NULL,
  category VARCHAR(120) NOT NULL,
  description TEXT NOT NULL,
  exercise_status VARCHAR(16) NOT NULL,
  remove_media BOOLEAN NOT NULL,
  upload_id UUID,
  upload_until TIMESTAMP WITH TIME ZONE NOT NULL,
  state VARCHAR(16) DEFAULT 'pending' NOT NULL,
  result JSONB,
  actor_id UUID NOT NULL,
  actor_name VARCHAR(200) NOT NULL,
  version INTEGER DEFAULT 1 NOT NULL,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
  id UUID NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
  CONSTRAINT pk_library_save_intents PRIMARY KEY (id),
  CONSTRAINT uq_library_save_intents_actor_id_request_key UNIQUE (actor_id, request_key),
  CONSTRAINT ck_library_save_intents_state_values CHECK (state IN ('pending', 'completed',
    'expired')),
  CONSTRAINT ck_library_save_intents_exercise_status_values CHECK (exercise_status IN ('active',
    'inactive')),
  CONSTRAINT ck_library_save_intents_request_digest CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
  CONSTRAINT ck_library_save_intents_review_version CHECK (expected_version IS NULL OR
    expected_version > 0),
  CONSTRAINT ck_library_save_intents_receipt_state CHECK ((state = 'completed') = (result IS NOT
    NULL)),
  CONSTRAINT ck_library_save_intents_details_bounds CHECK (length(btrim(name)) BETWEEN 1 AND 180
    AND length(description) <= 2000),
  CONSTRAINT uq_library_save_intents_upload_id UNIQUE (upload_id),
  CONSTRAINT fk_library_save_intents_upload_id_media_assets FOREIGN KEY(upload_id) REFERENCES
    media_assets (id),
  CONSTRAINT fk_library_save_intents_actor_id_staff_users FOREIGN KEY(actor_id) REFERENCES
    staff_users (id),
  CONSTRAINT ck_library_save_intents_positive_version CHECK (version > 0),
  CONSTRAINT ck_library_save_intents_actor_name_required CHECK (length(btrim(actor_name)) > 0)
)

;
CREATE INDEX ix_library_save_intents_actor_id ON library_save_intents (actor_id);
CREATE FUNCTION ff_library_intent() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'library original intent cannot be deleted' USING ERRCODE='23514';
  END IF;
  IF TG_OP = 'INSERT' THEN
    IF NEW.state <> 'pending' OR NEW.result IS NOT NULL THEN
      RAISE EXCEPTION 'library intent must start pending' USING ERRCODE='23514';
    END IF;
  ELSE
    IF OLD.state <> 'pending' OR NEW.state NOT IN ('completed', 'expired') OR
       (to_jsonb(NEW) - ARRAY['state','result','version','updated_at']) IS DISTINCT FROM
       (to_jsonb(OLD) - ARRAY['state','result','version','updated_at']) THEN
      RAISE EXCEPTION 'library original intent is immutable' USING ERRCODE='23514';
    END IF;
  END IF;
  IF NEW.upload_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM media_assets m WHERE m.id=NEW.upload_id
      AND m.purpose='exercise_media' AND m.uploaded_by=NEW.actor_id
  ) THEN
    RAISE EXCEPTION 'library upload must belong to original actor' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER ff_actor BEFORE INSERT ON library_save_intents
  FOR EACH ROW EXECUTE FUNCTION ff_actor();
CREATE TRIGGER ff_version BEFORE INSERT OR UPDATE ON library_save_intents
  FOR EACH ROW EXECUTE FUNCTION ff_version();
CREATE TRIGGER ff_library_intent BEFORE INSERT OR UPDATE OR DELETE ON library_save_intents
  FOR EACH ROW EXECUTE FUNCTION ff_library_intent();

"""

DOWNGRADE_SQL = r"""

DO $guard$
BEGIN
  IF EXISTS (SELECT 1 FROM library_save_intents) THEN
    RAISE EXCEPTION 'Library downgrade refused: retained save/upload evidence exists';
  END IF;
END;
$guard$;
DROP TABLE library_save_intents;
DROP FUNCTION ff_library_intent();

"""


def upgrade():
    op.execute(UPGRADE_SQL)


def downgrade():
    op.execute(DOWNGRADE_SQL)
