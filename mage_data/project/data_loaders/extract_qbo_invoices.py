import time
import logging
import requests
import json
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from mage_ai.data_preparation.shared.secrets import get_secret_value

if 'data_loader' not in globals():
    from mage_ai.data_preparation.decorators import data_loader

logger = logging.getLogger("qbo_pipeline")
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)



@data_loader
def execute(*args, **kwargs):

    pipeline_start = time.time()
    total_pages = 0
    total_records = 0

    logger.info("[AUTH] Starting QBO extraction")
    
    segments = args[0]
    access_token = args[1]

    if isinstance(segments, str): 
        segments = json.loads(segments)

    if isinstance(segments, dict): 
        segments = [segments]

    realm_id = get_secret_value("QBO_REALM_ID")

    base_url = f"https://sandbox-quickbooks.api.intuit.com/v3/company/{realm_id}/query"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": "text/plain"
    }

    session = requests.Session()

    retry_strategy = Retry(
        total=5,  
        backoff_factor=2,  
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST"],  
        raise_on_status=False
    )

    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)

    all_records = []

    for segment in segments:

        start = segment["window_start"]
        end = segment["window_end"]

        segment_start = time.time()
        segment_pages = 0
        segment_records = 0

        logger.info(f"[EXTRACT] Segment started -> {start} to {end}")

        start_position = 1
        page_size = 100

        while True:

            query = f"""
                SELECT * FROM Invoice 
                WHERE MetaData.LastUpdatedTime >= '{start}' 
                AND MetaData.LastUpdatedTime < '{end}'
                STARTPOSITION {start_position}
                MAXRESULTS {page_size}
            """

            print("QUERY:", query)

            try:
                response = session.post(
                    base_url,
                    headers=headers,
                    params={"query": query},
                    timeout=60
                )

            except requests.exceptions.RequestException as e:
                print("Network error:", str(e))
                raise

            if response.status_code != 200:
                logger.error(f"[QBO_API_ERROR] {response.text}")
                response.raise_for_status()

            data = response.json()

            invoices = data.get("QueryResponse", {}).get("invoicer", [])

            if isinstance(invoices, dict):
                invoices = [invoices]

            if not invoices:
                break
            
            segment_pages += 1
            total_pages += 1

            segment_records += len(invoices)
            total_records += len(invoices)

            page_number = ((start_position - 1) // page_size) + 1

            for cust in invoices:
                all_records.append({
                    "id": cust["Id"],
                    "payload": cust,
                    "window_start": start,
                    "window_end": end,
                    "page_number": page_number,
                    "page_size": page_size,
                    "request_payload": json.dumps({
                        "query": query.strip()
                    })
                })

            if len(invoices) < page_size:
                break

            start_position += page_size

        segment_duration = round(time.time() - segment_start, 2)

        logger.info(
            f"[EXTRACT_METRICS] "
            f"segment={start}->{end} | "
            f"records={segment_records} | "
            f"pages={segment_pages} | "
            f"duration={segment_duration}s"
        )
    
    total_duration = round(time.time() - pipeline_start, 2)

    logger.info(
        f"[PIPELINE_METRICS] "
        f"total_records={total_records} | "
        f"total_pages={total_pages} | "
        f"duration={total_duration}s"
    )

    print(f"Invoices extracted: {len(all_records)}")

    return all_records
