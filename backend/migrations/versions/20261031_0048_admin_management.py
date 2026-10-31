"""Owner-managed Admin supervision requirements and immutable lifecycle receipts."""

from alembic import op

revision = "20261031_0048"
down_revision = "20261031_0047"
branch_labels = None
depends_on = None

UPGRADE_SQL = r"""
CREATE TABLE admin_approval_requirements (
    user_id UUID NOT NULL REFERENCES admin_profiles(user_id),
    area VARCHAR(32) NOT NULL,
    required BOOLEAN NOT NULL,
    PRIMARY KEY(user_id, area),
    CONSTRAINT ck_admin_approval_requirements_area_values CHECK (area IN (
      'clientCreation','clientDetails','clientLifecycle','assessments',
      'trainerCreation','trainerDetails','trainerAssignment','trainerLifecycle',
      'sessionScheduling','sessionContent','sessionAcknowledgement',
      'packageCatalogue','clientPackages','exerciseLibrary','reports','content'))
);
CREATE TABLE admin_management_receipts (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    actor_id UUID NOT NULL REFERENCES staff_users(id),
    actor_name VARCHAR(200) NOT NULL,
    admin_id UUID NOT NULL REFERENCES admin_profiles(user_id),
    request_key UUID NOT NULL,
    request_sha256 VARCHAR(64) NOT NULL,
    operation VARCHAR(16) NOT NULL,
    previous JSONB NOT NULL,
    result JSONB NOT NULL,
    CONSTRAINT uq_admin_management_receipts_actor_id_request_key UNIQUE(actor_id, request_key),
    CONSTRAINT ck_admin_management_receipts_request_digest CHECK(request_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_admin_management_receipts_actor_name_required
      CHECK(length(btrim(actor_name)) > 0),
    CONSTRAINT ck_admin_management_receipts_operation_values
      CHECK(operation IN ('details','approvals','deactivate','reactivate'))
);
CREATE INDEX ix_admin_management_receipts_actor_id ON admin_management_receipts(actor_id);
CREATE INDEX ix_admin_management_receipts_admin_id ON admin_management_receipts(admin_id);
CREATE TRIGGER ff_actor BEFORE INSERT ON admin_management_receipts
    FOR EACH ROW EXECUTE FUNCTION ff_actor();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON admin_management_receipts
    FOR EACH ROW EXECUTE FUNCTION ff_immutable();
"""


def upgrade():
    op.execute(UPGRADE_SQL)


def downgrade():
    op.execute("""
DO $guard$
BEGIN
  IF EXISTS (SELECT 1 FROM admin_management_receipts) OR
     EXISTS (SELECT 1 FROM admin_approval_requirements) THEN
    RAISE EXCEPTION 'Admin management downgrade refused: supervision or account evidence exists';
  END IF;
END;
$guard$;
DROP TABLE admin_management_receipts;
DROP TABLE admin_approval_requirements;
""")
