"""Allow atomic chronological positions while preserving booking and capacity guards."""

from alembic import op

revision = "20261023_0031"
down_revision = "20261013_0030"
branch_labels = None
depends_on = None

UPGRADE_SQL = r"""
ALTER TABLE training_sessions DROP CONSTRAINT uq_training_sessions_purchase_id_session_number;
ALTER TABLE training_sessions ADD CONSTRAINT uq_training_sessions_purchase_id_session_number
 UNIQUE(purchase_id, session_number) DEFERRABLE INITIALLY DEFERRED;
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
     AND NEW.schedule_state=OLD.schedule_state AND NEW.session_number IS DISTINCT FROM (
       SELECT position FROM (
         SELECT id, row_number() OVER (ORDER BY training_date, starts_at, id) AS position
         FROM training_sessions WHERE purchase_id=NEW.purchase_id AND schedule_state='booked'
       ) numbered WHERE id=NEW.id
     ) THEN
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
"""

DOWNGRADE_SQL = r"""
ALTER TABLE training_sessions DROP CONSTRAINT uq_training_sessions_purchase_id_session_number;
ALTER TABLE training_sessions ADD CONSTRAINT uq_training_sessions_purchase_id_session_number
 UNIQUE(purchase_id, session_number);
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
"""


def upgrade():
    op.execute(UPGRADE_SQL)


def downgrade():
    op.execute(DOWNGRADE_SQL)
