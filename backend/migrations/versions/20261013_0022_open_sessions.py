"""Represent open sessions without fabricated calendar intervals or sequence numbers."""

from alembic import op

revision = "20261013_0022"
down_revision = "20261013_0021"
branch_labels = None
depends_on = None

UPGRADE_SQL = r"""
ALTER TABLE training_sessions ADD COLUMN schedule_state VARCHAR(16) NOT NULL DEFAULT 'booked';
ALTER TABLE training_sessions ALTER COLUMN session_number DROP NOT NULL;
ALTER TABLE training_sessions ALTER COLUMN training_date DROP NOT NULL;
ALTER TABLE training_sessions ALTER COLUMN starts_at DROP NOT NULL;
ALTER TABLE training_sessions ALTER COLUMN ends_at DROP NOT NULL;
ALTER TABLE training_sessions DROP CONSTRAINT ck_training_sessions_valid_session;
ALTER TABLE training_sessions ADD CONSTRAINT ck_training_sessions_schedule_state_values
    CHECK(schedule_state IN ('booked', 'open'));
ALTER TABLE training_sessions ADD CONSTRAINT ck_training_sessions_valid_session CHECK (
    (schedule_state='open' AND session_number IS NULL AND training_date IS NULL
     AND starts_at IS NULL AND ends_at IS NULL AND schedule_slot_id IS NULL AND status<>'completed')
    OR (schedule_state='booked' AND session_number IS NOT NULL AND session_number BETWEEN 1 AND 365
        AND training_date IS NOT NULL AND starts_at IS NOT NULL AND ends_at IS NOT NULL
        AND starts_at < ends_at)
);
DROP TRIGGER ff_preserve_fields ON training_sessions;
CREATE TRIGGER ff_preserve_fields BEFORE UPDATE ON training_sessions FOR EACH ROW
 EXECUTE FUNCTION ff_preserve_fields('client_id', 'purchase_id');
CREATE OR REPLACE FUNCTION ff_session_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE purchase package_purchases%ROWTYPE;
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status IN ('completed', 'cancelled') OR
       OLD.training_date + OLD.starts_at <= (clock_timestamp() AT TIME ZONE 'Asia/Singapore') OR
       EXISTS (SELECT 1 FROM acknowledgements WHERE session_id=OLD.id) OR
       EXISTS (SELECT 1 FROM credit_debits WHERE session_id=OLD.id) OR
       EXISTS (SELECT 1 FROM session_events WHERE session_id=OLD.id) THEN
      RAISE EXCEPTION 'session contains retained history or is no longer future' USING
    ERRCODE='23514'; END IF;
    RETURN OLD;
  END IF;
  IF TG_OP='UPDATE' AND NEW.session_number IS DISTINCT FROM OLD.session_number
     AND NEW.schedule_state=OLD.schedule_state THEN
    RAISE EXCEPTION 'immutable field: training_sessions.session_number' USING ERRCODE='23514';
  END IF;
  SELECT * INTO STRICT purchase FROM package_purchases WHERE id=NEW.purchase_id FOR UPDATE;
  IF (TG_OP='INSERT' OR (TG_OP='UPDATE' AND NEW.purchase_id IS DISTINCT FROM OLD.purchase_id))
    AND (SELECT count(*) FROM training_sessions WHERE purchase_id=NEW.purchase_id)
        >= purchase.total_sessions THEN
    RAISE EXCEPTION 'session count exceeds purchased capacity' USING ERRCODE='23514'; END IF;
  IF NEW.session_number > purchase.total_sessions THEN
    RAISE EXCEPTION 'session number exceeds purchased capacity' USING ERRCODE='23514'; END IF;
  IF TG_OP = 'INSERT' AND (NEW.training_date < purchase.start_date OR NEW.training_date >
    purchase.end_date) THEN
    RAISE EXCEPTION 'generated session is outside purchase validity' USING ERRCODE='23514'; END IF;
  IF TG_OP = 'UPDATE' AND OLD.status = 'completed' AND
     (NEW.status, NEW.training_date, NEW.starts_at, NEW.ends_at, NEW.trainer_id) IS DISTINCT FROM
     (OLD.status, OLD.training_date, OLD.starts_at, OLD.ends_at, OLD.trainer_id) THEN
    RAISE EXCEPTION 'completed session scheduling is retained evidence' USING ERRCODE='23514'; END
    IF;
  RETURN NEW;
END $$;
CREATE OR REPLACE FUNCTION ff_acknowledgement() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE booking training_sessions%ROWTYPE; previous acknowledgements%ROWTYPE;
BEGIN
  SELECT * INTO STRICT booking FROM training_sessions WHERE id=NEW.session_id FOR UPDATE;
  IF booking.schedule_state='open' OR
    booking.training_date > (clock_timestamp() AT TIME ZONE 'Asia/Singapore')::date OR
    booking.status='cancelled' THEN
    RAISE EXCEPTION 'session is not eligible for acknowledgement' USING ERRCODE='23514'; END IF;
  SELECT * INTO previous FROM acknowledgements WHERE session_id=NEW.session_id ORDER BY sequence
    DESC LIMIT 1;
  IF FOUND THEN
    IF previous.method <> 'late_no_show' OR NEW.method <> 'signature' OR NEW.sequence <> 2 THEN
      RAISE EXCEPTION 'only no-show to signature correction is allowed' USING ERRCODE='23514'; END
    IF;
  ELSIF NEW.sequence <> 1 THEN
    RAISE EXCEPTION 'first acknowledgement must start history' USING ERRCODE='23514';
  END IF;
  IF NEW.method='signature' AND encode(sha256(NEW.signature),'hex') IS DISTINCT FROM
    NEW.signature_sha256 THEN
    RAISE EXCEPTION 'signature digest mismatch' USING ERRCODE='23514'; END IF;
  RETURN NEW;
END $$;
"""

