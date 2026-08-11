# Movie cluster:
#   Collection → Movie → Movie_Genre/Country/Language/Company
#   → Person → Movie_Cast/Movie_Crew
#   → Keyword → Movie_Keyword
#   → Movie_Certification → Movie_Watch_Provider
#   → (optional) User_Review

# TV cluster:
#   TV_Series → TV_Genre/Country/Language/Company/Certification
#   → Person (dùng chung bảng Person đã có)
#   → TV_Cast/TV_Crew/TV_Creator
#   → Keyword → TV_Keyword
#   → TV_Watch_Provider
#   → TV_Season → TV_Episode
#   → Episode_Cast/Episode_Crew

import logging
from db_utils import (tmdb_get, ETLLogger, 
                      load_dept_job_maps, load_provider_map)
import config
from etl_search import (_upsert_person_full, _upsert_person_minimal, 
                        _upsert_company, _upsert_collection)

def _load_tv_serie_core(cur, series_id: int):
    data = tmdb_get(f"/tv/{series_id}", params={"language": "en-US"})
    if not data or "id" not in data:
        return False, None

    def _safe(v, default = None):
        return v if v is not None else default

    valid_types = {
        "Documentary", "News", "Miniseries",
        "Reality", "Scripted", "Talk Show", "Video"
    }
    type = data.get("type")
    if type not in valid_types:
        type = None

    valid_statuses = {
        "Rumored", "Planned", "In Production", 
        "Post Production", "Released", "Cancelled"
    }
    status = data.get("status")
    if status not in valid_statuses:
        status = None

    tv_s_sql = """
        INSERT INTO tv_series (
            series_id, tmdb_series_id, name, original_name, original_language, 
            overview, tagline, first_air_date, last_air_date, status, type, 
            in_production, homepage, popularity, vote_average, vote_count, 
            poster_path, backdrop_path, adult, etl_synced_at
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,%s,%s,%s,%s, NOW()
                )
        ON CONFLICT (tmdb_series_id) DO UPDATE
            SET
                name = EXCLUDED.name,
                original_name = EXCLUDED.original_name,
                original_language = EXCLUDED.original_language,
                overview = EXCLUDED.overview,
                tagline = EXCLUDED.tagline,
                first_air_date = EXCLUDED.first_air_date,
                last_air_date = EXCLUDED.last_air_date,
                status = EXCLUDED.status,
                type = EXCLUDED.type,
                in_production = EXCLUDED.in_production,
                homepage = EXCLUDED.homepage,
                popularity = EXCLUDED.popularity,
                vote_average = EXCLUDED.vote_average,
                vote_count = EXCLUDED.vote_count,
                poster_path = EXCLUDED.poster_path,
                backdrop_path = EXCLUDED.backdrop_path,
                adult = EXCLUDED.adult,
                etl_synced_at = NOW(),
                updated_at = NOW()
        """

    first_air_date = data.get("first_air_date") or None
    if first_air_date == "":
        first_air_date = None

    last_air_date = data.get("last_air_date") or None
    if last_air_date == "":
        last_air_date = None
    

    cur.execute(tv_s_sql, (
        data["id"],
        data["id"],
        data.get("name", ""),
        data.get("original_name", ""),
        data.get("original_language", "en"),
        data.get("overview"),
        data.get("tagline"),
        first_air_date,
        last_air_date,
        status,
        type,
        bool(data.get("in_production", False)),
        data.get("homepage"),
        _safe(data.get("popularity"), 0),
        _safe(data.get("vote_average"), 0),
        _safe(data.get("vote_count"), 0),
        data.get("poster_path"),
        data.get("backdrop_path"),
        bool(data.get("adult", False))
    ))

    tv_s_id = data["id"]

    cur.execute("DELETE FROM tv_genre where series_id=%s", (tv_s_id,))
    for g in (data.get("genres") or []):
        if g.get("id"):
            cur.execute(
                """ INSERT INTO tv_genre (series_id, genre_id)
                    VALUES (%s,%s) ON CONFLICT DO NOTHING""",
                    (tv_s_id, g["id"])
                    )

    
    cur.execute("DELETE FROM tv_country WHERE movie_id = %s", (tv_s_id,))
    for c in (data.get("production_countries") or []):
        if c.get("iso_3166_1"):
            cur.execute(
                """INSERT INTO tv_country (series_id, iso_3166_1)
                   VALUES (%s,%s) ON CONFLICT DO NOTHING""",
                (tv_s_id, c["iso_3166_1"])
            )

    cur.execute("DELETE FROM tv_language WHERE movie_id = %s", (tv_s_id,))
    orig_lang = data.get("original_language", "en")
    cur.execute(
        """INSERT INTO tv_language (series_id, iso_639_1, language_type)
           VALUES (%s,%s,'original') ON CONFLICT DO NOTHING""",
        (tv_s_id, orig_lang)
    )

    for lang in (data.get("spoken_languages") or []):
        code = lang.get("iso_639_1")
        if code and code != orig_lang:
            cur.execute(
                """INSERT INTO tv_language (series_id, iso_639_1, language_type)
                   VALUES (%s,%s,'spoken') ON CONFLICT DO NOTHING""",
                (tv_s_id, code)
            )

    cur.execute("DELETE FROM tv_company WHERE series_id = %s", (tv_s_id,))
    for comp in (data.get("production_companies") or []):
        if comp.get("id"):
            _upsert_company(cur, comp)
            cur.execute(
                """INSERT INTO tv_company (series_id, company_id)
                   VALUES (%s,%s) ON CONFLICT DO NOTHING""",
                (tv_s_id, comp["id"])
            )

    cur.execute("DELETE FROM tv_creator where series_id=%s", (tv_s_id,))
    for w in (data.get("created_by") or []):
        if w.get("id"):
            cur.execute(
                """ INSERT INTO tv_creator (series_id, person_id, credit_id)
                    VALUES (%s,%s,%s) ON CONFLICT DO NOTHING""",
                    (tv_s_id, w["id"], w["credit_id"])
                    )

    return True, data


