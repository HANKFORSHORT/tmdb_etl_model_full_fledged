from db_utils import tmdb_get



def _upsert_person_minimal(cur, p: dict):

    sql = """
        INSERT INTO Person (
            person_id, tmdb_person_id, name, original_name,
            gender, known_for_department, popularity,
            profile_path, adult
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (tmdb_person_id) DO UPDATE
            SET name                 = EXCLUDED.name,
                original_name        = EXCLUDED.original_name,
                gender               = EXCLUDED.gender,
                known_for_department = EXCLUDED.known_for_department,
                popularity           = EXCLUDED.popularity,
                profile_path         = EXCLUDED.profile_path,
                adult                = EXCLUDED.adult,
                updated_at           = NOW()
    """
    gender = p.get("gender")
    if gender not in (0, 1, 2, 3):
        gender = 0
    cur.execute(sql, (
        p["id"],
        p["id"],
        p.get("name", ""),
        p.get("original_name"),
        gender,
        p.get("known_for_department"),
        p.get("popularity") or 0,
        p.get("profile_path"),
        bool(p.get("adult", False)),
    ))


def _upsert_person_full(cur, person_id: int):
    """
    Gọi API GET /person/{person_id} để lấy đầy đủ thông tin,
    rồi upsert Person + Person_AKA.
    Chỉ gọi khi FETCH_FULL_PERSON_DETAIL=True.
    """
    data = tmdb_get(f"/person/{person_id}", params={"language": "en-US"})
    if not data:
        return

    gender = data.get("gender")
    if gender not in (0, 1, 2, 3):
        gender = 0

    # ── Person ──────────────────────────────────────────────────────────────
    sql_person = """
        INSERT INTO Person (
            person_id, tmdb_person_id, name, original_name, biography,
            birthday, deathday, gender, known_for_department,
            place_of_birth, popularity, profile_path, homepage,
            imdb_id, adult, etl_synced_at
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
        ON CONFLICT (tmdb_person_id) DO UPDATE
            SET name                 = EXCLUDED.name,
                original_name        = EXCLUDED.original_name,
                biography            = EXCLUDED.biography,
                birthday             = EXCLUDED.birthday,
                deathday             = EXCLUDED.deathday,
                gender               = EXCLUDED.gender,
                known_for_department = EXCLUDED.known_for_department,
                place_of_birth       = EXCLUDED.place_of_birth,
                popularity           = EXCLUDED.popularity,
                profile_path         = EXCLUDED.profile_path,
                homepage             = EXCLUDED.homepage,
                imdb_id              = EXCLUDED.imdb_id,
                adult                = EXCLUDED.adult,
                etl_synced_at        = NOW(),
                updated_at           = NOW()
    """
    def _safe_date(s):
        return s if s else None

    cur.execute(sql_person, (
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
