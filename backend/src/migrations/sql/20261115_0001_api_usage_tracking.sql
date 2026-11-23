CREATE TABLE IF NOT EXISTS api_usage (
    id SERIAL PRIMARY KEY,
    service VARCHAR(32) NOT NULL,
    model VARCHAR(64),
    input_tokens INT NOT NULL DEFAULT 0,
    output_tokens INT NOT NULL DEFAULT 0,
    audio_duration_seconds FLOAT NOT NULL DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_api_usage_service_created
    ON api_usage (service, created_at);
