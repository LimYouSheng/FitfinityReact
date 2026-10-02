"""Add immutable per-person assessment storage without changing M5.2/M5.3 data."""

import hashlib
import json
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "20260921_0004"
down_revision = "20260915_0003"
branch_labels = None
depends_on = None

UPGRADE_SQL = r"""
CREATE TABLE assessment_form_versions (
	form_id VARCHAR(64) NOT NULL,
	version INTEGER NOT NULL,
	title VARCHAR(200) NOT NULL,
	source_filename VARCHAR(200) NOT NULL,
	source_sha256 VARCHAR(64) NOT NULL,
	layout_release VARCHAR(64) NOT NULL,
	layout_sha256 VARCHAR(64) NOT NULL,
	definition JSONB NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_assessment_form_versions PRIMARY KEY (form_id, version),
	CONSTRAINT ck_assessment_form_versions_form_identity CHECK (form_id ~ '^[a-z][a-z0-9_]{0,63}$'),
	CONSTRAINT ck_assessment_form_versions_title_required CHECK (length(btrim(title)) > 0),
	CONSTRAINT ck_assessment_form_versions_source_digest CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
	CONSTRAINT ck_assessment_form_versions_layout_digest CHECK (layout_sha256 ~ '^[0-9a-f]{64}$'),
CONSTRAINT ck_assessment_form_versions_layout_release_required CHECK
(length(btrim(layout_release)) > 0),
CONSTRAINT ck_assessment_form_versions_definition_object CHECK (jsonb_typeof(definition) =
'object' AND octet_length(definition::text) <= 131072),
	CONSTRAINT ck_assessment_form_versions_positive_version CHECK (version > 0)
);

CREATE TABLE client_assessments (
	client_person_id UUID NOT NULL,
	form_id VARCHAR(64) NOT NULL,
	form_version INTEGER NOT NULL,
	actor_id UUID NOT NULL,
	actor_name VARCHAR(200) NOT NULL,
	version INTEGER DEFAULT 1 NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_client_assessments PRIMARY KEY (id),
CONSTRAINT fk_client_assessments_form_id_form_version_assessment_f_09a0 FOREIGN KEY(form_id,
form_version) REFERENCES assessment_form_versions (form_id, version),
	CONSTRAINT uq_client_assessments_id_form_id_form_version UNIQUE (id, form_id, form_version),
CONSTRAINT fk_client_assessments_client_person_id_client_people FOREIGN KEY(client_person_id)
REFERENCES client_people (id),
CONSTRAINT fk_client_assessments_actor_id_staff_users FOREIGN KEY(actor_id) REFERENCES
staff_users (id),
	CONSTRAINT ck_client_assessments_positive_version CHECK (version > 0),
	CONSTRAINT ck_client_assessments_actor_name_required CHECK (length(btrim(actor_name)) > 0)
);

CREATE INDEX ix_assessment_person_form_history ON client_assessments (client_person_id, form_id,
created_at);

CREATE INDEX ix_client_assessments_actor_id ON client_assessments (actor_id);

CREATE TABLE client_assessment_revisions (
	assessment_id UUID NOT NULL,
	revision INTEGER NOT NULL,
	previous_revision INTEGER,
	form_id VARCHAR(64) NOT NULL,
	form_version INTEGER NOT NULL,
	status VARCHAR(16) NOT NULL,
	event VARCHAR(16) NOT NULL,
	assessment_date DATE NOT NULL,
	assessor_id UUID NOT NULL,
	assessor_name VARCHAR(200) NOT NULL,
	client_name VARCHAR(200) NOT NULL,
	client_birthday DATE NOT NULL,
	answers JSONB NOT NULL,
	reason TEXT,
	actor_id UUID NOT NULL,
	actor_name VARCHAR(200) NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_client_assessment_revisions PRIMARY KEY (id),
CONSTRAINT uq_client_assessment_revisions_assessment_id_revision UNIQUE (assessment_id,
revision),
CONSTRAINT fk_client_assessment_revisions_assessment_id_form_id_fo_5ebe FOREIGN
KEY(assessment_id, form_id, form_version) REFERENCES client_assessments (id, form_id,
form_version),
CONSTRAINT fk_client_assessment_revisions_assessment_id_previous_r_a0ec FOREIGN
KEY(assessment_id, previous_revision) REFERENCES client_assessment_revisions (assessment_id,
revision),
CONSTRAINT ck_client_assessment_revisions_revision_chain CHECK ((revision = 1 AND
previous_revision IS NULL) OR (revision > 1 AND previous_revision IS NOT NULL AND
previous_revision = revision - 1)),
CONSTRAINT ck_client_assessment_revisions_status_values CHECK (status IN ('draft', 'completed',
'voided')),
CONSTRAINT ck_client_assessment_revisions_event_values CHECK (event IN ('draft', 'completed',
'correction', 'voided')),
CONSTRAINT ck_client_assessment_revisions_event_status CHECK ((event = 'draft' AND status =
'draft') OR (event IN ('completed', 'correction') AND status = 'completed') OR (event = 'voided'
AND status = 'voided')),
CONSTRAINT ck_client_assessment_revisions_reason_required CHECK ((event IN ('correction',
'voided') AND reason IS NOT NULL AND length(btrim(reason)) BETWEEN 1 AND 2000) OR (event IN
('draft', 'completed') AND reason IS NULL)),
CONSTRAINT ck_client_assessment_revisions_snapshot_names CHECK (length(btrim(client_name)) > 0
AND length(btrim(assessor_name)) > 0),
CONSTRAINT ck_client_assessment_revisions_answers_object CHECK (jsonb_typeof(answers) = 'object'
AND octet_length(answers::text) <= 65536),
CONSTRAINT fk_client_assessment_revisions_assessor_id_staff_users FOREIGN KEY(assessor_id)
REFERENCES staff_users (id),
CONSTRAINT fk_client_assessment_revisions_actor_id_staff_users FOREIGN KEY(actor_id) REFERENCES
staff_users (id),
CONSTRAINT ck_client_assessment_revisions_actor_name_required CHECK (length(btrim(actor_name)) >
0)
);

CREATE INDEX ix_assessment_revision_date ON client_assessment_revisions (assessment_date);

CREATE INDEX ix_client_assessment_revisions_actor_id ON client_assessment_revisions (actor_id);

CREATE INDEX ix_client_assessment_revisions_assessor_id ON client_assessment_revisions
(assessor_id);

ALTER TABLE client_assessments ADD CONSTRAINT fk_assessment_current_revision FOREIGN KEY(id,
version) REFERENCES client_assessment_revisions (assessment_id, revision) DEFERRABLE INITIALLY
DEFERRED;

-- All answers stay in one immutable revision; the root only owns identity/current version.
CREATE FUNCTION ff_assessment_revision() RETURNS trigger LANGUAGE plpgsql AS $fn$
DECLARE
  parent client_assessments;
  prior client_assessment_revisions;
  schema jsonb;
  field jsonb;
  answer record;
  plain text;
BEGIN
  SELECT * INTO STRICT parent FROM client_assessments
    WHERE id=NEW.assessment_id FOR UPDATE;
  SELECT * INTO prior FROM client_assessment_revisions
    WHERE assessment_id=NEW.assessment_id ORDER BY revision DESC LIMIT 1;
  IF NEW.revision <> parent.version OR NEW.revision <> COALESCE(prior.revision, 0) + 1 THEN
    RAISE EXCEPTION 'assessment revision sequence mismatch' USING ERRCODE='23514';
  END IF;
  IF (prior.id IS NULL AND NEW.event <> 'draft')
     OR (prior.status='draft' AND NEW.event NOT IN ('draft','completed','voided'))
     OR (prior.status='completed' AND NEW.event NOT IN ('correction','voided'))
     OR prior.status='voided' THEN
    RAISE EXCEPTION 'invalid assessment transition' USING ERRCODE='23514';
  END IF;
  IF (NEW.form_id, NEW.form_version) IS DISTINCT FROM (parent.form_id, parent.form_version) THEN
    RAISE EXCEPTION 'assessment form identity mismatch' USING ERRCODE='23514';
  END IF;
  SELECT name INTO NEW.actor_name FROM staff_users WHERE id=NEW.actor_id AND status='active';
  IF NOT FOUND THEN
    RAISE EXCEPTION 'active assessment recording staff required' USING ERRCODE='23514';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM client_people p JOIN clients c ON c.id=p.client_id
                 WHERE p.id=parent.client_person_id AND c.status='active') THEN
    RAISE EXCEPTION 'active assessment person required' USING ERRCODE='23514';
  END IF;
  NEW.created_at := clock_timestamp();
  IF prior.status='completed' OR NEW.event='voided' THEN
    -- A later profile/name edit must never rewrite the original assessment header.
    NEW.client_name := prior.client_name;
    NEW.client_birthday := prior.client_birthday;
    NEW.assessor_id := prior.assessor_id;
    NEW.assessor_name := prior.assessor_name;
  ELSE
    SELECT name, birthday INTO STRICT NEW.client_name, NEW.client_birthday
      FROM client_people WHERE id=parent.client_person_id;
    NEW.assessor_id := NEW.actor_id;
    NEW.assessor_name := NEW.actor_name;
  END IF;
  IF NEW.event='voided' AND
(NEW.answers, NEW.assessment_date) IS DISTINCT FROM (prior.answers, prior.assessment_date) THEN
    RAISE EXCEPTION 'void must preserve assessment evidence' USING ERRCODE='23514';
  END IF;
  SELECT definition INTO STRICT schema FROM assessment_form_versions
    WHERE form_id=NEW.form_id AND version=NEW.form_version;
  IF jsonb_typeof(NEW.answers) IS DISTINCT FROM 'object'
     OR octet_length(NEW.answers::text) > (schema->>'max_bytes')::integer THEN
    RAISE EXCEPTION 'invalid assessment answer object' USING ERRCODE='23514';
  END IF;
  FOR answer IN SELECT * FROM jsonb_each(NEW.answers) LOOP
    field := schema->'fields'->answer.key;
    IF field IS NULL THEN
      RAISE EXCEPTION 'unsupported assessment answer field' USING ERRCODE='23514';
    END IF;
    plain := answer.value #>> '{}';
    IF field->>'type'='number' THEN
      IF jsonb_typeof(answer.value) <> 'number' THEN
        RAISE EXCEPTION 'assessment answer must be numeric' USING ERRCODE='23514';
      END IF;
      IF plain::numeric < (field->>'min')::numeric
         OR (field ? 'max' AND plain::numeric > (field->>'max')::numeric) THEN
        RAISE EXCEPTION 'assessment answer out of range' USING ERRCODE='23514';
      END IF;
    ELSE
      IF jsonb_typeof(answer.value) <> 'string' OR plain !~ '[^[:space:]]' THEN
        RAISE EXCEPTION 'assessment answer must be nonblank text' USING ERRCODE='23514';
      END IF;
      IF field ? 'options' THEN
        IF NOT (field->'options' @> jsonb_build_array(answer.value)) THEN
          RAISE EXCEPTION 'invalid assessment choice' USING ERRCODE='23514';
        END IF;
      ELSIF length(plain) > (field->>'max_length')::integer THEN
        RAISE EXCEPTION 'assessment answer text too long' USING ERRCODE='23514';
      END IF;
    END IF;
  END LOOP;
  IF NEW.status='completed' AND NEW.answers='{}'::jsonb
     AND NOT (schema->>'allow_empty_completion')::boolean THEN
    RAISE EXCEPTION 'completed assessment requires an answer' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
END;
$fn$;

CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON assessment_form_versions
  FOR EACH ROW EXECUTE FUNCTION ff_immutable();
CREATE TRIGGER ff_version BEFORE INSERT OR UPDATE ON client_assessments
  FOR EACH ROW EXECUTE FUNCTION ff_version();
CREATE TRIGGER ff_actor BEFORE INSERT ON client_assessments
  FOR EACH ROW EXECUTE FUNCTION ff_actor();
CREATE TRIGGER ff_assessment_identity BEFORE UPDATE ON client_assessments
  FOR EACH ROW EXECUTE FUNCTION ff_preserve_fields(
    'client_person_id','form_id','form_version','actor_id','actor_name');
CREATE TRIGGER ff_immutable BEFORE DELETE ON client_assessments
  FOR EACH ROW EXECUTE FUNCTION ff_immutable();
CREATE TRIGGER ff_assessment_revision BEFORE INSERT ON client_assessment_revisions
  FOR EACH ROW EXECUTE FUNCTION ff_assessment_revision();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON client_assessment_revisions
  FOR EACH ROW EXECUTE FUNCTION ff_immutable();
"""

