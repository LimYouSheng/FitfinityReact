"""Reserve pending staff emails across onboarding and profile changes."""

from alembic import op

revision = "20261013_0013"
down_revision = "20261013_0012"
branch_labels = None
depends_on = None

UPGRADE_SQL = r"""
CREATE TABLE staff_email_changes (
    request_key UUID NOT NULL,
    trainer_version INTEGER NOT NULL,
    user_id UUID NOT NULL REFERENCES staff_users(id),
    identity_id UUID NOT NULL REFERENCES staff_identities(id),
    old_email VARCHAR(320) NOT NULL,
    new_email VARCHAR(320) NOT NULL,
    state VARCHAR(16) DEFAULT 'requested' NOT NULL,
    attempts INTEGER DEFAULT 0 NOT NULL,
    sends INTEGER DEFAULT 0 NOT NULL,
    last_sent_at TIMESTAMPTZ,
    lease_id UUID,
    lease_until TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    actor_id UUID NOT NULL REFERENCES staff_users(id),
    actor_name VARCHAR(200) NOT NULL,
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
    CONSTRAINT uq_staff_email_changes_actor_id_request_key UNIQUE(actor_id, request_key),
    CONSTRAINT ck_staff_email_changes_state_values
      CHECK(state IN ('requested', 'sending', 'pending', 'verifying', 'completed')),
    CONSTRAINT ck_staff_email_changes_attempt_limit CHECK(attempts BETWEEN 0 AND 6),
    CONSTRAINT ck_staff_email_changes_send_limit CHECK(sends BETWEEN 0 AND 6),
    CONSTRAINT ck_staff_email_changes_lease_pair
      CHECK((lease_id IS NULL) = (lease_until IS NULL)),
    CONSTRAINT ck_staff_email_changes_completion_pair
      CHECK((state = 'completed') = (completed_at IS NOT NULL)),
    CONSTRAINT ck_staff_email_changes_email_change
      CHECK(old_email <> new_email AND new_email = lower(btrim(new_email))
            AND position('@' in new_email) > 1),
    CONSTRAINT ck_staff_email_changes_actor_name_required CHECK(length(btrim(actor_name)) > 0)
);
CREATE INDEX ix_staff_email_changes_user_id ON staff_email_changes(user_id);
CREATE INDEX ix_staff_email_changes_actor_id ON staff_email_changes(actor_id);
CREATE UNIQUE INDEX uq_staff_email_changes_pending_user ON staff_email_changes(user_id)
  WHERE state <> 'completed';
CREATE UNIQUE INDEX uq_staff_email_changes_pending_email ON staff_email_changes(new_email)
  WHERE state <> 'completed';

CREATE FUNCTION ff_staff_email_reservation() RETURNS trigger LANGUAGE plpgsql AS $fn$
DECLARE address text; owner_id uuid;
BEGIN
  -- A database guard covers onboarding and direct persistence writers too. All checks
  -- run after acquiring the same transaction lock; no provider call holds this lock.
  PERFORM pg_advisory_xact_lock(714602036);
  IF TG_TABLE_NAME = 'staff_email_changes' THEN
    address := NEW.new_email; owner_id := NEW.user_id;
    IF NOT EXISTS (SELECT 1 FROM staff_identities
                   WHERE id = NEW.identity_id AND user_id = owner_id) THEN
      RAISE EXCEPTION 'email identity mismatch' USING ERRCODE = '23514';
    END IF;
    IF EXISTS (SELECT 1 FROM staff_users WHERE email = address AND id <> owner_id)
       OR EXISTS (SELECT 1 FROM trainers WHERE email = address
                  AND user_id IS DISTINCT FROM owner_id) THEN
      RAISE EXCEPTION 'staff email unavailable' USING ERRCODE = '23505';
    END IF;
  ELSE
    address := NEW.email;
    IF TG_TABLE_NAME = 'staff_users' THEN owner_id := NEW.id;
    ELSE owner_id := NEW.user_id; END IF;
  END IF;
  IF EXISTS (SELECT 1 FROM staff_email_changes WHERE new_email = address
             AND state <> 'completed' AND user_id IS DISTINCT FROM owner_id) THEN
    RAISE EXCEPTION 'staff email reserved' USING ERRCODE = '23505';
  END IF;
  RETURN NEW;
END;
$fn$;
CREATE TRIGGER ff_email_reservation BEFORE INSERT OR UPDATE OF email ON staff_users
  FOR EACH ROW EXECUTE FUNCTION ff_staff_email_reservation();
CREATE TRIGGER ff_email_reservation BEFORE INSERT OR UPDATE OF email, user_id ON trainers
  FOR EACH ROW EXECUTE FUNCTION ff_staff_email_reservation();
CREATE TRIGGER ff_email_reservation BEFORE INSERT ON staff_email_changes
  FOR EACH ROW EXECUTE FUNCTION ff_staff_email_reservation();
CREATE TRIGGER ff_actor BEFORE INSERT ON staff_email_changes
  FOR EACH ROW EXECUTE FUNCTION ff_actor();

CREATE FUNCTION ff_staff_email_evidence() RETURNS trigger LANGUAGE plpgsql AS $fn$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'immutable email change evidence' USING ERRCODE = '23514';
  END IF;
  IF OLD.state = 'completed' OR
     (OLD.id, OLD.user_id, OLD.identity_id, OLD.old_email, OLD.new_email,
      OLD.actor_id, OLD.actor_name, OLD.request_key, OLD.created_at, OLD.trainer_version)
     IS DISTINCT FROM
     (NEW.id, NEW.user_id, NEW.identity_id, NEW.old_email, NEW.new_email,
      NEW.actor_id, NEW.actor_name, NEW.request_key, NEW.created_at, NEW.trainer_version) THEN
    RAISE EXCEPTION 'immutable email change evidence' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$fn$;
CREATE TRIGGER ff_email_evidence BEFORE UPDATE OR DELETE ON staff_email_changes
  FOR EACH ROW EXECUTE FUNCTION ff_staff_email_evidence();
"""

DOWNGRADE_SQL = r"""
DO $guard$
BEGIN
  IF EXISTS (SELECT 1 FROM staff_email_changes) THEN
    RAISE EXCEPTION 'Verified email downgrade refused: change evidence exists';
  END IF;
END;
$guard$;
DROP TRIGGER ff_email_reservation ON staff_users;
DROP TRIGGER ff_email_reservation ON trainers;
DROP TABLE staff_email_changes;
DROP FUNCTION ff_staff_email_reservation();
DROP FUNCTION ff_staff_email_evidence();
"""


def upgrade():
    op.execute(UPGRADE_SQL)


def downgrade():
    op.execute(DOWNGRADE_SQL)
