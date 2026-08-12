#   TMDb API  →  Collection
#             →  Movie
#             →  Movie_Genre, Movie_Country, Movie_Language, Movie_Company
#             →  Person (upsert)  →  Movie_Cast, Movie_Crew
#             →  Keyword (upsert) →  Movie_Keyword
#             →  Movie_Watch_Provider
#             →  (optional) User_Review

import logging
from db_utils import tmdb_get, ETLLogger, load_dept_job_maps, load_provider_map
import config
from etl_search import (_upsert_person_full, _upsert_person_minimal, 
                        _upsert_company, _upsert_collection)

logger = logging.getLogger(__name__)

def _load_movie_core(cur, movie_id: int):

    data = tmdb_get(f"/movie/{movie_id}", params={"language": "en-US"})
    if not data or "id" not in data:
        return False, None

    belongToCollection = data.get("belongs_to_collection")
    _upsert_collection (cur, belongToCollection)
    collection_db_id = belongToCollection["id"] if belongToCollection else None

    def _safe(v, default = None):
        return v if v is not None else default

    valid_statuses = {
        "Rumored", "Planned", "In Production",
        "Post Production", "Released", "Canceled"
    }

    status = data.get("status")
    if status not in valid_statuses:
        status = None

    movie_sql = """
        INSERT INTO Movie (
            movie_id, tmdb_movie_id, imdb_id, title, original_title,
            original_language, overview, tagline, release_date, status,
            revenue, budget, runtime, popularity, vote_average, vote_count,
            poster_path, backdrop_path, homepage, adult,
            collection_id, etl_synced_at
        )
        VALUES (
            %s,%s,%s,%s,%s, %s,%s,%s,%s,%s,
            %s,%s,%s,%s,%s,%s,
            %s,%s,%s,%s, %s,NOW()
        )
        ON CONFLICT (tmdb_movie_id) DO UPDATE
            SET imdb_id = EXCLUDED.imdb_id,
                title = EXCLUDED.title,
                original_title = EXCLUDED.original_title,
                original_language = EXCLUDED.original_language,
                overview = EXCLUDED.overview,
                tagline = EXCLUDED.tagline,
                release_date = EXCLUDED.release_date,
                status = EXCLUDED.status,
                revenue = EXCLUDED.revenue,
                budget = EXCLUDED.budget,
                runtime = EXCLUDED.runtime,
                popularity = EXCLUDED.popularity,
                vote_average = EXCLUDED.vote_average,
                vote_count = EXCLUDED.vote_count,
                poster_path = EXCLUDED.poster_path,
                backdrop_path = EXCLUDED.backdrop_path,
                homepage = EXCLUDED.homepage,
                adult = EXCLUDED.adult,
                collection_id = EXCLUDED.collection_id,
                etl_synced_at = NOW(),
                updated_at = NOW()
    """

    release_date = data.get("release_date") or None
    if release_date == "":
        release_date = None

    cur.execute(movie_sql, (
        data["id"], data["id"],
        data.get("imdb_id"),
        data.get("title", ""),
        data.get("original_title", ""),
        data.get("original_language", "en"),
        data.get("overview"),
        data.get("tagline"),
        release_date,
        status,
        _safe(data.get("revenue"), 0),
        _safe(data.get("budget"), 0),
        data.get("runtime"),
        _safe(data.get("popularity"), 0),
        _safe(data.get("vote_average"), 0),
        _safe(data.get("vote_count"), 0),
        data.get("poster_path"),
        data.get("backdrop_path"),
        data.get("homepage"),
        bool(data.get("adult", False)),
        collection_db_id,
    ))

    m_id = data["id"]

    cur.execute("DELETE FROM Movie_Genre WHERE movie_id = %s", (m_id,))
    for g in (data.get("genres") or []):
        if g.get("id"):
            cur.execute(
                """INSERT INTO Movie_Genre (movie_id, genre_id)
                   VALUES (%s,%s) ON CONFLICT DO NOTHING""",
                (m_id, g["id"])
            )

    cur.execute("DELETE FROM Movie_Country WHERE movie_id = %s", (m_id,))
    for c in (data.get("production_countries") or []):
        if c.get("iso_3166_1"):
            cur.execute(
                """INSERT INTO Movie_Country (movie_id, iso_3166_1)
                   VALUES (%s,%s) ON CONFLICT DO NOTHING""",
                (m_id, c["iso_3166_1"])
            )

    cur.execute("DELETE FROM Movie_Language WHERE movie_id = %s", (m_id,))
    orig_lang = data.get("original_language", "en")
    cur.execute(
        """INSERT INTO Movie_Language (movie_id, iso_639_1, language_type)
           VALUES (%s,%s,'original') ON CONFLICT DO NOTHING""",
        (m_id, orig_lang)
    )

    for lang in (data.get("spoken_languages") or []):
        code = lang.get("iso_639_1")
        if code and code != orig_lang:
            cur.execute(
                """INSERT INTO Movie_Language (movie_id, iso_639_1, language_type)
                   VALUES (%s,%s,'spoken') ON CONFLICT DO NOTHING""",
                (m_id, code)
            )

    cur.execute("DELETE FROM Movie_Company WHERE movie_id = %s", (m_id,))
    for comp in (data.get("production_companies") or []):
        if comp.get("id"):
            _upsert_company(cur, comp)
            cur.execute(
                """INSERT INTO Movie_Company (movie_id, company_id)
                   VALUES (%s,%s) ON CONFLICT DO NOTHING""",
                (m_id, comp["id"])
            )

    return True, data