DOWNGRADE_SQL = r"""
DO $guard$
BEGIN
 IF EXISTS (SELECT 1 FROM training_sessions WHERE schedule_state='open') THEN
  RAISE EXCEPTION 'Open-session downgrade refused: unscheduled records exist';
 END IF;
END;
$guard$;
DROP TRIGGER ff_preserve_fields ON training_sessions;
CREATE TRIGGER ff_preserve_fields BEFORE UPDATE ON training_sessions FOR EACH ROW
 EXECUTE FUNCTION ff_preserve_fields('client_id', 'purchase_id', 'session_number');
CREATE OR REPLACE FUNCTION ff_session_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE purchase package_purchases%ROWTYPE;
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status IN ('completed', 'cancelled') OR
       OLD.training_date + OLD.starts_at <= (clock_timestamp() AT TIME ZONE 'Asia/Singapore') OR
       EXISTS (SELECT 1 FROM acknowledgements WHERE session_id=OLD.id) OR
       EXISTS (SELECT 1 FROM credit_debits WHERE session_id=OLD.id) OR
       EXISTS (SELECT 1 FROM session_events WHERE session_id=OLD.id) THEN
      RAISE EXCEPTION 'session contains retained history or is no longer future' USING
    ERRCODE='23514'; END IF;
    RETURN OLD;
  END IF;
  SELECT * INTO STRICT purchase FROM package_purchases WHERE id=NEW.purchase_id;
  IF NEW.session_number > purchase.total_sessions THEN
    RAISE EXCEPTION 'session number exceeds purchased capacity' USING ERRCODE='23514'; END IF;
  IF TG_OP = 'INSERT' AND (NEW.training_date < purchase.start_date OR NEW.training_date >
    purchase.end_date) THEN
    RAISE EXCEPTION 'generated session is outside purchase validity' USING ERRCODE='23514'; END IF;
  IF TG_OP = 'UPDATE' AND OLD.status = 'completed' AND
     (NEW.status, NEW.training_date, NEW.starts_at, NEW.ends_at, NEW.trainer_id) IS DISTINCT FROM
     (OLD.status, OLD.training_date, OLD.starts_at, OLD.ends_at, OLD.trainer_id) THEN
    RAISE EXCEPTION 'completed session scheduling is retained evidence' USING ERRCODE='23514'; END
    IF;
  RETURN NEW;
END $$;
CREATE OR REPLACE FUNCTION ff_acknowledgement() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE booking training_sessions%ROWTYPE; previous acknowledgements%ROWTYPE;
BEGIN
  SELECT * INTO STRICT booking FROM training_sessions WHERE id=NEW.session_id FOR UPDATE;
  IF booking.training_date > (clock_timestamp() AT TIME ZONE 'Asia/Singapore')::date OR
    booking.status='cancelled' THEN
    RAISE EXCEPTION 'session is not eligible for acknowledgement' USING ERRCODE='23514'; END IF;
  SELECT * INTO previous FROM acknowledgements WHERE session_id=NEW.session_id ORDER BY sequence
    DESC LIMIT 1;
  IF FOUND THEN
    IF previous.method <> 'late_no_show' OR NEW.method <> 'signature' OR NEW.sequence <> 2 THEN
      RAISE EXCEPTION 'only no-show to signature correction is allowed' USING ERRCODE='23514'; END
    IF;
  ELSIF NEW.sequence <> 1 THEN
    RAISE EXCEPTION 'first acknowledgement must start history' USING ERRCODE='23514';
  END IF;
  IF NEW.method='signature' AND encode(sha256(NEW.signature),'hex') IS DISTINCT FROM
    NEW.signature_sha256 THEN
    RAISE EXCEPTION 'signature digest mismatch' USING ERRCODE='23514'; END IF;
  RETURN NEW;
END $$;
ALTER TABLE training_sessions DROP CONSTRAINT ck_training_sessions_valid_session;
ALTER TABLE training_sessions DROP CONSTRAINT ck_training_sessions_schedule_state_values;
ALTER TABLE training_sessions ALTER COLUMN session_number SET NOT NULL;
ALTER TABLE training_sessions ALTER COLUMN training_date SET NOT NULL;
ALTER TABLE training_sessions ALTER COLUMN starts_at SET NOT NULL;
ALTER TABLE training_sessions ALTER COLUMN ends_at SET NOT NULL;
ALTER TABLE training_sessions DROP COLUMN schedule_state;
ALTER TABLE training_sessions ADD CONSTRAINT ck_training_sessions_valid_session
 CHECK(session_number BETWEEN 1 AND 365 AND starts_at < ends_at);

"""


def upgrade():
    op.execute(UPGRADE_SQL)


def downgrade():
    op.execute(DOWNGRADE_SQL)
