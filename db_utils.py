import time 
import logging
from contextlib import contextmanager
from datetime import datetime, timezone
import psycopg2
import requests
import config



logger = logging.getLogger(__name__)



def get_connection():
    return psycopg2.connect(**config.DB_CONFIG)

@contextmanager
def db_transaction():
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                yield conn, cur 
    finally:
        conn.close()



_SESSION = None
def _get_session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
        _SESSION.headers.update({
            "Authorization": f"Bearer {config.TMDB_API_TOKEN}",
            "accept": "application/json",
        })
    return _SESSION


def tmdb_get(path: str, params: dict = None) -> dict | list | None:
    url = config.TMDB_BASE_URL + path
    try:
        resp = _get_session().get(url, params=params, timeout=15)
        resp.raise_for_status()
        time.sleep(config.API_DELAY_SECONDS)
        return resp.json()
    except requests.HTTPError as e:
        logger.error("TMDb HTTP error %s for %s: %s", resp.status_code, url, e)
        return None
    except Exception as e:
        logger.error("TMDb request failed for %s: %s", url, e)
        return None



class ETLLogger:
    def __init__(self, endpoint: str, tmdb_id: int = None, media_type: str = None):
        self.endpoint       = endpoint
        self.tmdb_id        = tmdb_id
        self.media_type     = media_type
        self.started_at     = datetime.now(timezone.utc)
        self.log_id         = None

    def start(self):
        if not config.ENABLE_ETL_LOG:
            return
        sql = """
            INSERT INTO ETL_Log (endpoint, tmdb_id, media_type, status,
                                 records_processed, started_at)
            VALUES (%s, %s, %s, 'partial', 0, %s)
            RETURNING log_id
        """
        try: 
            with db_transaction() as (conn, cur):
                cur.execute(sql, (self.endpoint, self.tmdb_id, self.media_type, self.started_at))
                self.log_id = cur.fetchone()[0]
        except Exception as e:
            logger.warning("ETLLogger.start failed: %s", e)
    
    def finish(self, status: str, records: int = 0, error: str = None):
        if not config.ENABLE_ETL_LOG or self.log_id is None:
            return 
        sql = """
            UPDATE ETL_Log
            SET status = %s, records_processed = %s, error_message = %s, finished_at = %s
            WHERE log_id = %s
        """

        try:
            with db_transaction() as (conn, cur):
                cur.execute(sql, (status, records, error , datetime.now(timezone.utc), self.log_id))
        except Exception as e:
            logger.warning("ETLLogger.finish failed: %s", e)

    

def load_dept_job_maps(conn) -> tuple [dict, dict]:
    with conn.cursor() as cur:
        cur.execute("SELECT department_id, department_name FROM Department")
        dept_map = {row[1]: row[0] for row in cur.fetchall()}

        cur.execute("""
            SELECT j.job_id, d.department_name, j.job_name
            FROM Job j
            JOIN Department d ON d.department_id = j.department_id
        """)

        job_map = {(row[1], row[2]): row[0] for row in cur.fetchall()}
    return dept_map, job_map




def load_cert_map(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT cert_std_id, iso_3166_1, certification, media_type
            FROM   Certification_Standard
        """)
        return {(r[1], r[2], r[3]): r[0] for r in cur.fetchall()}



def load_provider_map(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT provider_id, tmdb_provider_id FROM Watch_Provider")
        return {r[1]: r[0] for r in cur.fetchall()}


def load_genre_map(conn) -> dict:
    """
    Returns {(tmdb_id, media_type): genre_id}. genre_id is now a surrogate
    key (auto-increment), separate from TMDb's own genre id, since movie
    and TV genres can share a tmdb_id but are distinct rows.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT genre_id, tmdb_id, media_type FROM Genre")
        return {(r[1], r[2]): r[0] for r in cur.fetchall()}