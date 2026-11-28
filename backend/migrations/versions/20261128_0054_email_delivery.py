"""Add durable transactional email attempts without changing business records."""

from alembic import op

revision = "20261128_0054"
down_revision = "20261127_0053"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
CREATE TABLE email_deliveries (
 id UUID PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 event_key VARCHAR(200) NOT NULL, kind VARCHAR(40) NOT NULL,
 recipient VARCHAR(320) NOT NULL, subject VARCHAR(200) NOT NULL, body TEXT NOT NULL,
 state VARCHAR(16) NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
 available_at TIMESTAMPTZ NOT NULL DEFAULT now(), lease_id UUID, lease_until TIMESTAMPTZ,
 provider_id VARCHAR(200), error_code VARCHAR(80),
 CONSTRAINT uq_email_deliveries_event_key_recipient UNIQUE(event_key, recipient),
 CONSTRAINT ck_email_deliveries_state_values
 CHECK(state IN ('pending','sending','accepted','failed','unknown')),
 CONSTRAINT ck_email_deliveries_bounded_attempts CHECK(attempts >= 0 AND attempts <= 5)
);
CREATE INDEX ix_email_deliveries_state_available_at ON email_deliveries(state, available_at);
CREATE TABLE email_report_receipts (
 id UUID PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 actor_id UUID NOT NULL REFERENCES staff_users(id), request_key UUID NOT NULL,
 request_sha256 VARCHAR(64) NOT NULL, result JSONB NOT NULL,
 CONSTRAINT uq_email_report_receipts_actor_id_request_key UNIQUE(actor_id,request_key),
 CONSTRAINT uq_email_report_receipts_actor_id_request_sha256 UNIQUE(actor_id,request_sha256)
);
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON email_report_receipts
 FOR EACH ROW EXECUTE FUNCTION ff_immutable();
CREATE FUNCTION ff_email_content_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
 BEGIN
 IF ROW(NEW.id, NEW.created_at, NEW.event_key, NEW.kind, NEW.recipient, NEW.subject, NEW.body)
 IS DISTINCT FROM ROW(OLD.id, OLD.created_at, OLD.event_key, OLD.kind,
                      OLD.recipient, OLD.subject, OLD.body)
 THEN RAISE EXCEPTION 'email content is immutable'; END IF;
 RETURN NEW;
 END $$;
CREATE TRIGGER ff_email_content_immutable BEFORE UPDATE ON email_deliveries
 FOR EACH ROW EXECUTE FUNCTION ff_email_content_immutable();
""")


def downgrade():
    op.execute("""DO $$ BEGIN
 IF EXISTS (SELECT 1 FROM email_deliveries) OR EXISTS (SELECT 1 FROM email_report_receipts) THEN
 RAISE EXCEPTION 'populated email delivery downgrade refused'; END IF;
 END $$""")
    op.drop_table("email_report_receipts")
    op.drop_table("email_deliveries")
    op.execute("DROP FUNCTION ff_email_content_immutable()")
