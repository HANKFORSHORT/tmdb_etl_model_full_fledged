import logging
from tmdb_etl_model_full_fledged.etl.db_utils import tmdb_get, db_transaction, ETLLogger

logger = logging.getLogger(__name__)



def load_languages():

    etl = ETLLogger("configuration/languages", media_type = "reference")
    etl.start()

    data = tmdb_get("/configuration/languages")
    if not data: 
        etl.finish("failed", error = "API call returned None")
        return False
    
    sql = """
        INSERT INTO Language (iso_639_1, english_name, native_name)
        VALUES (%s, %s, %s)
        ON CONFLICT (iso_639_1) DO UPDATE
            SET native_name = EXCLUDED.native_name
    """

    seen_lines = set()
    rows = []
    for item in data:
        line = item.get("iso_639_1")
        if not line or line in seen_lines:
            continue
        seen_lines.add(line)
        rows.append((
            line,
            item.get("english_name") or line,
            item.get("name") or ""
        ))

    try:
        with db_transaction() as (conn, cur):
            cur.executemany(sql, rows)
        logger.info("Language: upserted %d rows", len(rows))
        etl.finish("success", records = len(rows))
        return True
    except Exception as e:
        logger.error("Language load failed: %s", e)
        etl.finish("failed", error = str(e))
        return False



def load_genres_movie():

    etl = ETLLogger("genre/movie/list", media_type = "reference")
    etl.start()

    data = tmdb_get("/genre/movie/list", params = {"language" : "en"})
    if not data or "genres" not in data:
        etl.finish("failed", error = "API call returned None or bad format")
        return False
    
    sql = """
        INSERT INTO Genre (tmdb_id, name, media_type)
        VALUES (%s, %s, 'movie')
        ON CONFLICT (tmdb_id, media_type) DO UPDATE
            SET name = EXCLUDED.name
    """

    rows = [(g["id"], g["name"]) for g in data["genres"]]

    try:
        with db_transaction() as (conn, cur):
            cur.executemany(sql, rows)
        logger.info("Genre(movie): upserted %d rows", len(rows))
        etl.finish("success", records=len(rows))
        return True
    except Exception as e:
        logger.error("Genre(movie) load failed: %s", e)
        etl.finish("failed", error=str(e))
        return False

def load_genres_tv():

    etl = ETLLogger("genre/tv/list", media_type = "reference")
    etl.start()

    data = tmdb_get("/genre/tv/list", params={"language" : "en"})
    if not data or "genres" not in data:
        etl.finish("failed", error = "API call returned None or bad format")
        return False

    sql = """
            INSERT INTO Genre (tmdb_id, name, media_type)
            VALUES (%s, %s, 'tv')
            ON CONFLICT (tmdb_id, media_type) DO UPDATE
                SET name = EXCLUDED.name
        """

    
    rows = [(g["id"], g["name"]) for g in data["genres"]]

    try:
        with db_transaction() as (conn, cur):
            cur.executemany(sql, rows)
        logger.info("Genre(tv): upserted %d rows", len(rows))
        etl.finish("success", records=len(rows))
        return True
    except Exception as e:
        logger.error("Genre(tv) load failed: %s", e)
        etl.finish("failed", error=str(e))
        return False


