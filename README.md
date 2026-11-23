# Nginx Proxy Manager APM for Zabbix 8

Raccolta delle metriche HTTP e dei log di **Nginx Proxy Manager (NPM)** tramite **OpenTelemetry Collector Contrib** e visualizzazione in **Zabbix 8 APM** usando **ClickHouse**.

Il progetto fornisce **un solo servizio Docker Compose: il Collector**. Non avvia Nginx Proxy Manager, Zabbix, ClickHouse o altri componenti. Puo' essere usato su piu' host con lo stesso template Zabbix, cambiando soltanto il file `.env` e, se necessario, i permessi dei log.

## Architettura

```text
Nginx Proxy Manager (access/error log in /data/logs)
        |
        | bind mount in sola lettura
        v
OpenTelemetry Collector Contrib 0.165.0
        |  file_log -> regex_parser -> count connector
        |  log e metriche via OTLP/gRPC
        v
Zabbix Proxy 8 APM (TCP/4317)
        |
        v
ClickHouse (database OpenTelemetry)
        |
        +--> Zabbix 8 APM: Metrics / Logs
        +--> Zabbix 8: LLD / item / trigger / dashboard
```

**Ambito:** questo progetto produce **metriche e log**, non trace distribuiti delle richieste interne di NPM. Il nome del dominio in discovery e' l'header HTTP `Host` piu' osservato, **non** il dominio configurato ufficialmente in NPM.

## Requisiti

- **Nginx Proxy Manager** con file di access log `proxy-host-<id>_access.log` ed error log `proxy-host-<id>_error.log`, solitamente nella directory `/data/logs` all'interno del container NPM.
- **Docker Engine** con plugin `docker compose`, sul sistema che puo' leggere i file log NPM.
- **Zabbix Server/frontend 8.0** e **Zabbix Proxy 8 APM** configurato per ricevere OTLP/gRPC sulla porta TCP `4317`.
- **ClickHouse compatibile con Zabbix 8.0**, con schema OpenTelemetry creato dagli script ufficiali Zabbix. Per APM e' richiesta **ClickHouse >= 26.8.17.4** nell'intervallo supportato **26.3–26.9**; in pratica scegliere una release **26.8.x** o **26.9.x** compatibile.
- Sorgente globale **Administration → Data source → APM** configurata sul frontend Zabbix; accesso SQL/HTTP a ClickHouse disponibile al server o proxy che esegue le discovery.

