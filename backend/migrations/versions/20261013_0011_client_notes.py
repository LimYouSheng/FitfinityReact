"""Scoped general notes, immutable access evidence and retry receipts."""

from alembic import op

revision = "20261013_0011"
down_revision = "20261013_0010"
branch_labels = None
depends_on = None

UPGRADE_SQL = r"""
ALTER TABLE clients ADD COLUMN health_notes TEXT;
CREATE TABLE client_note_receipts (
    request_key UUID NOT NULL,
    request_sha256 VARCHAR(64) NOT NULL,
    client_id UUID NOT NULL,
    result JSONB NOT NULL,
    actor_id UUID NOT NULL,
    actor_name VARCHAR(200) NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_client_note_receipts PRIMARY KEY (id),
    CONSTRAINT uq_client_note_receipts_actor_id_request_key UNIQUE (actor_id, request_key),
    CONSTRAINT ck_client_note_receipts_request_digest
        CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT fk_client_note_receipts_client_id_clients
        FOREIGN KEY(client_id) REFERENCES clients (id),
    CONSTRAINT fk_client_note_receipts_actor_id_staff_users
        FOREIGN KEY(actor_id) REFERENCES staff_users (id),
    CONSTRAINT ck_client_note_receipts_actor_name_required
        CHECK (length(btrim(actor_name)) > 0)
);
CREATE TABLE client_note_access (
    client_id UUID NOT NULL REFERENCES clients(id),
    action VARCHAR(16) NOT NULL CHECK (action IN ('view', 'save', 'replay')),
    actor_id UUID NOT NULL REFERENCES staff_users(id),
    actor_name VARCHAR(200) NOT NULL CHECK (length(btrim(actor_name)) > 0),
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_client_note_access_client_id ON client_note_access(client_id);
CREATE INDEX ix_client_note_access_actor_id ON client_note_access(actor_id);
CREATE TRIGGER ff_actor BEFORE INSERT ON client_note_access
    FOR EACH ROW EXECUTE FUNCTION ff_actor();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON client_note_access
    FOR EACH ROW EXECUTE FUNCTION ff_immutable();
CREATE INDEX ix_client_note_receipts_actor_id ON client_note_receipts (actor_id);
CREATE TRIGGER ff_actor BEFORE INSERT ON client_note_receipts
    FOR EACH ROW EXECUTE FUNCTION ff_actor();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON client_note_receipts
    FOR EACH ROW EXECUTE FUNCTION ff_immutable();
"""

DOWNGRADE_SQL = r"""
DO $guard$
BEGIN
  IF EXISTS (SELECT 1 FROM client_note_receipts)
    OR EXISTS (SELECT 1 FROM client_note_access)
    OR EXISTS (SELECT 1 FROM clients WHERE health_notes IS NOT NULL) THEN
    RAISE EXCEPTION 'Client notes downgrade refused: receipts exist';
  END IF;
END;
$guard$;
DROP TABLE client_note_access;
DROP TABLE client_note_receipts;
ALTER TABLE clients DROP COLUMN health_notes;
"""


def upgrade():
    op.execute(UPGRADE_SQL)


def downgrade():
    op.execute(DOWNGRADE_SQL)
