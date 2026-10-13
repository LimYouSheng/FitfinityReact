"""Durable personal-information edit receipts; no health answers duplicated."""

from alembic import op

revision = "20261013_0009"
down_revision = "20261013_0008"
branch_labels = None
depends_on = None

UPGRADE_SQL = r"""
CREATE TABLE client_detail_receipts (
    request_key UUID NOT NULL,
    request_sha256 VARCHAR(64) NOT NULL,
    client_id UUID NOT NULL,
    result JSONB NOT NULL,
    actor_id UUID NOT NULL,
    actor_name VARCHAR(200) NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_client_detail_receipts PRIMARY KEY (id),
    CONSTRAINT uq_client_detail_receipts_actor_id_request_key UNIQUE (actor_id, request_key),
    CONSTRAINT ck_client_detail_receipts_request_digest
        CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT fk_client_detail_receipts_client_id_clients
        FOREIGN KEY(client_id) REFERENCES clients (id),
    CONSTRAINT fk_client_detail_receipts_actor_id_staff_users
        FOREIGN KEY(actor_id) REFERENCES staff_users (id),
    CONSTRAINT ck_client_detail_receipts_actor_name_required
        CHECK (length(btrim(actor_name)) > 0)
);
CREATE INDEX ix_client_detail_receipts_actor_id ON client_detail_receipts (actor_id);
CREATE TRIGGER ff_actor BEFORE INSERT ON client_detail_receipts
    FOR EACH ROW EXECUTE FUNCTION ff_actor();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON client_detail_receipts
    FOR EACH ROW EXECUTE FUNCTION ff_immutable();
"""

DOWNGRADE_SQL = r"""
DO $guard$
BEGIN
  IF EXISTS (SELECT 1 FROM client_detail_receipts) THEN
    RAISE EXCEPTION 'Client detail downgrade refused: receipts exist';
  END IF;
END;
$guard$;
DROP TABLE client_detail_receipts;
"""


def upgrade():
    op.execute(UPGRADE_SQL)


def downgrade():
    op.execute(DOWNGRADE_SQL)