def _load_tv_series_credits(cur, series_id: int, dept_map: dict, job_map: dict):
    data = tmdb_get(f"/tv/{series_id}/credits", params={"language": "en-US"})
    if not data:
        return 0
 
    count = 0
 
    cur.execute("DELETE FROM TV_Cast WHERE series_id = %s", (series_id,))
    for member in (data.get("cast") or []):
        person_id = member.get("id")
        if not person_id:
            continue
 
        if config.FETCH_FULL_PERSON_DETAIL:
            _upsert_person_full(cur, person_id)
        else:
            _upsert_person_minimal(cur, member)
 
        cast_order = int(member.get("order", 0)) + 1
        cur.execute(
            """
            INSERT INTO TV_Cast (series_id, person_id, cast_order, character_name, credit_id)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (series_id, person_id, cast_order) DO UPDATE
            SET character_name = EXCLUDED.character_name,
                credit_id = EXCLUDED.credit_id
            """,
            (
                series_id,
                person_id,
                cast_order,
                member.get("character") or "",
                member.get("credit_id"),
            )
        )
        count += 1
 
    cur.execute("DELETE FROM TV_Crew WHERE series_id = %s", (series_id,))
    for member in (data.get("crew") or []):
        pid = member.get("id")
        dept_name = (member.get("department") or "").strip()
        job_name = (member.get("job") or "").strip()
        if not pid or not dept_name or not job_name:
            continue
 
        dept_id = dept_map.get(dept_name)
        job_id = job_map.get((dept_name, job_name))
 
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
            INSERT INTO TV_Crew (series_id, person_id, department_id, job_id, credit_id)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (series_id, person_id, department_id, job_id) DO UPDATE
            SET credit_id = EXCLUDED.credit_id
            """,
            (series_id, pid, dept_id, job_id, member.get("credit_id"))
        )
        count += 1
 
    return count
 
 
def _load_tv_series_keywords(cur, series_id: int):
    data = tmdb_get(f"/tv/{series_id}/keywords")
    if not data:
        return 0
 
    # Lưu ý: endpoint TV trả về "results", không phải "keywords" như /movie/{id}/keywords
    keywords = data.get("results") or []
 
    cur.execute("DELETE FROM TV_Keyword WHERE series_id = %s", (series_id,))
    count = 0
    for kw in keywords:
        kw_id = kw.get("id")
        if not kw_id:
            continue
 
        cur.execute(
            """INSERT INTO Keyword (keyword_id, name)
               VALUES (%s, %s)
               ON CONFLICT (keyword_id) DO UPDATE SET name = EXCLUDED.name""",
            (kw_id, kw.get("name", ""))
        )
        cur.execute(
            """INSERT INTO TV_Keyword (series_id, keyword_id)
               VALUES (%s, %s) ON CONFLICT DO NOTHING""",
            (series_id, kw_id)
        )
        count += 1
 
    return count
 
 
def _load_tv_series_watch_providers(cur, series_id: int, provider_map: dict):
    data = tmdb_get(f"/tv/{series_id}/watch/providers")
    if not data or "results" not in data:
        return 0
 
    count = 0
    valid_types = {"flatrate", "rent", "buy", "free", "ads"}
 
    cur.execute("DELETE FROM TV_Watch_Provider WHERE series_id = %s", (series_id,))
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
                           VALUES (%s, %s, %s, %s)
                           ON CONFLICT (tmdb_provider_id) DO NOTHING""",
                        (tid, tid, p.get("provider_name", ""), p.get("logo_path"))
                    )
                    provider_map[tid] = tid
 
                cur.execute(
                    """
                    INSERT INTO TV_Watch_Provider
                        (series_id, provider_id, iso_3166_1, availability_type, display_priority)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (series_id, provider_id, iso_3166_1, availability_type)
                    DO UPDATE SET display_priority = EXCLUDED.display_priority
                    """,
                    (series_id, tid, country_code, avail_type, p.get("display_priority", 0))
                )
                count += 1
 
    return count
 
 
