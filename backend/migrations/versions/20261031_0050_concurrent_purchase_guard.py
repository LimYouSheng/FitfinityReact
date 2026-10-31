"""Retire sequential validity from the insert guard while retaining purchased-term checks."""

from alembic import op

revision = "20261031_0050"
down_revision = "20261031_0049"
branch_labels = None
depends_on = None

UPGRADE_SQL = r"""
CREATE OR REPLACE FUNCTION ff_purchase_insert() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE definition package_template_revisions%ROWTYPE;
BEGIN
  PERFORM 1 FROM clients WHERE id=NEW.client_id AND status='active' FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'active client required' USING ERRCODE='23514'; END IF;
  PERFORM 1 FROM package_templates WHERE id=NEW.template_id AND status='active' FOR SHARE;
  IF NOT FOUND THEN RAISE EXCEPTION 'active package template required' USING ERRCODE='23514'; END
    IF;
  IF NEW.template_revision <> (SELECT max(revision) FROM package_template_revisions WHERE
    template_id=NEW.template_id) THEN
    RAISE EXCEPTION 'package template revision changed after review' USING ERRCODE='23514'; END IF;
  SELECT * INTO STRICT definition FROM package_template_revisions
    WHERE template_id=NEW.template_id AND revision=NEW.template_revision;
  IF (NEW.name, NEW.total_sessions, NEW.validity_days) IS DISTINCT FROM
     (definition.name,definition.total_sessions,definition.validity_days) THEN
    RAISE EXCEPTION 'purchase terms must match reviewed template revision' USING ERRCODE='23514';
    END IF;
  RETURN NEW;
END $$;
"""

DOWNGRADE_SQL = r"""
DO $guard$
BEGIN
  IF EXISTS (SELECT 1 FROM package_purchases a JOIN package_purchases b
      ON a.client_id = b.client_id AND a.id < b.id
      WHERE a.status = 'active' AND b.status = 'active'
      AND daterange(a.start_date, a.end_date, '[]') &&
          daterange(b.start_date, b.end_date, '[]')) THEN
    RAISE EXCEPTION 'concurrent purchase downgrade refused: overlapping active purchases exist';
  END IF;
END;
$guard$;
CREATE OR REPLACE FUNCTION ff_purchase_insert() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE definition package_template_revisions%ROWTYPE; last_day date;
BEGIN
  PERFORM 1 FROM clients WHERE id=NEW.client_id AND status='active' FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'active client required' USING ERRCODE='23514'; END IF;
  PERFORM 1 FROM package_templates WHERE id=NEW.template_id AND status='active' FOR SHARE;
  IF NOT FOUND THEN RAISE EXCEPTION 'active package template required' USING ERRCODE='23514'; END
    IF;
  IF NEW.template_revision <> (SELECT max(revision) FROM package_template_revisions WHERE
    template_id=NEW.template_id) THEN
    RAISE EXCEPTION 'package template revision changed after review' USING ERRCODE='23514'; END IF;
  SELECT * INTO STRICT definition FROM package_template_revisions
    WHERE template_id=NEW.template_id AND revision=NEW.template_revision;
  IF (NEW.name, NEW.total_sessions, NEW.validity_days) IS DISTINCT FROM
     (definition.name,definition.total_sessions,definition.validity_days) THEN
    RAISE EXCEPTION 'purchase terms must match reviewed template revision' USING ERRCODE='23514';
    END IF;
  SELECT max(end_date) INTO last_day FROM package_purchases WHERE client_id=NEW.client_id AND
    status='active';
  IF NEW.start_date <= last_day THEN RAISE EXCEPTION
    'purchase must follow all active purchase dates' USING ERRCODE='23514'; END IF;
  RETURN NEW;
END $$;
"""


def upgrade():
    op.execute(UPGRADE_SQL)


def downgrade():
    op.execute(DOWNGRADE_SQL)
