"""Persist ordered plan details and preserve removed exercise evidence."""

from alembic import op

revision = "20261023_0036"
down_revision = "20261023_0035"
branch_labels = None
depends_on = None

UPGRADE_SQL = r"""
ALTER TABLE exercise_plan_items ADD COLUMN retired_at TIMESTAMPTZ;
ALTER TABLE exercise_plan_items ALTER COLUMN position DROP NOT NULL;
ALTER TABLE exercise_plan_items DROP CONSTRAINT ck_exercise_plan_items_valid_item;
ALTER TABLE exercise_plan_items ADD CONSTRAINT ck_exercise_plan_items_valid_item CHECK (
  length(btrim(name)) > 0 AND
  ((retired_at IS NULL AND position > 0 AND position IS NOT NULL) OR
   (retired_at IS NOT NULL AND position IS NULL))
);
CREATE FUNCTION ff_retired_plan() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.retired_at IS NOT NULL THEN
    RAISE EXCEPTION 'Retired exercise evidence is immutable';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER ff_retired_plan BEFORE UPDATE ON exercise_plan_items
  FOR EACH ROW EXECUTE FUNCTION ff_retired_plan();
CREATE TRIGGER ff_no_delete BEFORE DELETE ON exercise_plan_items
  FOR EACH ROW EXECUTE FUNCTION ff_immutable();
CREATE TABLE exercise_plan_details (
  id UUID PRIMARY KEY,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  version INTEGER DEFAULT 1 NOT NULL,
  plan_item_id UUID NOT NULL REFERENCES exercise_plan_items(id),
  detail_key VARCHAR(200) NOT NULL,
  position INTEGER NOT NULL,
  value TEXT NOT NULL,
  CONSTRAINT uq_exercise_plan_details_plan_item_id_detail_key UNIQUE(plan_item_id, detail_key),
  CONSTRAINT uq_exercise_plan_details_plan_item_id_position UNIQUE(plan_item_id, position)
    DEFERRABLE INITIALLY DEFERRED,
  CONSTRAINT ck_exercise_plan_details_positive_version CHECK(version > 0),
  CONSTRAINT ck_exercise_plan_details_valid_detail CHECK (
    position > 0 AND length(btrim(detail_key)) > 0 AND length(btrim(value)) > 0)
);
CREATE INDEX ix_exercise_plan_details_plan_item_id ON exercise_plan_details(plan_item_id);
CREATE TRIGGER ff_version BEFORE INSERT OR UPDATE ON exercise_plan_details
  FOR EACH ROW EXECUTE FUNCTION ff_version();
CREATE TRIGGER ff_preserve_fields BEFORE UPDATE ON exercise_plan_details
  FOR EACH ROW EXECUTE FUNCTION ff_preserve_fields('plan_item_id', 'detail_key');
CREATE FUNCTION ff_retired_plan_detail() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE retired TIMESTAMPTZ;
BEGIN
  SELECT retired_at INTO retired FROM exercise_plan_items
    WHERE id=COALESCE(NEW.plan_item_id, OLD.plan_item_id) FOR UPDATE;
  IF retired IS NOT NULL THEN
    RAISE EXCEPTION 'Retired exercise details are immutable';
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER ff_retired_plan_detail BEFORE INSERT OR UPDATE OR DELETE ON exercise_plan_details
  FOR EACH ROW EXECUTE FUNCTION ff_retired_plan_detail();
CREATE TABLE session_plan_receipts (
  id UUID PRIMARY KEY,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  request_key UUID NOT NULL,
  request_sha256 VARCHAR(64) NOT NULL,
  session_id UUID NOT NULL REFERENCES training_sessions(id),
  previous JSONB NOT NULL,
  result JSONB NOT NULL,
  actor_id UUID NOT NULL REFERENCES staff_users(id),
  actor_name VARCHAR(200) NOT NULL,
  CONSTRAINT uq_session_plan_receipts_actor_id_request_key UNIQUE(actor_id, request_key),
  CONSTRAINT ck_session_plan_receipts_request_digest CHECK(request_sha256 ~ '^[0-9a-f]{64}$'),
  CONSTRAINT ck_session_plan_receipts_actor_name_required CHECK(length(btrim(actor_name)) > 0)
);
CREATE INDEX ix_session_plan_receipts_actor_id ON session_plan_receipts(actor_id);
CREATE TRIGGER ff_actor BEFORE INSERT ON session_plan_receipts
  FOR EACH ROW EXECUTE FUNCTION ff_actor();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON session_plan_receipts
  FOR EACH ROW EXECUTE FUNCTION ff_immutable();
"""

DOWNGRADE_SQL = r"""
DO $guard$
BEGIN
  IF EXISTS (SELECT 1 FROM session_plan_receipts) OR
     EXISTS (SELECT 1 FROM exercise_plan_details) OR
     EXISTS (SELECT 1 FROM exercise_plan_items WHERE retired_at IS NOT NULL) THEN
    RAISE EXCEPTION 'Session plan downgrade refused: retained plan evidence exists';
  END IF;
END;
$guard$;
DROP TABLE session_plan_receipts;
DROP TABLE exercise_plan_details;
DROP FUNCTION ff_retired_plan_detail();
DROP TRIGGER ff_no_delete ON exercise_plan_items;
DROP TRIGGER ff_retired_plan ON exercise_plan_items;
DROP FUNCTION ff_retired_plan();
ALTER TABLE exercise_plan_items DROP CONSTRAINT ck_exercise_plan_items_valid_item;
ALTER TABLE exercise_plan_items DROP COLUMN retired_at;
ALTER TABLE exercise_plan_items ALTER COLUMN position SET NOT NULL;
ALTER TABLE exercise_plan_items ADD CONSTRAINT ck_exercise_plan_items_valid_item
  CHECK(position > 0 AND length(btrim(name)) > 0);
"""


def upgrade():
    op.execute(UPGRADE_SQL)


def downgrade():
    op.execute(DOWNGRADE_SQL)
