"""Durable Admin proposals and atomic, immutable Owner decisions."""

from alembic import op

revision = "20261031_0051"
down_revision = "20261031_0050"
branch_labels = None
depends_on = None

UPGRADE_SQL = r"""
CREATE TABLE admin_operation_requests (
 id UUID PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 version INTEGER NOT NULL DEFAULT 1, updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 actor_id UUID NOT NULL REFERENCES staff_users(id), actor_name VARCHAR(200) NOT NULL,
 request_key UUID NOT NULL, request_sha256 VARCHAR(64) NOT NULL,
 operation VARCHAR(100) NOT NULL, area VARCHAR(32) NOT NULL, body JSONB NOT NULL,
 status VARCHAR(16) NOT NULL, resolved_by UUID REFERENCES staff_users(id),
 resolved_at TIMESTAMPTZ,
 CONSTRAINT uq_admin_operation_requests_actor_id_request_key UNIQUE(actor_id,request_key),
 CONSTRAINT ck_admin_operation_requests_request_digest CHECK(request_sha256 ~ '^[0-9a-f]{64}$'),
 CONSTRAINT ck_admin_operation_requests_actor_name_required CHECK(length(btrim(actor_name)) > 0),
 CONSTRAINT ck_admin_operation_requests_status_values
   CHECK(status IN ('pending','approved','rejected','cancelled')),
 CONSTRAINT ck_admin_operation_requests_decision_evidence CHECK(
   (status='pending' AND resolved_by IS NULL AND resolved_at IS NULL) OR
   (status<>'pending' AND resolved_by IS NOT NULL AND resolved_at IS NOT NULL))
);
CREATE INDEX ix_admin_operation_requests_actor_id ON admin_operation_requests(actor_id);
CREATE TABLE admin_operation_decisions (
 id UUID PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 actor_id UUID NOT NULL REFERENCES staff_users(id), actor_name VARCHAR(200) NOT NULL,
 proposal_id UUID NOT NULL REFERENCES admin_operation_requests(id),
 request_key UUID NOT NULL, request_sha256 VARCHAR(64) NOT NULL, result JSONB NOT NULL,
 CONSTRAINT uq_admin_operation_decisions_actor_id_request_key UNIQUE(actor_id,request_key),
 CONSTRAINT uq_admin_operation_decisions_proposal_id UNIQUE(proposal_id),
 CONSTRAINT ck_admin_operation_decisions_request_digest CHECK(request_sha256 ~ '^[0-9a-f]{64}$'),
 CONSTRAINT ck_admin_operation_decisions_actor_name_required CHECK(length(btrim(actor_name)) > 0)
);
CREATE INDEX ix_admin_operation_decisions_actor_id ON admin_operation_decisions(actor_id);
CREATE FUNCTION ff_admin_proposal_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Admin proposal is immutable evidence'; END IF;
 IF TG_OP='INSERT' THEN
   IF NEW.status <> 'pending' OR NOT EXISTS (
       SELECT 1 FROM staff_users WHERE id=NEW.actor_id AND role='admin' AND status='active') THEN
     RAISE EXCEPTION 'active Admin proposal required';
   END IF;
 ELSE
   IF OLD.status <> 'pending' OR NEW.status='pending' OR NEW.version <> OLD.version+1 OR
      (NEW.id,NEW.created_at,NEW.actor_id,NEW.actor_name,NEW.request_key,NEW.request_sha256,
       NEW.operation,NEW.area,NEW.body) IS DISTINCT FROM
      (OLD.id,OLD.created_at,OLD.actor_id,OLD.actor_name,OLD.request_key,OLD.request_sha256,
       OLD.operation,OLD.area,OLD.body) THEN
     RAISE EXCEPTION 'Admin proposal is immutable evidence';
   END IF;
   IF NEW.status='cancelled' THEN
     IF NEW.resolved_by <> NEW.actor_id THEN RAISE EXCEPTION 'originating Admin required'; END IF;
   ELSIF NOT EXISTS (SELECT 1 FROM staff_users
       WHERE id=NEW.resolved_by AND role='owner' AND status='active') THEN
     RAISE EXCEPTION 'active Owner decision required';
   END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER ff_admin_proposal_guard BEFORE INSERT OR UPDATE OR DELETE
 ON admin_operation_requests FOR EACH ROW EXECUTE FUNCTION ff_admin_proposal_guard();
CREATE TRIGGER ff_actor BEFORE INSERT ON admin_operation_requests
 FOR EACH ROW EXECUTE FUNCTION ff_actor();
CREATE TRIGGER ff_actor BEFORE INSERT ON admin_operation_decisions
 FOR EACH ROW EXECUTE FUNCTION ff_actor();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON admin_operation_decisions
 FOR EACH ROW EXECUTE FUNCTION ff_immutable();
"""


def upgrade():
    op.execute(UPGRADE_SQL)


def downgrade():
    op.execute("""
DO $guard$
BEGIN
 IF EXISTS(SELECT 1 FROM admin_operation_requests) THEN
   RAISE EXCEPTION 'Admin approval downgrade refused: proposal evidence exists';
 END IF;
END;
$guard$;
DROP TABLE admin_operation_decisions;
DROP TABLE admin_operation_requests;
DROP FUNCTION ff_admin_proposal_guard();
""")
