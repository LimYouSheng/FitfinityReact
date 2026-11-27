"""Persist Owner contact details and immutable profile-save evidence."""

from alembic import op

revision = "20261127_0053"
down_revision = "20261101_0052"
branch_labels = None
depends_on = None

UPGRADE_SQL = """
CREATE TABLE owner_profiles (
 user_id UUID PRIMARY KEY,
 user_role VARCHAR(16) NOT NULL DEFAULT 'owner',
 FOREIGN KEY(user_id,user_role) REFERENCES staff_users(id,role),
 CONSTRAINT ck_owner_profiles_owner_role CHECK(user_role = 'owner'),
 phone_country_code VARCHAR(4) NOT NULL, phone_number VARCHAR(32) NOT NULL,
 birthday DATE NOT NULL, gender VARCHAR(24) NOT NULL,
 CONSTRAINT ck_owner_profiles_gender_values
 CHECK(gender IN ('Female','Male','Other','Prefer not to say'))
);
CREATE TABLE owner_profile_receipts (
 id UUID PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 actor_id UUID NOT NULL REFERENCES staff_users(id), actor_name VARCHAR(200) NOT NULL,
 request_key UUID NOT NULL, request_sha256 VARCHAR(64) NOT NULL, result JSONB NOT NULL,
 CONSTRAINT uq_owner_profile_receipts_actor_id_request_key UNIQUE(actor_id,request_key),
 CONSTRAINT ck_owner_profile_receipts_request_digest CHECK(request_sha256 ~ '^[0-9a-f]{64}$'),
 CONSTRAINT ck_owner_profile_receipts_actor_name_required CHECK(length(btrim(actor_name)) > 0)
);
CREATE INDEX ix_owner_profile_receipts_actor_id ON owner_profile_receipts(actor_id);
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON owner_profile_receipts
 FOR EACH ROW EXECUTE FUNCTION ff_immutable();
"""


def upgrade():
    op.execute(UPGRADE_SQL)


def downgrade():
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM owner_profiles)
        OR EXISTS (SELECT 1 FROM owner_profile_receipts) THEN
        RAISE EXCEPTION 'populated owner profile downgrade refused';
      END IF;
    END $$""")
    op.drop_table("owner_profile_receipts")
    op.drop_table("owner_profiles")
