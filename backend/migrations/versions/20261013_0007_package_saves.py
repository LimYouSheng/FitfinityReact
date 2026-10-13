"""Durable package command receipts and notice targets; preserve all purchased terms."""

from alembic import op

revision = "20261013_0007"
down_revision = "20260924_0006"
branch_labels = None
depends_on = None

UPGRADE_SQL = r"""
CREATE TABLE package_save_receipts (
    request_key UUID NOT NULL,
    request_sha256 VARCHAR(64) NOT NULL,
    template_id UUID NOT NULL,
    result JSONB NOT NULL,
    actor_id UUID NOT NULL,
    actor_name VARCHAR(200) NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_package_save_receipts PRIMARY KEY (id),
    CONSTRAINT uq_package_save_receipts_actor_id_request_key UNIQUE (actor_id, request_key),
    CONSTRAINT ck_package_save_receipts_request_digest CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT fk_package_save_receipts_template_id_package_templates
        FOREIGN KEY(template_id) REFERENCES package_templates (id),
    CONSTRAINT fk_package_save_receipts_actor_id_staff_users
        FOREIGN KEY(actor_id) REFERENCES staff_users (id),
    CONSTRAINT ck_package_save_receipts_actor_name_required CHECK (length(btrim(actor_name)) > 0)
);
CREATE INDEX ix_package_save_receipts_actor_id ON package_save_receipts (actor_id);
CREATE TRIGGER ff_actor BEFORE INSERT ON package_save_receipts
    FOR EACH ROW EXECUTE FUNCTION ff_actor();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON package_save_receipts
    FOR EACH ROW EXECUTE FUNCTION ff_immutable();
ALTER TABLE messages ADD COLUMN package_template_id UUID;
ALTER TABLE messages ADD CONSTRAINT fk_messages_package_template_id_package_templates
    FOREIGN KEY(package_template_id) REFERENCES package_templates (id);
"""

DOWNGRADE_SQL = r"""
DO $guard$
BEGIN
  IF EXISTS (SELECT 1 FROM package_save_receipts)
     OR EXISTS (SELECT 1 FROM messages WHERE package_template_id IS NOT NULL) THEN
    RAISE EXCEPTION 'Package save downgrade refused: receipts or notice targets exist';
  END IF;
END;
$guard$;
ALTER TABLE messages DROP COLUMN package_template_id;
DROP TABLE package_save_receipts;
"""


def upgrade():
    op.execute(UPGRADE_SQL)


def downgrade():
    op.execute(DOWNGRADE_SQL)
