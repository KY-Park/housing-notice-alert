CREATE TABLE IF NOT EXISTS notices (
    id BIGSERIAL PRIMARY KEY,
    provider TEXT NOT NULL,
    region TEXT NOT NULL,
    notice_type TEXT,
    title TEXT NOT NULL,
    notice_date DATE,
    apply_start_date DATE,
    apply_end_date DATE,
    status TEXT,
    url TEXT NOT NULL,
    attachment_url TEXT,
    content_hash TEXT NOT NULL UNIQUE,
    first_seen_at TIMESTAMPTZ DEFAULT NOW(),
    notified_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_notices_provider_notice_date
    ON notices (provider, notice_date DESC);
