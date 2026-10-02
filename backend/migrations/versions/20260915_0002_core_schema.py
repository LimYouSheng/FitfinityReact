"""Core storage schema. Frozen DDL: never import future ORM metadata into this revision.

Empty-schema rollback only. Populated environments require a reviewed restore/forward repair.
The shared btree_gist extension is intentionally retained on downgrade.
"""

from alembic import op

revision = "20260915_0002"
down_revision = "20260915_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute(UPGRADE_SQL)


def downgrade():
    op.execute(DOWNGRADE_SQL)


UPGRADE_SQL = r"""
CREATE TABLE content_entries (
    key VARCHAR(120) NOT NULL,
    title VARCHAR(180) NOT NULL,
    body TEXT NOT NULL,
    status VARCHAR(16) DEFAULT 'draft' NOT NULL,
    version INTEGER DEFAULT 1 NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_content_entries PRIMARY KEY (id),
    CONSTRAINT ck_content_entries_status_values CHECK (status IN ('draft', 'ready', 'archived')),
    CONSTRAINT ck_content_entries_content_bounds CHECK (key ~ '^[a-z0-9]+([-/][a-z0-9]+)*$' AND
    length(btrim(title)) > 0 AND length(btrim(body)) BETWEEN 1 AND 20000),
    CONSTRAINT uq_content_entries_key UNIQUE (key),
    CONSTRAINT ck_content_entries_positive_version CHECK (version > 0)
);

CREATE TABLE staff_users (
    name VARCHAR(200) NOT NULL,
    email VARCHAR(320) NOT NULL,
    role VARCHAR(16) NOT NULL,
    status VARCHAR(16) DEFAULT 'active' NOT NULL,
    version INTEGER DEFAULT 1 NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_staff_users PRIMARY KEY (id),
    CONSTRAINT ck_staff_users_role_values CHECK (role IN ('owner', 'trainer')),
    CONSTRAINT ck_staff_users_status_values CHECK (status IN ('active', 'inactive')),
    CONSTRAINT ck_staff_users_name_required CHECK (length(btrim(name)) > 0),
    CONSTRAINT ck_staff_users_email_normalized CHECK (email = lower(btrim(email)) AND position('@'
    in
    email) > 1),
    CONSTRAINT uq_staff_users_id_role UNIQUE (id, role),
    CONSTRAINT uq_staff_users_email UNIQUE (email),
    CONSTRAINT ck_staff_users_positive_version CHECK (version > 0)
);

CREATE TABLE package_templates (
    status VARCHAR(16) DEFAULT 'active' NOT NULL,
    version INTEGER DEFAULT 1 NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_package_templates PRIMARY KEY (id),
    CONSTRAINT ck_package_templates_status_values CHECK (status IN ('active', 'inactive')),
    CONSTRAINT ck_package_templates_positive_version CHECK (version > 0)
);

CREATE TABLE exercises (
    name VARCHAR(200) NOT NULL,
    category VARCHAR(120) NOT NULL,
    description TEXT DEFAULT '' NOT NULL,
    status VARCHAR(16) DEFAULT 'active' NOT NULL,
    media_id UUID,
    version INTEGER DEFAULT 1 NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_exercises PRIMARY KEY (id),
    CONSTRAINT ck_exercises_status_values CHECK (status IN ('active', 'inactive')),
    CONSTRAINT ck_exercises_details_required CHECK (length(btrim(name)) > 0 AND
    length(btrim(category)) > 0),
    CONSTRAINT ck_exercises_positive_version CHECK (version > 0)
);

CREATE INDEX ix_exercises_category ON exercises (category);

CREATE UNIQUE INDEX uq_exercise_name ON exercises (lower(btrim(name)));

CREATE TABLE staff_identities (
    user_id UUID NOT NULL,
    issuer VARCHAR(512) NOT NULL,
    subject VARCHAR(256) NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_staff_identities PRIMARY KEY (id),
    CONSTRAINT uq_staff_identities_issuer_subject UNIQUE (issuer, subject),
    CONSTRAINT ck_staff_identities_identity_required CHECK (length(btrim(issuer)) > 0 AND
    length(btrim(subject)) > 0),
    CONSTRAINT fk_staff_identities_user_id_staff_users FOREIGN KEY(user_id) REFERENCES staff_users
    (id)
);

CREATE INDEX ix_staff_identities_user_id ON staff_identities (user_id);

CREATE TABLE trainers (
    user_id UUID,
    user_role VARCHAR(16) DEFAULT 'trainer' NOT NULL,
    name VARCHAR(200) NOT NULL,
    email VARCHAR(320) NOT NULL,
    phone_country_code VARCHAR(4) NOT NULL,
    phone_number VARCHAR(32) NOT NULL,
    birthday DATE NOT NULL,
    gender VARCHAR(24) NOT NULL,
    trainer_type VARCHAR(120) NOT NULL,
    qualifications TEXT DEFAULT '' NOT NULL,
    public_profile BOOLEAN DEFAULT true NOT NULL,
    status VARCHAR(16) DEFAULT 'active' NOT NULL,
    peak_rate_cents BIGINT NOT NULL,
    off_peak_rate_cents BIGINT NOT NULL,
    approve_availability BOOLEAN DEFAULT true NOT NULL,
    approve_session_time BOOLEAN DEFAULT true NOT NULL,
    approve_session_trainer BOOLEAN DEFAULT true NOT NULL,
    approve_weekly_schedule BOOLEAN DEFAULT true NOT NULL,
    version INTEGER DEFAULT 1 NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_trainers PRIMARY KEY (id),
    CONSTRAINT fk_trainers_user_id_user_role_staff_users FOREIGN KEY(user_id, user_role) REFERENCES
    staff_users (id, role),
    CONSTRAINT ck_trainers_trainer_role CHECK (user_role = 'trainer'),
    CONSTRAINT ck_trainers_status_values CHECK (status IN ('active', 'inactive')),
    CONSTRAINT ck_trainers_gender_values CHECK (gender IN ('Female', 'Male', 'Other',
    'Prefer not to say')),
    CONSTRAINT ck_trainers_nonnegative_rates CHECK (peak_rate_cents >= 0 AND off_peak_rate_cents >=
    0),
    CONSTRAINT ck_trainers_profile_required CHECK (length(btrim(name)) > 0 AND
    length(btrim(trainer_type)) > 0),
    CONSTRAINT ck_trainers_email_normalized CHECK (email = lower(btrim(email)) AND position('@' in
    email) > 1),
    CONSTRAINT uq_trainers_user_id UNIQUE (user_id),
    CONSTRAINT uq_trainers_email UNIQUE (email),
    CONSTRAINT ck_trainers_positive_version CHECK (version > 0),
    CONSTRAINT ck_trainers_phone_format CHECK (phone_country_code ~ '^\+[1-9][0-9]{0,2}$' AND
    phone_number ~ '^[0-9 ()-]+$' AND length(regexp_replace(phone_number, '[^0-9]', '', 'g')) >= 6
    AND length(regexp_replace(phone_country_code || phone_number, '[^0-9]', '', 'g')) <= 15)
);

CREATE INDEX ix_trainers_name ON trainers (name);

CREATE INDEX ix_trainers_name_folded ON trainers (lower(name));

CREATE TABLE package_template_revisions (
    template_id UUID NOT NULL,
    revision INTEGER NOT NULL,
    name VARCHAR(200) NOT NULL,
    total_sessions INTEGER NOT NULL,
    validity_days INTEGER NOT NULL,
    actor_id UUID NOT NULL,
    actor_name VARCHAR(200) NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_package_template_revisions PRIMARY KEY (id),
    CONSTRAINT uq_package_template_revisions_template_id_revision UNIQUE (template_id, revision),
    CONSTRAINT ck_package_template_revisions_valid_terms CHECK (revision > 0 AND total_sessions
    BETWEEN 1 AND 365 AND validity_days > 0),
    CONSTRAINT ck_package_template_revisions_name_required CHECK (length(btrim(name)) > 0),
    CONSTRAINT fk_package_template_revisions_template_id_package_templates FOREIGN KEY(template_id)
    REFERENCES package_templates (id),
    CONSTRAINT fk_package_template_revisions_actor_id_staff_users FOREIGN KEY(actor_id) REFERENCES
    staff_users (id),
    CONSTRAINT ck_package_template_revisions_actor_name_required CHECK (length(btrim(actor_name))
    > 0)
);

CREATE INDEX ix_package_template_revisions_actor_id ON package_template_revisions (actor_id);

CREATE INDEX ix_package_template_revisions_template_id ON package_template_revisions (template_id);

CREATE TABLE remuneration_approvals (
    trainer_id UUID NOT NULL,
    trainer_name VARCHAR(200) NOT NULL,
    cycle_key VARCHAR(7) NOT NULL,
    cycle_start DATE NOT NULL,
    cycle_end DATE NOT NULL,
    payout_date DATE NOT NULL,
    currency VARCHAR(3) DEFAULT 'SGD' NOT NULL,
    amount_cents BIGINT NOT NULL,
    total_minutes INTEGER NOT NULL,
    session_count INTEGER NOT NULL,
    source_sha256 VARCHAR(64) NOT NULL,
    created_xid TEXT DEFAULT pg_current_xact_id()::text NOT NULL,
    actor_id UUID NOT NULL,
    actor_name VARCHAR(200) NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_remuneration_approvals PRIMARY KEY (id),
    CONSTRAINT uq_remuneration_approvals_trainer_id_cycle_key UNIQUE (trainer_id, cycle_key),
    CONSTRAINT uq_remuneration_approvals_id_trainer_id UNIQUE (id, trainer_id),
    CONSTRAINT ck_remuneration_approvals_cycle_dates CHECK (cycle_key ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'
    AND cycle_start < cycle_end AND payout_date > cycle_end),
    CONSTRAINT ck_remuneration_approvals_pay_bounds CHECK (amount_cents >= 0 AND total_minutes >= 0
    AND session_count > 0),
    CONSTRAINT ck_remuneration_approvals_evidence_format CHECK (currency = 'SGD' AND source_sha256 ~
    '^[0-9a-f]{64}$'),
    CONSTRAINT fk_remuneration_approvals_trainer_id_trainers FOREIGN KEY(trainer_id) REFERENCES
    trainers (id),
    CONSTRAINT fk_remuneration_approvals_actor_id_staff_users FOREIGN KEY(actor_id) REFERENCES
    staff_users (id),
    CONSTRAINT ck_remuneration_approvals_actor_name_required CHECK (length(btrim(actor_name)) > 0)
);

CREATE INDEX ix_remuneration_approvals_actor_id ON remuneration_approvals (actor_id);

CREATE INDEX ix_remuneration_approvals_trainer_id ON remuneration_approvals (trainer_id);

CREATE TABLE trainer_availability (
    trainer_id UUID NOT NULL,
    weekday INTEGER NOT NULL,
    starts_at TIME WITHOUT TIME ZONE NOT NULL,
    ends_at TIME WITHOUT TIME ZONE NOT NULL,
    version INTEGER DEFAULT 1 NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_trainer_availability PRIMARY KEY (id),
    CONSTRAINT ck_trainer_availability_valid_slot CHECK (weekday BETWEEN 0 AND 6 AND starts_at <
    ends_at),
    CONSTRAINT uq_trainer_availability_trainer_id_weekday_starts_at_ends_at UNIQUE (trainer_id,
    weekday, starts_at, ends_at),
    CONSTRAINT fk_trainer_availability_trainer_id_trainers FOREIGN KEY(trainer_id) REFERENCES
    trainers (id),
    CONSTRAINT ck_trainer_availability_positive_version CHECK (version > 0)
);

CREATE INDEX ix_trainer_availability_trainer_id ON trainer_availability (trainer_id);

CREATE TABLE clients (
    kind VARCHAR(16) NOT NULL,
    name VARCHAR(400) NOT NULL,
    status VARCHAR(16) DEFAULT 'active' NOT NULL,
    trainer_id UUID NOT NULL,
    gender_preference VARCHAR(16) DEFAULT 'any' NOT NULL,
    remarks TEXT DEFAULT '' NOT NULL,
    lifecycle_event_id UUID,
    version INTEGER DEFAULT 1 NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_clients PRIMARY KEY (id),
    CONSTRAINT ck_clients_kind_values CHECK (kind IN ('individual', 'couple')),
    CONSTRAINT ck_clients_status_values CHECK (status IN ('active', 'inactive')),
    CONSTRAINT ck_clients_gender_preference_values CHECK (gender_preference IN ('any', 'female',
    'male')),
    CONSTRAINT ck_clients_name_required CHECK (length(btrim(name)) > 0),
    CONSTRAINT fk_clients_trainer_id_trainers FOREIGN KEY(trainer_id) REFERENCES trainers (id),
    CONSTRAINT ck_clients_positive_version CHECK (version > 0)
);

CREATE INDEX ix_clients_name ON clients (name);

CREATE INDEX ix_clients_name_folded ON clients (lower(name));

CREATE INDEX ix_clients_trainer_id ON clients (trainer_id);

CREATE TABLE client_people (
    client_id UUID NOT NULL,
    position INTEGER NOT NULL,
    name VARCHAR(200) NOT NULL,
    email VARCHAR(320) NOT NULL,
    phone_country_code VARCHAR(4) NOT NULL,
    phone_number VARCHAR(32) NOT NULL,
    birthday DATE NOT NULL,
    gender VARCHAR(24) NOT NULL,
    health_notes TEXT DEFAULT '' NOT NULL,
    emergency_name VARCHAR(200) NOT NULL,
    emergency_relationship VARCHAR(24) NOT NULL,
    emergency_country_code VARCHAR(4) NOT NULL,
    emergency_number VARCHAR(32) NOT NULL,
    version INTEGER DEFAULT 1 NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_client_people PRIMARY KEY (id),
    CONSTRAINT uq_client_people_client_id_position UNIQUE (client_id, position),
    CONSTRAINT ck_client_people_person_position CHECK (position IN (1, 2)),
    CONSTRAINT ck_client_people_gender_values CHECK (gender IN ('Female', 'Male', 'Other',
    'Prefer not to say')),
    CONSTRAINT ck_client_people_names_required CHECK (length(btrim(name)) > 0 AND
    length(btrim(emergency_name)) > 0),
    CONSTRAINT ck_client_people_email_normalized CHECK (email = lower(btrim(email)) AND position('@'
    in email) > 1),
    CONSTRAINT ck_client_people_emergency_relationship_values CHECK (emergency_relationship IN
    ('Spouse', 'Parent', 'Sibling', 'Child', 'Partner', 'Friend', 'Guardian', 'Other')),
    CONSTRAINT fk_client_people_client_id_clients FOREIGN KEY(client_id) REFERENCES clients (id),
    CONSTRAINT ck_client_people_positive_version CHECK (version > 0),
    CONSTRAINT ck_client_people_phone_format CHECK (phone_country_code ~ '^\+[1-9][0-9]{0,2}$' AND
    phone_number ~ '^[0-9 ()-]+$' AND length(regexp_replace(phone_number, '[^0-9]', '', 'g')) >= 6
    AND length(regexp_replace(phone_country_code || phone_number, '[^0-9]', '', 'g')) <= 15),
    CONSTRAINT ck_client_people_emergency_format CHECK (emergency_country_code ~
    '^\+[1-9][0-9]{0,2}$' AND emergency_number ~ '^[0-9 ()-]+$' AND
    length(regexp_replace(emergency_number, '[^0-9]', '', 'g')) >= 6 AND
    length(regexp_replace(emergency_country_code || emergency_number, '[^0-9]', '', 'g')) <= 15)
);

CREATE INDEX ix_client_people_client_id ON client_people (client_id);

CREATE INDEX ix_client_people_email ON client_people (email);

CREATE INDEX ix_client_people_name ON client_people (name);

CREATE TABLE package_purchases (
    client_id UUID NOT NULL,
    template_id UUID NOT NULL,
    template_revision INTEGER NOT NULL,
    name VARCHAR(200) NOT NULL,
    total_sessions INTEGER NOT NULL,
    validity_days INTEGER NOT NULL,
    sessions_per_week INTEGER NOT NULL,
    free_gym BOOLEAN NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    purchased_trainer_id UUID NOT NULL,
    trainer_id UUID NOT NULL,
    gender_preference VARCHAR(16) DEFAULT 'any' NOT NULL,
    status VARCHAR(16) DEFAULT 'active' NOT NULL,
    stage VARCHAR(16) DEFAULT 'queued' NOT NULL,
    activated_at TIMESTAMP WITH TIME ZONE,
    lifecycle_event_id UUID,
    created_xid TEXT DEFAULT pg_current_xact_id()::text NOT NULL,
    version INTEGER DEFAULT 1 NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_package_purchases PRIMARY KEY (id),
    CONSTRAINT uq_package_purchases_id_client_id UNIQUE (id, client_id),
    CONSTRAINT fk_package_purchases_template_id_template_revision_pack_827f FOREIGN KEY(template_id,
    template_revision) REFERENCES package_template_revisions (template_id, revision),
    CONSTRAINT ck_package_purchases_status_values CHECK (status IN ('active', 'inactive')),
    CONSTRAINT ck_package_purchases_stage_values CHECK (stage IN ('queued', 'current',
    'archived')),
    CONSTRAINT ck_package_purchases_gender_preference_values CHECK (gender_preference IN ('any',
    'female', 'male')),
    CONSTRAINT ck_package_purchases_valid_terms CHECK (total_sessions BETWEEN 1 AND 365 AND
    sessions_per_week BETWEEN 1 AND 7 AND validity_days > 0),
    CONSTRAINT ck_package_purchases_inclusive_validity CHECK (end_date = start_date +
    validity_days -
    1),
    CONSTRAINT ck_package_purchases_snapshot_required CHECK (template_revision > 0 AND
    length(btrim(name)) > 0),
    CONSTRAINT ex_purchase_dates EXCLUDE USING gist (client_id WITH =, daterange(start_date,
    end_date, '[]') WITH &&) WHERE (status = 'active'),
    CONSTRAINT fk_package_purchases_client_id_clients FOREIGN KEY(client_id) REFERENCES clients
    (id),
    CONSTRAINT fk_package_purchases_template_id_package_templates FOREIGN KEY(template_id)
    REFERENCES
    package_templates (id),
    CONSTRAINT fk_package_purchases_purchased_trainer_id_trainers FOREIGN KEY(purchased_trainer_id)
    REFERENCES trainers (id),
    CONSTRAINT fk_package_purchases_trainer_id_trainers FOREIGN KEY(trainer_id) REFERENCES trainers
    (id),
    CONSTRAINT ck_package_purchases_positive_version CHECK (version > 0)
);

CREATE INDEX ix_package_purchases_client_id ON package_purchases (client_id);

CREATE INDEX ix_package_purchases_template_id ON package_purchases (template_id);

CREATE INDEX ix_package_purchases_trainer_id ON package_purchases (trainer_id);

CREATE INDEX ix_purchase_activation ON package_purchases (start_date) WHERE stage = 'queued' AND
    status = 'active';

CREATE UNIQUE INDEX uq_current_purchase ON package_purchases (client_id) WHERE stage = 'current';

CREATE TABLE assignment_events (
    client_id UUID NOT NULL,
    old_trainer_id UUID NOT NULL,
    new_trainer_id UUID NOT NULL,
    old_trainer_name VARCHAR(200) NOT NULL,
    new_trainer_name VARCHAR(200) NOT NULL,
    client_version INTEGER NOT NULL,
    actor_id UUID NOT NULL,
    actor_name VARCHAR(200) NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_assignment_events PRIMARY KEY (id),
    CONSTRAINT ck_assignment_events_changed_trainer CHECK (old_trainer_id <> new_trainer_id),
    CONSTRAINT fk_assignment_events_client_id_clients FOREIGN KEY(client_id) REFERENCES clients
    (id),
    CONSTRAINT fk_assignment_events_old_trainer_id_trainers FOREIGN KEY(old_trainer_id) REFERENCES
    trainers (id),
    CONSTRAINT fk_assignment_events_new_trainer_id_trainers FOREIGN KEY(new_trainer_id) REFERENCES
    trainers (id),
    CONSTRAINT fk_assignment_events_actor_id_staff_users FOREIGN KEY(actor_id) REFERENCES
    staff_users
    (id),
    CONSTRAINT ck_assignment_events_actor_name_required CHECK (length(btrim(actor_name)) > 0)
);

CREATE INDEX ix_assignment_events_actor_id ON assignment_events (actor_id);

CREATE INDEX ix_assignment_events_client_id ON assignment_events (client_id);

CREATE INDEX ix_assignment_events_new_trainer_id ON assignment_events (new_trainer_id);

CREATE INDEX ix_assignment_events_old_trainer_id ON assignment_events (old_trainer_id);

CREATE TABLE report_audit (
    client_id UUID NOT NULL,
    purchase_id UUID,
    kind VARCHAR(24) NOT NULL,
    request_sha256 VARCHAR(64) NOT NULL,
    actor_id UUID NOT NULL,
    actor_name VARCHAR(200) NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_report_audit PRIMARY KEY (id),
    CONSTRAINT fk_report_audit_purchase_id_client_id_package_purchases FOREIGN KEY(purchase_id,
    client_id) REFERENCES package_purchases (id, client_id),
    CONSTRAINT ck_report_audit_kind_values CHECK (kind IN ('pdf_export', 'pdf_share_opened',
    'whatsapp_opened', 'csv_export')),
    CONSTRAINT ck_report_audit_request_digest CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT fk_report_audit_client_id_clients FOREIGN KEY(client_id) REFERENCES clients (id),
    CONSTRAINT fk_report_audit_actor_id_staff_users FOREIGN KEY(actor_id) REFERENCES staff_users
    (id),
    CONSTRAINT ck_report_audit_actor_name_required CHECK (length(btrim(actor_name)) > 0)
);

CREATE INDEX ix_report_audit_actor_id ON report_audit (actor_id);

CREATE INDEX ix_report_audit_client_id ON report_audit (client_id);

CREATE INDEX ix_report_audit_purchase_id ON report_audit (purchase_id);

CREATE TABLE lifecycle_events (
    client_id UUID,
    purchase_id UUID,
    trainer_id UUID,
    status VARCHAR(16) NOT NULL,
    reason VARCHAR(24) NOT NULL,
    note TEXT DEFAULT '' NOT NULL,
    cause_id UUID,
    actor_id UUID NOT NULL,
    actor_name VARCHAR(200) NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_lifecycle_events PRIMARY KEY (id),
    CONSTRAINT ck_lifecycle_events_one_target CHECK (num_nonnulls(client_id, purchase_id,
    trainer_id)
    = 1),
    CONSTRAINT ck_lifecycle_events_status_values CHECK (status IN ('active', 'inactive')),
    CONSTRAINT ck_lifecycle_events_reason_values CHECK (reason IN ('owner', 'client',
    'client_reactivated')),
    CONSTRAINT fk_lifecycle_events_client_id_clients FOREIGN KEY(client_id) REFERENCES clients
    (id),
    CONSTRAINT fk_lifecycle_events_purchase_id_package_purchases FOREIGN KEY(purchase_id) REFERENCES
    package_purchases (id),
    CONSTRAINT fk_lifecycle_events_trainer_id_trainers FOREIGN KEY(trainer_id) REFERENCES trainers
    (id),
    CONSTRAINT fk_lifecycle_events_cause_id_lifecycle_events FOREIGN KEY(cause_id) REFERENCES
    lifecycle_events (id),
    CONSTRAINT fk_lifecycle_events_actor_id_staff_users FOREIGN KEY(actor_id) REFERENCES staff_users
    (id),
    CONSTRAINT ck_lifecycle_events_actor_name_required CHECK (length(btrim(actor_name)) > 0)
);

CREATE INDEX ix_lifecycle_events_actor_id ON lifecycle_events (actor_id);

CREATE INDEX ix_lifecycle_events_cause_id ON lifecycle_events (cause_id);

CREATE INDEX ix_lifecycle_events_client_id ON lifecycle_events (client_id);

CREATE INDEX ix_lifecycle_events_purchase_id ON lifecycle_events (purchase_id);

CREATE INDEX ix_lifecycle_events_trainer_id ON lifecycle_events (trainer_id);

CREATE TABLE purchase_schedule_slots (
    purchase_id UUID NOT NULL,
    weekday INTEGER NOT NULL,
    starts_at TIME WITHOUT TIME ZONE NOT NULL,
    ends_at TIME WITHOUT TIME ZONE NOT NULL,
    purchased_weekday INTEGER NOT NULL,
    purchased_starts_at TIME WITHOUT TIME ZONE NOT NULL,
    purchased_ends_at TIME WITHOUT TIME ZONE NOT NULL,
    version INTEGER DEFAULT 1 NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_purchase_schedule_slots PRIMARY KEY (id),
    CONSTRAINT uq_purchase_schedule_slots_id_purchase_id UNIQUE (id, purchase_id),
    CONSTRAINT uq_purchase_schedule_slots_purchase_id_weekday UNIQUE (purchase_id, weekday)
    DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT ck_purchase_schedule_slots_valid_slot CHECK (weekday BETWEEN 0 AND 6 AND starts_at <
    ends_at),
    CONSTRAINT ck_purchase_schedule_slots_valid_snapshot CHECK (purchased_weekday BETWEEN 0 AND 6
    AND
    purchased_starts_at < purchased_ends_at),
    CONSTRAINT fk_purchase_schedule_slots_purchase_id_package_purchases FOREIGN KEY(purchase_id)
    REFERENCES package_purchases (id),
    CONSTRAINT ck_purchase_schedule_slots_positive_version CHECK (version > 0)
);

CREATE INDEX ix_purchase_schedule_slots_purchase_id ON purchase_schedule_slots (purchase_id);

CREATE TABLE purchase_preferences (
    purchase_id UUID NOT NULL,
    weekday INTEGER NOT NULL,
    starts_at TIME WITHOUT TIME ZONE NOT NULL,
    ends_at TIME WITHOUT TIME ZONE NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_purchase_preferences PRIMARY KEY (id),
    CONSTRAINT ck_purchase_preferences_valid_slot CHECK (weekday BETWEEN 0 AND 6 AND starts_at <
    ends_at),
    CONSTRAINT uq_purchase_preferences_purchase_id_weekday_starts_at_ends_at UNIQUE (purchase_id,
    weekday, starts_at, ends_at),
    CONSTRAINT fk_purchase_preferences_purchase_id_package_purchases FOREIGN KEY(purchase_id)
    REFERENCES package_purchases (id)
);

CREATE INDEX ix_purchase_preferences_purchase_id ON purchase_preferences (purchase_id);

CREATE TABLE training_sessions (
    client_id UUID NOT NULL,
    purchase_id UUID NOT NULL,
    trainer_id UUID NOT NULL,
    schedule_slot_id UUID,
    session_number INTEGER NOT NULL,
    training_date DATE NOT NULL,
    starts_at TIME WITHOUT TIME ZONE NOT NULL,
    ends_at TIME WITHOUT TIME ZONE NOT NULL,
    status VARCHAR(16) DEFAULT 'scheduled' NOT NULL,
    trainer_comments TEXT DEFAULT '' NOT NULL,
    client_summary TEXT DEFAULT '' NOT NULL,
    copied_from_session_id UUID,
    whatsapp_opened_at TIMESTAMP WITH TIME ZONE,
    whatsapp_open_count INTEGER DEFAULT 0 NOT NULL,
    version INTEGER DEFAULT 1 NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_training_sessions PRIMARY KEY (id),
    CONSTRAINT fk_training_sessions_purchase_id_client_id_package_purchases FOREIGN KEY(purchase_id,
    client_id) REFERENCES package_purchases (id, client_id),
    CONSTRAINT fk_training_sessions_schedule_slot_id_purchase_id_purch_0057 FOREIGN
    KEY(schedule_slot_id, purchase_id) REFERENCES purchase_schedule_slots (id, purchase_id),
    CONSTRAINT uq_training_sessions_purchase_id_session_number UNIQUE (purchase_id,
    session_number),
    CONSTRAINT uq_training_sessions_id_purchase_id_client_id UNIQUE (id, purchase_id, client_id),
    CONSTRAINT ck_training_sessions_status_values CHECK (status IN ('scheduled', 'planned',
    'completed', 'cancelled')),
    CONSTRAINT ck_training_sessions_valid_session CHECK (session_number BETWEEN 1 AND 365 AND
    starts_at < ends_at),
    CONSTRAINT ck_training_sessions_handoff_count CHECK (whatsapp_open_count >= 0),
    CONSTRAINT fk_training_sessions_client_id_clients FOREIGN KEY(client_id) REFERENCES clients
    (id),
    CONSTRAINT fk_training_sessions_trainer_id_trainers FOREIGN KEY(trainer_id) REFERENCES trainers
    (id),
    CONSTRAINT fk_training_sessions_copied_from_session_id_training_sessions FOREIGN
    KEY(copied_from_session_id) REFERENCES training_sessions (id),
    CONSTRAINT ck_training_sessions_positive_version CHECK (version > 0)
);

CREATE INDEX ix_session_client_calendar ON training_sessions (client_id, training_date, starts_at);

CREATE INDEX ix_session_trainer_calendar ON training_sessions (trainer_id, training_date,
    starts_at);

CREATE INDEX ix_training_sessions_client_id ON training_sessions (client_id);

CREATE INDEX ix_training_sessions_purchase_id ON training_sessions (purchase_id);

CREATE INDEX ix_training_sessions_trainer_id ON training_sessions (trainer_id);

CREATE TABLE change_requests (
    kind VARCHAR(32) NOT NULL,
    status VARCHAR(16) DEFAULT 'pending' NOT NULL,
    trainer_id UUID NOT NULL,
    client_id UUID,
    purchase_id UUID,
    session_id UUID,
    expected_version INTEGER NOT NULL,
    replacement_trainer_id UUID,
    old_date DATE,
    old_start TIME WITHOUT TIME ZONE,
    old_end TIME WITHOUT TIME ZONE,
    new_date DATE,
    new_start TIME WITHOUT TIME ZONE,
    new_end TIME WITHOUT TIME ZONE,
    resolved_at TIMESTAMP WITH TIME ZONE,
    resolved_by UUID,
    resolution_note TEXT DEFAULT '' NOT NULL,
    created_xid TEXT DEFAULT pg_current_xact_id()::text NOT NULL,
    actor_id UUID NOT NULL,
    actor_name VARCHAR(200) NOT NULL,
    version INTEGER DEFAULT 1 NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_change_requests PRIMARY KEY (id),
    CONSTRAINT ck_change_requests_kind_values CHECK (kind IN ('session_time', 'session_trainer',
    'fixed_weekly_schedule', 'trainer_availability')),
    CONSTRAINT ck_change_requests_status_values CHECK (status IN ('pending', 'approved', 'rejected',
    'cancelled', 'superseded')),
    CONSTRAINT fk_change_requests_session_id_purchase_id_client_id_tra_2567 FOREIGN KEY(session_id,
    purchase_id, client_id) REFERENCES training_sessions (id, purchase_id, client_id),
    CONSTRAINT fk_change_requests_purchase_id_client_id_package_purchases FOREIGN KEY(purchase_id,
    client_id) REFERENCES package_purchases (id, client_id),
    CONSTRAINT ck_change_requests_review_version CHECK (expected_version > 0),
    CONSTRAINT ck_change_requests_typed_target CHECK ((kind IN ('session_time', 'session_trainer')
    AND session_id IS NOT NULL AND purchase_id IS NOT NULL AND client_id IS NOT NULL) OR (kind =
    'fixed_weekly_schedule' AND session_id IS NULL AND purchase_id IS NOT NULL AND client_id IS
    NOT NULL) OR (kind = 'trainer_availability' AND session_id IS NULL AND purchase_id IS NULL AND
    client_id IS NULL)),
    CONSTRAINT ck_change_requests_typed_times CHECK ((kind = 'session_time' AND old_date IS NOT NULL
    AND new_date IS NOT NULL AND old_start IS NOT NULL AND old_end IS NOT NULL AND new_start IS
    NOT NULL AND new_end IS NOT NULL AND old_start < old_end AND new_start < new_end) OR (kind <>
    'session_time' AND num_nonnulls(old_date, new_date, old_start, old_end, new_start, new_end) =
    0)),
    CONSTRAINT ck_change_requests_typed_replacement CHECK ((kind = 'session_trainer' AND
    replacement_trainer_id IS NOT NULL AND replacement_trainer_id <> trainer_id) OR (kind <>
    'session_trainer' AND replacement_trainer_id IS NULL)),
    CONSTRAINT ck_change_requests_decision_evidence CHECK ((status = 'pending' AND resolved_at IS
    NULL AND resolved_by IS NULL) OR (status <> 'pending' AND resolved_at IS NOT NULL AND
    resolved_by IS NOT NULL)),
    CONSTRAINT fk_change_requests_trainer_id_trainers FOREIGN KEY(trainer_id) REFERENCES trainers
    (id),
    CONSTRAINT fk_change_requests_client_id_clients FOREIGN KEY(client_id) REFERENCES clients (id),
    CONSTRAINT fk_change_requests_replacement_trainer_id_trainers FOREIGN
    KEY(replacement_trainer_id)
    REFERENCES trainers (id),
    CONSTRAINT fk_change_requests_resolved_by_staff_users FOREIGN KEY(resolved_by) REFERENCES
    staff_users (id),
    CONSTRAINT fk_change_requests_actor_id_staff_users FOREIGN KEY(actor_id) REFERENCES staff_users
    (id),
    CONSTRAINT ck_change_requests_positive_version CHECK (version > 0),
    CONSTRAINT ck_change_requests_actor_name_required CHECK (length(btrim(actor_name)) > 0)
);

CREATE INDEX ix_change_requests_actor_id ON change_requests (actor_id);

CREATE INDEX ix_change_requests_client_id ON change_requests (client_id);

CREATE INDEX ix_change_requests_purchase_id ON change_requests (purchase_id);

CREATE INDEX ix_change_requests_session_id ON change_requests (session_id);

CREATE INDEX ix_change_requests_trainer_id ON change_requests (trainer_id);

CREATE INDEX ix_request_pending ON change_requests (trainer_id, created_at) WHERE status =
    'pending';

CREATE TABLE session_events (
    session_id UUID NOT NULL,
    session_version INTEGER NOT NULL,
    kind VARCHAR(64) NOT NULL,
    note TEXT DEFAULT '' NOT NULL,
    old_date DATE,
    new_date DATE,
    old_start TIME WITHOUT TIME ZONE,
    old_end TIME WITHOUT TIME ZONE,
    new_start TIME WITHOUT TIME ZONE,
    new_end TIME WITHOUT TIME ZONE,
    old_trainer_id UUID,
    new_trainer_id UUID,
    actor_id UUID NOT NULL,
    actor_name VARCHAR(200) NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_session_events PRIMARY KEY (id),
    CONSTRAINT ck_session_events_valid_version CHECK (session_version > 0),
    CONSTRAINT fk_session_events_session_id_training_sessions FOREIGN KEY(session_id) REFERENCES
    training_sessions (id),
    CONSTRAINT fk_session_events_old_trainer_id_trainers FOREIGN KEY(old_trainer_id) REFERENCES
    trainers (id),
    CONSTRAINT fk_session_events_new_trainer_id_trainers FOREIGN KEY(new_trainer_id) REFERENCES
    trainers (id),
    CONSTRAINT fk_session_events_actor_id_staff_users FOREIGN KEY(actor_id) REFERENCES staff_users
    (id),
    CONSTRAINT ck_session_events_actor_name_required CHECK (length(btrim(actor_name)) > 0)
);

CREATE INDEX ix_session_events_actor_id ON session_events (actor_id);

CREATE INDEX ix_session_events_session_id ON session_events (session_id);

CREATE TABLE media_assets (
    purpose VARCHAR(24) NOT NULL,
    status VARCHAR(16) DEFAULT 'pending' NOT NULL,
    bucket VARCHAR(63) NOT NULL,
    object_key VARCHAR(1024) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    content_type VARCHAR(100) NOT NULL,
    size_bytes BIGINT NOT NULL,
    content_sha256 VARCHAR(64) NOT NULL,
    uploaded_by UUID NOT NULL,
    client_id UUID,
    purchase_id UUID,
    session_id UUID,
    original_session_id UUID,
    original_plan_item_id UUID,
    expires_at TIMESTAMP WITH TIME ZONE,
    version INTEGER DEFAULT 1 NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_media_assets PRIMARY KEY (id),
    CONSTRAINT uq_media_assets_bucket_object_key UNIQUE (bucket, object_key),
    CONSTRAINT ck_media_assets_purpose_values CHECK (purpose IN ('session_video',
    'exercise_media')),
    CONSTRAINT ck_media_assets_status_values CHECK (status IN ('pending', 'ready', 'delete_pending',
    'deleted')),
    CONSTRAINT fk_media_assets_purchase_id_client_id_package_purchases FOREIGN KEY(purchase_id,
    client_id) REFERENCES package_purchases (id, client_id),
    CONSTRAINT ck_media_assets_content_evidence CHECK (size_bytes > 0 AND content_sha256 ~
    '^[0-9a-f]{64}$'),
    CONSTRAINT ck_media_assets_storage_required CHECK (length(btrim(bucket)) > 0 AND
    length(btrim(object_key)) > 0),
    CONSTRAINT ck_media_assets_purpose_scope CHECK ((purpose = 'session_video' AND
    original_session_id IS NOT NULL AND original_plan_item_id IS NOT NULL AND client_id IS NOT
    NULL AND purchase_id IS NOT NULL AND expires_at IS NOT NULL AND expires_at > created_at) OR
    (purpose = 'exercise_media' AND num_nonnulls(original_session_id, original_plan_item_id,
    session_id, client_id, purchase_id, expires_at) = 0)),
    CONSTRAINT fk_media_assets_uploaded_by_staff_users FOREIGN KEY(uploaded_by) REFERENCES
    staff_users (id),
    CONSTRAINT fk_media_assets_client_id_clients FOREIGN KEY(client_id) REFERENCES clients (id),
    CONSTRAINT fk_media_assets_session_id_training_sessions FOREIGN KEY(session_id) REFERENCES
    training_sessions (id) ON DELETE SET NULL,
    CONSTRAINT ck_media_assets_positive_version CHECK (version > 0)
);

CREATE INDEX ix_media_assets_client_id ON media_assets (client_id);

CREATE INDEX ix_media_assets_purchase_id ON media_assets (purchase_id);

CREATE INDEX ix_media_assets_session_id ON media_assets (session_id);

CREATE INDEX ix_media_expiry ON media_assets (expires_at) WHERE status = 'ready' AND expires_at IS
    NOT NULL;

CREATE TABLE exercise_plan_items (
    session_id UUID NOT NULL,
    exercise_id UUID,
    position INTEGER NOT NULL,
    name VARCHAR(200) NOT NULL,
    weight VARCHAR(100) DEFAULT '' NOT NULL,
    reps VARCHAR(100) DEFAULT '' NOT NULL,
    rounds VARCHAR(100) DEFAULT '' NOT NULL,
    rest VARCHAR(100) DEFAULT '' NOT NULL,
    notes TEXT DEFAULT '' NOT NULL,
    version INTEGER DEFAULT 1 NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_exercise_plan_items PRIMARY KEY (id),
    CONSTRAINT uq_exercise_plan_items_session_id_position UNIQUE (session_id, position) DEFERRABLE
    INITIALLY DEFERRED,
    CONSTRAINT uq_exercise_plan_items_id_session_id UNIQUE (id, session_id),
    CONSTRAINT ck_exercise_plan_items_valid_item CHECK (position > 0 AND length(btrim(name)) > 0),
    CONSTRAINT fk_exercise_plan_items_session_id_training_sessions FOREIGN KEY(session_id)
    REFERENCES
    training_sessions (id),
    CONSTRAINT fk_exercise_plan_items_exercise_id_exercises FOREIGN KEY(exercise_id) REFERENCES
    exercises (id),
    CONSTRAINT ck_exercise_plan_items_positive_version CHECK (version > 0)
);

CREATE INDEX ix_exercise_plan_items_exercise_id ON exercise_plan_items (exercise_id);

CREATE INDEX ix_exercise_plan_items_session_id ON exercise_plan_items (session_id);

CREATE TABLE acknowledgements (
    session_id UUID NOT NULL,
    sequence INTEGER NOT NULL,
    method VARCHAR(16) NOT NULL,
    signer_name VARCHAR(200),
    signature BYTEA,
    signature_sha256 VARCHAR(64),
    note TEXT DEFAULT '' NOT NULL,
    actor_id UUID NOT NULL,
    actor_name VARCHAR(200) NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_acknowledgements PRIMARY KEY (id),
    CONSTRAINT uq_acknowledgements_session_id_sequence UNIQUE (session_id, sequence),
    CONSTRAINT uq_acknowledgements_id_session_id UNIQUE (id, session_id),
    CONSTRAINT ck_acknowledgements_method_values CHECK (method IN ('signature', 'late_no_show')),
    CONSTRAINT ck_acknowledgements_bounded_history CHECK (sequence IN (1, 2)),
    CONSTRAINT ck_acknowledgements_signature_evidence CHECK ((method = 'signature' AND signer_name
    IS
    NOT NULL AND length(btrim(signer_name)) > 0 AND signature IS NOT NULL AND
    octet_length(signature) BETWEEN 1 AND 1000000 AND signature_sha256 IS NOT NULL AND
    signature_sha256 ~ '^[0-9a-f]{64}$') OR (method = 'late_no_show' AND signer_name IS NULL AND
    signature IS NULL AND signature_sha256 IS NULL)),
    CONSTRAINT fk_acknowledgements_session_id_training_sessions FOREIGN KEY(session_id) REFERENCES
    training_sessions (id),
    CONSTRAINT fk_acknowledgements_actor_id_staff_users FOREIGN KEY(actor_id) REFERENCES staff_users
    (id),
    CONSTRAINT ck_acknowledgements_actor_name_required CHECK (length(btrim(actor_name)) > 0)
);

CREATE INDEX ix_acknowledgements_actor_id ON acknowledgements (actor_id);

CREATE INDEX ix_acknowledgements_session_id ON acknowledgements (session_id);

CREATE TABLE credit_debits (
    session_id UUID NOT NULL,
    purchase_id UUID NOT NULL,
    client_id UUID NOT NULL,
    amount INTEGER DEFAULT -1 NOT NULL,
    actor_id UUID NOT NULL,
    actor_name VARCHAR(200) NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_credit_debits PRIMARY KEY (id),
    CONSTRAINT fk_credit_debits_session_id_purchase_id_client_id_train_9eb1 FOREIGN KEY(session_id,
    purchase_id, client_id) REFERENCES training_sessions (id, purchase_id, client_id),
    CONSTRAINT ck_credit_debits_single_credit CHECK (amount = -1),
    CONSTRAINT uq_credit_debits_session_id UNIQUE (session_id),
    CONSTRAINT fk_credit_debits_purchase_id_package_purchases FOREIGN KEY(purchase_id) REFERENCES
    package_purchases (id),
    CONSTRAINT fk_credit_debits_client_id_clients FOREIGN KEY(client_id) REFERENCES clients (id),
    CONSTRAINT fk_credit_debits_actor_id_staff_users FOREIGN KEY(actor_id) REFERENCES staff_users
    (id),
    CONSTRAINT ck_credit_debits_actor_name_required CHECK (length(btrim(actor_name)) > 0)
);

CREATE INDEX ix_credit_debits_actor_id ON credit_debits (actor_id);

CREATE INDEX ix_credit_debits_client_id ON credit_debits (client_id);

CREATE INDEX ix_credit_debits_purchase_id ON credit_debits (purchase_id);

CREATE TABLE assignment_changes (
    event_id UUID NOT NULL,
    purchase_id UUID,
    session_id UUID,
    old_trainer_id UUID NOT NULL,
    new_trainer_id UUID NOT NULL,
    old_version INTEGER NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_assignment_changes PRIMARY KEY (id),
    CONSTRAINT ck_assignment_changes_one_target CHECK (num_nonnulls(purchase_id, session_id) = 1),
    CONSTRAINT ck_assignment_changes_valid_version CHECK (old_version > 0),
    CONSTRAINT uq_assignment_changes_event_id_purchase_id UNIQUE (event_id, purchase_id),
    CONSTRAINT uq_assignment_changes_event_id_session_id UNIQUE (event_id, session_id),
    CONSTRAINT fk_assignment_changes_event_id_assignment_events FOREIGN KEY(event_id) REFERENCES
    assignment_events (id),
    CONSTRAINT fk_assignment_changes_purchase_id_package_purchases FOREIGN KEY(purchase_id)
    REFERENCES package_purchases (id),
    CONSTRAINT fk_assignment_changes_session_id_training_sessions FOREIGN KEY(session_id) REFERENCES
    training_sessions (id),
    CONSTRAINT fk_assignment_changes_old_trainer_id_trainers FOREIGN KEY(old_trainer_id) REFERENCES
    trainers (id),
    CONSTRAINT fk_assignment_changes_new_trainer_id_trainers FOREIGN KEY(new_trainer_id) REFERENCES
    trainers (id)
);

CREATE INDEX ix_assignment_changes_event_id ON assignment_changes (event_id);

CREATE TABLE request_slots (
    request_id UUID NOT NULL,
    side VARCHAR(3) NOT NULL,
    slot_identity UUID NOT NULL,
    weekday INTEGER NOT NULL,
    starts_at TIME WITHOUT TIME ZONE NOT NULL,
    ends_at TIME WITHOUT TIME ZONE NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_request_slots PRIMARY KEY (id),
    CONSTRAINT ck_request_slots_side_values CHECK (side IN ('old', 'new')),
    CONSTRAINT ck_request_slots_valid_slot CHECK (weekday BETWEEN 0 AND 6 AND starts_at < ends_at),
    CONSTRAINT uq_request_slots_request_id_side_slot_identity UNIQUE (request_id, side,
    slot_identity),
    CONSTRAINT fk_request_slots_request_id_change_requests FOREIGN KEY(request_id) REFERENCES
    change_requests (id)
);

CREATE INDEX ix_request_slots_request_id ON request_slots (request_id);

CREATE TABLE request_events (
    request_id UUID NOT NULL,
    sequence INTEGER NOT NULL,
    status VARCHAR(16) NOT NULL,
    note TEXT DEFAULT '' NOT NULL,
    actor_id UUID NOT NULL,
    actor_name VARCHAR(200) NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_request_events PRIMARY KEY (id),
    CONSTRAINT ck_request_events_status_values CHECK (status IN ('pending', 'approved', 'rejected',
    'cancelled', 'superseded')),
    CONSTRAINT uq_request_events_request_id_sequence UNIQUE (request_id, sequence),
    CONSTRAINT ck_request_events_bounded_history CHECK (sequence IN (1, 2)),
    CONSTRAINT fk_request_events_request_id_change_requests FOREIGN KEY(request_id) REFERENCES
    change_requests (id),
    CONSTRAINT fk_request_events_actor_id_staff_users FOREIGN KEY(actor_id) REFERENCES staff_users
    (id),
    CONSTRAINT ck_request_events_actor_name_required CHECK (length(btrim(actor_name)) > 0)
);

CREATE INDEX ix_request_events_actor_id ON request_events (actor_id);

CREATE INDEX ix_request_events_request_id ON request_events (request_id);

CREATE TABLE messages (
    kind VARCHAR(64) NOT NULL,
    title VARCHAR(500) NOT NULL,
    body TEXT NOT NULL,
    client_id UUID,
    purchase_id UUID,
    session_id UUID,
    trainer_id UUID,
    request_id UUID,
    remuneration_id UUID,
    exercise_id UUID,
    content_id UUID,
    actor_id UUID NOT NULL,
    actor_name VARCHAR(200) NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_messages PRIMARY KEY (id),
    CONSTRAINT ck_messages_details_required CHECK (length(btrim(title)) > 0 AND
    length(btrim(kind)) >
    0),
    CONSTRAINT fk_messages_purchase_id_client_id_package_purchases FOREIGN KEY(purchase_id,
    client_id) REFERENCES package_purchases (id, client_id),
    CONSTRAINT ck_messages_purchase_scope CHECK (purchase_id IS NULL OR client_id IS NOT NULL),
    CONSTRAINT fk_messages_client_id_clients FOREIGN KEY(client_id) REFERENCES clients (id),
    CONSTRAINT fk_messages_session_id_training_sessions FOREIGN KEY(session_id) REFERENCES
    training_sessions (id),
    CONSTRAINT fk_messages_trainer_id_trainers FOREIGN KEY(trainer_id) REFERENCES trainers (id),
    CONSTRAINT fk_messages_request_id_change_requests FOREIGN KEY(request_id) REFERENCES
    change_requests (id),
    CONSTRAINT fk_messages_remuneration_id_remuneration_approvals FOREIGN KEY(remuneration_id)
    REFERENCES remuneration_approvals (id),
    CONSTRAINT fk_messages_exercise_id_exercises FOREIGN KEY(exercise_id) REFERENCES exercises
    (id),
    CONSTRAINT fk_messages_content_id_content_entries FOREIGN KEY(content_id) REFERENCES
    content_entries (id),
    CONSTRAINT fk_messages_actor_id_staff_users FOREIGN KEY(actor_id) REFERENCES staff_users (id),
    CONSTRAINT ck_messages_actor_name_required CHECK (length(btrim(actor_name)) > 0)
);

CREATE INDEX ix_messages_actor_id ON messages (actor_id);

CREATE INDEX ix_messages_client_id ON messages (client_id);

CREATE INDEX ix_messages_kind ON messages (kind);

CREATE INDEX ix_messages_purchase_id ON messages (purchase_id);

CREATE INDEX ix_messages_remuneration_id ON messages (remuneration_id);

CREATE INDEX ix_messages_request_id ON messages (request_id);

CREATE INDEX ix_messages_session_id ON messages (session_id);

CREATE INDEX ix_messages_trainer_id ON messages (trainer_id);

CREATE TABLE remuneration_lines (
    approval_id UUID NOT NULL,
    trainer_id UUID NOT NULL,
    session_id UUID NOT NULL,
    client_id UUID NOT NULL,
    purchase_id UUID NOT NULL,
    client_name VARCHAR(400) NOT NULL,
    client_kind VARCHAR(16) NOT NULL,
    training_date DATE NOT NULL,
    starts_at TIME WITHOUT TIME ZONE NOT NULL,
    ends_at TIME WITHOUT TIME ZONE NOT NULL,
    session_version INTEGER NOT NULL,
    acknowledgement_id UUID NOT NULL,
    acknowledgement_method VARCHAR(16) NOT NULL,
    band VARCHAR(16) NOT NULL,
    minutes INTEGER NOT NULL,
    amount_cents BIGINT NOT NULL,
    source_sha256 VARCHAR(64) NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_remuneration_lines PRIMARY KEY (id),
    CONSTRAINT fk_remuneration_lines_approval_id_trainer_id_remunerati_479f FOREIGN KEY(approval_id,
    trainer_id) REFERENCES remuneration_approvals (id, trainer_id),
    CONSTRAINT fk_remuneration_lines_session_id_purchase_id_client_id__cdc3 FOREIGN KEY(session_id,
    purchase_id, client_id) REFERENCES training_sessions (id, purchase_id, client_id),
    CONSTRAINT fk_remuneration_lines_acknowledgement_id_session_id_ack_4a82 FOREIGN
    KEY(acknowledgement_id, session_id) REFERENCES acknowledgements (id, session_id),
    CONSTRAINT uq_remuneration_lines_approval_id_session_id UNIQUE (approval_id, session_id),
    CONSTRAINT uq_remuneration_lines_session_id UNIQUE (session_id),
    CONSTRAINT ck_remuneration_lines_band_values CHECK (band IN ('peak', 'off_peak')),
    CONSTRAINT ck_remuneration_lines_acknowledgement_method_values CHECK (acknowledgement_method IN
    ('signature', 'late_no_show')),
    CONSTRAINT ck_remuneration_lines_pay_bounds CHECK (amount_cents >= 0 AND minutes >= 0 AND
    starts_at < ends_at AND session_version > 0),
    CONSTRAINT ck_remuneration_lines_evidence_digest CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT fk_remuneration_lines_trainer_id_trainers FOREIGN KEY(trainer_id) REFERENCES trainers
    (id),
    CONSTRAINT fk_remuneration_lines_client_id_clients FOREIGN KEY(client_id) REFERENCES clients
    (id),
    CONSTRAINT fk_remuneration_lines_purchase_id_package_purchases FOREIGN KEY(purchase_id)
    REFERENCES package_purchases (id)
);

CREATE INDEX ix_remuneration_lines_approval_id ON remuneration_lines (approval_id);

CREATE INDEX ix_remuneration_lines_session_id ON remuneration_lines (session_id);

CREATE INDEX ix_remuneration_lines_trainer_id ON remuneration_lines (trainer_id);

CREATE TABLE media_deletions (
    media_id UUID NOT NULL,
    status VARCHAR(16) DEFAULT 'pending' NOT NULL,
    reason VARCHAR(24) NOT NULL,
    attempts INTEGER DEFAULT 0 NOT NULL,
    next_attempt_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    lease_until TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    error_code VARCHAR(64),
    version INTEGER DEFAULT 1 NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_media_deletions PRIMARY KEY (id),
    CONSTRAINT ck_media_deletions_status_values CHECK (status IN ('pending', 'processing',
    'done')),
    CONSTRAINT ck_media_deletions_reason_values CHECK (reason IN ('expired', 'replaced', 'removed',
    'session_deleted')),
    CONSTRAINT ck_media_deletions_attempt_count CHECK (attempts >= 0),
    CONSTRAINT ck_media_deletions_completion_state CHECK ((status = 'done') = (completed_at IS NOT
    NULL)),
    CONSTRAINT uq_media_deletions_media_id UNIQUE (media_id),
    CONSTRAINT fk_media_deletions_media_id_media_assets FOREIGN KEY(media_id) REFERENCES
    media_assets
    (id),
    CONSTRAINT ck_media_deletions_positive_version CHECK (version > 0)
);

CREATE INDEX ix_deletion_pending ON media_deletions (next_attempt_at) WHERE status <> 'done';

CREATE TABLE exercise_results (
    session_id UUID NOT NULL,
    plan_item_id UUID,
    name VARCHAR(200) NOT NULL,
    load_kg NUMERIC(9, 4) NOT NULL,
    reps INTEGER NOT NULL,
    sets INTEGER NOT NULL,
    version INTEGER DEFAULT 1 NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_exercise_results PRIMARY KEY (id),
    CONSTRAINT fk_exercise_results_plan_item_id_session_id_exercise_plan_items FOREIGN
    KEY(plan_item_id, session_id) REFERENCES exercise_plan_items (id, session_id),
    CONSTRAINT uq_exercise_results_session_id_plan_item_id UNIQUE (session_id, plan_item_id),
    CONSTRAINT ck_exercise_results_measurement_bounds CHECK (load_kg BETWEEN 0 AND 2000 AND reps
    BETWEEN 1 AND 1000 AND sets BETWEEN 1 AND 100),
    CONSTRAINT ck_exercise_results_name_required CHECK (length(btrim(name)) > 0),
    CONSTRAINT fk_exercise_results_session_id_training_sessions FOREIGN KEY(session_id) REFERENCES
    training_sessions (id),
    CONSTRAINT ck_exercise_results_positive_version CHECK (version > 0)
);

CREATE INDEX ix_exercise_results_session_id ON exercise_results (session_id);

CREATE TABLE message_receipts (
    message_id UUID NOT NULL,
    user_id UUID NOT NULL,
    read_at TIMESTAMP WITH TIME ZONE,
    version INTEGER DEFAULT 1 NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_message_receipts PRIMARY KEY (id),
    CONSTRAINT uq_message_receipts_message_id_user_id UNIQUE (message_id, user_id),
    CONSTRAINT fk_message_receipts_message_id_messages FOREIGN KEY(message_id) REFERENCES messages
    (id),
    CONSTRAINT fk_message_receipts_user_id_staff_users FOREIGN KEY(user_id) REFERENCES staff_users
    (id),
    CONSTRAINT ck_message_receipts_positive_version CHECK (version > 0)
);

CREATE INDEX ix_message_receipts_message_id ON message_receipts (message_id);

CREATE INDEX ix_message_receipts_user_id ON message_receipts (user_id);

CREATE INDEX ix_receipt_unread ON message_receipts (user_id, created_at) WHERE read_at IS NULL;

CREATE TABLE exercise_result_revisions (
    result_id UUID NOT NULL,
    result_version INTEGER NOT NULL,
    name VARCHAR(200) NOT NULL,
    load_kg NUMERIC(9, 4) NOT NULL,
    reps INTEGER NOT NULL,
    sets INTEGER NOT NULL,
    actor_id UUID NOT NULL,
    actor_name VARCHAR(200) NOT NULL,
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT pk_exercise_result_revisions PRIMARY KEY (id),
    CONSTRAINT uq_exercise_result_revisions_result_id_result_version UNIQUE (result_id,
    result_version),
    CONSTRAINT ck_exercise_result_revisions_measurement_bounds CHECK (result_version > 0 AND load_kg
    BETWEEN 0 AND 2000 AND reps BETWEEN 1 AND 1000 AND sets BETWEEN 1 AND 100),
    CONSTRAINT fk_exercise_result_revisions_result_id_exercise_results FOREIGN KEY(result_id)
    REFERENCES exercise_results (id),
    CONSTRAINT fk_exercise_result_revisions_actor_id_staff_users FOREIGN KEY(actor_id) REFERENCES
    staff_users (id),
    CONSTRAINT ck_exercise_result_revisions_actor_name_required CHECK (length(btrim(actor_name)) >
    0)
);

CREATE INDEX ix_exercise_result_revisions_actor_id ON exercise_result_revisions (actor_id);

CREATE INDEX ix_exercise_result_revisions_result_id ON exercise_result_revisions (result_id);

ALTER TABLE clients ADD CONSTRAINT fk_clients_lifecycle_event_id_lifecycle_events FOREIGN
    KEY(lifecycle_event_id) REFERENCES lifecycle_events (id);

ALTER TABLE exercises ADD CONSTRAINT fk_exercises_media_id_media_assets FOREIGN KEY(media_id)
    REFERENCES media_assets (id);

ALTER TABLE package_purchases ADD CONSTRAINT
    fk_package_purchases_lifecycle_event_id_lifecycle_events FOREIGN KEY(lifecycle_event_id)
    REFERENCES lifecycle_events (id);

-- Transactional invariants are enforced even if a future writer bypasses the ORM.
CREATE FUNCTION ff_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'immutable evidence: %', TG_TABLE_NAME USING ERRCODE = '23514'; END $$;

CREATE FUNCTION ff_version() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    IF NEW.version <> 1 THEN RAISE EXCEPTION 'initial version must be one' USING ERRCODE='23514';
    END IF;
    NEW.created_at := transaction_timestamp(); NEW.updated_at := NEW.created_at;
  ELSE
    IF NEW.version <> OLD.version + 1 OR NEW.id <> OLD.id OR NEW.created_at <> OLD.created_at THEN
      RAISE EXCEPTION 'version or identity mismatch' USING ERRCODE='23514';
    END IF;
    NEW.updated_at := clock_timestamp();
  END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION ff_preserve_fields() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE field text;
BEGIN
  FOREACH field IN ARRAY TG_ARGV LOOP
    IF to_jsonb(NEW)->field IS DISTINCT FROM to_jsonb(OLD)->field THEN
      RAISE EXCEPTION 'immutable field: %.%', TG_TABLE_NAME, field USING ERRCODE='23514';
    END IF;
  END LOOP;
  RETURN NEW;
END $$;

CREATE FUNCTION ff_actor() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  SELECT name INTO STRICT NEW.actor_name FROM staff_users WHERE id = NEW.actor_id;
  NEW.created_at := transaction_timestamp();
  RETURN NEW;
END $$;

CREATE FUNCTION ff_birth() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN NEW.created_xid := pg_current_xact_id()::text; RETURN NEW; END $$;

CREATE FUNCTION ff_people_count() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE target uuid; expected integer; actual integer;
BEGIN
  IF TG_TABLE_NAME = 'clients' THEN target := NEW.id;
  ELSIF TG_OP = 'DELETE' THEN target := OLD.client_id;
  ELSE target := NEW.client_id; END IF;
  SELECT CASE kind WHEN 'individual' THEN 1 ELSE 2 END INTO expected FROM clients WHERE id=target
    FOR UPDATE;
  IF NOT FOUND THEN RETURN NULL; END IF;
  SELECT count(*) INTO actual FROM client_people WHERE client_id=target;
  IF actual <> expected THEN RAISE EXCEPTION 'client requires exactly % people', expected USING
    ERRCODE='23514'; END IF;
  RETURN NULL;
END $$;

CREATE FUNCTION ff_purchase_insert() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE definition package_template_revisions%ROWTYPE; last_day date;
BEGIN
  PERFORM 1 FROM clients WHERE id=NEW.client_id AND status='active' FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'active client required' USING ERRCODE='23514'; END IF;
  PERFORM 1 FROM package_templates WHERE id=NEW.template_id AND status='active' FOR SHARE;
  IF NOT FOUND THEN RAISE EXCEPTION 'active package template required' USING ERRCODE='23514'; END
    IF;
  IF NEW.template_revision <> (SELECT max(revision) FROM package_template_revisions WHERE
    template_id=NEW.template_id) THEN
    RAISE EXCEPTION 'package template revision changed after review' USING ERRCODE='23514'; END IF;
  SELECT * INTO STRICT definition FROM package_template_revisions
    WHERE template_id=NEW.template_id AND revision=NEW.template_revision;
  IF (NEW.name, NEW.total_sessions, NEW.validity_days) IS DISTINCT FROM
     (definition.name,definition.total_sessions,definition.validity_days) THEN
    RAISE EXCEPTION 'purchase terms must match reviewed template revision' USING ERRCODE='23514';
    END IF;
  SELECT max(end_date) INTO last_day FROM package_purchases WHERE client_id=NEW.client_id AND
    status='active';
  IF NEW.start_date <= last_day THEN RAISE EXCEPTION
    'purchase must follow all active purchase dates' USING ERRCODE='23514'; END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION ff_purchase_complete() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE slots integer; sessions integer;
BEGIN
  SELECT count(*) INTO slots FROM purchase_schedule_slots WHERE purchase_id=NEW.id;
  SELECT count(*) INTO sessions FROM training_sessions WHERE purchase_id=NEW.id;
  IF slots <> NEW.sessions_per_week OR sessions <> NEW.total_sessions THEN
    RAISE EXCEPTION
    'purchase requires complete schedule and generated sessions in one transaction' USING
    ERRCODE='23514'; END IF;
  RETURN NULL;
END $$;

CREATE FUNCTION ff_purchase_child() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE birth text;
BEGIN
  SELECT created_xid INTO birth FROM package_purchases WHERE id=NEW.purchase_id;
  IF birth IS DISTINCT FROM pg_current_xact_id()::text THEN
    RAISE EXCEPTION 'purchase snapshot must be inserted with purchase' USING ERRCODE='23514'; END
    IF;
  IF TG_TABLE_NAME = 'purchase_schedule_slots' THEN
    IF (NEW.weekday, NEW.starts_at, NEW.ends_at) IS DISTINCT FROM
     (NEW.purchased_weekday, NEW.purchased_starts_at, NEW.purchased_ends_at) THEN
    RAISE EXCEPTION 'initial schedule must equal purchased snapshot' USING ERRCODE='23514'; END IF;
  END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION ff_session_guard() RETURNS trigger LANGUAGE plpgsql AS $$
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

CREATE FUNCTION ff_acknowledgement() RETURNS trigger LANGUAGE plpgsql AS $$
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

CREATE FUNCTION ff_completion() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE target uuid; state text; debits integer; acks integer;
BEGIN
  IF TG_TABLE_NAME='training_sessions' THEN target:=NEW.id; ELSE target:=NEW.session_id; END IF;
  SELECT status INTO state FROM training_sessions WHERE id=target FOR UPDATE;
  SELECT count(*) INTO debits FROM credit_debits WHERE session_id=target;
  SELECT count(*) INTO acks FROM acknowledgements WHERE session_id=target;
  IF (state='completed' AND (debits<>1 OR acks=0)) OR (state<>'completed' AND (debits<>0 OR
    acks<>0)) THEN
    RAISE EXCEPTION 'completion, acknowledgement and debit must commit together' USING
    ERRCODE='23514'; END IF;
  RETURN NULL;
END $$;

CREATE FUNCTION ff_request_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.status <> 'pending' OR NEW.status = 'pending' THEN
    RAISE EXCEPTION 'request can only transition once from pending' USING ERRCODE='23514'; END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION ff_request_slot() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent change_requests%ROWTYPE;
BEGIN
  SELECT * INTO STRICT parent FROM change_requests WHERE id=NEW.request_id;
  IF parent.kind NOT IN ('fixed_weekly_schedule', 'trainer_availability') OR
     parent.created_xid <> pg_current_xact_id()::text THEN
    RAISE EXCEPTION 'typed slot proposal must be inserted with request' USING ERRCODE='23514'; END
    IF;
  RETURN NEW;
END $$;

CREATE FUNCTION ff_request_history() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE target uuid; parent change_requests%ROWTYPE; history integer; old_slots integer; new_slots
    integer;
BEGIN
  IF TG_TABLE_NAME='change_requests' THEN target:=NEW.id; ELSE target:=NEW.request_id; END IF;
  SELECT * INTO STRICT parent FROM change_requests WHERE id=target;
  SELECT count(*) INTO history FROM request_events WHERE request_id=target;
  IF history <> (CASE WHEN parent.status='pending' THEN 1 ELSE 2 END) OR
     NOT EXISTS(SELECT 1 FROM request_events WHERE request_id=target AND sequence=1 AND
    status='pending') OR
     (parent.status<>'pending' AND NOT EXISTS(SELECT 1 FROM request_events WHERE request_id=target
    AND sequence=2 AND status=parent.status)) THEN
    RAISE EXCEPTION 'request status requires matching append-only history' USING ERRCODE='23514';
    END IF;
  IF parent.kind='fixed_weekly_schedule' THEN
    SELECT count(*) INTO old_slots FROM request_slots WHERE request_id=target AND side='old';
    SELECT count(*) INTO new_slots FROM request_slots WHERE request_id=target AND side='new';
    IF old_slots=0 OR old_slots<>new_slots THEN
      RAISE EXCEPTION 'weekly request needs matching old and new slots' USING ERRCODE='23514'; END
    IF;
  END IF;
  RETURN NULL;
END $$;

CREATE FUNCTION ff_pay_line() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE approval remuneration_approvals%ROWTYPE; booking training_sessions%ROWTYPE; ack
    acknowledgements%ROWTYPE;
BEGIN
  SELECT * INTO STRICT approval FROM remuneration_approvals WHERE id=NEW.approval_id;
  SELECT * INTO STRICT booking FROM training_sessions WHERE id=NEW.session_id FOR UPDATE;
  SELECT * INTO STRICT ack FROM acknowledgements WHERE session_id=NEW.session_id ORDER BY sequence
    DESC LIMIT 1;
  IF approval.created_xid <> pg_current_xact_id()::text OR booking.status<>'completed' OR
     (booking.client_id, booking.purchase_id, booking.trainer_id, booking.training_date,
    booking.starts_at, booking.ends_at, booking.version) IS DISTINCT FROM
     (NEW.client_id, NEW.purchase_id, NEW.trainer_id, NEW.training_date, NEW.starts_at,
    NEW.ends_at, NEW.session_version) OR
     (ack.id,ack.method) IS DISTINCT FROM (NEW.acknowledgement_id, NEW.acknowledgement_method) OR
     NEW.training_date NOT BETWEEN approval.cycle_start AND approval.cycle_end THEN
    RAISE EXCEPTION 'pay evidence must match completed session at approval' USING ERRCODE='23514';
    END IF;
  IF (ack.method='late_no_show' AND NEW.minutes<>0) OR
     (ack.method='signature' AND NEW.minutes<>extract(epoch FROM (NEW.ends_at-NEW.starts_at))/60)
    THEN
    RAISE EXCEPTION 'pay minutes must match attendance and scheduled duration' USING
    ERRCODE='23514'; END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION ff_pay_totals() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE target uuid; approval remuneration_approvals%ROWTYPE; amount bigint; minutes integer;
    sessions integer;
BEGIN
  IF TG_TABLE_NAME='remuneration_approvals' THEN target:=NEW.id; ELSE target:=NEW.approval_id; END
    IF;
  SELECT * INTO STRICT approval FROM remuneration_approvals WHERE id=target;
  SELECT coalesce(sum(amount_cents),0), coalesce(sum(remuneration_lines.minutes),0), count(*) INTO
    amount,minutes,sessions
    FROM remuneration_lines WHERE approval_id=target;
  IF (amount,minutes,sessions) IS DISTINCT FROM
    (approval.amount_cents,approval.total_minutes,approval.session_count) OR
     approval.cycle_end >= (clock_timestamp() AT TIME ZONE 'Asia/Singapore')::date THEN
    RAISE EXCEPTION 'closed pay approval must reconcile with all evidence rows' USING
    ERRCODE='23514'; END IF;
  RETURN NULL;
END $$;

CREATE FUNCTION ff_media_scope() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='INSERT' AND NEW.purpose='session_video' AND NOT EXISTS (
    SELECT 1 FROM exercise_plan_items p JOIN training_sessions s ON s.id=p.session_id
    WHERE p.id=NEW.original_plan_item_id AND s.id=NEW.original_session_id AND s.id=NEW.session_id
      AND s.client_id=NEW.client_id AND s.purchase_id=NEW.purchase_id
  ) THEN RAISE EXCEPTION 'video scope must match stored exercise/session/purchase/client' USING
    ERRCODE='23514'; END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION ff_template_revision() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE latest integer;
BEGIN
  PERFORM 1 FROM package_templates WHERE id=NEW.template_id FOR UPDATE;
  SELECT coalesce(max(revision),0) INTO latest FROM package_template_revisions WHERE
    template_id=NEW.template_id;
  IF NEW.revision <> latest+1 THEN RAISE EXCEPTION 'template revisions must be sequential' USING
    ERRCODE='23514'; END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION ff_lifecycle_event() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent lifecycle_events%ROWTYPE; client uuid;
BEGIN
  IF NEW.reason='owner' AND NEW.cause_id IS NOT NULL THEN
    RAISE EXCEPTION 'owner lifecycle change has no client cause' USING ERRCODE='23514'; END IF;
  IF NEW.reason IN ('client', 'client_reactivated') THEN
    SELECT * INTO parent FROM lifecycle_events WHERE id=NEW.cause_id;
    SELECT client_id INTO client FROM package_purchases WHERE id=NEW.purchase_id;
    IF NEW.purchase_id IS NULL OR parent.id IS NULL OR parent.client_id IS DISTINCT FROM client OR
       parent.status IS DISTINCT FROM NEW.status OR
       (NEW.reason='client' AND NEW.status<>'inactive') OR
       (NEW.reason='client_reactivated' AND NEW.status<>'active') THEN
      RAISE EXCEPTION 'purchase lifecycle cause must match the client event' USING
    ERRCODE='23514'; END IF;
  END IF;
  RETURN NEW;
END $$;

CREATE FUNCTION ff_lifecycle_state() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE evidence lifecycle_events%ROWTYPE;
BEGIN
  IF NEW.status IS DISTINCT FROM OLD.status THEN
    SELECT * INTO evidence FROM lifecycle_events WHERE id=NEW.lifecycle_event_id;
    IF evidence.id IS NULL OR evidence.status IS DISTINCT FROM NEW.status OR
       (TG_TABLE_NAME='clients' AND evidence.client_id IS DISTINCT FROM NEW.id) OR
       (TG_TABLE_NAME='package_purchases' AND evidence.purchase_id IS DISTINCT FROM NEW.id) THEN
      RAISE EXCEPTION 'lifecycle state requires matching recorded evidence' USING ERRCODE='23514';
    END IF;
  END IF;
  IF TG_TABLE_NAME='clients' AND NEW.status='inactive' AND EXISTS (
    SELECT 1 FROM package_purchases WHERE client_id=NEW.id AND status='active'
  ) THEN RAISE EXCEPTION 'client deactivation must freeze purchases atomically' USING
    ERRCODE='23514'; END IF;
  RETURN NULL;
END $$;

CREATE TRIGGER ff_version BEFORE INSERT OR UPDATE ON change_requests FOR EACH ROW EXECUTE FUNCTION
    ff_version();
CREATE TRIGGER ff_actor BEFORE INSERT ON change_requests FOR EACH ROW EXECUTE FUNCTION ff_actor();
CREATE TRIGGER ff_birth BEFORE INSERT ON change_requests FOR EACH ROW EXECUTE FUNCTION ff_birth();
CREATE TRIGGER ff_no_delete BEFORE DELETE ON change_requests FOR EACH ROW EXECUTE FUNCTION
    ff_immutable();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON request_slots FOR EACH ROW EXECUTE FUNCTION
    ff_immutable();
CREATE TRIGGER ff_actor BEFORE INSERT ON request_events FOR EACH ROW EXECUTE FUNCTION ff_actor();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON request_events FOR EACH ROW EXECUTE
    FUNCTION ff_immutable();
CREATE TRIGGER ff_actor BEFORE INSERT ON messages FOR EACH ROW EXECUTE FUNCTION ff_actor();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON messages FOR EACH ROW EXECUTE FUNCTION
    ff_immutable();
CREATE TRIGGER ff_version BEFORE INSERT OR UPDATE ON message_receipts FOR EACH ROW EXECUTE
    FUNCTION ff_version();
CREATE TRIGGER ff_actor BEFORE INSERT ON session_events FOR EACH ROW EXECUTE FUNCTION ff_actor();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON session_events FOR EACH ROW EXECUTE
    FUNCTION ff_immutable();
CREATE TRIGGER ff_actor BEFORE INSERT ON remuneration_approvals FOR EACH ROW EXECUTE FUNCTION
    ff_actor();
CREATE TRIGGER ff_birth BEFORE INSERT ON remuneration_approvals FOR EACH ROW EXECUTE FUNCTION
    ff_birth();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON remuneration_approvals FOR EACH ROW EXECUTE
    FUNCTION ff_immutable();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON remuneration_lines FOR EACH ROW EXECUTE
    FUNCTION ff_immutable();
CREATE TRIGGER ff_actor BEFORE INSERT ON report_audit FOR EACH ROW EXECUTE FUNCTION ff_actor();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON report_audit FOR EACH ROW EXECUTE FUNCTION
    ff_immutable();
CREATE TRIGGER ff_version BEFORE INSERT OR UPDATE ON media_assets FOR EACH ROW EXECUTE FUNCTION
    ff_version();
CREATE TRIGGER ff_no_delete BEFORE DELETE ON media_assets FOR EACH ROW EXECUTE FUNCTION
    ff_immutable();
CREATE TRIGGER ff_version BEFORE INSERT OR UPDATE ON media_deletions FOR EACH ROW EXECUTE FUNCTION
    ff_version();
CREATE TRIGGER ff_no_delete BEFORE DELETE ON media_deletions FOR EACH ROW EXECUTE FUNCTION
    ff_immutable();
CREATE TRIGGER ff_version BEFORE INSERT OR UPDATE ON content_entries FOR EACH ROW EXECUTE FUNCTION
    ff_version();
CREATE TRIGGER ff_no_delete BEFORE DELETE ON content_entries FOR EACH ROW EXECUTE FUNCTION
    ff_immutable();
CREATE TRIGGER ff_version BEFORE INSERT OR UPDATE ON staff_users FOR EACH ROW EXECUTE FUNCTION
    ff_version();
CREATE TRIGGER ff_no_delete BEFORE DELETE ON staff_users FOR EACH ROW EXECUTE FUNCTION
    ff_immutable();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON staff_identities FOR EACH ROW EXECUTE
    FUNCTION ff_immutable();
CREATE TRIGGER ff_version BEFORE INSERT OR UPDATE ON trainers FOR EACH ROW EXECUTE FUNCTION
    ff_version();
CREATE TRIGGER ff_no_delete BEFORE DELETE ON trainers FOR EACH ROW EXECUTE FUNCTION ff_immutable();
CREATE TRIGGER ff_version BEFORE INSERT OR UPDATE ON trainer_availability FOR EACH ROW EXECUTE
    FUNCTION ff_version();
CREATE TRIGGER ff_version BEFORE INSERT OR UPDATE ON clients FOR EACH ROW EXECUTE FUNCTION
    ff_version();
CREATE TRIGGER ff_no_delete BEFORE DELETE ON clients FOR EACH ROW EXECUTE FUNCTION ff_immutable();
CREATE TRIGGER ff_version BEFORE INSERT OR UPDATE ON client_people FOR EACH ROW EXECUTE FUNCTION
    ff_version();
CREATE TRIGGER ff_no_delete BEFORE DELETE ON client_people FOR EACH ROW EXECUTE FUNCTION
    ff_immutable();
CREATE TRIGGER ff_actor BEFORE INSERT ON lifecycle_events FOR EACH ROW EXECUTE FUNCTION ff_actor();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON lifecycle_events FOR EACH ROW EXECUTE
    FUNCTION ff_immutable();
CREATE TRIGGER ff_version BEFORE INSERT OR UPDATE ON package_templates FOR EACH ROW EXECUTE
    FUNCTION ff_version();
CREATE TRIGGER ff_no_delete BEFORE DELETE ON package_templates FOR EACH ROW EXECUTE FUNCTION
    ff_immutable();
CREATE TRIGGER ff_actor BEFORE INSERT ON package_template_revisions FOR EACH ROW EXECUTE FUNCTION
    ff_actor();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON package_template_revisions FOR EACH ROW
    EXECUTE FUNCTION ff_immutable();
CREATE TRIGGER ff_version BEFORE INSERT OR UPDATE ON package_purchases FOR EACH ROW EXECUTE
    FUNCTION ff_version();
CREATE TRIGGER ff_birth BEFORE INSERT ON package_purchases FOR EACH ROW EXECUTE FUNCTION ff_birth();
CREATE TRIGGER ff_no_delete BEFORE DELETE ON package_purchases FOR EACH ROW EXECUTE FUNCTION
    ff_immutable();
CREATE TRIGGER ff_version BEFORE INSERT OR UPDATE ON purchase_schedule_slots FOR EACH ROW EXECUTE
    FUNCTION ff_version();
CREATE TRIGGER ff_no_delete BEFORE DELETE ON purchase_schedule_slots FOR EACH ROW EXECUTE FUNCTION
    ff_immutable();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON purchase_preferences FOR EACH ROW EXECUTE
    FUNCTION ff_immutable();
CREATE TRIGGER ff_version BEFORE INSERT OR UPDATE ON training_sessions FOR EACH ROW EXECUTE
    FUNCTION ff_version();
CREATE TRIGGER ff_version BEFORE INSERT OR UPDATE ON exercises FOR EACH ROW EXECUTE FUNCTION
    ff_version();
CREATE TRIGGER ff_no_delete BEFORE DELETE ON exercises FOR EACH ROW EXECUTE FUNCTION ff_immutable();
CREATE TRIGGER ff_version BEFORE INSERT OR UPDATE ON exercise_plan_items FOR EACH ROW EXECUTE
    FUNCTION ff_version();
CREATE TRIGGER ff_version BEFORE INSERT OR UPDATE ON exercise_results FOR EACH ROW EXECUTE
    FUNCTION ff_version();
CREATE TRIGGER ff_actor BEFORE INSERT ON exercise_result_revisions FOR EACH ROW EXECUTE FUNCTION
    ff_actor();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON exercise_result_revisions FOR EACH ROW
    EXECUTE FUNCTION ff_immutable();
CREATE TRIGGER ff_actor BEFORE INSERT ON acknowledgements FOR EACH ROW EXECUTE FUNCTION ff_actor();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON acknowledgements FOR EACH ROW EXECUTE
    FUNCTION ff_immutable();
CREATE TRIGGER ff_actor BEFORE INSERT ON credit_debits FOR EACH ROW EXECUTE FUNCTION ff_actor();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON credit_debits FOR EACH ROW EXECUTE FUNCTION
    ff_immutable();
CREATE TRIGGER ff_actor BEFORE INSERT ON assignment_events FOR EACH ROW EXECUTE FUNCTION ff_actor();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON assignment_events FOR EACH ROW EXECUTE
    FUNCTION ff_immutable();
CREATE TRIGGER ff_immutable BEFORE UPDATE OR DELETE ON assignment_changes FOR EACH ROW EXECUTE
    FUNCTION ff_immutable();
CREATE TRIGGER ff_preserve_fields BEFORE UPDATE ON package_purchases FOR EACH ROW EXECUTE FUNCTION
    ff_preserve_fields('client_id', 'template_id', 'template_revision', 'name', 'total_sessions',
    'validity_days', 'sessions_per_week', 'free_gym', 'start_date', 'end_date',
    'purchased_trainer_id', 'gender_preference', 'created_xid');
CREATE TRIGGER ff_preserve_fields BEFORE UPDATE ON purchase_schedule_slots FOR EACH ROW EXECUTE
    FUNCTION ff_preserve_fields('purchase_id', 'purchased_weekday', 'purchased_starts_at',
    'purchased_ends_at');
CREATE TRIGGER ff_preserve_fields BEFORE UPDATE ON training_sessions FOR EACH ROW EXECUTE FUNCTION
    ff_preserve_fields('client_id', 'purchase_id', 'session_number');
CREATE TRIGGER ff_preserve_fields BEFORE UPDATE ON client_people FOR EACH ROW EXECUTE FUNCTION
    ff_preserve_fields('client_id', 'position');
CREATE TRIGGER ff_preserve_fields BEFORE UPDATE ON exercise_results FOR EACH ROW EXECUTE FUNCTION
    ff_preserve_fields('session_id', 'plan_item_id');
CREATE TRIGGER ff_preserve_fields BEFORE UPDATE ON exercise_plan_items FOR EACH ROW EXECUTE
    FUNCTION ff_preserve_fields('session_id');
CREATE TRIGGER ff_preserve_fields BEFORE UPDATE ON change_requests FOR EACH ROW EXECUTE FUNCTION
    ff_preserve_fields('kind', 'trainer_id', 'client_id', 'purchase_id', 'session_id',
    'expected_version', 'replacement_trainer_id', 'old_date', 'old_start', 'old_end', 'new_date',
    'new_start', 'new_end', 'actor_id', 'actor_name', 'created_xid');
CREATE TRIGGER ff_preserve_fields BEFORE UPDATE ON media_assets FOR EACH ROW EXECUTE FUNCTION
    ff_preserve_fields('purpose', 'bucket', 'object_key', 'original_filename', 'content_type',
    'size_bytes', 'content_sha256', 'uploaded_by', 'client_id', 'purchase_id',
    'original_session_id', 'original_plan_item_id', 'expires_at');
CREATE TRIGGER ff_preserve_fields BEFORE UPDATE ON message_receipts FOR EACH ROW EXECUTE FUNCTION
    ff_preserve_fields('message_id', 'user_id');
CREATE TRIGGER ff_preserve_fields BEFORE UPDATE ON media_deletions FOR EACH ROW EXECUTE FUNCTION
    ff_preserve_fields('media_id', 'reason');
CREATE CONSTRAINT TRIGGER ff_people_count AFTER INSERT OR UPDATE ON clients DEFERRABLE INITIALLY
    DEFERRED FOR EACH ROW EXECUTE FUNCTION ff_people_count();
CREATE CONSTRAINT TRIGGER ff_people_count AFTER INSERT OR UPDATE OR DELETE ON client_people
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ff_people_count();
CREATE TRIGGER ff_purchase_insert BEFORE INSERT ON package_purchases FOR EACH ROW EXECUTE FUNCTION
    ff_purchase_insert();
CREATE CONSTRAINT TRIGGER ff_purchase_complete AFTER INSERT ON package_purchases DEFERRABLE
    INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ff_purchase_complete();
CREATE TRIGGER ff_purchase_child BEFORE INSERT ON purchase_schedule_slots FOR EACH ROW EXECUTE
    FUNCTION ff_purchase_child();
CREATE TRIGGER ff_purchase_child BEFORE INSERT ON purchase_preferences FOR EACH ROW EXECUTE
    FUNCTION ff_purchase_child();
CREATE TRIGGER ff_session_guard BEFORE INSERT OR UPDATE OR DELETE ON training_sessions FOR EACH
    ROW EXECUTE FUNCTION ff_session_guard();
CREATE TRIGGER ff_acknowledgement BEFORE INSERT ON acknowledgements FOR EACH ROW EXECUTE FUNCTION
    ff_acknowledgement();
CREATE CONSTRAINT TRIGGER ff_completion AFTER INSERT OR UPDATE ON training_sessions DEFERRABLE
    INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ff_completion();
CREATE CONSTRAINT TRIGGER ff_completion AFTER INSERT ON acknowledgements DEFERRABLE INITIALLY
    DEFERRED FOR EACH ROW EXECUTE FUNCTION ff_completion();
CREATE CONSTRAINT TRIGGER ff_completion AFTER INSERT ON credit_debits DEFERRABLE INITIALLY
    DEFERRED FOR EACH ROW EXECUTE FUNCTION ff_completion();
CREATE TRIGGER ff_request_guard BEFORE UPDATE ON change_requests FOR EACH ROW EXECUTE FUNCTION
    ff_request_guard();
CREATE TRIGGER ff_request_slot BEFORE INSERT ON request_slots FOR EACH ROW EXECUTE FUNCTION
    ff_request_slot();
CREATE CONSTRAINT TRIGGER ff_request_history AFTER INSERT OR UPDATE ON change_requests DEFERRABLE
    INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ff_request_history();
CREATE CONSTRAINT TRIGGER ff_request_history AFTER INSERT ON request_events DEFERRABLE INITIALLY
    DEFERRED FOR EACH ROW EXECUTE FUNCTION ff_request_history();
CREATE TRIGGER ff_pay_line BEFORE INSERT ON remuneration_lines FOR EACH ROW EXECUTE FUNCTION
    ff_pay_line();
CREATE CONSTRAINT TRIGGER ff_pay_totals AFTER INSERT ON remuneration_approvals DEFERRABLE
    INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ff_pay_totals();
CREATE CONSTRAINT TRIGGER ff_pay_totals AFTER INSERT ON remuneration_lines DEFERRABLE INITIALLY
    DEFERRED FOR EACH ROW EXECUTE FUNCTION ff_pay_totals();
CREATE TRIGGER ff_media_scope BEFORE INSERT OR UPDATE ON media_assets FOR EACH ROW EXECUTE
    FUNCTION ff_media_scope();
CREATE TRIGGER ff_template_revision BEFORE INSERT ON package_template_revisions FOR EACH ROW
    EXECUTE FUNCTION ff_template_revision();
CREATE TRIGGER ff_lifecycle_event BEFORE INSERT ON lifecycle_events FOR EACH ROW EXECUTE FUNCTION
    ff_lifecycle_event();
CREATE CONSTRAINT TRIGGER ff_lifecycle_state AFTER UPDATE ON clients DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION ff_lifecycle_state();
CREATE CONSTRAINT TRIGGER ff_lifecycle_state AFTER UPDATE ON package_purchases DEFERRABLE
    INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ff_lifecycle_state();
"""

