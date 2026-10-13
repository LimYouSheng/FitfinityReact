"""Retain single-session postponement proposals without applying their open state."""

from alembic import op

revision = "20261013_0024"
down_revision = "20261013_0023"
branch_labels = None
depends_on = None

UPGRADE_SQL = r"""
ALTER TABLE change_requests DROP CONSTRAINT ck_change_requests_kind_values;
ALTER TABLE change_requests ADD CONSTRAINT ck_change_requests_kind_values CHECK (kind IN
    ('session_time', 'session_trainer', 'session_postpone',
    'fixed_weekly_schedule', 'trainer_availability'));
ALTER TABLE change_requests DROP CONSTRAINT ck_change_requests_typed_target;
ALTER TABLE change_requests ADD CONSTRAINT ck_change_requests_typed_target CHECK ((kind IN
    ('session_time', 'session_trainer', 'session_postpone')
    AND session_id IS NOT NULL AND purchase_id IS NOT NULL AND client_id IS NOT NULL) OR (kind =
    'fixed_weekly_schedule' AND session_id IS NULL AND purchase_id IS NOT NULL AND client_id IS
    NOT NULL) OR (kind = 'trainer_availability' AND session_id IS NULL AND purchase_id IS NULL AND
    client_id IS NULL));
ALTER TABLE change_requests DROP CONSTRAINT ck_change_requests_typed_times;
ALTER TABLE change_requests ADD CONSTRAINT ck_change_requests_typed_times CHECK ((kind =
    'session_time' AND new_date IS NOT NULL AND new_start IS NOT NULL
    AND new_end IS NOT NULL AND new_start < new_end AND
    (num_nonnulls(old_date, old_start, old_end) = 0 OR (old_date IS NOT NULL
    AND old_start IS NOT NULL AND old_end IS NOT NULL AND old_start < old_end))) OR (kind =
    'session_postpone' AND old_date IS NOT NULL AND old_start IS NOT NULL
    AND old_end IS NOT NULL AND old_start < old_end AND num_nonnulls(new_date, new_start,
    new_end) = 0)
    OR (kind NOT IN ('session_time', 'session_postpone') AND num_nonnulls(old_date, new_date,
    old_start, old_end, new_start, new_end) =
    0));
"""

DOWNGRADE_SQL = r"""
DO $guard$
BEGIN
  IF EXISTS (SELECT 1 FROM change_requests WHERE kind = 'session_postpone'
    OR (kind = 'session_time' AND old_date IS NULL)) THEN
    RAISE EXCEPTION 'Postponement-request downgrade refused: proposals exist';
  END IF;
END;
$guard$;
ALTER TABLE change_requests DROP CONSTRAINT ck_change_requests_kind_values;
ALTER TABLE change_requests ADD CONSTRAINT ck_change_requests_kind_values CHECK (kind IN
    ('session_time', 'session_trainer',
    'fixed_weekly_schedule', 'trainer_availability'));
ALTER TABLE change_requests DROP CONSTRAINT ck_change_requests_typed_target;
ALTER TABLE change_requests ADD CONSTRAINT ck_change_requests_typed_target CHECK ((kind IN
    ('session_time', 'session_trainer')
    AND session_id IS NOT NULL AND purchase_id IS NOT NULL AND client_id IS NOT NULL) OR (kind =
    'fixed_weekly_schedule' AND session_id IS NULL AND purchase_id IS NOT NULL AND client_id IS
    NOT NULL) OR (kind = 'trainer_availability' AND session_id IS NULL AND purchase_id IS NULL AND
    client_id IS NULL));
ALTER TABLE change_requests DROP CONSTRAINT ck_change_requests_typed_times;
ALTER TABLE change_requests ADD CONSTRAINT ck_change_requests_typed_times CHECK ((kind =
    'session_time' AND old_date IS NOT NULL
    AND new_date IS NOT NULL AND old_start IS NOT NULL AND old_end IS NOT NULL AND new_start IS
    NOT NULL AND new_end IS NOT NULL AND old_start < old_end AND new_start < new_end) OR (kind <>
    'session_time' AND num_nonnulls(old_date, new_date, old_start, old_end, new_start, new_end) =
    0));
"""


def upgrade():
    op.execute(UPGRADE_SQL)


def downgrade():
    op.execute(DOWNGRADE_SQL)
