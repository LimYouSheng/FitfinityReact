"""Expand stable Trainer attribution without guessing original legacy ownership."""

import sqlalchemy as sa
from alembic import op

revision = "20261025_0046"
down_revision = "20261024_0045"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("session_events", sa.Column("request_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_session_events_request_id_change_requests",
        "session_events",
        "change_requests",
        ["request_id"],
        ["id"],
    )
    op.add_column(
        "training_sessions",
        sa.Column(
            "assigned_trainer_id",
            sa.Uuid(),
            sa.Computed("trainer_id", persisted=True),
            nullable=False,
        ),
    )
    op.create_table(
        "session_trainer_attributions",
        sa.Column(
            "session_id", sa.Uuid(), sa.ForeignKey("session_identities.id"), primary_key=True
        ),
        sa.Column("original_trainer_id", sa.Uuid(), sa.ForeignKey("trainers.id")),
        sa.Column("performed_by_trainer_id", sa.Uuid(), sa.ForeignKey("trainers.id")),
        sa.Column("original_state", sa.String(24), nullable=False),
        sa.CheckConstraint(
            "(original_state = 'captured' AND original_trainer_id IS NOT NULL) OR "
            "(original_state = 'legacy_unresolved' AND original_trainer_id IS NULL)",
            name="original_evidence",
        ),
    )
    op.create_table(
        "session_trainer_assignment_history",
        sa.Column("event_id", sa.Uuid(), sa.ForeignKey("session_events.id"), primary_key=True),
        sa.Column("session_id", sa.Uuid(), sa.ForeignKey("session_identities.id"), nullable=False),
        sa.Column("old_trainer_id", sa.Uuid(), sa.ForeignKey("trainers.id"), nullable=False),
        sa.Column("new_trainer_id", sa.Uuid(), sa.ForeignKey("trainers.id"), nullable=False),
    )
    op.create_index(
        "ix_session_trainer_assignment_history_session_id",
        "session_trainer_assignment_history",
        ["session_id"],
    )
    op.execute(UPGRADE_SQL)


UPGRADE_SQL = r"""
-- Completion has always frozen trainer_id in the database. It identifies the
-- credited Trainer, not the Owner/Admin who may have recorded acknowledgement.
INSERT INTO session_trainer_attributions
    (session_id, original_trainer_id, performed_by_trainer_id, original_state)
SELECT i.id, NULL, CASE WHEN s.status='completed' THEN s.trainer_id END, 'legacy_unresolved'
FROM session_identities i LEFT JOIN training_sessions s ON s.id=i.id;

INSERT INTO session_trainer_assignment_history
    (event_id, session_id, old_trainer_id, new_trainer_id)
SELECT id, session_id, old_trainer_id, new_trainer_id FROM session_events
WHERE old_trainer_id IS NOT NULL AND new_trainer_id IS NOT NULL
    AND old_trainer_id <> new_trainer_id;

CREATE FUNCTION ff_capture_session_attribution() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='INSERT' THEN
  INSERT INTO session_trainer_attributions
      (session_id, original_trainer_id, performed_by_trainer_id, original_state)
  VALUES(NEW.id, NEW.trainer_id,
      CASE WHEN NEW.status='completed' THEN NEW.trainer_id END, 'captured')
  ON CONFLICT(session_id) DO NOTHING;
 ELSIF NEW.status='completed' AND OLD.status<>'completed' THEN
  UPDATE session_trainer_attributions SET performed_by_trainer_id=NEW.trainer_id
  WHERE session_id=NEW.id AND performed_by_trainer_id IS NULL;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER ff_capture_session_attribution AFTER INSERT OR UPDATE ON training_sessions
FOR EACH ROW EXECUTE FUNCTION ff_capture_session_attribution();

CREATE FUNCTION ff_guard_session_attribution() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='INSERT' THEN
  IF NEW.original_state<>'captured' OR NOT EXISTS(
      SELECT 1 FROM training_sessions s WHERE s.id=NEW.session_id
      AND s.trainer_id=NEW.original_trainer_id
      AND NEW.performed_by_trainer_id IS NOT DISTINCT FROM
          CASE WHEN s.status='completed' THEN s.trainer_id END) THEN
   RAISE EXCEPTION 'invalid Trainer attribution' USING ERRCODE='23514';
  END IF;
  RETURN NEW;
 END IF;
 IF TG_OP='DELETE' THEN
  RAISE EXCEPTION 'immutable Trainer attribution' USING ERRCODE='23514';
 END IF;
 IF (NEW.session_id, NEW.original_trainer_id, NEW.original_state) IS DISTINCT FROM
    (OLD.session_id, OLD.original_trainer_id, OLD.original_state)
    OR OLD.performed_by_trainer_id IS NOT NULL
    OR NEW.performed_by_trainer_id IS NULL
    OR NOT EXISTS(SELECT 1 FROM training_sessions s WHERE s.id=NEW.session_id
        AND s.status='completed' AND s.trainer_id=NEW.performed_by_trainer_id) THEN
  RAISE EXCEPTION 'immutable Trainer attribution' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER ff_guard_session_attribution BEFORE INSERT OR UPDATE OR DELETE
ON session_trainer_attributions FOR EACH ROW EXECUTE FUNCTION ff_guard_session_attribution();

CREATE FUNCTION ff_capture_assignment_history() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.old_trainer_id IS NOT NULL AND NEW.new_trainer_id IS NOT NULL
    AND NEW.old_trainer_id<>NEW.new_trainer_id THEN
  INSERT INTO session_trainer_assignment_history
      (event_id,session_id,old_trainer_id,new_trainer_id)
  VALUES(NEW.id,NEW.session_id,NEW.old_trainer_id,NEW.new_trainer_id);
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER ff_capture_assignment_history AFTER INSERT ON session_events
FOR EACH ROW EXECUTE FUNCTION ff_capture_assignment_history();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON session_trainer_assignment_history
FOR EACH ROW EXECUTE FUNCTION ff_immutable();
CREATE FUNCTION ff_assignment_history_source() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM session_events e WHERE e.id=NEW.event_id
    AND e.session_id=NEW.session_id AND e.old_trainer_id=NEW.old_trainer_id
    AND e.new_trainer_id=NEW.new_trainer_id AND e.old_trainer_id<>e.new_trainer_id) THEN
  RAISE EXCEPTION 'invalid assignment history source' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER ff_assignment_history_source BEFORE INSERT ON session_trainer_assignment_history
FOR EACH ROW EXECUTE FUNCTION ff_assignment_history_source();
"""


def downgrade():
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM session_trainer_attributions)
        OR EXISTS(SELECT 1 FROM session_trainer_assignment_history) THEN
        RAISE EXCEPTION 'populated attribution downgrade refused';
      END IF;
    END $$;""")
    op.execute("DROP TRIGGER ff_capture_assignment_history ON session_events")
    op.execute("DROP FUNCTION ff_capture_assignment_history()")
    op.execute("DROP TRIGGER ff_capture_session_attribution ON training_sessions")
    op.execute("DROP FUNCTION ff_capture_session_attribution()")
    op.drop_table("session_trainer_assignment_history")
    op.execute("DROP FUNCTION ff_assignment_history_source()")
    op.drop_table("session_trainer_attributions")
    op.execute("DROP FUNCTION ff_guard_session_attribution()")
    op.drop_column("training_sessions", "assigned_trainer_id")
    op.drop_column("session_events", "request_id")
