"""Retain private acknowledgement revisions and original-command recovery evidence."""

from alembic import op

revision = "20261024_0039"
down_revision = "20261024_0038"
branch_labels = None
depends_on = None

UPGRADE_SQL = r"""
CREATE TABLE session_acknowledgement_receipts (
  id UUID PRIMARY KEY,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
  request_key UUID NOT NULL,
  request_sha256 VARCHAR(64) NOT NULL,
  session_id UUID NOT NULL REFERENCES training_sessions(id),
  previous JSONB NOT NULL,
  result JSONB NOT NULL,
  actor_id UUID NOT NULL REFERENCES staff_users(id),
  actor_name VARCHAR(200) NOT NULL,
  CONSTRAINT uq_session_acknowledgement_receipts_actor_id_request_key UNIQUE(actor_id, request_key),
  CONSTRAINT ck_session_acknowledgement_receipts_request_digest
    CHECK(request_sha256 ~ '^[0-9a-f]{64}$'),
  CONSTRAINT ck_session_acknowledgement_receipts_actor_name_required
    CHECK(length(btrim(actor_name)) > 0)
);
CREATE INDEX ix_session_acknowledgement_receipts_actor_id
  ON session_acknowledgement_receipts(actor_id);
CREATE TRIGGER ff_actor BEFORE INSERT ON session_acknowledgement_receipts
  FOR EACH ROW EXECUTE FUNCTION ff_actor();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON session_acknowledgement_receipts
  FOR EACH ROW EXECUTE FUNCTION ff_immutable();
"""

DOWNGRADE_SQL = r"""
DO $guard$
BEGIN
  IF EXISTS (SELECT 1 FROM session_acknowledgement_receipts) THEN
    RAISE EXCEPTION 'Session acknowledgement downgrade refused: %',
      'retained acknowledgement evidence exists';
  END IF;
END;
$guard$;
DROP TABLE session_acknowledgement_receipts;
"""


def upgrade():
    op.execute(UPGRADE_SQL)


def downgrade():
    op.execute(DOWNGRADE_SQL)
