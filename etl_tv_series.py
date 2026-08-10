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

#def _load_tv_series_credits(cur, series_id: int, dept_map: dict, job_map: dict):
