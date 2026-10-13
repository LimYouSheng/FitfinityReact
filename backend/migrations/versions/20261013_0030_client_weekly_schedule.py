"""Immutable reviewed current-purchase weekly schedule receipts."""

from alembic import op

revision = "20261013_0030"
down_revision = "20261013_0029"
branch_labels = None
depends_on = None

UPGRADE_SQL = r"""
CREATE TABLE client_weekly_schedule_receipts (
    request_key UUID NOT NULL,
    request_sha256 VARCHAR(64) NOT NULL,
    client_id UUID NOT NULL REFERENCES clients(id),
    purchase_id UUID NOT NULL REFERENCES package_purchases(id),
    previous JSONB NOT NULL,
    result JSONB NOT NULL,
    actor_id UUID NOT NULL REFERENCES staff_users(id),
    actor_name VARCHAR(200) NOT NULL,
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    CONSTRAINT uq_client_weekly_schedule_receipts_actor_id_request_key
        UNIQUE(actor_id, request_key),
    CONSTRAINT ck_client_weekly_schedule_receipts_request_digest
        CHECK(request_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_client_weekly_schedule_receipts_actor_name_required
        CHECK(length(btrim(actor_name)) > 0)
);
CREATE INDEX ix_client_weekly_schedule_receipts_actor_id
    ON client_weekly_schedule_receipts(actor_id);
CREATE TRIGGER ff_actor BEFORE INSERT ON client_weekly_schedule_receipts
    FOR EACH ROW EXECUTE FUNCTION ff_actor();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON client_weekly_schedule_receipts
    FOR EACH ROW EXECUTE FUNCTION ff_immutable();
"""

DOWNGRADE_SQL = r"""
DO $guard$
BEGIN
  IF EXISTS (SELECT 1 FROM client_weekly_schedule_receipts) THEN
    RAISE EXCEPTION 'Client weekly schedule downgrade refused: receipts exist';
  END IF;
END;
$guard$;
DROP TABLE client_weekly_schedule_receipts;
"""


def upgrade():
    op.execute(UPGRADE_SQL)


def downgrade():
    op.execute(DOWNGRADE_SQL)