def _load_movie_credits(cur, movie_id: int, dept_map: dict, job_map: dict):
    data = tmdb_get(f"/movie/{movie_id}/credits", params={"language": "en-US"})
    if not data:
        return 0

    count = 0

    cur.execute("DELETE FROM Movie_cast WHERE movie_id = %s", (movie_id,))

    for member in (data.get("cast") or []):
        person_id = member.get("id")
        if not person_id:
            return

        if config.FETCH_FULL_PERSON_DETAIL:
            _upsert_person_full(cur, person_id)
        else:
            _upsert_person_minimal(cur, member)

        cast_order = int(member.get("order", 0)) + 1

        cur.execute(
            """
            INSERT INTO Movie_cast (movie_id, person_id, cast_order, character_name, credit_id)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (movie_id, person_id, cast_order) DO UPDATE
                SET character_name = EXCLUDED.character_name,
                    credit_id      = EXCLUDED.credit_id
            """,
            (
                movie_id, 
                person_id,
                cast_order,
                member.get("character") or "",
                member.get("credit_id")
            )
        )

        count +=1
    cur.execute("DELETE FROM Movie_Crew WHERE movie_id = %s", (movie_id,))

    for member in (data.get("crew") or []):
        pid       = member.get("id")
        dept_name = (member.get("department") or "").strip()
        job_name  = (member.get("job") or "").strip()
        if not pid or not dept_name or not job_name:
            continue

        dept_id = dept_map.get(dept_name)
        job_id  = job_map.get((dept_name, job_name))

        if dept_id is None or job_id is None:
            if dept_id is None:
                cur.execute(
                    """INSERT INTO Department (department_name)
                       VALUES (%s) ON CONFLICT (department_name) DO UPDATE
                       SET department_name=EXCLUDED.department_name
                       RETURNING department_id""",
                    (dept_name,)
                )
                row = cur.fetchone()
                if row is None:
                    cur.execute(
                        "SELECT department_id FROM Department WHERE department_name=%s",
                        (dept_name,)
                    )
                    row = cur.fetchone()
                dept_id = row[0]
                dept_map[dept_name] = dept_id

            if job_id is None:
                cur.execute(
                    """INSERT INTO Job (department_id, job_name)
                       VALUES (%s,%s) ON CONFLICT (department_id, job_name) DO NOTHING
                       RETURNING job_id""",
                    (dept_id, job_name)
                )
                row = cur.fetchone()
                if row is None:
                    cur.execute(
                        "SELECT job_id FROM Job WHERE department_id=%s AND job_name=%s",
                        (dept_id, job_name)
                    )
                    row = cur.fetchone()
                if row:
                    job_id = row[0]
                    job_map[(dept_name, job_name)] = job_id
                else:
                    continue 

        if config.FETCH_FULL_PERSON_DETAIL:
            _upsert_person_full(cur, pid)
        else:
            _upsert_person_minimal(cur, member)

        cur.execute(
            """
            INSERT INTO Movie_Crew (movie_id, person_id, department_id, job_id, credit_id)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (movie_id, person_id, department_id, job_id) DO UPDATE
                SET credit_id = EXCLUDED.credit_id
            """,
            (movie_id, pid, dept_id, job_id, member.get("credit_id"))
        )
        count += 1

    return count

