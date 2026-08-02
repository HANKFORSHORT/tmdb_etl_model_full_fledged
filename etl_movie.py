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

