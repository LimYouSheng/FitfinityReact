"""Staff identity/session lifecycle; refuse destructive rollback with saved auth state."""

from alembic import op

revision = "20260915_0003"
down_revision = "20260915_0002"
branch_labels = None
depends_on = None

UPGRADE_SQL = r"""
ALTER TABLE staff_identities ADD COLUMN provider_username VARCHAR(128);

ALTER TABLE staff_identities ADD COLUMN status VARCHAR(16) DEFAULT 'active' NOT NULL;

ALTER TABLE staff_identities ADD CONSTRAINT ck_staff_identities_provider_username_required CHECK
    (provider_username IS NULL OR length(btrim(provider_username)) > 0);

ALTER TABLE staff_identities ADD CONSTRAINT uq_staff_identities_id_user_id UNIQUE (id, user_id);

ALTER TABLE staff_identities ADD CONSTRAINT ck_staff_identities_status_values CHECK (status IN
    ('active', 'inactive'));

ALTER TABLE staff_identities ADD CONSTRAINT uq_staff_identities_user_id_issuer UNIQUE (user_id,
    issuer);

CREATE TABLE auth_accounts (
    user_id UUID NOT NULL,
    epoch BIGINT DEFAULT '0' NOT NULL,
    pending_id UUID,
    pending_until TIMESTAMP WITH TIME ZONE,
    CONSTRAINT pk_auth_accounts PRIMARY KEY (user_id),
    CONSTRAINT ck_auth_accounts_nonnegative_epoch CHECK (epoch >= 0),
    CONSTRAINT ck_auth_accounts_pending_pair CHECK ((pending_id IS NULL) = (pending_until IS NULL)),
    CONSTRAINT fk_auth_accounts_user_id_staff_users FOREIGN KEY(user_id) REFERENCES staff_users (id)
);

CREATE TABLE auth_flows (
    handle_hash VARCHAR(64) NOT NULL,
    user_id UUID NOT NULL,
    epoch BIGINT NOT NULL,
    kind VARCHAR(16) NOT NULL,
    step VARCHAR(32) NOT NULL,
    username VARCHAR(128) NOT NULL,
    provider_state BYTEA,
    attempts INTEGER DEFAULT '0' NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_auth_flows PRIMARY KEY (id),
    CONSTRAINT ck_auth_flows_kind_values CHECK (kind IN ('sign_in', 'recovery')),
    CONSTRAINT ck_auth_flows_step_values CHECK (step IN ('starting', 'NEW_PASSWORD_REQUIRED',
    'SOFTWARE_TOKEN_MFA', 'MFA_SETUP', 'recovery', 'processing', 'ended')),
    CONSTRAINT ck_auth_flows_attempt_limit CHECK (attempts BETWEEN 0 AND 6),
    CONSTRAINT ck_auth_flows_nonnegative_epoch CHECK (epoch >= 0),
    CONSTRAINT ck_auth_flows_flow_window CHECK (created_at < expires_at),
    CONSTRAINT ck_auth_flows_handle_digest CHECK (handle_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT uq_auth_flows_handle_hash UNIQUE (handle_hash),
    CONSTRAINT fk_auth_flows_user_id_staff_users FOREIGN KEY(user_id) REFERENCES staff_users (id)
);

CREATE INDEX ix_auth_flows_expires_at ON auth_flows (expires_at);

CREATE INDEX ix_auth_flows_user_id ON auth_flows (user_id);

CREATE TABLE auth_sessions (
    handle_hash VARCHAR(64) NOT NULL,
    user_id UUID NOT NULL,
    identity_id UUID NOT NULL,
    epoch BIGINT NOT NULL,
    authenticated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    access_expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    access_cipher BYTEA,
    refresh_cipher BYTEA,
    closed_at TIMESTAMP WITH TIME ZONE,
    refresh_lease_id UUID,
    refresh_lease_until TIMESTAMP WITH TIME ZONE,
    revoke_pending BOOLEAN DEFAULT false NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_auth_sessions PRIMARY KEY (id),
    CONSTRAINT ck_auth_sessions_handle_digest CHECK (handle_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_auth_sessions_session_window CHECK (authenticated_at <= expires_at),
    CONSTRAINT ck_auth_sessions_nonnegative_epoch CHECK (epoch >= 0),
    CONSTRAINT ck_auth_sessions_open_credentials CHECK (closed_at IS NOT NULL OR (access_cipher IS
    NOT NULL AND refresh_cipher IS NOT NULL)),
    CONSTRAINT ck_auth_sessions_lease_pair CHECK ((refresh_lease_id IS NULL) =
    (refresh_lease_until IS NULL)),
    CONSTRAINT fk_auth_sessions_identity_id_user_id_staff_identities FOREIGN KEY(identity_id,
    user_id) REFERENCES staff_identities (id, user_id),
    CONSTRAINT uq_auth_sessions_handle_hash UNIQUE (handle_hash),
    CONSTRAINT fk_auth_sessions_user_id_staff_users FOREIGN KEY(user_id) REFERENCES staff_users
    (id),
    CONSTRAINT fk_auth_sessions_identity_id_staff_identities FOREIGN KEY(identity_id) REFERENCES
    staff_identities (id)
);

CREATE INDEX ix_auth_sessions_expires_at ON auth_sessions (expires_at);

CREATE INDEX ix_auth_sessions_identity_id ON auth_sessions (identity_id);

CREATE INDEX ix_auth_sessions_revoke_pending ON auth_sessions (revoke_pending);

CREATE INDEX ix_auth_sessions_user_id ON auth_sessions (user_id);

DROP TRIGGER ff_immutable ON staff_identities;
CREATE FUNCTION ff_staff_identity_guard() RETURNS trigger LANGUAGE plpgsql AS $fn$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'immutable evidence: staff_identities' USING ERRCODE = '23514';
  END IF;
  IF (OLD.id, OLD.user_id, OLD.issuer, OLD.subject, OLD.created_at) IS DISTINCT FROM
     (NEW.id, NEW.user_id, NEW.issuer, NEW.subject, NEW.created_at)
     OR (OLD.provider_username IS NOT NULL AND
         OLD.provider_username IS DISTINCT FROM NEW.provider_username) THEN
    RAISE EXCEPTION 'immutable identity ownership: staff_identities' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$fn$;
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON staff_identities
  FOR EACH ROW EXECUTE FUNCTION ff_staff_identity_guard();
CREATE FUNCTION ff_auth_epoch_changed() RETURNS trigger LANGUAGE plpgsql AS $fn$
DECLARE old_user uuid; new_user uuid; affected uuid;
BEGIN
  IF TG_TABLE_NAME = 'staff_users' THEN
    IF (OLD.role, OLD.status, OLD.email) IS NOT DISTINCT FROM
       (NEW.role, NEW.status, NEW.email) THEN RETURN NEW; END IF;
    old_user := OLD.id; new_user := NEW.id;
  ELSIF TG_TABLE_NAME = 'trainers' THEN
    IF (OLD.status, OLD.user_id) IS NOT DISTINCT FROM (NEW.status, NEW.user_id)
       THEN RETURN NEW; END IF;
    old_user := OLD.user_id; new_user := NEW.user_id;
  ELSE
    old_user := OLD.user_id;
    IF TG_OP = 'UPDATE' THEN
      IF (OLD.user_id, OLD.issuer, OLD.subject, OLD.provider_username, OLD.status) IS NOT DISTINCT
    FROM
         (NEW.user_id, NEW.issuer, NEW.subject, NEW.provider_username, NEW.status) THEN RETURN
    NEW; END IF;
      new_user := NEW.user_id;
    END IF;
  END IF;
  FOR affected IN SELECT DISTINCT value FROM (VALUES (old_user), (new_user)) AS users(value)
                  WHERE value IS NOT NULL ORDER BY value LOOP
    INSERT INTO auth_accounts(user_id, epoch) VALUES (affected, 1)
      ON CONFLICT(user_id) DO UPDATE SET epoch = auth_accounts.epoch + 1;
    UPDATE auth_sessions SET closed_at = clock_timestamp(), access_cipher = NULL,
      revoke_pending = true, refresh_lease_id = NULL, refresh_lease_until = NULL
      WHERE user_id = affected;
  END LOOP;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END;
$fn$;
CREATE TRIGGER ff_auth_staff_changed AFTER UPDATE ON staff_users
  FOR EACH ROW EXECUTE FUNCTION ff_auth_epoch_changed();
CREATE TRIGGER ff_auth_trainer_changed AFTER UPDATE ON trainers
  FOR EACH ROW EXECUTE FUNCTION ff_auth_epoch_changed();
CREATE TRIGGER ff_auth_identity_changed AFTER UPDATE OR DELETE ON staff_identities
  FOR EACH ROW EXECUTE FUNCTION ff_auth_epoch_changed();
"""