def load_departments_and_jobs():

    etl = ETLLogger("configuration/jobs", media_type = "reference")
    etl.start()

    data = tmdb_get("/configuration/jobs")
    if not data: 
        etl.finish("failed", error = "API call return None")
        return False
    
    dept_sql = """
        INSERT INTO Department (department_name)
        VALUES (%s)
        ON CONFLICT (department_name) DO UPDATE
            SET department_name = EXCLUDED.department_name
        RETURNING department_id, department_name
    """

    job_sql = """
        INSERT INTO Job (department_id, job_name)
        VALUES (%s, %s)
        ON CONFLICT (department_id, job_name) DO NOTHING 
    """

    total_depts = 0
    total_jobs = 0

    try:
        with db_transaction() as (conn, cur):
            for entry in data:
                dept_name = entry.get("department", "").strip()
                jobs = entry.get ("jobs", [])
                if not dept_name:
                    continue

                cur.execute(dept_sql, (dept_name,))
                row = cur.fetchone()
                if row is None:
                    cur.execute (
                        "SELECT department_id FROM Department WHERE department_name = %s", (dept_name,)
                    )
                    row = cur.fetchone()
                dept_id = row[0]
                total_depts += 1

                job_rows = [(dept_id, j.strip()) for j in jobs if j.strip()]
                cur.executemany(job_sql, job_rows)
                total_jobs += len(job_rows)

        logger.info("Department: %d | Job: %d rows processed", total_depts, total_jobs)
        etl.finish("success", records=total_depts + total_jobs)
        return True
    except Exception as e:
        logger.error("Department/Job load failed: %s", e)
        etl.finish("failed", error=str(e))
        return False




def load_certifications_movie():
    etl = ETLLogger("certification/movie/list", media_type="reference")
    etl.start()

    data = tmdb_get("/certification/movie/list")
    if not data or "certifications" not in data:
        etl.finish("failed", error="API call returned None or bad format")
        return False

    sql = """
        INSERT INTO Certification_Standard
            (iso_3166_1, certification, meaning, cert_order, media_type)
        VALUES (%s, %s, %s, %s, 'movie')
        ON CONFLICT (iso_3166_1, certification, media_type) DO UPDATE
            SET meaning     = EXCLUDED.meaning,
                cert_order  = EXCLUDED.cert_order
    """
    rows = []
    for country_code, certs in data["certifications"].items():
        if len(country_code) != 2:    
            continue                      
        for c in certs:
            raw_order = c.get("order", 0)
            cert_order = max(1, int(raw_order) + 1) if raw_order == 0 else max(1, int(raw_order))
            
            certification = (c.get("certification") or "")[:20]

            rows.append((
                country_code,
                certification, 
                c.get("meaning") or "",
                cert_order,
            ))

    try:
        with db_transaction() as (conn, cur):
            cur.executemany(sql, rows)
        logger.info("Certification_Standard(movie): upserted %d rows", len(rows))
        etl.finish("success", records=len(rows))
        return True
    except Exception as e:
        logger.error("Certification_Standard(movie): load failed: %s", e)
        etl.finish("failed", error=str(e))
        return False


def load_certifications_tv():
    etl = ETLLogger("certification/tv/list", media_type="reference")
    etl.start()

    data = tmdb_get("/certification/tv/list")
    if not data or "certifications" not in data:
        etl.finish("failed", error="API call returned None or bad format")
        return False

    sql = """
        INSERT INTO Certification_Standard
            (iso_3166_1, certification, meaning, cert_order, media_type)
        VALUES (%s, %s, %s, %s, 'tv')
        ON CONFLICT (iso_3166_1, certification, media_type) DO UPDATE
            SET meaning     = EXCLUDED.meaning,
                cert_order  = EXCLUDED.cert_order
    """
    rows = []
    for country_code, certs in data["certifications"].items():
        if len(country_code) != 2:    
            continue                      
        for c in certs:
            raw_order = c.get("order", 0)
            cert_order = max(1, int(raw_order) + 1) if raw_order == 0 else max(1, int(raw_order))
            
            certification = (c.get("certification") or "")[:20]

            rows.append((
                country_code,
                certification, 
                c.get("meaning") or "",
                cert_order,
            ))

    try:
        with db_transaction() as (conn, cur):
            cur.executemany(sql, rows)
        logger.info("Certification_Standard(tv): upserted %d rows", len(rows))
        etl.finish("success", records=len(rows))
        return True
    except Exception as e:
        logger.error("Certification_Standard(tv): load failed: %s", e)
        etl.finish("failed", error=str(e))
        return False