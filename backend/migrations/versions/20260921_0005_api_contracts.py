"""Add durable API retry receipts and assessment-access evidence; preserve applied history."""

from alembic import op

revision = "20260921_0005"
down_revision = "20260921_0004"
branch_labels = None
depends_on = None

UPGRADE_SQL = r"""
CREATE TABLE api_receipts (
	request_key UUID NOT NULL,
	operation VARCHAR(32) NOT NULL,
	request_sha256 VARCHAR(64) NOT NULL,
	revision_id UUID NOT NULL,
	actor_id UUID NOT NULL,
	actor_name VARCHAR(200) NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_api_receipts PRIMARY KEY (id),
	CONSTRAINT uq_api_receipts_actor_id_request_key UNIQUE (actor_id, request_key),
        CONSTRAINT ck_api_receipts_operation_values CHECK (operation IN ('assessment_create',
'assessment_save')),
	CONSTRAINT ck_api_receipts_request_digest CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
        CONSTRAINT fk_api_receipts_revision_id_client_assessment_revisions FOREIGN
KEY(revision_id) REFERENCES client_assessment_revisions (id),
        CONSTRAINT fk_api_receipts_actor_id_staff_users FOREIGN KEY(actor_id) REFERENCES
staff_users (id),
	CONSTRAINT ck_api_receipts_actor_name_required CHECK (length(btrim(actor_name)) > 0)
);

CREATE INDEX ix_api_receipts_actor_id ON api_receipts (actor_id);

CREATE TRIGGER ff_actor BEFORE INSERT ON api_receipts FOR EACH ROW EXECUTE FUNCTION ff_actor();

CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON api_receipts FOR EACH ROW EXECUTE
FUNCTION ff_immutable();

CREATE TABLE assessment_access (
	client_person_id UUID NOT NULL,
	action VARCHAR(16) NOT NULL,
	assessment_id UUID,
	actor_id UUID NOT NULL,
	actor_name VARCHAR(200) NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_assessment_access PRIMARY KEY (id),
        CONSTRAINT ck_assessment_access_action_values CHECK (action IN ('list', 'view',
'history', 'create', 'save', 'replay')),
        CONSTRAINT fk_assessment_access_client_person_id_client_people FOREIGN
KEY(client_person_id) REFERENCES client_people (id),
        CONSTRAINT fk_assessment_access_assessment_id_client_assessments FOREIGN
KEY(assessment_id) REFERENCES client_assessments (id),
        CONSTRAINT fk_assessment_access_actor_id_staff_users FOREIGN KEY(actor_id) REFERENCES
staff_users (id),
	CONSTRAINT ck_assessment_access_actor_name_required CHECK (length(btrim(actor_name)) > 0)
);

CREATE INDEX ix_assessment_access_actor_id ON assessment_access (actor_id);

CREATE INDEX ix_assessment_access_assessment_id ON assessment_access (assessment_id);

CREATE INDEX ix_assessment_access_client_person_id ON assessment_access (client_person_id);

CREATE TRIGGER ff_actor BEFORE INSERT ON assessment_access FOR EACH ROW EXECUTE FUNCTION ff_actor();

CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON assessment_access FOR EACH ROW EXECUTE
FUNCTION ff_immutable();
"""

DOWNGRADE_SQL = r"""
DO $guard$
BEGIN
  IF EXISTS (SELECT 1 FROM api_receipts) OR EXISTS (SELECT 1 FROM assessment_access) THEN
    RAISE EXCEPTION 'API contract downgrade refused: receipt or access history exists';
  END IF;
END;
$guard$;
DROP TABLE assessment_access;
DROP TABLE api_receipts;
"""


def upgrade():
    op.execute(UPGRADE_SQL)


def downgrade():
    op.execute(DOWNGRADE_SQL)
