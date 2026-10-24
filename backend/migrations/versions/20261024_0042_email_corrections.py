"""Supersede reviewed stable email requests without releasing uncertain destinations."""

from alembic import op

revision = "20261024_0042"
down_revision = "20261024_0041"
branch_labels = None
depends_on = None

UPGRADE_SQL = r"""
ALTER TABLE staff_email_changes
  ADD COLUMN supersedes_id UUID REFERENCES staff_email_changes(id),
  ADD COLUMN superseded_at TIMESTAMPTZ,
  ADD COLUMN reservation_released_at TIMESTAMPTZ,
  ADD CONSTRAINT uq_staff_email_changes_supersedes_id UNIQUE(supersedes_id);
-- Existing terminal evidence remains terminal; only new superseded rows can hold
-- an old destination until the replacement has actually been verified.
ALTER TABLE staff_email_changes DISABLE TRIGGER ff_email_evidence;
UPDATE staff_email_changes SET reservation_released_at = completed_at WHERE state = 'completed';
ALTER TABLE staff_email_changes ENABLE TRIGGER ff_email_evidence;
ALTER TABLE staff_email_changes DROP CONSTRAINT ck_staff_email_changes_state_values;
ALTER TABLE staff_email_changes ADD CONSTRAINT ck_staff_email_changes_state_values
  CHECK(state IN ('requested', 'sending', 'pending', 'verifying', 'completed', 'superseded'));
ALTER TABLE staff_email_changes ADD CONSTRAINT ck_staff_email_changes_supersession_pair
  CHECK((state = 'superseded') = (superseded_at IS NOT NULL));
ALTER TABLE staff_email_changes ADD CONSTRAINT ck_staff_email_changes_reservation_release
  CHECK(reservation_released_at IS NULL OR state IN ('completed', 'superseded'));
DROP INDEX uq_staff_email_changes_pending_user;
DROP INDEX uq_staff_email_changes_pending_email;
CREATE UNIQUE INDEX uq_staff_email_changes_pending_user ON staff_email_changes(user_id)
  WHERE state NOT IN ('completed', 'superseded');
CREATE UNIQUE INDEX uq_staff_email_changes_pending_email ON staff_email_changes(new_email)
  WHERE state NOT IN ('completed', 'superseded');

CREATE OR REPLACE FUNCTION ff_staff_email_reservation() RETURNS trigger LANGUAGE plpgsql AS $fn$
DECLARE address text; owner_id uuid;
BEGIN
  PERFORM pg_advisory_xact_lock(714602036);
  IF TG_TABLE_NAME = 'staff_email_changes' THEN
    address := NEW.new_email; owner_id := NEW.user_id;
    IF NOT EXISTS (SELECT 1 FROM staff_identities
                   WHERE id = NEW.identity_id AND user_id = owner_id) THEN
      RAISE EXCEPTION 'email identity mismatch' USING ERRCODE = '23514';
    END IF;
    IF NEW.state <> 'requested' OR NEW.reservation_released_at IS NOT NULL
       OR NEW.superseded_at IS NOT NULL THEN
      RAISE EXCEPTION 'email change must begin requested' USING ERRCODE = '23514';
    END IF;
    IF NEW.supersedes_id IS NOT NULL AND NOT EXISTS (
      SELECT 1 FROM staff_email_changes prior WHERE prior.id = NEW.supersedes_id
        AND prior.user_id = owner_id AND prior.identity_id = NEW.identity_id
        AND prior.old_email = NEW.old_email AND prior.state = 'superseded'
        AND prior.reservation_released_at IS NULL
        AND (prior.sends, prior.attempts, prior.last_sent_at) IS NOT DISTINCT FROM
            (NEW.sends, NEW.attempts, NEW.last_sent_at)
    ) THEN
      RAISE EXCEPTION 'email correction predecessor mismatch' USING ERRCODE = '23514';
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
             AND reservation_released_at IS NULL AND user_id IS DISTINCT FROM owner_id) THEN
    RAISE EXCEPTION 'staff email reserved' USING ERRCODE = '23505';
  END IF;
  RETURN NEW;
END;
$fn$;

CREATE OR REPLACE FUNCTION ff_staff_email_evidence() RETURNS trigger LANGUAGE plpgsql AS $fn$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'immutable email change evidence' USING ERRCODE = '23514';
  END IF;
  IF OLD.state = 'completed' OR
     (OLD.id, OLD.user_id, OLD.identity_id, OLD.old_email, OLD.new_email,
      OLD.actor_id, OLD.actor_name, OLD.request_key, OLD.created_at,
      OLD.trainer_version, OLD.supersedes_id)
     IS DISTINCT FROM
     (NEW.id, NEW.user_id, NEW.identity_id, NEW.old_email, NEW.new_email,
      NEW.actor_id, NEW.actor_name, NEW.request_key, NEW.created_at,
      NEW.trainer_version, NEW.supersedes_id) THEN
    RAISE EXCEPTION 'immutable email change evidence' USING ERRCODE = '23514';
  END IF;
  IF NEW.state = 'completed' AND OLD.state <> 'completed' THEN
    NEW.reservation_released_at := NEW.completed_at;
  END IF;
  IF OLD.state = 'superseded' THEN
    IF to_jsonb(OLD) - 'reservation_released_at' IS DISTINCT FROM
       to_jsonb(NEW) - 'reservation_released_at'
       OR OLD.reservation_released_at IS NOT NULL
       OR NEW.reservation_released_at IS NULL
       OR NOT EXISTS (
         WITH RECURSIVE successors AS (
           SELECT id, state, user_id, identity_id FROM staff_email_changes
             WHERE supersedes_id = OLD.id
           UNION ALL
           SELECT c.id, c.state, c.user_id, c.identity_id FROM staff_email_changes c
             JOIN successors s ON c.supersedes_id = s.id
         ) SELECT 1 FROM successors WHERE state = 'completed'
             AND user_id = OLD.user_id AND identity_id = OLD.identity_id
       ) THEN
      RAISE EXCEPTION 'immutable superseded email evidence' USING ERRCODE = '23514';
    END IF;
  ELSIF NEW.state = 'superseded' THEN
    IF OLD.state NOT IN ('requested', 'pending') OR OLD.lease_id IS NOT NULL
       OR NEW.lease_id IS NOT NULL OR NEW.superseded_at IS NULL
       OR NEW.reservation_released_at IS NOT NULL
       OR to_jsonb(OLD) - 'state' - 'superseded_at' IS DISTINCT FROM
          to_jsonb(NEW) - 'state' - 'superseded_at' THEN
      RAISE EXCEPTION 'email provider action must reconcile before correction'
        USING ERRCODE = '23514';
    END IF;
  ELSIF NEW.reservation_released_at IS DISTINCT FROM OLD.reservation_released_at
        AND (NEW.state <> 'completed' OR NEW.reservation_released_at IS NULL) THEN
    RAISE EXCEPTION 'email reservation needs verified completion' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$fn$;

-- Completion owns reservation release even while the previous application is
-- serving requests during a compatible rollback. AFTER sees terminal evidence.
CREATE FUNCTION ff_release_email_predecessors() RETURNS trigger LANGUAGE plpgsql AS $fn$
BEGIN
  WITH RECURSIVE ancestors AS (
    SELECT id, supersedes_id FROM staff_email_changes WHERE id = NEW.supersedes_id
    UNION ALL
    SELECT prior.id, prior.supersedes_id FROM staff_email_changes prior
      JOIN ancestors child ON prior.id = child.supersedes_id
  ) UPDATE staff_email_changes SET reservation_released_at = NEW.completed_at
    WHERE id IN (SELECT id FROM ancestors) AND state = 'superseded'
      AND user_id = NEW.user_id AND identity_id = NEW.identity_id
      AND reservation_released_at IS NULL;
  RETURN NEW;
END;
$fn$;
CREATE TRIGGER ff_email_release AFTER UPDATE OF state ON staff_email_changes
  FOR EACH ROW WHEN (NEW.state = 'completed' AND OLD.state <> 'completed')
  EXECUTE FUNCTION ff_release_email_predecessors();
"""


