-- TAYVORIQ V2 prototype only; intentionally not wired into any workflow.
-- PostgreSQL 15+ target. Do not apply to production without migration review,
-- transactional/fencing tests and a tested backup/restore procedure.
-- Personal secrets, signed webhook tokens and full private source material
-- must never be persisted in these public repository samples.

BEGIN;
CREATE SCHEMA IF NOT EXISTS tayvoriq_v2;
REVOKE ALL ON SCHEMA tayvoriq_v2 FROM PUBLIC;

-- Immutable approval-bound data. Use a separate progress row for transitions.
CREATE TABLE IF NOT EXISTS tayvoriq_v2.request_bindings (
    request_id                  text PRIMARY KEY,
    source_request_id           text NOT NULL UNIQUE,
    trend_id                    text NOT NULL,
    slot_date                   date NOT NULL,
    slot                       text NOT NULL CHECK (slot IN ('morning', 'evening')),
    telegram_approval_message_id bigint NOT NULL,
    approval_digest            text NOT NULL,
    source_context_hash        text NOT NULL,
    topic                      text NOT NULL,
    content_angle              text NOT NULL,
    approved_at                timestamptz NOT NULL,
    created_at                 timestamptz NOT NULL DEFAULT now(),
    UNIQUE (slot_date, slot)
);

-- No silent rebinding of an approved request. Schema-owner migrations must be
-- deliberately reviewed; application roles must not own/alter these tables.
CREATE OR REPLACE FUNCTION tayvoriq_v2.reject_binding_mutations()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'TAYVORIQ immutable request binding cannot be updated or deleted';
END $$;
DROP TRIGGER IF EXISTS trg_immutable_request_binding ON tayvoriq_v2.request_bindings;
CREATE TRIGGER trg_immutable_request_binding
BEFORE UPDATE OR DELETE ON tayvoriq_v2.request_bindings
FOR EACH ROW EXECUTE FUNCTION tayvoriq_v2.reject_binding_mutations();

CREATE TABLE IF NOT EXISTS tayvoriq_v2.request_progress (
    request_id                 text PRIMARY KEY REFERENCES tayvoriq_v2.request_bindings(request_id),
    state                      text NOT NULL DEFAULT 'APPROVED',
    last_successful_gate       text,
    active_gate                text,
    failure_class              text,
    attempt                    integer NOT NULL DEFAULT 0 CHECK (attempt >= 0),
    recovery_generation        integer NOT NULL DEFAULT 0 CHECK (recovery_generation >= 0),
    version                    bigint NOT NULL DEFAULT 0 CHECK (version >= 0),
    owner_epoch                bigint NOT NULL DEFAULT 0 CHECK (owner_epoch >= 0),
    last_progress_at           timestamptz NOT NULL DEFAULT now(),
    updated_at                 timestamptz NOT NULL DEFAULT now(),
    CHECK (state IN (
      'APPROVED', 'REQUEST_LOCKED', 'SOURCES_LOCKED', 'PREFLIGHT_PASSED',
      'PRODUCTION_RUNNING', 'RENDER_AVAILABLE', 'LOCAL_REPAIR_RUNNING',
      'MASTER_PUBLISHABLE', 'QUALITY_PASSED', 'REVIEW_READY',
      'REVIEW_DELIVERED', 'PUBLISHED', 'COMPLETED',
      'DETERMINISTIC_STOP', 'EXTERNAL_BLOCKER', 'DUPLICATE_BLOCKED',
      'RECOVERY_EXHAUSTED', 'BLOCKED'
    ))
);
CREATE INDEX IF NOT EXISTS idx_tayvoriq_v2_progress_state
    ON tayvoriq_v2.request_progress(state);

