-- Query di esempio: adattare database e host tecnico.
-- La query usa SUM(Value) per aggregare contatori Delta.
SELECT
    MetricName,
    ResourceAttributes['host.name'] AS zabbix_host,
    Attributes['log.file.name'] AS npm_log,
    sum(Value) AS hits
FROM otel.otel_metrics_sum
WHERE ServiceName = 'nginx-proxy-manager'
  AND ResourceAttributes['host.name'] = 'proxy-manager-01'
  AND TimeUnix >= now() - INTERVAL 15 MINUTE
GROUP BY MetricName, zabbix_host, npm_log
ORDER BY npm_log, MetricName;

-- Domini HTTP osservati e conteggio richieste
SELECT
    Attributes['log.file.name'] AS npm_log,
    Attributes['http_host'] AS observed_host,
    sum(Value) AS hits
FROM otel.otel_metrics_sum
WHERE MetricName = 'npm.http.host_requests'
  AND TimeUnix >= now() - INTERVAL 1 HOUR
GROUP BY npm_log, observed_host
ORDER BY hits DESC;
