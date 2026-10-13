"""Immutable request cancellation receipts."""

from alembic import op

revision = "20261013_0023"
down_revision = "20261013_0022"
branch_labels = None
depends_on = None

UPGRADE_SQL = r"""
CREATE TABLE request_cancellation_receipts (
    request_key UUID NOT NULL,
    request_sha256 VARCHAR(64) NOT NULL,
    change_request_id UUID NOT NULL REFERENCES change_requests(id),
    result JSONB NOT NULL,
    actor_id UUID NOT NULL REFERENCES staff_users(id),
    actor_name VARCHAR(200) NOT NULL,
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    CONSTRAINT uq_request_cancellation_receipts_actor_id_request_key UNIQUE(actor_id, request_key),
    CONSTRAINT ck_request_cancellation_receipts_request_digest
        CHECK(request_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_request_cancellation_receipts_actor_name_required
        CHECK(length(btrim(actor_name)) > 0)
);
CREATE INDEX ix_request_cancellation_receipts_actor_id ON request_cancellation_receipts(actor_id);
CREATE TRIGGER ff_actor BEFORE INSERT ON request_cancellation_receipts
    FOR EACH ROW EXECUTE FUNCTION ff_actor();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON request_cancellation_receipts
    FOR EACH ROW EXECUTE FUNCTION ff_immutable();
"""

DOWNGRADE_SQL = r"""
DO $guard$
BEGIN
  IF EXISTS (SELECT 1 FROM request_cancellation_receipts) THEN
    RAISE EXCEPTION 'Request cancellation downgrade refused: receipts exist';
  END IF;
END;
$guard$;
DROP TABLE request_cancellation_receipts;
"""


def upgrade():
    op.execute(UPGRADE_SQL)


def downgrade():
    op.execute(DOWNGRADE_SQL)
