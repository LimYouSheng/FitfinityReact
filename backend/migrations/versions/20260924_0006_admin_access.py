"""Expand staff roles and add Admin contacts/invitation receipts; preserve all existing records.

Deploy compatible application versions before creating Admin accounts. Downgrade refuses
once Admin data exists; no rename, removed column, or rewriting of earlier migrations.
"""

from alembic import op

revision = "20260924_0006"
down_revision = "20260921_0005"
branch_labels = None
depends_on = None

UPGRADE_SQL = r"""
ALTER TABLE staff_users DROP CONSTRAINT ck_staff_users_role_values;

ALTER TABLE staff_users ADD CONSTRAINT ck_staff_users_role_values CHECK (role IN ('owner',
    'admin', 'trainer'));

CREATE TABLE admin_profiles (
    user_id UUID NOT NULL,
    user_role VARCHAR(16) DEFAULT 'admin' NOT NULL,
    phone_country_code VARCHAR(4) NOT NULL,
    phone_number VARCHAR(32) NOT NULL,
    birthday DATE NOT NULL,
    gender VARCHAR(24) NOT NULL,
    version INTEGER DEFAULT 1 NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_admin_profiles PRIMARY KEY (id),
    CONSTRAINT fk_admin_profiles_user_id_user_role_staff_users FOREIGN KEY(user_id, user_role)
    REFERENCES staff_users (id, role),
    CONSTRAINT ck_admin_profiles_admin_role CHECK (user_role = 'admin'),
    CONSTRAINT ck_admin_profiles_gender_values CHECK (gender IN ('Female', 'Male', 'Other',
    'Prefer not to say')),
    CONSTRAINT uq_admin_profiles_user_id UNIQUE (user_id),
    CONSTRAINT ck_admin_profiles_positive_version CHECK (version > 0),
    CONSTRAINT ck_admin_profiles_phone_format CHECK (phone_country_code ~ '^\+[1-9][0-9]{0,2}$'
    AND phone_number ~ '^[0-9 ()-]+$' AND length(regexp_replace(phone_number, '[^0-9]', '',
    'g')) >= 6 AND length(regexp_replace(phone_country_code || phone_number, '[^0-9]', '', 'g'))
    <= 15)
);

CREATE TABLE staff_invitations (
    user_id UUID NOT NULL,
    request_key UUID NOT NULL,
    request_sha256 VARCHAR(64) NOT NULL,
    status VARCHAR(16) DEFAULT 'pending' NOT NULL,
    lease_id UUID,
    lease_until TIMESTAMP WITH TIME ZONE,
    sent_at TIMESTAMP WITH TIME ZONE,
    actor_id UUID NOT NULL,
    actor_name VARCHAR(200) NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_staff_invitations PRIMARY KEY (id),
    CONSTRAINT ck_staff_invitations_status_values CHECK (status IN ('pending',
    'sending', 'sent', 'unknown')),
    CONSTRAINT ck_staff_invitations_request_digest CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_staff_invitations_lease_pair CHECK ((lease_id IS NULL) = (lease_until IS NULL)),
    CONSTRAINT uq_staff_invitations_user_id UNIQUE (user_id),
    CONSTRAINT fk_staff_invitations_user_id_staff_users FOREIGN KEY(user_id) REFERENCES
    staff_users (id),
    CONSTRAINT uq_staff_invitations_request_key UNIQUE (request_key),
    CONSTRAINT fk_staff_invitations_actor_id_staff_users FOREIGN KEY(actor_id) REFERENCES
    staff_users (id),
    CONSTRAINT ck_staff_invitations_actor_name_required CHECK (length(btrim(actor_name)) > 0)
);

CREATE INDEX ix_staff_invitations_actor_id ON staff_invitations (actor_id);

CREATE TRIGGER ff_version BEFORE INSERT OR UPDATE ON admin_profiles FOR EACH ROW EXECUTE
    FUNCTION ff_version();

CREATE TRIGGER ff_no_delete BEFORE DELETE ON admin_profiles FOR EACH ROW EXECUTE FUNCTION
    ff_immutable();

CREATE TRIGGER ff_preserve BEFORE UPDATE ON admin_profiles FOR EACH ROW EXECUTE FUNCTION
    ff_preserve_fields('user_id', 'user_role');

CREATE TRIGGER ff_actor BEFORE INSERT ON staff_invitations FOR EACH ROW EXECUTE FUNCTION ff_actor();

CREATE TRIGGER ff_no_delete BEFORE DELETE ON staff_invitations FOR EACH ROW EXECUTE FUNCTION
    ff_immutable();

CREATE TRIGGER ff_preserve BEFORE UPDATE ON staff_invitations FOR EACH ROW EXECUTE FUNCTION
    ff_preserve_fields('id', 'created_at', 'user_id', 'request_key', 'request_sha256',
    'actor_id', 'actor_name');
"""

DOWNGRADE_SQL = r"""
DO $guard$
BEGIN
  IF EXISTS (SELECT 1 FROM staff_users WHERE role = 'admin')
     OR EXISTS (SELECT 1 FROM admin_profiles) OR EXISTS (SELECT 1 FROM staff_invitations) THEN
    RAISE EXCEPTION 'Admin downgrade refused: staff or invitation records exist';
  END IF;
END;
$guard$;
DROP TABLE staff_invitations;
DROP TABLE admin_profiles;
ALTER TABLE staff_users DROP CONSTRAINT ck_staff_users_role_values;
ALTER TABLE staff_users ADD CONSTRAINT ck_staff_users_role_values CHECK (role IN ('owner',
    'trainer'));
"""


def upgrade():
    op.execute(UPGRADE_SQL)


def downgrade():
    op.execute(DOWNGRADE_SQL)
