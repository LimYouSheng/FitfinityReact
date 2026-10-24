"""Typed recording intents and one-time publication expiry; existing evidence stays immutable."""

from alembic import op

revision = "20261024_0044"
down_revision = "20261024_0043"
branch_labels = None
depends_on = None

UPGRADE_SQL = r"""

CREATE TABLE session_media_intents (
	request_key UUID NOT NULL,
	request_sha256 VARCHAR(64) NOT NULL,
	expected_sha256 VARCHAR(64) NOT NULL,
	session_id UUID NOT NULL,
	plan_item_id UUID NOT NULL,
	remove_media BOOLEAN NOT NULL,
	upload_id UUID,
	previous_media_id UUID,
	duration_seconds INTEGER,
	source VARCHAR(16) NOT NULL,
	caption TEXT NOT NULL,
	processing_status VARCHAR(16) NOT NULL,
	audio_included BOOLEAN,
	upload_until TIMESTAMP WITH TIME ZONE NOT NULL,
	state VARCHAR(16) DEFAULT 'pending' NOT NULL,
	completed_at TIMESTAMP WITH TIME ZONE,
	result JSONB,
	actor_id UUID NOT NULL,
	actor_name VARCHAR(200) NOT NULL,
	version INTEGER DEFAULT 1 NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	CONSTRAINT pk_session_media_intents PRIMARY KEY (id),
	CONSTRAINT uq_session_media_intents_actor_id_request_key UNIQUE (actor_id, request_key),
    CONSTRAINT fk_session_media_intents_plan_item_id_session_id_exerci_5e20 FOREIGN
    KEY(plan_item_id, session_id) REFERENCES exercise_plan_items (id, session_id),
    CONSTRAINT ck_session_media_intents_state_values CHECK (state IN ('pending', 'completed',
    'expired')),
	CONSTRAINT ck_session_media_intents_source_values CHECK (source IN ('recorded', 'attached')),
    CONSTRAINT ck_session_media_intents_processing_status_values CHECK (processing_status IN
    ('complete', 'deferred')),
    CONSTRAINT ck_session_media_intents_request_digest CHECK (request_sha256 ~ '^[0-9a-f]{64}$'
    AND expected_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_session_media_intents_receipt_state CHECK ((state = 'completed') = (result IS
    NOT NULL) AND (state = 'completed') = (completed_at IS NOT NULL)),
	CONSTRAINT ck_session_media_intents_upload_action CHECK (remove_media = (upload_id IS NULL)),
    CONSTRAINT ck_session_media_intents_duration_bound CHECK (duration_seconds IS NULL OR
    duration_seconds BETWEEN 1 AND 60),
	CONSTRAINT ck_session_media_intents_caption_bound CHECK (length(caption) <= 10000),
    CONSTRAINT fk_session_media_intents_session_id_session_identities FOREIGN KEY(session_id)
    REFERENCES session_identities (id),
	CONSTRAINT uq_session_media_intents_upload_id UNIQUE (upload_id),
    CONSTRAINT fk_session_media_intents_upload_id_media_assets FOREIGN KEY(upload_id) REFERENCES
    media_assets (id),
    CONSTRAINT fk_session_media_intents_previous_media_id_media_assets FOREIGN
    KEY(previous_media_id) REFERENCES media_assets (id),
    CONSTRAINT fk_session_media_intents_actor_id_staff_users FOREIGN KEY(actor_id) REFERENCES
    staff_users (id),
	CONSTRAINT ck_session_media_intents_positive_version CHECK (version > 0),
	CONSTRAINT ck_session_media_intents_actor_name_required CHECK (length(btrim(actor_name)) > 0)
)

;
CREATE INDEX ix_session_media_intents_actor_id ON session_media_intents (actor_id);
CREATE INDEX ix_session_media_intents_session_id ON session_media_intents (session_id);

CREATE TRIGGER ff_version BEFORE INSERT OR UPDATE ON session_media_intents
FOR EACH ROW EXECUTE FUNCTION ff_version();
CREATE TRIGGER ff_no_delete BEFORE DELETE ON session_media_intents
FOR EACH ROW EXECUTE FUNCTION ff_immutable();
CREATE TRIGGER ff_preserve_fields BEFORE UPDATE ON session_media_intents
FOR EACH ROW EXECUTE FUNCTION ff_preserve_fields('request_key','request_sha256',
'expected_sha256','session_id','plan_item_id','remove_media','upload_id','previous_media_id',
'duration_seconds','source','caption','processing_status','audio_included','upload_until',
'actor_id','actor_name');
CREATE FUNCTION ff_recording_intent() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='INSERT' AND (NEW.state <> 'pending' OR NEW.completed_at IS NOT NULL
   OR NEW.result IS NOT NULL) THEN
   RAISE EXCEPTION 'recording intent must start pending' USING ERRCODE='23514';
 END IF;
 IF TG_OP='UPDATE' AND OLD.state <> 'pending' THEN
   RAISE EXCEPTION 'immutable terminal recording intent' USING ERRCODE='23514';
 END IF;
 IF NEW.upload_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM media_assets m
   WHERE m.id=NEW.upload_id AND m.purpose='session_video'
   AND m.original_session_id=NEW.session_id AND m.original_plan_item_id=NEW.plan_item_id
   AND m.uploaded_by=NEW.actor_id) THEN
   RAISE EXCEPTION 'recording intent ownership mismatch' USING ERRCODE='23514';
 END IF;
 IF NEW.state='completed' AND NEW.upload_id IS NOT NULL AND NOT EXISTS (
   SELECT 1 FROM media_assets WHERE id=NEW.upload_id AND status='ready'
   AND session_id=NEW.session_id AND expires_at=NEW.completed_at+interval '7 days') THEN
   RAISE EXCEPTION 'recording publication requires fixed original expiry' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER ff_recording_intent BEFORE INSERT OR UPDATE ON session_media_intents
FOR EACH ROW EXECUTE FUNCTION ff_recording_intent();

-- Expiry becomes final exactly once, at publication. Existing ready/retired media
-- keeps its original deadline even when restored, replaced or configuration changes.
DROP TRIGGER ff_preserve_fields ON media_assets;
CREATE TRIGGER ff_preserve_fields BEFORE UPDATE ON media_assets FOR EACH ROW EXECUTE FUNCTION
ff_preserve_fields('purpose','bucket','object_key','original_filename','content_type',
'size_bytes','content_sha256','uploaded_by','client_id','purchase_id',
'original_session_id','original_plan_item_id');
CREATE FUNCTION ff_recording_expiry() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.expires_at IS DISTINCT FROM OLD.expires_at AND NOT (
   OLD.purpose='session_video' AND OLD.status='pending' AND NEW.status='ready'
   AND NEW.expires_at=transaction_timestamp()+interval '7 days'
   AND EXISTS(SELECT 1 FROM session_media_intents i WHERE i.upload_id=OLD.id
              AND i.state='pending' AND i.upload_until>transaction_timestamp())
 ) THEN RAISE EXCEPTION 'immutable field: media_assets.expires_at' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER ff_recording_expiry BEFORE UPDATE ON media_assets
FOR EACH ROW EXECUTE FUNCTION ff_recording_expiry();
"""

DOWNGRADE_SQL = r"""

DO $$ BEGIN IF EXISTS(SELECT 1 FROM session_media_intents) THEN
 RAISE EXCEPTION 'Recording downgrade refused: original intents exist' USING ERRCODE='23514';
END IF; END $$;
DROP TRIGGER ff_recording_expiry ON media_assets;
DROP FUNCTION ff_recording_expiry();
DROP TRIGGER ff_preserve_fields ON media_assets;
CREATE TRIGGER ff_preserve_fields BEFORE UPDATE ON media_assets FOR EACH ROW EXECUTE FUNCTION
ff_preserve_fields('purpose','bucket','object_key','original_filename','content_type',
'size_bytes','content_sha256','uploaded_by','client_id','purchase_id',
'original_session_id','original_plan_item_id','expires_at');
DROP TABLE session_media_intents;
DROP FUNCTION ff_recording_intent();
"""


def upgrade():
    op.execute(UPGRADE_SQL)


def downgrade():
    op.execute(DOWNGRADE_SQL)