def _load_movie_keywords(cur, movie_id:int, provider_map: dict):
    data = tmdb_get(f"/movie/{movie_id}/keywords")
    if not data:
        return 0

    m_id = movie_id
    count = 0
    valid_types = {"flatrate", "rent", "buy", "free", "ads"}

    cur.execute("DELETE FROM Movie_Watch_Provider WHERE movie_id = %s", (m_id,))

    for country_code, avail in data["result"].item():
        if len(country_code) != 2:
            continue

        cur.execute(
            """ INSERT INTO Country (iso_3166-1, english_name, native_name)
                VALUES (%s, %s. '')
                ON CONFLICT (iso_3166_1) DO NOTHING""", (country_code, country_code)
        )
        for avail_type, providers in avail.items():
            if avail_type not in valid_types or not isinstance(providers, list):
                continue
            for p in providers:
                p_id = p.get("provider_id")
                if not p_id:
                    continue

                if p_id not in provider_map:
                    cur.execute(
                        """
                        INSERT INTO watch_provider (provider_id, tmdb_provider_id, provider_name, logo_path)
                        VALUES (%s,%s,%s,%s)
                        ON CONFLICT (tmdb_provider_id) DO NOTHING
                        """, (p_id,
                            p_id,
                            p.get("provider_name", ""),
                            p.get("logo_path", "")
                            )
                    )
                    provider_map[p_id] = p_id

                cur.execute(
                    """
                    INSERT INTO Movie_Watch_Provider (movie_id, provider_id, iso_3166_1, availability_type, display_priority)
                    VALUES(%s,%s,%s,%s,%s)
                    ON CONFLICT (movie_id, provider_id, iso_3166_1, availability_type)
                    DO UPDATE SET display_priority = EXCLUDED.display_priority
                    """,
                    (m_id, p_id, country_code, avail_type, p.get("display_priority", 0))
                )
                count += 1
    return count

def _load_movie_certifications(cur, movie_id: int):
    data = tmdb_get(f"/movie/{movie_id}/release_dates")
    if not data or "results" not in data:
        return 0
 
    m_id = movie_id
    count = 0
 
    cur.execute("DELETE FROM Movie_Certification WHERE movie_id = %s", (m_id,))
 
    for country_entry in (data.get("results") or []):
        country_code = country_entry.get("iso_3166_1")
        if not country_code or len(country_code) != 2:
            continue
 
        for release in (country_entry.get("release_dates") or []):
            certification = release.get("certification")
            if not certification:
                continue
 
            language_code = release.get("iso_639_1") or ""
            release_type = release.get("type")
            if release_type is None:
                continue
 
            cur.execute(
                """SELECT cert_std_id FROM Certification_Standard
                   WHERE iso_3166_1 = %s AND certification = %s AND media_type = 'movie'""",
                (country_code, certification)
            )
            row = cur.fetchone()
            if row is None:
                logger.warning(
                    "movie/%d: no certification_standard match for %s/%s",
                    m_id, country_code, certification
                )
                continue
            cert_std_id = row[0]
 
            cur.execute(
                """
                INSERT INTO Movie_Certification
                    (movie_id, country_code, language_code, release_type, cert_std_id, descriptors)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (movie_id, country_code, language_code, release_type)
                DO UPDATE SET cert_std_id = EXCLUDED.cert_std_id,
                              descriptors = EXCLUDED.descriptors
                """,
                (m_id, country_code, language_code, release_type,
                 cert_std_id, release.get("descriptors") or [])
            )
            count += 1
 
    return count

def _load_movie_watch_providers(cur, movie_id: int, provider_map: dict):
    data = tmdb_get(f"/movie/{movie_id}/watch/providers")
    if not data or "results" not in data:
        return 0

    mid   = movie_id
    count = 0
    valid_types = {"flatrate", "rent", "buy", "free", "ads"}

    cur.execute("DELETE FROM Movie_Watch_Provider WHERE movie_id = %s", (mid,))

    for country_code, avail in data["results"].items():
        if len(country_code) != 2:
            continue

        cur.execute(
            """INSERT INTO Country (iso_3166_1, english_name, native_name)
                VALUES (%s, %s, '')
                ON CONFLICT (iso_3166_1) DO NOTHING""",
            (country_code, country_code)
        )
        for avail_type, providers in avail.items():
            if avail_type not in valid_types or not isinstance(providers, list):
                continue
            for p in providers:
                tid = p.get("provider_id")
                if not tid:
                    continue

                if tid not in provider_map:
                    cur.execute(
                        """INSERT INTO Watch_Provider (provider_id, tmdb_provider_id,
                               provider_name, logo_path)
                           VALUES (%s,%s,%s,%s)
                           ON CONFLICT (tmdb_provider_id) DO NOTHING""",
                        (tid, tid, p.get("provider_name", ""), p.get("logo_path"))
                    )
                    provider_map[tid] = tid

                cur.execute(
                    """
                    INSERT INTO Movie_Watch_Provider
                        (movie_id, provider_id, iso_3166_1, availability_type, display_priority)
                    VALUES (%s,%s,%s,%s,%s)
                    ON CONFLICT (movie_id, provider_id, iso_3166_1, availability_type)
                    DO UPDATE SET display_priority = EXCLUDED.display_priority
                    """,
                    (mid, tid, country_code, avail_type,
                     p.get("display_priority", 0))
                )
                count += 1

    return count

