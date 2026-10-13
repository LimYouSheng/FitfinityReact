"""Optional trainer contacts and immutable profile save receipts."""

from alembic import op

revision = "20261013_0014"
down_revision = "20261013_0013"
branch_labels = None
depends_on = None

UPGRADE_SQL = r"""
ALTER TABLE trainers ALTER COLUMN birthday DROP NOT NULL;
ALTER TABLE trainers DROP CONSTRAINT ck_trainers_phone_format;
ALTER TABLE trainers ADD CONSTRAINT ck_trainers_phone_format
 CHECK (phone_country_code ~ '^\+[1-9][0-9]{0,2}$' AND (phone_number = ''
    OR (phone_number ~ '^[0-9 ()-]+$'
    AND length(regexp_replace(phone_number, '[^0-9]', '', 'g')) >= 6
    AND length(regexp_replace(phone_country_code || phone_number, '[^0-9]', '', 'g')) <= 15)));
CREATE TABLE trainer_detail_receipts (
    request_key UUID NOT NULL,
    request_sha256 VARCHAR(64) NOT NULL,
    trainer_id UUID NOT NULL REFERENCES trainers(id),
    result JSONB NOT NULL,
    actor_id UUID NOT NULL REFERENCES staff_users(id),
    actor_name VARCHAR(200) NOT NULL,
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    CONSTRAINT uq_trainer_detail_receipts_actor_id_request_key UNIQUE(actor_id, request_key),
    CONSTRAINT ck_trainer_detail_receipts_request_digest
        CHECK(request_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_trainer_detail_receipts_actor_name_required CHECK(length(btrim(actor_name)) > 0)
);
CREATE INDEX ix_trainer_detail_receipts_actor_id ON trainer_detail_receipts(actor_id);
CREATE TRIGGER ff_actor BEFORE INSERT ON trainer_detail_receipts
    FOR EACH ROW EXECUTE FUNCTION ff_actor();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON trainer_detail_receipts
    FOR EACH ROW EXECUTE FUNCTION ff_immutable();
"""

DOWNGRADE_SQL = r"""
DO $guard$
BEGIN
  IF EXISTS (SELECT 1 FROM trainer_detail_receipts)
     OR EXISTS (SELECT 1 FROM trainers WHERE birthday IS NULL OR phone_number = '') THEN
    RAISE EXCEPTION 'Trainer details downgrade refused: receipts or cleared contacts exist';
  END IF;
END;
$guard$;
DROP TABLE trainer_detail_receipts;
ALTER TABLE trainers ALTER COLUMN birthday SET NOT NULL;
ALTER TABLE trainers DROP CONSTRAINT ck_trainers_phone_format;
ALTER TABLE trainers ADD CONSTRAINT ck_trainers_phone_format
 CHECK (phone_country_code ~ '^\+[1-9][0-9]{0,2}$' AND phone_number ~ '^[0-9 ()-]+$'
    AND length(regexp_replace(phone_number, '[^0-9]', '', 'g')) >= 6
    AND length(regexp_replace(phone_country_code || phone_number, '[^0-9]', '', 'g')) <= 15);
"""


def upgrade():
    op.execute(UPGRADE_SQL)


def downgrade():
    op.execute(DOWNGRADE_SQL)