def upgrade():
    op.execute(UPGRADE_SQL)


DOWNGRADE_SQL = r"""
DO $guard$
BEGIN
  IF EXISTS (SELECT 1 FROM staff_email_changes) THEN
    RAISE EXCEPTION 'Email correction downgrade refused: change evidence exists';
  END IF;
END;
$guard$;
DROP TRIGGER ff_email_release ON staff_email_changes;
DROP FUNCTION ff_release_email_predecessors();
DROP INDEX uq_staff_email_changes_pending_user;
DROP INDEX uq_staff_email_changes_pending_email;
CREATE UNIQUE INDEX uq_staff_email_changes_pending_user ON staff_email_changes(user_id)
  WHERE state <> 'completed';
CREATE UNIQUE INDEX uq_staff_email_changes_pending_email ON staff_email_changes(new_email)
  WHERE state <> 'completed';
ALTER TABLE staff_email_changes
  DROP CONSTRAINT ck_staff_email_changes_reservation_release,
  DROP CONSTRAINT ck_staff_email_changes_supersession_pair,
  DROP CONSTRAINT ck_staff_email_changes_state_values,
  DROP COLUMN supersedes_id,
  DROP COLUMN superseded_at,
  DROP COLUMN reservation_released_at;
ALTER TABLE staff_email_changes ADD CONSTRAINT ck_staff_email_changes_state_values
  CHECK(state IN ('requested', 'sending', 'pending', 'verifying', 'completed'));
CREATE OR REPLACE FUNCTION ff_staff_email_reservation() RETURNS trigger LANGUAGE plpgsql AS $fn$
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
CREATE OR REPLACE FUNCTION ff_staff_email_evidence() RETURNS trigger LANGUAGE plpgsql AS $fn$
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
"""


def downgrade():
    op.execute(DOWNGRADE_SQL)
