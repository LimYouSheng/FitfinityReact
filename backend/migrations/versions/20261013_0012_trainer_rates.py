"""Durable trainer rate receipts with immutable before and after evidence."""

from alembic import op

revision = "20261013_0012"
down_revision = "20261013_0011"
branch_labels = None
depends_on = None

UPGRADE_SQL = r"""
CREATE TABLE trainer_rate_receipts (
    request_key UUID NOT NULL,
    request_sha256 VARCHAR(64) NOT NULL,
    trainer_id UUID NOT NULL,
    previous JSONB NOT NULL,
    rates JSONB NOT NULL,
    result JSONB NOT NULL,
    actor_id UUID NOT NULL,
    actor_name VARCHAR(200) NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_trainer_rate_receipts PRIMARY KEY (id),
    CONSTRAINT uq_trainer_rate_receipts_actor_id_request_key UNIQUE (actor_id, request_key),
    CONSTRAINT ck_trainer_rate_receipts_request_digest
        CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT fk_trainer_rate_receipts_trainer_id_trainers
        FOREIGN KEY(trainer_id) REFERENCES trainers (id),
    CONSTRAINT fk_trainer_rate_receipts_actor_id_staff_users
        FOREIGN KEY(actor_id) REFERENCES staff_users (id),
    CONSTRAINT ck_trainer_rate_receipts_actor_name_required
        CHECK (length(btrim(actor_name)) > 0)
);
CREATE INDEX ix_trainer_rate_receipts_actor_id ON trainer_rate_receipts (actor_id);
CREATE TRIGGER ff_actor BEFORE INSERT ON trainer_rate_receipts
    FOR EACH ROW EXECUTE FUNCTION ff_actor();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON trainer_rate_receipts
    FOR EACH ROW EXECUTE FUNCTION ff_immutable();
"""

DOWNGRADE_SQL = r"""
DO $guard$
BEGIN
  IF EXISTS (SELECT 1 FROM trainer_rate_receipts) THEN
    RAISE EXCEPTION 'Trainer rate downgrade refused: receipts exist';
  END IF;
END;
$guard$;
DROP TABLE trainer_rate_receipts;
"""


def upgrade():
    op.execute(UPGRADE_SQL)


def downgrade():
    op.execute(DOWNGRADE_SQL)
