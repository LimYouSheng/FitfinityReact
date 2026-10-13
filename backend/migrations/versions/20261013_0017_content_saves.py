"""Immutable actor-scoped content save receipts."""

from alembic import op

revision = "20261013_0017"
down_revision = "20261013_0016"
branch_labels = None
depends_on = None

UPGRADE_SQL = r"""
CREATE TABLE content_save_receipts (
    request_key UUID NOT NULL,
    request_sha256 VARCHAR(64) NOT NULL,
    content_id UUID NOT NULL REFERENCES content_entries(id),
    previous JSONB,
    result JSONB NOT NULL,
    actor_id UUID NOT NULL REFERENCES staff_users(id),
    actor_name VARCHAR(200) NOT NULL,
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    CONSTRAINT uq_content_save_receipts_actor_id_request_key UNIQUE(actor_id, request_key),
    CONSTRAINT ck_content_save_receipts_request_digest
        CHECK(request_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_content_save_receipts_actor_name_required
        CHECK(length(btrim(actor_name)) > 0)
);
CREATE INDEX ix_content_save_receipts_actor_id ON content_save_receipts(actor_id);
CREATE TRIGGER ff_actor BEFORE INSERT ON content_save_receipts
    FOR EACH ROW EXECUTE FUNCTION ff_actor();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON content_save_receipts
    FOR EACH ROW EXECUTE FUNCTION ff_immutable();
"""

DOWNGRADE_SQL = r"""
DO $guard$
BEGIN
  IF EXISTS (SELECT 1 FROM content_save_receipts) THEN
    RAISE EXCEPTION 'Content save downgrade refused: receipts exist';
  END IF;
END;
$guard$;
DROP TABLE content_save_receipts;
"""


def upgrade():
    op.execute(UPGRADE_SQL)


def downgrade():
    op.execute(DOWNGRADE_SQL)