Questo repository **non** comprende la procedura di installazione di Zabbix/ClickHouse: usare la [guida APM ufficiale Zabbix](https://www.zabbix.com/documentation/8.0/en/manual/installation/guides/more/monitor_opentelemetry) per quella infrastruttura.

## Struttura

```text
.
├── README.md
├── LICENSE
├── .env.example
├── .gitignore
├── collector.yaml
├── docker-compose.yaml
├── zabbix/
│   └── zabbix_npm_apm_template.yaml
├── clickhouse/
│   ├── create_discovery_user.sql
│   └── verification_queries.sql
├── docs/
│   └── TROUBLESHOOTING.md
├── tests/
│   └── test_project.py
├── requirements-dev.txt
└── .github/workflows/validate.yml
```

## Avvio del Collector

### 1. Individuare la directory dei log

Verificare la directory **sul sistema che esegue Compose**, non il percorso interno al container NPM. Se NPM gira in Docker, ad esempio:

```bash
docker inspect nome-container-npm \
  --format '{{range .Mounts}}{{println .Source "->" .Destination}}{{end}}'
```

Individuare il bind mount associato a `/data`, quindi utilizzare la sottodirectory `logs` di quel mount come `NPM_LOG_DIR`.

### 2. Configurare `.env`

```bash
cp .env.example .env
```

Aprire `.env` e personalizzare:

| Variabile | Descrizione |
|---|---|
| `NPM_LOG_DIR` | Percorso assoluto dei log NPM sull'host Docker. |
| `ZABBIX_OTLP_ENDPOINT` | Host/IP del **Proxy Zabbix APM**, porta `4317`; non e' l'indirizzo di Zabbix Server se su una macchina diversa. |
| `OTEL_HOST_NAME` | **Host name tecnico** del corrispondente host in Zabbix (esempio: `proxy-manager-01`). |
| `OTEL_ENVIRONMENT` | Etichetta dell'ambiente (esempio: `production`, `lab`). |
| `OTEL_COLLECTOR_UID` / `OTEL_COLLECTOR_GID` | Identita' Linux che legge i log. Default `10001:10001`; impostare `0:0` **solo se necessario** per restrizioni ACL. |

**Importante:** il file `.env` viene letto da Docker Compose, ma **non** e' automaticamente disponibile come ambiente del processo nel container. Il `docker-compose.yaml` di questo progetto passa esplicitamente `OTEL_HOST_NAME`, `OTEL_ENVIRONMENT` e `ZABBIX_OTLP_ENDPOINT` al Collector; `collector.yaml` usa `${env:NOME_VARIABILE}` per espanderle.

Per un nuovo host occorre soltanto una copia dei due YAML e un `.env` personalizzato. **Non modificare** i nomi degli attributi `service.name`, `deployment.environment.name` e `host.name`.

### 3. Verificare e avviare

```bash
# Il comando stampa la configurazione Compose risultante, non i contenuti di collector.yaml.
docker compose config

docker compose up -d

docker compose ps
docker compose logs --tail=100 otel-collector
```

Il Collector legge **solo i nuovi record** dopo il primo avvio (`start_at: end`). Generare traffico su un dominio gestito da NPM e verificare l'arrivo delle metriche.

### Permessi dei file

I log sono montati `:ro` (sola lettura). L'immagine Collector usa normalmente un UID non privilegiato. Se il sistema applica ACL che impediscono la lettura, correggere i permessi del percorso; come alternativa esplicita, modificare **solo nel proprio `.env`**:

```dotenv
OTEL_COLLECTOR_UID=0
OTEL_COLLECTOR_GID=0
```

Il container come `root` aumenta la superficie di rischio, anche con bind mount in sola lettura. Non usare `chmod -R 777`.

## Preparazione di ClickHouse per la discovery

La raccolta OTLP e l'archiviazione APM devono gia' essere configurate. Il nome del database varia da installazione a installazione; negli esempi e' `otel`.

La seconda LLD interroga via HTTP la tabella `otel_metrics_sum` per identificare i file `proxy-host-ID` e il dominio HTTP piu' osservato. Creare un utente **sola lettura** con i comandi in [`clickhouse/create_discovery_user.sql`](clickhouse/create_discovery_user.sql). **Sostituire la password segnaposto e il nome del database prima di eseguire lo script**.

Il server/proxy Zabbix che esegue la regola Script deve raggiungere ClickHouse via HTTP(S); limitare l'accesso di rete a quella sorgente.

## Importare il template Zabbix

1. In **Data collection → Templates → Import**, selezionare [`zabbix/zabbix_npm_apm_template.yaml`](zabbix/zabbix_npm_apm_template.yaml).
2. Per aggiornare una versione precedente, usare **Update existing** e mantenere **Delete missing** disattivato. Il template preserva UUID e chiavi della precedente versione.
3. Aprire **Macros** del template e configurare:

   | Macro | Valore |
   |---|---|
   | `{$NPM.CH.URL}` | `http://<CLICKHOUSE_HOST>:8123` oppure HTTPS. |
   | `{$NPM.CH.DATABASE}` | Nome del database con lo schema OTEL, ad esempio `otel`. |
   | `{$NPM.CH.USER}` | `zbx_npm_discovery` o utente readonly equivalente. |
   | `{$NPM.CH.PASSWORD}` | **Creare manualmente come `Secret text`**, usando la password dell'utente readonly; non e' nel file YAML. |
   | `{$NPM.5XX.PCT.WARN}` | `10` = soglia percentuale 5xx. |
   | `{$NPM.5XX.MIN_REQUESTS}` | `30` = richieste minime negli ultimi 5 minuti. |
   | `{$NPM.5XX.MIN_ERRORS}` | `5` = errori 5xx minimi negli ultimi 5 minuti. |
   | `{$NPM.5XX.ABS.CRIT}` | `50` = errori 5xx in 5 minuti per trigger High. |

   **Nota per aggiornamenti:** se una macro segreta e' gia' definita, conservarla e verificarne il valore dopo l'import. **Non caricare su Git password o token reali.**

4. Associare il template a ciascun host Zabbix che rappresenta un'installazione NPM. **Il campo Host name tecnico deve essere identico a `OTEL_HOST_NAME`** sul Collector di quell'installazione.
5. Eseguire **Host Discovery** e **Proxy hosts discovery** (LLD di tipo Script), poi controllare gli item creati e **NPM APM - Overview**.

### Perche' servono due discovery

- **Host Discovery**: converte `{HOST.HOST}` in `{#ZBX.HOST}`. In questo modo i prototipi filtrano `ResourceAttributes['host.name'] = {#ZBX.HOST}`, automaticamente per ogni host a cui e' collegato il template.
- **Proxy hosts discovery**: legge `log.file.name` da ClickHouse, scopre ogni `proxy-host-<id>_access.log` e genera `{#NPM.ID}`, `{#NPM.FILE}`, `{#NPM.DOMAIN}`; il dominio e' l'HTTP Host prevalente negli ultimi sette giorni.

Gli item restano identificati dall'**ID** del proxy: il cambiamento del nome visibile non cambia la chiave storica. Un proxy che **non genera richieste** non sara' scoperto da questa LLD; le risorse perse non sono eliminate automaticamente nella configurazione fornita.

## Metriche e alert

Metriche generate a partire dagli access log:

| Metric name | Descrizione |
|---|---|
| `npm.http.requests` | Totale accessi HTTP, anche se il parser non riconosce una riga. |
| `npm.http.responses.2xx` | Risposte HTTP 2xx restituite al client. |
| `npm.http.responses.3xx` | Risposte HTTP 3xx. |
| `npm.http.responses.4xx` | Risposte HTTP 4xx. |
| `npm.http.responses.5xx` | Risposte HTTP 5xx. |
| `npm.http.unparsed` | Log di accesso non riconosciuti dalla regex. |
| `npm.http.host_requests` | Volume per `log.file.name` e HTTP `Host`, usato dalla discovery per il nome del proxy. |

Le metriche sono **contatori Delta**: per calcolare il totale delle richieste in un intervallo, aggregare `sum(Value)`, **non** contare le righe di ClickHouse.

Il template contiene item per host e per proxy-host, percentuali 4xx/5xx su 5 minuti, dashboard host specifica e due trigger per proxy-host:

- **Warning:** percentuale 5xx oltre soglia, con volume minimo di richieste e di errori.
- **High:** numero assoluto di 5xx nei cinque minuti oltre la soglia.

Una metrica `0` significa che non sono stati osservati record nel periodo: **non equivale a un controllo di disponibilita'**. Per la disponibilita' usare verifiche HTTP/TCP Zabbix indipendenti.

## Test di end-to-end

```bash
# Sul sistema con il Collector
docker compose logs --tail=100 otel-collector

# Query su ClickHouse (sostituire database e host tecnico)
clickhouse-client --query "
SELECT MetricName, ResourceAttributes['host.name'] AS host,
       Attributes['log.file.name'] AS log_file, sum(Value) AS hits
FROM otel.otel_metrics_sum
WHERE ServiceName='nginx-proxy-manager'
  AND ResourceAttributes['host.name']='proxy-manager-01'
  AND TimeUnix >= now() - INTERVAL 15 MINUTE
GROUP BY MetricName, host, log_file
ORDER BY MetricName, log_file
"
```

Altri esempi: [`clickhouse/verification_queries.sql`](clickhouse/verification_queries.sql).

Se la LLD non trova proxy, controllare che ci siano nuove metriche `npm.http.requests` e che il nome host corrisponda; consultare [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md).

## Sicurezza, limiti e privacy

- `tls.insecure: true` nel Collector abilita **OTLP/gRPC non cifrato**; usare solo in una rete controllata. Configurare TLS/mTLS dove richiesto.
- I **log Nginx possono contenere indirizzi IP, URI e query string con token**. Limitare la retention e l'accesso al database. I log vengono esportati nella pipeline OTLP; valutare filtraggio o redazione prima dell'uso in produzione.
- L'header HTTP `Host` e' controllabile dal client: la metrica `npm.http.host_requests` puo' produrre **elevata cardinalita'** o mostrare un dominio non canonico. Per proxy pubblici non fidati, disabilitare questa metrica (la LLD conserva il fallback `proxy-host-ID`), oppure creare regole di allowlist specifiche.
- Il progetto richiede il formato dei log predefinito NPM in cui il **terzo status** e' il codice HTTP verso il client. Formati personalizzati richiedono di adattare `regex_parser`.
- Nessun componente di questo progetto verifica certificati TLS o health check degli upstream NPM. Non si tratta di tracing distribuito end-to-end.
- Il nome database `otel` e' solo un esempio: sceglierne uno coerente in schema ClickHouse, macro Zabbix e query.
- Questo template deriva da un export Zabbix 8.0: **la validazione di import e dei widget deve essere eseguita in un'istanza reale**, oltre ai test statici inclusi nel repository.

## Sviluppo e verifica dei file

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m unittest discover -s tests -v

docker compose --env-file .env.example config --quiet
```

## Riferimenti

- [Zabbix 8.0 — guida APM e OpenTelemetry](https://www.zabbix.com/documentation/8.0/en/manual/installation/guides/more/monitor_opentelemetry)
- [Zabbix 8.0 — Telemetry query](https://www.zabbix.com/documentation/8.0/en/manual/config/items/itemtypes/telemetry_query)
- [Zabbix 8.0 — template YAML export/import](https://www.zabbix.com/documentation/8.0/en/manual/config/xml_export_import/templates)
- [OpenTelemetry Collector — configurazione](https://opentelemetry.io/docs/collector/configuration/)
- [OpenTelemetry Count connector](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/connector/countconnector)
- [Nginx Proxy Manager](https://nginxproxymanager.com/)

## Licenza

Codice e documentazione del repository distribuiti sotto licenza **MIT** (vedere [`LICENSE`](LICENSE)). Questo repository non comprende binari o software dei progetti Zabbix, OpenTelemetry e Nginx Proxy Manager.