-- Unique process owner: consumers must use an atomic INSERT/UPDATE with
-- expires_at check and increment fencing_epoch on acquisition.
CREATE TABLE IF NOT EXISTS tayvoriq_v2.owner_lease (
    lease_name                 text PRIMARY KEY,
    owner_id                   text NOT NULL,
    fencing_epoch              bigint NOT NULL CHECK (fencing_epoch > 0),
    expires_at                 timestamptz NOT NULL,
    updated_at                 timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tayvoriq_v2.run_attempts (
    request_id                 text NOT NULL REFERENCES tayvoriq_v2.request_bindings(request_id),
    attempt                    integer NOT NULL CHECK (attempt > 0),
    recovery_generation        integer NOT NULL CHECK (recovery_generation >= 0),
    github_repository          text NOT NULL,
    github_run_id              bigint NOT NULL,
    studio_commit_sha          text NOT NULL,
    controller_epoch           bigint NOT NULL CHECK (controller_epoch > 0),
    started_at                 timestamptz NOT NULL DEFAULT now(),
    finished_at                timestamptz,
    status                     text NOT NULL CHECK (status IN ('DISPATCHED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED', 'UNKNOWN')),
    PRIMARY KEY (request_id, attempt),
    UNIQUE (github_repository, github_run_id)
);

-- Immutable audit evidence; a workflow exit code alone does not constitute
-- successful production, gate acceptance or Telegram delivery.
CREATE TABLE IF NOT EXISTS tayvoriq_v2.gate_receipts (
    receipt_id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id                 text NOT NULL REFERENCES tayvoriq_v2.request_bindings(request_id),
    attempt                    integer NOT NULL,
    gate_name                  text NOT NULL,
    status                     text NOT NULL CHECK (status IN ('PASS', 'FAIL')),
    evidence_sha256            text NOT NULL,
    evidence_uri               text NOT NULL,
    observed_at                timestamptz NOT NULL,
    UNIQUE (request_id, attempt, gate_name, evidence_sha256),
    FOREIGN KEY (request_id, attempt)
      REFERENCES tayvoriq_v2.run_attempts(request_id, attempt)
);

CREATE TABLE IF NOT EXISTS tayvoriq_v2.checkpoint_receipts (
    checkpoint_id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id                 text NOT NULL REFERENCES tayvoriq_v2.request_bindings(request_id),
    attempt                    integer NOT NULL,
    artifact_kind              text NOT NULL,
    artifact_sha256            text NOT NULL,
    artifact_uri               text NOT NULL,
    reusable                   boolean NOT NULL DEFAULT false,
    created_at                 timestamptz NOT NULL DEFAULT now(),
    UNIQUE (request_id, artifact_kind, artifact_sha256),
    FOREIGN KEY (request_id, attempt)
      REFERENCES tayvoriq_v2.run_attempts(request_id, attempt)
);

CREATE TABLE IF NOT EXISTS tayvoriq_v2.telegram_review_receipts (
    delivery_id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id                 text NOT NULL REFERENCES tayvoriq_v2.request_bindings(request_id),
    review_hash                text NOT NULL,
    master_sha256              text NOT NULL,
    telegram_chat_ref_digest   text NOT NULL,
    telegram_message_id        bigint NOT NULL,
    sent_at                    timestamptz NOT NULL,
    UNIQUE (request_id, review_hash),
    UNIQUE (telegram_chat_ref_digest, telegram_message_id)
);

-- Separate publish approval, never inferred from a review delivery.
CREATE TABLE IF NOT EXISTS tayvoriq_v2.user_publish_decisions (
    decision_id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    delivery_id                bigint NOT NULL REFERENCES tayvoriq_v2.telegram_review_receipts(delivery_id),
    decision                   text NOT NULL CHECK (decision IN ('APPROVE', 'REJECT')),
    decision_message_id        bigint NOT NULL,
    decision_digest            text NOT NULL,
    decided_at                 timestamptz NOT NULL,
    UNIQUE (delivery_id, decision_message_id)
);

CREATE TABLE IF NOT EXISTS tayvoriq_v2.platform_publish_receipts (
    publish_id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id                 text NOT NULL REFERENCES tayvoriq_v2.request_bindings(request_id),
    decision_id                bigint NOT NULL REFERENCES tayvoriq_v2.user_publish_decisions(decision_id),
    platform                   text NOT NULL CHECK (platform IN ('YOUTUBE', 'TIKTOK')),
    platform_content_id        text NOT NULL,
    published_at               timestamptz NOT NULL,
    UNIQUE (request_id, platform),
    UNIQUE (platform, platform_content_id)
);
-- Integration must verify decision='APPROVE' AND that the decision's
-- delivery belongs to the same request; cross-table integrity cannot be
-- assumed merely from individual foreign keys.

CREATE TABLE IF NOT EXISTS tayvoriq_v2.event_inbox (
    idempotency_key            text PRIMARY KEY,
    event_type                 text NOT NULL,
    request_id                 text REFERENCES tayvoriq_v2.request_bindings(request_id),
    received_at                timestamptz NOT NULL DEFAULT now(),
    payload_hash               text NOT NULL
);
CREATE TABLE IF NOT EXISTS tayvoriq_v2.command_outbox (
    command_id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    idempotency_key            text NOT NULL UNIQUE,
    request_id                 text NOT NULL REFERENCES tayvoriq_v2.request_bindings(request_id),
    command_type               text NOT NULL,
    owner_epoch                bigint NOT NULL CHECK (owner_epoch > 0),
    payload                    jsonb NOT NULL,
    status                     text NOT NULL DEFAULT 'PENDING'
                                    CHECK (status IN ('PENDING', 'IN_FLIGHT', 'CONFIRMED', 'UNKNOWN', 'FAILED')),
    created_at                 timestamptz NOT NULL DEFAULT now(),
    updated_at                 timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tayvoriq_v2_outbox_status
    ON tayvoriq_v2.command_outbox(status, created_at);

CREATE TABLE IF NOT EXISTS tayvoriq_v2.transition_events (
    event_id                   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id                 text REFERENCES tayvoriq_v2.request_bindings(request_id),
    event_type                 text NOT NULL,
    actor                      text NOT NULL,
    old_state                  text,
    new_state                  text,
    owner_epoch                bigint,
    state_version              bigint,
    observed_at                timestamptz NOT NULL DEFAULT now(),
    evidence_hash              text,
    metadata                   jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_tayvoriq_v2_event_request
    ON tayvoriq_v2.transition_events(request_id, event_id);

COMMIT;

-- REQUIRED FOLLOW-UP BEFORE USE:
-- 1. Define least-privilege runtime roles; deny application UPDATE/DELETE on
--    immutable receipts, events and approvals (admin/migration role distinct).
-- 2. Implement tested transition procedures (CAS on version + fencing_epoch).
-- 3. Implement slot-release and user approval policy; never infer acceptance.
-- 4. Add adversarial concurrent-transaction and cross-table consistency tests.
-- 5. Add outbox delivery reconciliation; avoid Telegram/YouTube duplicates.
-- 6. Verify backup/restore and retention; do not deploy this prototype alone.
