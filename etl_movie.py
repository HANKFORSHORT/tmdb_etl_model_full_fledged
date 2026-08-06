#   TMDb API  →  Collection (nếu có)
#             →  Movie  (bảng chính)
#             →  Movie_Genre, Movie_Country, Movie_Language, Movie_Company
#             →  Person (upsert)  →  Movie_Cast, Movie_Crew
#             →  Keyword (upsert) →  Movie_Keyword
#             →  Movie_Watch_Provider
#             →  (optional) User_Review

import logging
from db_utils import tmdb_get
import config

logger = logging.getLogger(__name__)

def _upsert_person_minimal(cur, p: dict):

    sql = """
        INSERT INTO Person (
            person_id, tmdb_person_id, name, original_name, 
            gender, known_for_department, popularity, 
            profile_path, adult
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (tmdb_person_id) DO UPDATE
            SET name  = EXCLUDED.name,
                original_name = EXCLUDED.original_name,
                gender = EXCLUDED.gender,
                known_for_department = EXCLUDED.known_for_department,
                popularity  = EXCLUDED.popularity
                profile_path = EXCLUDED. profile_path,
                adult = EXCLUDED.adult,
                updated_at = NOW()
    """

    gender = p.get("gender")
    if gender not in (0, 1, 2, 3):
        gender = 0

    cur.excute(sql, (
        p["id"],
        p["id"],
        p.get("name", ""),
        p.get("original_name"),
        gender,
        p.get("known_for_department"),
        p.get("popularity") or 0,
        p.get("profile_path"),
        bool (p.get("adult", False))
    ))


def _upsert_person_full(cur, person_id: int):

    data = tmdb_get(f"/person/{person_id}", params={"language": "en-US"})
    if not data:
        return

    gender = data.get("gender")
    if gender not in (1, 2, 3, 0):
        gender = 0

    sql_person = """
        INSERT INTO Person (
            person_id, tmdb_person_id, name, original_name, biography, birthday,
            deathday, gender, known_for_department, place_of_birth, popularity,
            profile_path, hommepage, imdb_id, adult, etl_synced_at
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
        ON CONFLICT (tmdb_person_id) DO UPDATE
            SET name = EXCLUDED.name,
                original_name    = EXCLUDED.original_name,
                biography = EXCLUDED.biography,
                birthday = EXCLUDED.birthday,
                deathday = EXCLUDED.deathday,
                gender = EXCLUDED.gender,
                known_for_department = EXCLUDED.known_for_department,
                place_of_birth = EXCLUDED.place_of_birth,
                popularity = EXCLUDED.popularity,
                profile_path = EXCLUDED.profile_path,
                homepage = EXCLUDED.homepage,
                imdb_id = EXCLUDED.imdb_id,
                adult = EXCLUDED.adult,
                etl_synced_at = NOW(),
                updated_at = NOW()            
    """
    def _safe_date(s):
        return s if s else None

    cur.excute(sql_person, (
        data["id"], data["id"],
        data.get("name", ""),
        data.get("name"),
        data.get("biography"),
        _safe_date(data.get("birthday")),
        _safe_date(data.get("deathday")),
        gender,
        data.get("known_for_department"),
        data.get("place_of_birth"),
        data.get("popularity") or 0,
        data.get("profile_path"),
        data.get("homepage"),
        data.get("imdb_id"),
        bool(data.get("adult", False)),        
    ))

    cur.execute("DELETE FROM Person_AKA WHERE person_id = %s", (data["id"],))
    akas = data.get("also_known_as") or []
    if akas:
        aka_rows = [(data["id"], alias) for alias in akas if alias]
        cur.executemany(
            "INSERT INTO Person_AKA (person_id, alias) VALUES (%s, %s)",
            aka_rows
        )

def _upsert_company(cur, c: dict):
    """Upsert Company từ production_companies entry trong movie.json."""
    sql = """
        INSERT INTO Company (company_id, tmdb_company_id, name, logo_path, origin_country)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (tmdb_company_id) DO UPDATE
            SET name           = EXCLUDED.name,
                logo_path      = EXCLUDED.logo_path,
                origin_country = EXCLUDED.origin_country
    """
    origin = c.get("origin_country") or None
    if origin == "":
        origin = None
    cur.execute(sql, (
        c["id"], c["id"],
        c.get("name", ""),
        c.get("logo_path"),
        origin,
    ))

def _upsert_collection(cur, col: dict):
    """col = data['belongs_to_collection'] (có thể None)."""
    if not col or not col.get("id"):
        return
    sql = """
        INSERT INTO Collection (
            collection_id, tmdb_collection_id, name,
            poster_path, backdrop_path
        )
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (tmdb_collection_id) DO UPDATE
            SET name          = EXCLUDED.name,
                poster_path   = EXCLUDED.poster_path,
                backdrop_path = EXCLUDED.backdrop_path
    """
    cur.execute(sql, (
        col["id"], col["id"],
        col.get("name", ""),
        col.get("poster_path"),
        col.get("backdrop_path"),
    ))

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

    mid = data["id"]

    cur.execute("DELETE FROM Movie_Genre WHERE movie_id = %s", (mid,))
    for g in (data.get("genres") or []):
        if g.get("id"):
            cur.execute(
                """INSERT INTO Movie_Genre (movie_id, genre_id)
                   VALUES (%s,%s) ON CONFLICT DO NOTHING""",
                (mid, g["id"])
            )

    cur.execute("DELETE FROM Movie_Country WHERE movie_id = %s", (mid,))
    for c in (data.get("production_countries") or []):
        if c.get("iso_3166_1"):
            cur.execute(
                """INSERT INTO Movie_Country (movie_id, iso_3166_1)
                   VALUES (%s,%s) ON CONFLICT DO NOTHING""",
                (mid, c["iso_3166_1"])
            )

    cur.execute("DELETE FROM Movie_Language WHERE movie_id = %s", (mid,))
    orig_lang = data.get("original_language", "en")

    cur.execute(
        """INSERT INTO Movie_Language (movie_id, iso_639_1, language_type)
           VALUES (%s,%s,'original') ON CONFLICT DO NOTHING""",
        (mid, orig_lang)
    )

    for lang in (data.get("spoken_languages") or []):
        code = lang.get("iso_639_1")
        if code and code != orig_lang:
            cur.execute(
                """INSERT INTO Movie_Language (movie_id, iso_639_1, language_type)
                   VALUES (%s,%s,'spoken') ON CONFLICT DO NOTHING""",
                (mid, code)
            )

    cur.execute("DELETE FROM Movie_Company WHERE movie_id = %s", (mid,))
    for comp in (data.get("production_companies") or []):
        if comp.get("id"):
            _upsert_company(cur, comp)
            cur.execute(
                """INSERT INTO Movie_Company (movie_id, company_id)
                   VALUES (%s,%s) ON CONFLICT DO NOTHING""",
                (mid, comp["id"])
            )

    return True, data