def _load_tv_series_certifications(cur, series_id: int):
    data = tmdb_get(f"/tv/{series_id}/content_ratings")
    if not data:
        return 0
 
    results = data.get("results") or []
 
    cur.execute("DELETE FROM TV_Certification WHERE series_id = %s", (series_id,))
    count = 0
    for r in results:
        country_code = r.get("iso_3166_1")
        rating = r.get("rating")
        if not country_code or not rating:
            continue
 
        cur.execute(
            """INSERT INTO Country (iso_3166_1, english_name, native_name)
               VALUES (%s, %s, '')
               ON CONFLICT (iso_3166_1) DO NOTHING""",
            (country_code, country_code)
        )
 
        descriptors = r.get("descriptors") or []
        cur.execute(
            """
            INSERT INTO TV_Certification (series_id, iso_3166_1, rating, descriptors)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (series_id, iso_3166_1) DO UPDATE
            SET rating = EXCLUDED.rating,
                descriptors = EXCLUDED.descriptors
            """,
            (series_id, country_code, rating, descriptors)
        )
        count += 1
 
    return count
 
 
def _load_episode_cast_crew(cur, episode_id: int, ep: dict, dept_map: dict, job_map: dict):
    """
    Episode_Cast lưu guest_stars (is_guest=True) — TMDb không trả "cast" riêng
    cho từng episode, chỉ có main cast ở cấp series (TV_Cast) và guest_stars
    ở cấp episode.
    """
    cast_count = 0
    crew_count = 0
 
    cur.execute("DELETE FROM Episode_Cast WHERE episode_id = %s", (episode_id,))
    for member in (ep.get("guest_stars") or []):
        person_id = member.get("id")
        if not person_id:
            continue
 
        if config.FETCH_FULL_PERSON_DETAIL:
            _upsert_person_full(cur, person_id)
        else:
            _upsert_person_minimal(cur, member)
 
        cast_order = int(member.get("order", 0)) + 1
        cur.execute(
            """
            INSERT INTO Episode_Cast
                (episode_id, person_id, cast_order, character_name, credit_id, is_guest)
            VALUES (%s, %s, %s, %s, %s, TRUE)
            ON CONFLICT (episode_id, person_id, cast_order) DO UPDATE
            SET character_name = EXCLUDED.character_name,
                credit_id = EXCLUDED.credit_id,
                is_guest = TRUE
            """,
            (
                episode_id,
                person_id,
                cast_order,
                member.get("character") or "",
                member.get("credit_id"),
            )
        )
        cast_count += 1
 
    cur.execute("DELETE FROM Episode_Crew WHERE episode_id = %s", (episode_id,))
    for member in (ep.get("crew") or []):
        pid = member.get("id")
        dept_name = (member.get("department") or "").strip()
        job_name = (member.get("job") or "").strip()
        if not pid or not dept_name or not job_name:
            continue
 
        dept_id = dept_map.get(dept_name)
        job_id = job_map.get((dept_name, job_name))
 
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
            INSERT INTO Episode_Crew (episode_id, person_id, department_id, job_id, credit_id)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (episode_id, person_id, department_id, job_id) DO UPDATE
            SET credit_id = EXCLUDED.credit_id
            """,
            (episode_id, pid, dept_id, job_id, member.get("credit_id"))
        )
        crew_count += 1
 
    return cast_count, crew_count
 
 
def _load_tv_seasons_and_episodes(cur, series_id: int, seasons_summary: list,
                                   dept_map: dict, job_map: dict):
    """
    seasons_summary = series_data["seasons"] — đã có sẵn từ response /tv/{series_id}
    trong _load_tv_serie_core, nên không cần gọi lại API để lấy danh sách season.
    Với mỗi season, gọi /tv/{series_id}/season/{season_number} để lấy episodes
    (kèm crew + guest_stars ngay trong response, không cần gọi riêng từng episode).
    """
    season_count = 0
    episode_count = 0
    cast_count = 0
    crew_count = 0
 
    for s in (seasons_summary or []):
        season_id = s.get("id")
        season_number = s.get("season_number")
        if season_id is None or season_number is None:
            continue
 
        season_sql = """
            INSERT INTO TV_Season (
                season_id, tmdb_season_id, series_id, season_number, name,
                overview, air_date, poster_path, vote_average, episode_count
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (tmdb_season_id) DO UPDATE
            SET name = EXCLUDED.name,
                overview = EXCLUDED.overview,
                air_date = EXCLUDED.air_date,
                poster_path = EXCLUDED.poster_path,
                vote_average = EXCLUDED.vote_average,
                episode_count = EXCLUDED.episode_count
        """
        air_date = s.get("air_date") or None
        if air_date == "":
            air_date = None
 
        cur.execute(season_sql, (
            season_id, season_id, series_id, season_number,
            s.get("name"), s.get("overview"), air_date,
            s.get("poster_path"), s.get("vote_average"), s.get("episode_count"),
        ))
        season_count += 1
 
        season_detail = tmdb_get(
            f"/tv/{series_id}/season/{season_number}", params={"language": "en-US"}
        )
        if not season_detail:
            continue
 
        for ep in (season_detail.get("episodes") or []):
            episode_id = ep.get("id")
            episode_number = ep.get("episode_number")
            if episode_id is None or episode_number is None:
                continue
 
            episode_sql = """
                INSERT INTO TV_Episode (
                    episode_id, tmdb_episode_id, season_id, series_id, episode_number,
                    episode_type, name, overview, air_date, runtime, production_code,
                    still_path, vote_average, vote_count
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (tmdb_episode_id) DO UPDATE
                SET episode_type = EXCLUDED.episode_type,
                    name = EXCLUDED.name,
                    overview = EXCLUDED.overview,
                    air_date = EXCLUDED.air_date,
                    runtime = EXCLUDED.runtime,
                    production_code = EXCLUDED.production_code,
                    still_path = EXCLUDED.still_path,
                    vote_average = EXCLUDED.vote_average,
                    vote_count = EXCLUDED.vote_count
            """
            ep_air_date = ep.get("air_date") or None
            if ep_air_date == "":
                ep_air_date = None
 
            cur.execute(episode_sql, (
                episode_id, episode_id, season_id, series_id, episode_number,
                ep.get("episode_type"), ep.get("name", ""), ep.get("overview"),
                ep_air_date, ep.get("runtime"), ep.get("production_code"),
                ep.get("still_path"), ep.get("vote_average"), ep.get("vote_count", 0),
            ))
            episode_count += 1
 
            c, w = _load_episode_cast_crew(cur, episode_id, ep, dept_map, job_map)
            cast_count += c
            crew_count += w
 
    return season_count, episode_count, cast_count, crew_count
 
 
# def run_tv_series_etl(series_id: int):
#     etl = ETLLogger(f"tv/{series_id}", tmdb_id=series_id, media_type="tv")
#     etl.start()
#     logger.info(" → [tv] id=%d: bắt đầu ETL...", series_id)
 
#     try:
#         conn = __import__("db_utils").get_connection()
#         try:
#             with conn:
#                 with conn.cursor() as cur:
#                     dept_map, job_map = load_dept_job_maps(conn)
#                     provider_map = load_provider_map(conn)
 
#                     ok, series_data = _load_tv_serie_core(cur, series_id)
#                     if not ok:
#                         raise ValueError(f"tv/{series_id}: API trả về None hoặc lỗi")
 
#                     records = 1
 
#                     n = _load_tv_series_credits(cur, series_id, dept_map, job_map)
#                     logger.info("    credits: %d người", n)
#                     records += n
 
#                     n = _load_tv_series_keywords(cur, series_id)
#                     logger.info("    keywords: %d", n)
#                     records += n
 
#                     n = _load_tv_series_watch_providers(cur, series_id, provider_map)
#                     logger.info("    watch_providers: %d links", n)
#                     records += n
 
#                     n = _load_tv_series_certifications(cur, series_id)
#                     logger.info("    certifications: %d", n)
#                     records += n
 
#                     n_season, n_ep, n_cast, n_crew = _load_tv_seasons_and_episodes(
#                         cur, series_id, series_data.get("seasons") or [], dept_map, job_map
#                     )
#                     logger.info(
#                         "    seasons: %d, episodes: %d, episode_cast: %d, episode_crew: %d",
#                         n_season, n_ep, n_cast, n_crew
#                     )
#                     records += n_season + n_ep + n_cast + n_crew
 
#                     logger.info(" ✓ [tv] id=%d: DONE (%d records)", series_id, records)
#                     etl.finish("success", records=records)
#                     return True
 
#         except Exception as e:
#             conn.rollback()
#             logger.error(" ✗ [tv] id=%d: FAILED — %s", series_id, e)
#             etl.finish("failed", error=str(e))
#             return False
#         finally:
#             conn.close()
 
#     except Exception as e:
#         logger.error(" ✗ [tv] id=%d: DB connection error — %s", series_id, e)
#         etl.finish("failed", error=str(e))
#         return False
 
 
# def run_tv_series_batch_etl(series_ids: list[int], stop_on_error: bool = False):
#     success = 0
#     failed = 0
 
#     logger.info("=" * 60)
#     logger.info("START: TV Series ETL — %d series", len(series_ids))
#     logger.info("=" * 60)
 
#     for sid in series_ids:
#         ok = run_tv_series_etl(sid)
#         if ok:
#             success += 1
#         else:
#             failed += 1
#             if stop_on_error:
#                 logger.error("stop_on_error=True: dừng tại series_id=%d", sid)
#                 break
 
#     logger.info("=" * 60)
#     logger.info("DONE: success=%d / failed=%d / total=%d",
#                  success, failed, success + failed)
#     logger.info("=" * 60)
#     return success, failed
 
