-- Backend-owned tables of specs/architecture/02_database_pgvector_and_redis_schema.md
-- (ADR-06: products, manual_chunks, product_relations, ingestion_jobs).
-- Idempotent: applied by every ingestion run.
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

CREATE TABLE IF NOT EXISTS products (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    sku VARCHAR(64) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(100) NOT NULL,
    subcategory VARCHAR(100) NOT NULL,
    brand VARCHAR(100) NOT NULL,
    price NUMERIC(10, 2) NOT NULL CHECK (price > 0),
    stock_quantity INTEGER NOT NULL DEFAULT 0 CHECK (stock_quantity >= 0),
    voltage VARCHAR(20) NOT NULL CHECK (voltage IN ('127V', '220V', 'BIVOLT', 'N/A')),
    capacity_liters NUMERIC(6, 2),
    power_watts INTEGER,
    tier_rank INTEGER NOT NULL DEFAULT 1 CHECK (tier_rank BETWEEN 1 AND 5),
    image_url TEXT NOT NULL,
    marketplace VARCHAR(30) NOT NULL DEFAULT 'AMAZON' CHECK (marketplace IN ('AMAZON', 'MERCADO_LIVRE', 'SHOPEE', 'LOJA_OFICIAL')),
    checkout_url TEXT NOT NULL,
    specs_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_products_active_stock_cat
    ON products (is_active, stock_quantity, category, subcategory, voltage);

CREATE TABLE IF NOT EXISTS manual_chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    sku VARCHAR(64) NOT NULL,
    manual_title VARCHAR(255) NOT NULL,
    page_number INTEGER NOT NULL CHECK (page_number >= 1),
    chunk_index INTEGER NOT NULL CHECK (chunk_index >= 0),
    manual_source TEXT NOT NULL,
    manual_version VARCHAR(64) NOT NULL,
    section_title VARCHAR(255),
    content TEXT NOT NULL,
    embedding vector(1536) NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (product_id, manual_source, page_number, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_manual_chunks_embedding_hnsw
    ON manual_chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
CREATE INDEX IF NOT EXISTS idx_manual_chunks_product_id ON manual_chunks (product_id);
CREATE INDEX IF NOT EXISTS idx_manual_chunks_sku ON manual_chunks (sku);

CREATE TABLE IF NOT EXISTS product_relations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    base_product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    related_product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    relation_type VARCHAR(20) NOT NULL CHECK (relation_type IN ('UPSELL', 'CROSS_SELL')),
    affinity_weight NUMERIC(4, 3) NOT NULL DEFAULT 0.800 CHECK (affinity_weight BETWEEN 0 AND 1),
    justification_template TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (base_product_id, related_product_id, relation_type)
);

CREATE TABLE IF NOT EXISTS ingestion_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID REFERENCES products(id) ON DELETE CASCADE,
    source_file TEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'RUNNING', 'INDEXED', 'FAILED', 'NEEDS_INTERVENTION')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    last_error TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_file, content_hash)
);
