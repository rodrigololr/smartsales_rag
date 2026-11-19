-- M02-owned tables. Apply transactionally under the migration advisory lock.
CREATE TABLE IF NOT EXISTS chat_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_fingerprint VARCHAR(128),
    state VARCHAR(16) NOT NULL DEFAULT 'ACTIVE' CHECK (state IN ('ACTIVE','ENDED')),
    active_filters JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL CHECK (role IN ('user','assistant','system')),
    content TEXT NOT NULL,
    citations JSONB NOT NULL DEFAULT '[]'::jsonb,
    recommended_skus JSONB NOT NULL DEFAULT '[]'::jsonb,
    ttft_ms INTEGER, total_latency_ms INTEGER, tokens_used INTEGER,
    intent VARCHAR(30) CHECK (intent IN ('TECHNICAL_QA','PRODUCT_COMPARISON','PURCHASE_INTENT','OUT_OF_DOMAIN')),
    cache_hit BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created ON chat_messages(session_id,created_at);
CREATE TABLE IF NOT EXISTS chat_turn_requests (
    session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    client_request_id UUID NOT NULL,
    payload_hash VARCHAR(64) NOT NULL,
    message_id UUID UNIQUE REFERENCES chat_messages(id),
    status VARCHAR(16) NOT NULL CHECK (status IN ('RUNNING','COMPLETED','FAILED','EXPIRED')),
    terminal_payload JSONB,
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '24 hours'),
    PRIMARY KEY(session_id,client_request_id)
);
-- Additive migration for databases already initialized from the normative DDL.
ALTER TABLE chat_turn_requests ADD COLUMN IF NOT EXISTS reserved_message_id UUID NOT NULL DEFAULT gen_random_uuid();
ALTER TABLE chat_turn_requests ADD COLUMN IF NOT EXISTS user_message_id UUID REFERENCES chat_messages(id);
ALTER TABLE chat_turn_requests ADD COLUMN IF NOT EXISTS owner_token UUID;
ALTER TABLE chat_turn_requests ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ;
ALTER TABLE chat_turn_requests ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE chat_turn_requests ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_chat_turn_requests_session_status ON chat_turn_requests(session_id,status);

-- Preserve the public message id of terminals created with the original schema.
UPDATE chat_turn_requests SET reserved_message_id=message_id
    WHERE message_id IS NOT NULL AND reserved_message_id<>message_id;
