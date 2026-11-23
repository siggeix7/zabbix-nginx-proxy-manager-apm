-- Eseguire come amministratore ClickHouse DOPO aver creato lo schema OpenTelemetry.
-- Modificare il nome del database se non e' "otel".
-- SOSTITUIRE la stringa della password PRIMA di eseguire il file.
-- Non committare mai una copia contenente la vera password.
CREATE USER IF NOT EXISTS zbx_npm_discovery
IDENTIFIED WITH sha256_password
BY 'REPLACE_WITH_A_LONG_RANDOM_PASSWORD';

GRANT SELECT ON otel.otel_metrics_sum TO zbx_npm_discovery;