DOWNGRADE_SQL = r"""
DO $$ BEGIN IF EXISTS (SELECT 1 FROM content_entries) OR EXISTS (SELECT 1 FROM staff_users) OR
    EXISTS (SELECT 1 FROM package_templates) OR EXISTS (SELECT 1 FROM exercises) OR EXISTS (SELECT
    1 FROM staff_identities) OR EXISTS (SELECT 1 FROM trainers) OR EXISTS (SELECT 1 FROM
    package_template_revisions) OR EXISTS (SELECT 1 FROM remuneration_approvals) OR EXISTS (SELECT
    1 FROM trainer_availability) OR EXISTS (SELECT 1 FROM clients) OR EXISTS (SELECT 1 FROM
    client_people) OR EXISTS (SELECT 1 FROM package_purchases) OR EXISTS (SELECT 1 FROM
    assignment_events) OR EXISTS (SELECT 1 FROM report_audit) OR EXISTS (SELECT 1 FROM
    lifecycle_events) OR EXISTS (SELECT 1 FROM purchase_schedule_slots) OR EXISTS (SELECT 1 FROM
    purchase_preferences) OR EXISTS (SELECT 1 FROM training_sessions) OR EXISTS (SELECT 1 FROM
    change_requests) OR EXISTS (SELECT 1 FROM session_events) OR EXISTS (SELECT 1 FROM
    media_assets) OR EXISTS (SELECT 1 FROM exercise_plan_items) OR EXISTS (SELECT 1 FROM
    acknowledgements) OR EXISTS (SELECT 1 FROM credit_debits) OR EXISTS (SELECT 1 FROM
    assignment_changes) OR EXISTS (SELECT 1 FROM request_slots) OR EXISTS (SELECT 1 FROM
    request_events) OR EXISTS (SELECT 1 FROM messages) OR EXISTS (SELECT 1 FROM
    remuneration_lines) OR EXISTS (SELECT 1 FROM media_deletions) OR EXISTS (SELECT 1 FROM
    exercise_results) OR EXISTS (SELECT 1 FROM message_receipts) OR EXISTS (SELECT 1 FROM
    exercise_result_revisions) THEN RAISE EXCEPTION
    'M5.2 downgrade refused: domain data exists; restore a reviewed backup instead'; END IF; END $$;
ALTER TABLE clients DROP CONSTRAINT fk_clients_lifecycle_event_id_lifecycle_events;
ALTER TABLE exercises DROP CONSTRAINT fk_exercises_media_id_media_assets;
ALTER TABLE package_purchases DROP CONSTRAINT
    fk_package_purchases_lifecycle_event_id_lifecycle_events;
DROP TABLE exercise_result_revisions;
DROP TABLE message_receipts;
DROP TABLE exercise_results;
DROP TABLE media_deletions;
DROP TABLE remuneration_lines;
DROP TABLE messages;
DROP TABLE request_events;
DROP TABLE request_slots;
DROP TABLE assignment_changes;
DROP TABLE credit_debits;
DROP TABLE acknowledgements;
DROP TABLE exercise_plan_items;
DROP TABLE media_assets;
DROP TABLE session_events;
DROP TABLE change_requests;
DROP TABLE training_sessions;
DROP TABLE purchase_preferences;
DROP TABLE purchase_schedule_slots;
DROP TABLE lifecycle_events;
DROP TABLE report_audit;
DROP TABLE assignment_events;
DROP TABLE package_purchases;
DROP TABLE client_people;
DROP TABLE clients;
DROP TABLE trainer_availability;
DROP TABLE remuneration_approvals;
DROP TABLE package_template_revisions;
DROP TABLE trainers;
DROP TABLE staff_identities;
DROP TABLE exercises;
DROP TABLE package_templates;
DROP TABLE staff_users;
DROP TABLE content_entries;
DROP FUNCTION ff_immutable();
DROP FUNCTION ff_version();
DROP FUNCTION ff_preserve_fields();
DROP FUNCTION ff_actor();
DROP FUNCTION ff_birth();
DROP FUNCTION ff_people_count();
DROP FUNCTION ff_purchase_insert();
DROP FUNCTION ff_purchase_complete();
DROP FUNCTION ff_purchase_child();
DROP FUNCTION ff_session_guard();
DROP FUNCTION ff_acknowledgement();
DROP FUNCTION ff_completion();
DROP FUNCTION ff_request_guard();
DROP FUNCTION ff_request_slot();
DROP FUNCTION ff_request_history();
DROP FUNCTION ff_pay_line();
DROP FUNCTION ff_pay_totals();
DROP FUNCTION ff_media_scope();
DROP FUNCTION ff_template_revision();
DROP FUNCTION ff_lifecycle_event();
DROP FUNCTION ff_lifecycle_state();
"""
