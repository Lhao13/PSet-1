import time
import logging
import psycopg2
from psycopg2.extras import Json, execute_values
from datetime import datetime
from mage_ai.data_preparation.shared.secrets import get_secret_value

if 'data_exporter' not in globals():
    from mage_ai.data_preparation.decorators import data_exporter


logger = logging.getLogger("qbo_pipeline")
logger.setLevel(logging.INFO)


@data_exporter
def execute(records, **kwargs):

    if not records:
        logger.info("[LOAD] No records received — skipping load.")
        return

    start_time = time.time()

    logger.info(f"[LOAD] Starting Postgres load | records={len(records)}")

    conn = psycopg2.connect(
        host=get_secret_value("PG_HOST"),
        port=get_secret_value("PG_PORT"),
        dbname=get_secret_value("PG_DB"),
        user=get_secret_value("PG_USER"),
        password=get_secret_value("PG_PASSWORD"),
    )

    try:
        cursor = conn.cursor()

        query = """
        INSERT INTO raw.qb_customers (
            id,
            payload,
            ingested_at_utc,
            extract_window_start_utc,
            extract_window_end_utc,
            page_number,
            page_size,
            request_payload
        )
        VALUES %s
        ON CONFLICT (id)
        DO UPDATE SET
            payload = EXCLUDED.payload,
            ingested_at_utc = EXCLUDED.ingested_at_utc,
            extract_window_start_utc = EXCLUDED.extract_window_start_utc,
            extract_window_end_utc = EXCLUDED.extract_window_end_utc,
            page_number = EXCLUDED.page_number,
            page_size = EXCLUDED.page_size,
            request_payload = EXCLUDED.request_payload
        RETURNING (xmax = 0) AS inserted;
        """

        values = [
            (
                r["id"],
                Json(r["payload"]),
                datetime.utcnow(),
                r["window_start"],
                r["window_end"],
                r["page_number"],
                r["page_size"],
                r["request_payload"]
            )
            for r in records
        ]

        execute_values(
            cursor,
            query,
            values,
            page_size=500
        )

        results = cursor.fetchall()

        inserted = sum(row[0] for row in results)
        updated = len(results) - inserted

        conn.commit()

        duration = round(time.time() - start_time, 2)
        conflict_rate = round((updated / len(records)) * 100, 2)

        logger.info(
            f"[LOAD_METRICS] inserted={inserted} | "
            f"updated={updated} | total={len(records)} | "
            f"conflict_rate={conflict_rate}% | "
            f"duration={duration}s"
        )

        logger.info("[LOAD] Completed successfully")

    except Exception as e:

        conn.rollback()

        logger.exception(
            "[LOAD_ERROR] Postgres load failed — transaction rolled back"
        )

        raise

    finally:
        cursor.close()
        conn.close()
