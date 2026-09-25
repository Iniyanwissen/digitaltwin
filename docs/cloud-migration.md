# Cloud Migration (Deferred): Azure → Snowflake

> Status: DESIGN ONLY, not in MVP. Start after Phase 7 when the local pipeline is stable.
> Principle: the move is an **adapter swap + infrastructure**, not a rewrite. Engine, processor logic, event contracts and dbt models stay the same.

---

## 1. Target flow

```
simulation-engine ──EventPublisher(EventHubs)──▶ Azure Event Hubs (Kafka-compatible endpoint)
                                                   │
                         event-processor (consumer group "state") ──▶ Redis (live state, unchanged)
                                                   │
                  archiver (consumer group "archive") ──▶ ADLS Gen2  raw/events/year=…/hour=…/event_type=…/part-*.jsonl.gz
                                                   │  BlobCreated
                                         Event Grid ──▶ Storage Queue
                                                   │
                                      Snowflake notification integration
                                                   │
                                    Snowpipe (AUTO_INGEST) ──▶ RAW.RAW_EVENTS (VARIANT + metadata)
                                                   │
                           Dynamic Tables (STAGING/CORE, TARGET_LAG) + dbt-snowflake (marts)
                                                   │
                                   API analytics endpoints (WarehouseClient: Snowflake)
PostgreSQL master + mock SaaS ──loaders (ADF / pipeline-runner)──▶ RAW master/SaaS tables
```

Entries, exits, internal area access, room check-ins, logins and sensor movements all arrive through the same path, so Snowflake reflects movement through floors, areas and rooms with ~1–2 minute latency.

---

## 2. Adapter mapping

| Interface | Local | Cloud |
|---|---|---|
| EventPublisher / EventConsumer | Redis Streams | Event Hubs (Kafka protocol, `aiokafka` or `azure-eventhub`) |
| RawArchiveWriter | local filesystem | ADLS Gen2 (`azure-storage-file-datalake`), same partitioning, gzip |
| WarehouseClient | DuckDB | Snowflake (`snowflake-connector-python`) |
| dbt adapter | dbt-duckdb | dbt-snowflake |
| Secrets | `.env` | Key Vault + managed identity |

Topic per stream group (`ev.access`, `ev.workspace`, `ev.occupancy`, `ev.environment`, `ev.system`, `ev.truth`), partition key = `entity_id` for per-entity ordering.

---

## 3. Snowflake setup (sketch)

```sql
CREATE STORAGE INTEGRATION adls_raw_int
  TYPE = EXTERNAL_STAGE STORAGE_PROVIDER = 'AZURE' ENABLED = TRUE
  AZURE_TENANT_ID = '<tenant>' STORAGE_ALLOWED_LOCATIONS = ('azure://<account>.blob.core.windows.net/raw/');

CREATE NOTIFICATION INTEGRATION adls_raw_notify
  ENABLED = TRUE TYPE = QUEUE NOTIFICATION_PROVIDER = AZURE_STORAGE_QUEUE
  AZURE_STORAGE_QUEUE_PRIMARY_URI = 'https://<account>.queue.core.windows.net/snowpipe-raw'
  AZURE_TENANT_ID = '<tenant>';

CREATE FILE FORMAT raw.jsonl TYPE = JSON STRIP_OUTER_ARRAY = FALSE COMPRESSION = AUTO;
CREATE STAGE raw.events_stage URL = 'azure://<account>.blob.core.windows.net/raw/events/'
  STORAGE_INTEGRATION = adls_raw_int FILE_FORMAT = raw.jsonl;

CREATE TABLE raw.raw_events (
  event VARIANT, file_name STRING, file_row NUMBER, loaded_at TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP());

CREATE PIPE raw.events_pipe AUTO_INGEST = TRUE INTEGRATION = 'ADLS_RAW_NOTIFY' AS
  COPY INTO raw.raw_events (event, file_name, file_row)
  FROM (SELECT $1, METADATA$FILENAME, METADATA$FILE_ROW_NUMBER FROM @raw.events_stage);
```

Near-real-time layer (examples):

```sql
CREATE DYNAMIC TABLE staging.stg_access TARGET_LAG = '1 minute' WAREHOUSE = wh_xs AS
SELECT event:event_id::string event_id, event:event_type::string event_type,
       event:event_time::timestamp_tz event_time, event:entity_id::string employee_id,
       event:payload:reader_type::string reader_type, event:payload:area_id::string area_id,
       event:simulation_run_id::string run_id
FROM raw.raw_events
WHERE event:event_type::string IN ('ACCESS_IN','ACCESS_OUT','AREA_ACCESS','ROOM_CHECK_IN')
QUALIFY ROW_NUMBER() OVER (PARTITION BY run_id, event_id ORDER BY loaded_at) = 1;
```

Heavier facts/marts stay in dbt (scheduled), or become Dynamic Tables with `TARGET_LAG = '5 minutes'` where freshness matters.

---

## 4. File sizing and cost

- The archiver rolls files every **60 s or 100 MB**, gzip. Smaller files lower latency but each file adds Snowpipe per-file overhead; at medium scale that is ~1,440 files/day per event group — acceptable. Consolidate groups if cost matters.
- Dedup stays in STAGING (`QUALIFY` on `(run_id, event_id)`), because both Event Hubs and Snowpipe are at-least-once.
- Upgrade path for seconds-level latency: Snowflake Kafka connector with Snowpipe Streaming reading directly from Event Hubs (Kafka endpoint).

---

## 5. Phases

| Phase | Scope | Done when |
|---|---|---|
| C1 | Event Hubs + ADLS adapters, archiver service, Terraform/Bicep for EH, ADLS, Event Grid, Storage Queue | Live run in Azure; files land partitioned; local mode still works via config |
| C2 | Snowflake integrations, stage, pipe, RAW tables, dbt-snowflake target, master/SaaS loaders | Same reconciliation tests as Phase 8A pass on Snowflake |
| C3 | Dynamic Tables for live-ish marts, API `WarehouseClient` switch, cost dashboard | Analytics pages served from Snowflake; lag < 2 min |

Local mode must remain the default for development (`APP_MODE=local`).
