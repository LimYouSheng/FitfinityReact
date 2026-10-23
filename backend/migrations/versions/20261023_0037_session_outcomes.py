"""Retain corrected measurements and private outcome command receipts."""

from alembic import op

revision = "20261023_0037"
down_revision = "20261023_0036"
branch_labels = None
depends_on = None

UPGRADE_SQL = r"""
ALTER TABLE exercise_results ADD COLUMN retired_at TIMESTAMPTZ;
ALTER TABLE exercise_result_revisions ADD COLUMN retired_at TIMESTAMPTZ;
CREATE TRIGGER ff_no_delete BEFORE DELETE ON exercise_results
  FOR EACH ROW EXECUTE FUNCTION ff_immutable();
CREATE TABLE session_outcome_receipts (
  id UUID PRIMARY KEY,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  request_key UUID NOT NULL,
  request_sha256 VARCHAR(64) NOT NULL,
  session_id UUID NOT NULL REFERENCES training_sessions(id),
  previous JSONB NOT NULL,
  result JSONB NOT NULL,
  actor_id UUID NOT NULL REFERENCES staff_users(id),
  actor_name VARCHAR(200) NOT NULL,
  CONSTRAINT uq_session_outcome_receipts_actor_id_request_key UNIQUE(actor_id, request_key),
  CONSTRAINT ck_session_outcome_receipts_request_digest CHECK(request_sha256 ~ '^[0-9a-f]{64}$'),
  CONSTRAINT ck_session_outcome_receipts_actor_name_required CHECK(length(btrim(actor_name)) > 0)
);
CREATE INDEX ix_session_outcome_receipts_actor_id ON session_outcome_receipts(actor_id);
CREATE TRIGGER ff_actor BEFORE INSERT ON session_outcome_receipts
  FOR EACH ROW EXECUTE FUNCTION ff_actor();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON session_outcome_receipts
  FOR EACH ROW EXECUTE FUNCTION ff_immutable();
"""

DOWNGRADE_SQL = r"""
DO $guard$
BEGIN
  IF EXISTS (SELECT 1 FROM session_outcome_receipts) OR
     EXISTS (SELECT 1 FROM exercise_results WHERE retired_at IS NOT NULL) OR
     EXISTS (SELECT 1 FROM exercise_result_revisions WHERE retired_at IS NOT NULL) THEN
    RAISE EXCEPTION 'Session outcome downgrade refused: retained outcome evidence exists';
  END IF;
END;
$guard$;
DROP TABLE session_outcome_receipts;
DROP TRIGGER ff_no_delete ON exercise_results;
ALTER TABLE exercise_result_revisions DROP COLUMN retired_at;
ALTER TABLE exercise_results DROP COLUMN retired_at;
"""


def upgrade():
    op.execute(UPGRADE_SQL)


def downgrade():
    op.execute(DOWNGRADE_SQL)
