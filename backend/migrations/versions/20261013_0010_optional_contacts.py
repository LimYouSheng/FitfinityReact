"""Preserve prototype optional contact edits without inventing missing identity values."""

from alembic import op

revision = "20261013_0010"
down_revision = "20261013_0009"
branch_labels = None
depends_on = None

UPGRADE_SQL = r"""
ALTER TABLE client_people DROP CONSTRAINT ck_client_people_emergency_format;
ALTER TABLE client_people ADD CONSTRAINT ck_client_people_emergency_format
 CHECK (emergency_country_code ~ '^\+[1-9][0-9]{0,2}$' AND (emergency_number = ''
    OR (emergency_number ~ '^[0-9 ()-]+$'
    AND length(regexp_replace(emergency_number, '[^0-9]', '', 'g')) >= 6
    AND length(regexp_replace(emergency_country_code || emergency_number,
        '[^0-9]', '', 'g')) <= 15)));

ALTER TABLE client_people DROP CONSTRAINT ck_client_people_phone_format;
ALTER TABLE client_people ADD CONSTRAINT ck_client_people_phone_format
 CHECK (phone_country_code ~ '^\+[1-9][0-9]{0,2}$' AND (phone_number = ''
    OR (phone_number ~ '^[0-9 ()-]+$'
    AND length(regexp_replace(phone_number, '[^0-9]', '', 'g')) >= 6
    AND length(regexp_replace(phone_country_code || phone_number, '[^0-9]', '', 'g')) <= 15)));

ALTER TABLE client_people ALTER COLUMN birthday DROP NOT NULL;
ALTER TABLE client_people DROP CONSTRAINT ck_client_people_names_required;
ALTER TABLE client_people ADD CONSTRAINT ck_client_people_names_required
    CHECK (length(btrim(name)) > 0);
ALTER TABLE client_people DROP CONSTRAINT ck_client_people_email_normalized;
ALTER TABLE client_people ADD CONSTRAINT ck_client_people_email_normalized
    CHECK (email = '' OR (email = lower(btrim(email)) AND position('@' in email) > 1));
ALTER TABLE client_people DROP CONSTRAINT ck_client_people_gender_values;
ALTER TABLE client_people ADD CONSTRAINT ck_client_people_gender_values
    CHECK (gender IN ('', 'Female', 'Male', 'Other', 'Prefer not to say'));
ALTER TABLE client_people DROP CONSTRAINT ck_client_people_emergency_relationship_values;
ALTER TABLE client_people ADD CONSTRAINT ck_client_people_emergency_relationship_values
    CHECK (emergency_relationship IN
        ('', 'Spouse', 'Parent', 'Sibling', 'Child', 'Partner', 'Friend', 'Guardian', 'Other'));
"""

DOWNGRADE_SQL = r"""
DO $guard$
BEGIN
    IF EXISTS (SELECT 1 FROM client_people WHERE birthday IS NULL OR email = ''
        OR phone_number = '' OR emergency_number = ''
        OR gender = '' OR length(btrim(emergency_name)) = 0 OR emergency_relationship = '') THEN
        RAISE EXCEPTION 'Optional contacts downgrade refused: cleared fields exist';
    END IF;
END;
$guard$;
ALTER TABLE client_people DROP CONSTRAINT ck_client_people_phone_format;
ALTER TABLE client_people ADD CONSTRAINT ck_client_people_phone_format
 CHECK (phone_country_code ~ '^\+[1-9][0-9]{0,2}$'
    AND phone_number ~ '^[0-9 ()-]+$'
    AND length(regexp_replace(phone_number, '[^0-9]', '', 'g')) >= 6
    AND length(regexp_replace(phone_country_code || phone_number, '[^0-9]', '', 'g')) <= 15);
ALTER TABLE client_people DROP CONSTRAINT ck_client_people_emergency_format;
ALTER TABLE client_people ADD CONSTRAINT ck_client_people_emergency_format
 CHECK (emergency_country_code ~ '^\+[1-9][0-9]{0,2}$'
    AND emergency_number ~ '^[0-9 ()-]+$'
    AND length(regexp_replace(emergency_number, '[^0-9]', '', 'g')) >= 6
    AND length(regexp_replace(emergency_country_code || emergency_number,
        '[^0-9]', '', 'g')) <= 15);
ALTER TABLE client_people ALTER COLUMN birthday SET NOT NULL;
ALTER TABLE client_people DROP CONSTRAINT ck_client_people_names_required;
ALTER TABLE client_people ADD CONSTRAINT ck_client_people_names_required
    CHECK (length(btrim(name)) > 0 AND length(btrim(emergency_name)) > 0);
ALTER TABLE client_people DROP CONSTRAINT ck_client_people_email_normalized;
ALTER TABLE client_people ADD CONSTRAINT ck_client_people_email_normalized
    CHECK (email = lower(btrim(email)) AND position('@' in email) > 1);
ALTER TABLE client_people DROP CONSTRAINT ck_client_people_gender_values;
ALTER TABLE client_people ADD CONSTRAINT ck_client_people_gender_values
    CHECK (gender IN ('Female', 'Male', 'Other', 'Prefer not to say'));
ALTER TABLE client_people DROP CONSTRAINT ck_client_people_emergency_relationship_values;
ALTER TABLE client_people ADD CONSTRAINT ck_client_people_emergency_relationship_values
    CHECK (emergency_relationship IN
        ('Spouse', 'Parent', 'Sibling', 'Child', 'Partner', 'Friend', 'Guardian', 'Other'));
"""


def upgrade():
    op.execute(UPGRADE_SQL)


def downgrade():
    op.execute(DOWNGRADE_SQL)