DOWNGRADE_SQL = r"""
DO $guard$
BEGIN
  IF EXISTS (SELECT 1 FROM client_assessments)
     OR EXISTS (SELECT 1 FROM client_assessment_revisions) THEN
    RAISE EXCEPTION 'assessment downgrade refused: saved assessments exist';
  END IF;
  IF (SELECT count(*) FROM assessment_form_versions) <> 11
     OR EXISTS (SELECT 1 FROM assessment_form_versions WHERE version <> 1) THEN
    RAISE EXCEPTION 'assessment downgrade refused: additional form definitions exist';
  END IF;
END;
$guard$;
ALTER TABLE client_assessments DROP CONSTRAINT fk_assessment_current_revision;
DROP TABLE client_assessment_revisions;
DROP TABLE client_assessments;
DROP TABLE assessment_form_versions;
DROP FUNCTION ff_assessment_revision();
"""


def upgrade():
    # Frozen release data, not mutable application imports. Future forms need a new migration.
    content = (
        Path(__file__).parent.parent / "definitions/20260921_assessments_v1.json"
    ).read_bytes()
    if (
        hashlib.sha256(content).hexdigest()
        != "1d53752765fe92a07ab07cc370e67a6d8ac15da18126e84cfedf2be5d3d6c54d"
    ):
        raise RuntimeError("Assessment form release digest mismatch")
    op.execute(UPGRADE_SQL)
    statement = sa.text(
        "INSERT INTO assessment_form_versions "
        "(form_id, version, title, source_filename, source_sha256, layout_release, "
        "layout_sha256, definition) VALUES "
        "(:form_id, :version, :title, :source_filename, :source_sha256, :layout_release, "
        ":layout_sha256, CAST(:definition AS jsonb))"
    )
    for record in json.loads(content):
        record["definition"] = json.dumps(record["definition"], ensure_ascii=False)
        op.get_bind().execute(statement, record)


def downgrade():
    op.execute(DOWNGRADE_SQL)
