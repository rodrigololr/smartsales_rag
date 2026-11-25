-- M05 tables from specs/architecture/02_database_pgvector_and_redis_schema.md.
-- chat_sessions/chat_messages come from app/db/schema.sql (applied first by the session store);
-- products is created by the backend before the gateway starts.
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
        recommendation_type IN ('PRIMARY', 'UPSELL', 'CROSS_SELL', 'OPTION')
    ),
    quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
    unit_price_at_click NUMERIC(10, 2) NOT NULL,
    status VARCHAR(30) NOT NULL CHECK (status IN ('CONFIRMED', 'OUT_OF_STOCK', 'PRICE_CHANGED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE checkout_events DROP CONSTRAINT IF EXISTS checkout_events_recommendation_type_check;
ALTER TABLE checkout_events ADD CONSTRAINT checkout_events_recommendation_type_check CHECK (
    recommendation_type IN ('PRIMARY', 'UPSELL', 'CROSS_SELL', 'OPTION')
);

CREATE INDEX IF NOT EXISTS idx_checkout_events_created ON checkout_events (created_at);