DOWNGRADE_SQL = r"""
DO $guard$
BEGIN
  IF EXISTS (SELECT 1 FROM auth_accounts) OR EXISTS (SELECT 1 FROM auth_flows)
     OR EXISTS (SELECT 1 FROM auth_sessions)
     OR EXISTS (SELECT 1 FROM staff_identities WHERE provider_username IS NOT NULL OR status <>
    'active') THEN
    RAISE EXCEPTION 'authentication downgrade refused: durable authentication state exists';
  END IF;
END;
$guard$;
DROP TRIGGER ff_auth_identity_changed ON staff_identities;
DROP TRIGGER ff_auth_trainer_changed ON trainers;
DROP TRIGGER ff_auth_staff_changed ON staff_users;
DROP FUNCTION ff_auth_epoch_changed();
DROP TRIGGER ff_immutable ON staff_identities;
DROP FUNCTION ff_staff_identity_guard();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON staff_identities
  FOR EACH ROW EXECUTE FUNCTION ff_immutable();
DROP TABLE auth_sessions;
DROP TABLE auth_flows;
DROP TABLE auth_accounts;
ALTER TABLE staff_identities DROP CONSTRAINT uq_staff_identities_id_user_id;
ALTER TABLE staff_identities DROP CONSTRAINT uq_staff_identities_user_id_issuer;
ALTER TABLE staff_identities DROP CONSTRAINT ck_staff_identities_provider_username_required;
ALTER TABLE staff_identities DROP CONSTRAINT ck_staff_identities_status_values;
ALTER TABLE staff_identities DROP COLUMN status;
ALTER TABLE staff_identities DROP COLUMN provider_username;
"""


def upgrade():
    op.execute(UPGRADE_SQL)


def downgrade():
    op.execute(DOWNGRADE_SQL)
