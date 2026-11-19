-- Gateway-owned tables from specs/architecture/02_database_pgvector_and_redis_schema.md.
-- The backend initializes products before the gateway starts.
CREATE TABLE IF NOT EXISTS chat_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_fingerprint VARCHAR(128),
    state VARCHAR(16) NOT NULL DEFAULT 'ACTIVE' CHECK (state IN ('ACTIVE', 'ENDED')),
    active_filters JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    citations JSONB NOT NULL DEFAULT '[]'::jsonb,
    recommended_skus JSONB NOT NULL DEFAULT '[]'::jsonb,
    ttft_ms INTEGER,
    total_latency_ms INTEGER,
    tokens_used INTEGER,
    intent VARCHAR(30) CHECK (
        intent IN ('TECHNICAL_QA', 'PRODUCT_COMPARISON', 'PURCHASE_INTENT', 'OUT_OF_DOMAIN')
    ),
    cache_hit BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS feedback_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id UUID NOT NULL UNIQUE REFERENCES chat_messages(id) ON DELETE CASCADE,
    session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    rating VARCHAR(10) NOT NULL CHECK (rating IN ('LIKE', 'DISLIKE')),
    reason_category VARCHAR(20) CHECK (
        reason_category IN ('HALLUCINATION', 'WRONG_VOLTAGE', 'SLOW', 'OTHER')
    ),
    comment TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS checkout_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    message_id UUID REFERENCES chat_messages(id) ON DELETE SET NULL,
    product_id UUID NOT NULL REFERENCES products(id),
    sku VARCHAR(64) NOT NULL,
    recommendation_type VARCHAR(20) NOT NULL CHECK (
        recommendation_type IN ('PRIMARY', 'UPSELL', 'CROSS_SELL')
    ),
    quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
    unit_price_at_click NUMERIC(10, 2) NOT NULL,
    status VARCHAR(30) NOT NULL CHECK (status IN ('CONFIRMED', 'OUT_OF_STOCK', 'PRICE_CHANGED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session_created
    ON chat_messages (session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_checkout_events_created ON checkout_events (created_at);
