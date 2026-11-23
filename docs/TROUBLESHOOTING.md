# Troubleshooting — Zabbix APM / Nginx Proxy Manager

## Il Collector non parte: `permission denied` su `/etc/otelcol/config.yaml`

Il file `collector.yaml` deve essere leggibile dall'UID del container (predefinito `10001:10001`).

```bash
ls -l collector.yaml
chmod 644 collector.yaml
docker compose up -d --force-recreate
```

Su filesystem con ACL, verificare anche permessi ACL e directory antenate. Se non basta, provare a usare temporaneamente UID `0:0` con `OTEL_COLLECTOR_UID=0` e `OTEL_COLLECTOR_GID=0` nel `.env` (con consapevolezza dei rischi).

## Nessun dato nei log NPM

Controllare il bind mount e l'accesso al file dalla stessa identita' con cui gira il Collector. `start_at: end` significa che occorrono **nuove** righe nei log dopo l'avvio.

```bash
docker compose config
docker inspect npm-otel-collector \
  --format '{{range .Mounts}}{{println .Source "->" .Destination}}{{end}}'
docker compose logs --since=10m otel-collector
```

Se la directory e' errata, correggere `NPM_LOG_DIR` e ricreare il container.

## Le metriche non compaiono in Zabbix / ClickHouse

Verificare prima la raggiungibilita' del Proxy Zabbix APM (TCP 4317) dal sistema Docker, poi che il Proxy abbia `StartAPMCollector=1` e la raccolta abilitata nel frontend Zabbix. I messaggi del Collector devono essere privi di errori OTLP (`Unauthenticated`, `Unavailable`, `deadline exceeded` ecc.).

Controllare direttamente ClickHouse usando le query in `clickhouse/verification_queries.sql`; le metriche `npm.http.responses.4xx`/`5xx` possono mancare se non ci sono errori reali. Prima controllare `npm.http.requests`.

## `host.name` o ambiente risultano vuoti

Controllare che `docker-compose.yaml` passi tutte le variabili in `environment:` e che il Collector usi `${env:OTEL_HOST_NAME}` e `${env:OTEL_ENVIRONMENT}`. Un `.env` usato per sostituire i campi Compose **non** equivale a `environment:` del container.

```bash
docker compose config | grep -A5 'environment:'
```

## La discovery host funziona ma la discovery proxy restituisce `[]`

- Generare traffico su un proxy host attivo.
- Cercare `npm.http.requests` in `otel_metrics_sum`.
- Controllare che `ResourceAttributes['host.name']` sia identico al campo **Host name tecnico** in Zabbix.
- Impostare `{$NPM.CH.URL}`, `{$NPM.CH.DATABASE}`, `{$NPM.CH.USER}` e `{$NPM.CH.PASSWORD}` (Secret text) nel template/host.
- Controllare che l'utente readonly abbia `SELECT` su `<db>.otel_metrics_sum`.
- Verificare che Zabbix Server/Proxy (non solo il browser) raggiunga ClickHouse via 8123 o HTTPS.

Una LLD basata sui dati osservati non scopre proxy host senza traffico; i domini possono apparire come `proxy-host-ID` se `npm.http.host_requests` non e' presente.

## `npm.http.unparsed` aumenta

Il formato dei log potrebbe differire dallo standard NPM. Esempio del formato atteso:

```text
[24/Nov/2026:10:15:00 +0000] - 200 200 - GET https example.org "/path" [Client 192.0.2.10]
```

Il terzo valore di status dopo timestamp/cache/upstream e' lo status verso il client. Adeguare l'espressione regolare nel blocco `operators` di `collector.yaml` e riavviare.

## Trigger e percentuali non corrispondono al traffico

I contatori sono **Delta**. Zabbix esegue query su bucket temporali e crea item al minuto. Eventuali disallineamenti di timestamp, intervalli mancanti e ritardi di consegna OTLP possono causare discrepanze nei conteggi su 5 minuti. Verificare NTP e granularita' prima di modificare le soglie.

## Import del template

Fare backup dell'export precedente, usare **Update existing**, disabilitare **Delete missing** e controllare le macro, specialmente la secret `{$NPM.CH.PASSWORD}`. La dashboard puo' richiedere aggiustamenti nella propria versione esatta di Zabbix 8.0.

## Le query funzionano ma la sezione APM Logs e' vuota

I log e le metriche percorrono pipeline distinte; verificare le righe in `otel_logs` senza filtro e i log del Proxy Zabbix. Le metriche corrette non dimostrano che la pipeline Logs funzioni. Attenzione: i log possono contenere dati sensibili.
