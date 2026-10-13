"""Immutable reviewed purchase reactivation receipts."""

from alembic import op

revision = "20261013_0027"
down_revision = "20261013_0026"
branch_labels = None
depends_on = None

UPGRADE_SQL = r"""
CREATE TABLE package_reactivation_receipts (
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
    CONSTRAINT uq_package_reactivation_receipts_actor_id_request_key UNIQUE(actor_id, request_key),
    CONSTRAINT ck_package_reactivation_receipts_request_digest
        CHECK(request_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_package_reactivation_receipts_actor_name_required
        CHECK(length(btrim(actor_name)) > 0)
);
CREATE INDEX ix_package_reactivation_receipts_actor_id ON package_reactivation_receipts(actor_id);
CREATE TRIGGER ff_actor BEFORE INSERT ON package_reactivation_receipts
    FOR EACH ROW EXECUTE FUNCTION ff_actor();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON package_reactivation_receipts
    FOR EACH ROW EXECUTE FUNCTION ff_immutable();
"""

DOWNGRADE_SQL = r"""
DO $guard$
BEGIN
  IF EXISTS (SELECT 1 FROM package_reactivation_receipts) THEN
    RAISE EXCEPTION 'Package reactivation downgrade refused: receipts exist';
  END IF;
END;
$guard$;
DROP TABLE package_reactivation_receipts;
"""


def upgrade():
    op.execute(UPGRADE_SQL)


def downgrade():
    op.execute(DOWNGRADE_SQL)