def _load_movie_reviews(cur, movie_id: int):
    if not config.IMPORT_REVIEWS:
        return 0

    data = tmdb_get(
        f"/movie/{movie_id}/reviews", 
        params={"language": "en-US", "page": 1}
    )
    if not data or "results" not in data:
        return 0

    m_id = movie_id
    count = 0

    for rev in (data.get("results") or []):
        r_id = rev.get("id")
        if not r_id:
            continue

        rating_raw = (rev.get("author_details") or {}).get("rating")
        if rating_raw is not None:
            rating = max(0.5, min(10.0, round(float(rating_raw) * 2) / 2))
        else:
            rating = None

        created = rev.get("created_at")
        if created:
            created = created[:26]

        cur.execute(
            """
            INSERT INTO User_Review
                (tmdb_review_id, user_id, media_type, movie_id,
                 content, rating, tmdb_url, created_at)
            VALUES (%s,%s,'movie',%s,%s,%s,%s,
                    COALESCE(%s::TIMESTAMPTZ, NOW()))
            ON CONFLICT (tmdb_review_id) DO UPDATE
                SET content = EXCLUDED.content,
                    rating = EXCLUDED.rating,
                    updated_at = NOW()
            """,
            (
                r_id,
                config.TMDB_SYSTEM_USER_ID,
                m_id,
                rev.get("content", ""),
                rating,
                rev.get("url"),
                created,
            )
        )
        count += 1

    return count

def run_movie_etl(movie_id: int):
    etl = ETLLogger(f"movie/{movie_id}", tmdb_id = movie_id, media_type = "movie")
    etl.start()
    
    logger.info("  → [movie] id=%d: bắt đầu ETL...", movie_id)

    try:
        conn = __import__("db_utils").get_connection()
        try:
            with conn:
                with conn.cursor() as cur:

                    dept_map, job_map = load_dept_job_maps(conn)
                    provider_map      = load_provider_map(conn)

                    ok, movie_data = _load_movie_core(cur, movie_id)
                    if not ok:
                        raise ValueError(f"movie/{movie_id}: API trả về None hoặc lỗi")

                    records = 1

                    n = _load_movie_credits(cur, movie_id, dept_map, job_map)
                    logger.info("    credits: %d người", n)
                    records += n

                    n = _load_movie_keywords(cur, movie_id)
                    logger.info("    keywords: %d", n)
                    records += n

                    n = _load_movie_watch_providers(cur, movie_id, provider_map)
                    logger.info("    watch_providers: %d links", n)
                    records += n

                    n = _load_movie_reviews(cur, movie_id)
                    if n:
                        logger.info("    reviews: %d", n)
                    records += n

            logger.info("  ✓ [movie] id=%d: DONE (%d records)", movie_id, records)
            etl.finish("success", records=records)
            return True

        except Exception as e:
            conn.rollback()
            logger.error("  ✗ [movie] id=%d: FAILED — %s", movie_id, e)
            etl.finish("failed", error=str(e))
            return False
        finally:
            conn.close()

    except Exception as e:
        logger.error("  ✗ [movie] id=%d: DB connection error — %s", movie_id, e)
        etl.finish("failed", error=str(e))
        return False

def run_movies_etl(movie_ids: list[int], stop_on_error: bool = False):
    success = 0
    failed  = 0

    logger.info("=" * 60)
    logger.info("START: Movie ETL — %d movie(s)", len(movie_ids))
    logger.info("=" * 60)

    for mid in movie_ids:
        ok = run_movie_etl(mid)
        if ok:
            success += 1
        else:
            failed += 1
            if stop_on_error:
                logger.error("stop_on_error=True: dừng tại movie_id=%d", mid)
                break

    logger.info("=" * 60)
    logger.info("DONE: success=%d / failed=%d / total=%d",
                success, failed, success + failed)
    logger.info("=" * 60)
    return success, failed
