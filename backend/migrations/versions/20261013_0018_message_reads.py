"""Immutable actor-scoped message read receipts."""

from alembic import op

revision = "20261013_0018"
down_revision = "20261013_0017"
branch_labels = None
depends_on = None

UPGRADE_SQL = r"""
CREATE TABLE message_read_receipts (
    request_key UUID NOT NULL,
    request_sha256 VARCHAR(64) NOT NULL,
    message_id UUID NOT NULL REFERENCES messages(id),
    result JSONB NOT NULL,
    actor_id UUID NOT NULL REFERENCES staff_users(id),
    actor_name VARCHAR(200) NOT NULL,
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    CONSTRAINT uq_message_read_receipts_actor_id_request_key UNIQUE(actor_id, request_key),
    CONSTRAINT ck_message_read_receipts_request_digest
        CHECK(request_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_message_read_receipts_actor_name_required
        CHECK(length(btrim(actor_name)) > 0)
);
CREATE INDEX ix_message_read_receipts_actor_id ON message_read_receipts(actor_id);
CREATE TRIGGER ff_actor BEFORE INSERT ON message_read_receipts
    FOR EACH ROW EXECUTE FUNCTION ff_actor();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON message_read_receipts
    FOR EACH ROW EXECUTE FUNCTION ff_immutable();
"""

DOWNGRADE_SQL = r"""
DO $guard$
BEGIN
  IF EXISTS (SELECT 1 FROM message_read_receipts) THEN
    RAISE EXCEPTION 'Message read downgrade refused: receipts exist';
  END IF;
END;
$guard$;
DROP TABLE message_read_receipts;
"""


def upgrade():
    op.execute(UPGRADE_SQL)


def downgrade():
    op.execute(DOWNGRADE_SQL)
