"""
Movie domain: Movie plus all Movie_* join/detail tables (cast, crew, genre,
keyword, company, country, language, certification, watch provider).
Depends on: schema_shared.py, schema_reference.py

Auto-generated from a pg_dump schema export and split into domain modules
mirroring the etl_movie.py / etl_tv_series.py / etl_reference.py convention
used elsewhere in this repo. Run directly to create these objects in the
target database:

    python schema_movie.py

Uses db_utils.get_connection() / db_utils.db_transaction() for the actual
connection, same as the rest of the ETL codebase.
"""

import logging

import db_utils

logger = logging.getLogger(__name__)

DDL_STATEMENTS = [
    #
    """
    CREATE FUNCTION public.fn_get_movie_cast_count(p_movie_id integer) RETURNS integer
        LANGUAGE sql STABLE
        AS $$
        SELECT COUNT(*)::INTEGER FROM Movie_Cast WHERE movie_id = p_movie_id;
    $$;
    """,
    """
    ALTER FUNCTION public.fn_get_movie_cast_count(p_movie_id integer) OWNER TO postgres;
    """,
    """
    CREATE FUNCTION public.fn_get_movie_crew_count(p_movie_id integer) RETURNS integer
        LANGUAGE sql STABLE
        AS $$
        SELECT COUNT(*)::INTEGER FROM Movie_Crew WHERE movie_id = p_movie_id;
    $$;
    """,
    """
    ALTER FUNCTION public.fn_get_movie_crew_count(p_movie_id integer) OWNER TO postgres;
    """,
    """
    CREATE FUNCTION public.fn_get_movie_review_count(p_movie_id integer) RETURNS integer
        LANGUAGE sql STABLE
        AS $$
        SELECT COUNT(*)::INTEGER FROM User_Review WHERE movie_id = p_movie_id;
    $$;
    """,
    """
    ALTER FUNCTION public.fn_get_movie_review_count(p_movie_id integer) OWNER TO postgres;
    """,
    """
    CREATE FUNCTION public.fn_get_movie_runtime_fmt(p_movie_id integer) RETURNS text
        LANGUAGE plpgsql STABLE
        AS $$
    DECLARE
        v_runtime SMALLINT;
    BEGIN
        SELECT runtime INTO v_runtime FROM Movie WHERE movie_id = p_movie_id;
        IF v_runtime IS NULL OR v_runtime <= 0 THEN RETURN NULL; END IF;
        RETURN (v_runtime / 60)::TEXT || 'h ' || (v_runtime % 60)::TEXT || 'm';
    END;
    $$;
    """,
    """
    ALTER FUNCTION public.fn_get_movie_runtime_fmt(p_movie_id integer) OWNER TO postgres;
    """,
    """
    CREATE FUNCTION public.fn_get_movie_user_avg(p_movie_id integer) RETURNS numeric
        LANGUAGE sql STABLE
        AS $$
        SELECT ROUND(AVG(rating)::NUMERIC, 2)
        FROM   User_Movie_Rating
        WHERE  movie_id = p_movie_id;
    $$;
    """,
    """
    ALTER FUNCTION public.fn_get_movie_user_avg(p_movie_id integer) OWNER TO postgres;
    """,
    """
    CREATE FUNCTION public.fn_get_movie_vote_avg(p_movie_id integer) RETURNS numeric
        LANGUAGE sql STABLE
        AS $$
        SELECT vote_average FROM Movie WHERE movie_id = p_movie_id;
    $$;
    """,
    """
    ALTER FUNCTION public.fn_get_movie_vote_avg(p_movie_id integer) OWNER TO postgres;
    """,
    """
    CREATE FUNCTION public.fn_get_person_movie_count(p_person_id integer) RETURNS integer
        LANGUAGE sql STABLE
        AS $$
        SELECT COUNT(DISTINCT movie_id)::INTEGER
        FROM (
            SELECT movie_id FROM Movie_Cast WHERE person_id = p_person_id
            UNION
            SELECT movie_id FROM Movie_Crew WHERE person_id = p_person_id
        ) sub;
    $$;
    """,
    """
    ALTER FUNCTION public.fn_get_person_movie_count(p_person_id integer) OWNER TO postgres;
    """,
    """
    CREATE FUNCTION public.fn_top_rated_movies(p_genre_id integer, p_top_n integer DEFAULT 50) RETURNS TABLE(rank integer, movie_id integer, title character varying, release_date date, vote_average numeric, vote_count integer, popularity numeric, runtime_fmt text, roi_pct numeric)
        LANGUAGE plpgsql
        AS $$
    DECLARE
        cur_movies CURSOR FOR
            SELECT m.movie_id, m.title, m.release_date,
                   m.vote_average, m.vote_count,
                   m.popularity, m.revenue, m.budget,
                   fn_get_movie_runtime_fmt(m.movie_id) AS runtime_fmt
            FROM   Movie m
            JOIN   Movie_Genre mg ON mg.movie_id = m.movie_id
            WHERE  mg.genre_id = p_genre_id
              AND  m.vote_count >= 100
            ORDER  BY m.vote_average DESC, m.vote_count DESC
            LIMIT  p_top_n;

        rec      RECORD;
        v_rank   INTEGER := 0;
    BEGIN
        OPEN cur_movies;
        LOOP
            FETCH cur_movies INTO rec;
            EXIT WHEN NOT FOUND;

            v_rank := v_rank + 1;

            rank         := v_rank;
            movie_id     := rec.movie_id;
            title        := rec.title;
            release_date := rec.release_date;
            vote_average := rec.vote_average;
            vote_count   := rec.vote_count;
            popularity   := rec.popularity;
            runtime_fmt  := rec.runtime_fmt;
            roi_pct      := CASE WHEN rec.budget > 0
                                THEN ROUND((rec.revenue - rec.budget)::NUMERIC
                                           / rec.budget * 100, 2)
                                ELSE NULL END;
            RETURN NEXT;
        END LOOP;
        CLOSE cur_movies;
    END;
    $$;
    """,
    """
    ALTER FUNCTION public.fn_top_rated_movies(p_genre_id integer, p_top_n integer) OWNER TO postgres;
    """,
    """
    CREATE PROCEDURE public.sp_cur_top_rated_movies(IN p_genre_id integer, IN p_top_n integer DEFAULT 50)
        LANGUAGE plpgsql
        AS $$
    DECLARE
        cur_movies CURSOR FOR
            SELECT m.movie_id, m.title, m.release_date,
                   m.vote_average, m.vote_count,
                   m.popularity, m.revenue, m.budget,
                   fn_get_movie_runtime_fmt(m.movie_id) AS runtime_fmt
            FROM   Movie m
            JOIN   Movie_Genre mg ON mg.movie_id = m.movie_id
            WHERE  mg.genre_id = p_genre_id
              AND  m.vote_count >= 100
            ORDER  BY m.vote_average DESC, m.vote_count DESC
            LIMIT  p_top_n;

        rec         RECORD;   
        v_rank      INTEGER := 0;
        v_roi       NUMERIC;
    BEGIN
        OPEN cur_movies;
        LOOP
            FETCH cur_movies INTO rec;
            EXIT WHEN NOT FOUND;
                    v_rank := v_rank + 1;
            IF rec.budget > 0 THEN
                v_roi := ROUND(
                    (rec.revenue - rec.budget)::NUMERIC / rec.budget * 100, 2
                );
            ELSE
                v_roi := NULL;
            END IF;
 
            INSERT INTO pbi_staging_top_movies
                (rank, genre_id, movie_id, title, release_date,
                 vote_average, vote_count, popularity,
                 runtime_fmt, roi_pct, generated_at)
            VALUES
                (v_rank, p_genre_id, rec.movie_id, rec.title,
                 rec.release_date, rec.vote_average, rec.vote_count,
                 rec.popularity, rec.runtime_fmt, v_roi, NOW())
            ON CONFLICT (genre_id, movie_id)
                DO UPDATE SET rank = v_rank, roi_pct = v_roi,
                              generated_at = NOW();

        END LOOP;
        CLOSE cur_movies;
    END;
    $$;
    """,
    """
    ALTER PROCEDURE public.sp_cur_top_rated_movies(IN p_genre_id integer, IN p_top_n integer) OWNER TO postgres;
    """,
    """
    CREATE FUNCTION public.sp_getmoviedetail(p_movie_id integer) RETURNS TABLE(movie_id integer, tmdb_movie_id integer, imdb_id character varying, title character varying, original_title character varying, original_language character, overview text, tagline character varying, release_date date, status character varying, revenue bigint, budget bigint, runtime smallint, runtime_fmt text, popularity numeric, vote_average numeric, vote_count integer, user_avg_rating numeric, user_review_count integer, poster_path character varying, backdrop_path character varying, homepage character varying, adult boolean, collection_id integer, collection_name character varying)
        LANGUAGE sql STABLE
        AS $$
        SELECT
            m.movie_id,
            m.tmdb_movie_id,
            m.imdb_id,
            m.title,
            m.original_title,
            m.original_language,
            m.overview,
            m.tagline,
            m.release_date,
            m.status,
            m.revenue,
            m.budget,
            m.runtime,
            fn_get_movie_runtime_fmt(m.movie_id),
            m.popularity,
            m.vote_average,
            m.vote_count,
            fn_get_movie_user_avg(m.movie_id),
            fn_get_movie_review_count(m.movie_id),
            m.poster_path,
            m.backdrop_path,
            m.homepage,
            m.adult,
            m.collection_id,
            c.name
        FROM  Movie m
        LEFT JOIN Collection c ON c.collection_id = m.collection_id
        WHERE m.movie_id = p_movie_id;
    $$;
    """,
    """
    ALTER FUNCTION public.sp_getmoviedetail(p_movie_id integer) OWNER TO postgres;
    """,
    """
    CREATE FUNCTION public.sp_getmoviesbygenre(p_genre_id integer, p_page integer DEFAULT 1, p_page_size integer DEFAULT 20) RETURNS TABLE(movie_id integer, title character varying, release_date date, popularity numeric, vote_average numeric, poster_path character varying)
        LANGUAGE sql STABLE
        AS $$
        SELECT
            m.movie_id,
            m.title,
            m.release_date,
            m.popularity,
            m.vote_average,
            m.poster_path
        FROM  Movie_Genre mg
        JOIN  Movie m ON m.movie_id = mg.movie_id
        WHERE mg.genre_id = p_genre_id
        ORDER BY m.popularity DESC
        LIMIT  p_page_size
        OFFSET (p_page - 1) * p_page_size;
    $$;
    """,
    """
    ALTER FUNCTION public.sp_getmoviesbygenre(p_genre_id integer, p_page integer, p_page_size integer) OWNER TO postgres;
    """,
    """
    CREATE FUNCTION public.sp_getmoviesneedingetlsync(p_interval interval DEFAULT '7 days'::interval, p_limit integer DEFAULT 100) RETURNS TABLE(movie_id integer, tmdb_movie_id integer, etl_synced_at timestamp with time zone)
        LANGUAGE sql STABLE
        AS $$
        SELECT movie_id, tmdb_movie_id, etl_synced_at
        FROM   Movie
        WHERE  fn_etl_needs_sync(etl_synced_at, p_interval)
        ORDER  BY etl_synced_at NULLS FIRST
        LIMIT  p_limit;
    $$;
    """,
    """
    ALTER FUNCTION public.sp_getmoviesneedingetlsync(p_interval interval, p_limit integer) OWNER TO postgres;
    """,
    """
    CREATE PROCEDURE public.sp_insertmoviecast(IN p_movie_id integer, IN p_person_id integer, IN p_cast_order smallint, IN p_character_name character varying DEFAULT ''::character varying, IN p_credit_id character varying DEFAULT NULL::character varying)
        LANGUAGE plpgsql
        AS $$
    BEGIN
        IF p_cast_order <= 0 THEN
            RAISE EXCEPTION 'cast_order phß║úi > 0, nhß║¡n ─æ╞░ß╗úc: %', p_cast_order;
        END IF;
        INSERT INTO Movie_Cast (movie_id, person_id, cast_order, character_name, credit_id)
        VALUES (p_movie_id, p_person_id, p_cast_order, COALESCE(p_character_name,''), p_credit_id)
        ON CONFLICT (movie_id, person_id, cast_order) DO UPDATE
            SET character_name = EXCLUDED.character_name,
                credit_id      = EXCLUDED.credit_id;
    END;
    $$;
    """,
    """
    ALTER PROCEDURE public.sp_insertmoviecast(IN p_movie_id integer, IN p_person_id integer, IN p_cast_order smallint, IN p_character_name character varying, IN p_credit_id character varying) OWNER TO postgres;
    """,
    """
    CREATE PROCEDURE public.sp_insertmoviecertification(IN p_movie_id integer, IN p_cert_std_id smallint)
        LANGUAGE plpgsql
        AS $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM Certification_Standard WHERE cert_std_id = p_cert_std_id) THEN
            RAISE EXCEPTION 'cert_std_id=% kh├┤ng tß╗ôn tß║íi.', p_cert_std_id;
        END IF;
        INSERT INTO Movie_Certification (movie_id, cert_std_id) VALUES (p_movie_id, p_cert_std_id) ON CONFLICT DO NOTHING;
    END;
    $$;
    """,
    """
    ALTER PROCEDURE public.sp_insertmoviecertification(IN p_movie_id integer, IN p_cert_std_id smallint) OWNER TO postgres;
    """,
    """
    CREATE PROCEDURE public.sp_insertmoviecompany(IN p_movie_id integer, IN p_company_id integer)
        LANGUAGE plpgsql
        AS $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM Company WHERE company_id = p_company_id) THEN
            RAISE EXCEPTION 'company_id=% kh├┤ng tß╗ôn tß║íi.', p_company_id;
        END IF;
        INSERT INTO Movie_Company (movie_id, company_id) VALUES (p_movie_id, p_company_id) ON CONFLICT DO NOTHING;
    END;
    $$;
    """,
    """
    ALTER PROCEDURE public.sp_insertmoviecompany(IN p_movie_id integer, IN p_company_id integer) OWNER TO postgres;
    """,
    """
    CREATE PROCEDURE public.sp_insertmoviecountry(IN p_movie_id integer, IN p_iso_3166_1 character)
        LANGUAGE plpgsql
        AS $$
    BEGIN
        INSERT INTO Movie_Country (movie_id, iso_3166_1) VALUES (p_movie_id, p_iso_3166_1) ON CONFLICT DO NOTHING;
    END;
    $$;
    """,
    """
    ALTER PROCEDURE public.sp_insertmoviecountry(IN p_movie_id integer, IN p_iso_3166_1 character) OWNER TO postgres;
    """,
    """
    CREATE PROCEDURE public.sp_insertmoviegenre(IN p_movie_id integer, IN p_genre_id integer)
        LANGUAGE plpgsql
        AS $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM Genre WHERE genre_id = p_genre_id AND media_type = 'movie') THEN
            RAISE EXCEPTION 'genre_id=% kh├┤ng tß╗ôn tß║íi vß╗¢i media_type=''movie''.', p_genre_id;
        END IF;
        INSERT INTO Movie_Genre (movie_id, genre_id) VALUES (p_movie_id, p_genre_id)
        ON CONFLICT DO NOTHING;
    END;
    $$;
    """,
    """
    ALTER PROCEDURE public.sp_insertmoviegenre(IN p_movie_id integer, IN p_genre_id integer) OWNER TO postgres;
    """,
    """
    CREATE PROCEDURE public.sp_insertmoviekeyword(IN p_movie_id integer, IN p_keyword_id integer, IN p_keyword_name character varying DEFAULT NULL::character varying)
        LANGUAGE plpgsql
        AS $$
    BEGIN
        IF p_keyword_name IS NOT NULL THEN
            INSERT INTO Keyword (keyword_id, name) VALUES (p_keyword_id, p_keyword_name)
            ON CONFLICT (keyword_id) DO NOTHING;
        END IF;
        INSERT INTO Movie_Keyword (movie_id, keyword_id) VALUES (p_movie_id, p_keyword_id)
        ON CONFLICT DO NOTHING;
    END;
    $$;
    """,
    """
    ALTER PROCEDURE public.sp_insertmoviekeyword(IN p_movie_id integer, IN p_keyword_id integer, IN p_keyword_name character varying) OWNER TO postgres;
    """,
    """
    CREATE PROCEDURE public.sp_insertmovielanguage(IN p_movie_id integer, IN p_iso_639_1 character, IN p_language_type character varying)
        LANGUAGE plpgsql
        AS $$
    BEGIN
        IF p_language_type NOT IN ('spoken','original') THEN
            RAISE EXCEPTION 'language_type kh├┤ng hß╗úp lß╗ç: "%"', p_language_type;
        END IF;
        INSERT INTO Movie_Language (movie_id, iso_639_1, language_type)
        VALUES (p_movie_id, p_iso_639_1, p_language_type) ON CONFLICT DO NOTHING;
    END;
    $$;
    """,
    """
    ALTER PROCEDURE public.sp_insertmovielanguage(IN p_movie_id integer, IN p_iso_639_1 character, IN p_language_type character varying) OWNER TO postgres;
    """,
    """
    CREATE PROCEDURE public.sp_insertmoviewatchprovider(IN p_movie_id integer, IN p_provider_id integer, IN p_iso_3166_1 character, IN p_availability_type character varying, IN p_display_priority smallint)
        LANGUAGE plpgsql
        AS $$
    BEGIN
        IF p_availability_type NOT IN ('flatrate','rent','buy','free','ads') THEN
            RAISE EXCEPTION 'availability_type kh├┤ng hß╗úp lß╗ç: "%"', p_availability_type;
        END IF;
        INSERT INTO Movie_Watch_Provider (movie_id, provider_id, iso_3166_1, availability_type, display_priority)
        VALUES (p_movie_id, p_provider_id, p_iso_3166_1, p_availability_type, p_display_priority)
        ON CONFLICT (movie_id, provider_id, iso_3166_1, availability_type) DO UPDATE
            SET display_priority = EXCLUDED.display_priority;
    END;
    $$;
    """,
    """
    ALTER PROCEDURE public.sp_insertmoviewatchprovider(IN p_movie_id integer, IN p_provider_id integer, IN p_iso_3166_1 character, IN p_availability_type character varying, IN p_display_priority smallint) OWNER TO postgres;
    """,
    """
    CREATE PROCEDURE public.sp_syncmoviecast(IN p_movie_id integer, IN p_cast jsonb)
        LANGUAGE plpgsql
        AS $$
    DECLARE
        v_item      JSONB;
        v_new_ids   TEXT[];
    BEGIN
        SELECT ARRAY(
            SELECT c->>'credit_id' FROM jsonb_array_elements(p_cast) c
            WHERE c->>'credit_id' IS NOT NULL
        ) INTO v_new_ids;

        DELETE FROM Movie_Cast
        WHERE movie_id  = p_movie_id
          AND credit_id IS NOT NULL
          AND credit_id != ALL(v_new_ids);

        FOR v_item IN SELECT * FROM jsonb_array_elements(p_cast) LOOP
            CALL sp_InsertMovieCast(
                p_movie_id,
                (v_item->>'person_id')::INTEGER,
                (v_item->>'cast_order')::SMALLINT,
                COALESCE(v_item->>'character_name', ''),
                v_item->>'credit_id'
            );
        END LOOP;
    END;
    $$;
    """,
    """
    ALTER PROCEDURE public.sp_syncmoviecast(IN p_movie_id integer, IN p_cast jsonb) OWNER TO postgres;
    """,
    """
    CREATE PROCEDURE public.sp_syncmoviecrew(IN p_movie_id integer, IN p_crew jsonb)
        LANGUAGE plpgsql
        AS $$
    DECLARE
        v_item    JSONB;
        v_new_ids TEXT[];
    BEGIN
        SELECT ARRAY(
            SELECT c->>'credit_id' FROM jsonb_array_elements(p_crew) c
            WHERE c->>'credit_id' IS NOT NULL
        ) INTO v_new_ids;

        DELETE FROM Movie_Crew
        WHERE movie_id  = p_movie_id
          AND credit_id IS NOT NULL
          AND credit_id != ALL(v_new_ids);

        FOR v_item IN SELECT * FROM jsonb_array_elements(p_crew) LOOP
            CALL sp_InsertMovieCrew(
                p_movie_id,
                (v_item->>'person_id')::INTEGER,
                (v_item->>'department_id')::SMALLINT,
                (v_item->>'job_id')::SMALLINT,
                v_item->>'credit_id'
            );
        END LOOP;
    END;
    $$;
    """,
    """
    ALTER PROCEDURE public.sp_syncmoviecrew(IN p_movie_id integer, IN p_crew jsonb) OWNER TO postgres;
    """,
    """
    CREATE PROCEDURE public.sp_syncmoviemetadata(IN p_movie_id integer, IN p_data jsonb)
        LANGUAGE plpgsql
        AS $$
    DECLARE
        v_item JSONB;
    BEGIN
        DELETE FROM Movie_Genre WHERE movie_id = p_movie_id;
        FOR v_item IN SELECT * FROM jsonb_array_elements(COALESCE(p_data->'genres', '[]'::JSONB)) LOOP
            CALL sp_InsertMovieGenre(p_movie_id, (v_item->>'id')::INTEGER);
        END LOOP;

        DELETE FROM Movie_Keyword WHERE movie_id = p_movie_id;
        FOR v_item IN SELECT * FROM jsonb_array_elements(COALESCE(p_data->'keywords', '[]'::JSONB)) LOOP
            CALL sp_InsertMovieKeyword(p_movie_id, (v_item->>'id')::INTEGER, v_item->>'name');
        END LOOP;

        DELETE FROM Movie_Language WHERE movie_id = p_movie_id;
        FOR v_item IN SELECT * FROM jsonb_array_elements(COALESCE(p_data->'spoken_languages', '[]'::JSONB)) LOOP
            CALL sp_InsertMovieLanguage(p_movie_id, v_item->>'iso_639_1', 'spoken');
        END LOOP;

        DELETE FROM Movie_Country WHERE movie_id = p_movie_id;
        FOR v_item IN SELECT * FROM jsonb_array_elements(COALESCE(p_data->'production_countries', '[]'::JSONB)) LOOP
            CALL sp_InsertMovieCountry(p_movie_id, v_item->>'iso_3166_1');
        END LOOP;

        DELETE FROM Movie_Company WHERE movie_id = p_movie_id;
        FOR v_item IN SELECT * FROM jsonb_array_elements(COALESCE(p_data->'production_companies', '[]'::JSONB)) LOOP
            CALL sp_InsertMovieCompany(p_movie_id, (v_item->>'id')::INTEGER);
        END LOOP;

        DELETE FROM Movie_Certification WHERE movie_id = p_movie_id;
        FOR v_item IN SELECT * FROM jsonb_array_elements(COALESCE(p_data->'certifications', '[]'::JSONB)) LOOP
            CALL sp_InsertMovieCertification(p_movie_id, (v_item->>'cert_std_id')::SMALLINT);
        END LOOP;
    END;
    $$;
    """,
    """
    ALTER PROCEDURE public.sp_syncmoviemetadata(IN p_movie_id integer, IN p_data jsonb) OWNER TO postgres;
    """,
    """
    CREATE PROCEDURE public.sp_togglemoviefavorite(IN p_user_id integer, IN p_movie_id integer)
        LANGUAGE plpgsql
        AS $$
    BEGIN
        IF EXISTS (SELECT 1 FROM User_Movie_Favorite WHERE user_id = p_user_id AND movie_id = p_movie_id) THEN
            DELETE FROM User_Movie_Favorite WHERE user_id = p_user_id AND movie_id = p_movie_id;
        ELSE
            INSERT INTO User_Movie_Favorite (user_id, movie_id) VALUES (p_user_id, p_movie_id);
        END IF;
    END;
    $$;
    """,
    """
    ALTER PROCEDURE public.sp_togglemoviefavorite(IN p_user_id integer, IN p_movie_id integer) OWNER TO postgres;
    """,
    """
    CREATE PROCEDURE public.sp_togglemoviewatchlist(IN p_user_id integer, IN p_movie_id integer)
        LANGUAGE plpgsql
        AS $$
    BEGIN
        IF EXISTS (SELECT 1 FROM User_Movie_Watchlist WHERE user_id = p_user_id AND movie_id = p_movie_id) THEN
            DELETE FROM User_Movie_Watchlist WHERE user_id = p_user_id AND movie_id = p_movie_id;
        ELSE
            INSERT INTO User_Movie_Watchlist (user_id, movie_id) VALUES (p_user_id, p_movie_id);
        END IF;
    END;
    $$;
    """,
    """
    ALTER PROCEDURE public.sp_togglemoviewatchlist(IN p_user_id integer, IN p_movie_id integer) OWNER TO postgres;
    """,
    """
    CREATE PROCEDURE public.sp_upsertmovie(IN p_data jsonb)
        LANGUAGE plpgsql
        AS $$
    DECLARE
        v_movie_id     INTEGER;
        v_tmdb_id      INTEGER;
        v_collection_id INTEGER;
        v_item         JSONB;
    BEGIN
        v_tmdb_id := (p_data->>'tmdb_movie_id')::INTEGER;
        IF v_tmdb_id IS NULL THEN
            RAISE EXCEPTION 'tmdb_movie_id l├á bß║»t buß╗Öc trong JSONB payload.';
        END IF;

        IF p_data->'collection' IS NOT NULL AND p_data->'collection' != 'null' THEN
            v_collection_id := (p_data->'collection'->>'id')::INTEGER;
            CALL sp_UpsertCollection(
                v_collection_id,
                p_data->'collection'->>'name',
                p_data->'collection'->>'original_name',
                NULL, NULL,
                p_data->'collection'->>'poster_path',
                p_data->'collection'->>'backdrop_path'
            );
        ELSE
            v_collection_id := NULL;
        END IF;

        INSERT INTO Movie (
            movie_id, tmdb_movie_id, imdb_id,
            title, original_title, original_language,
            overview, tagline, release_date, status,
            revenue, budget, runtime,
            popularity, vote_average, vote_count,
            poster_path, backdrop_path, homepage,
            adult, collection_id, etl_synced_at
        )
        VALUES (
            v_tmdb_id,
            v_tmdb_id,
            p_data->>'imdb_id',
            p_data->>'title',
            p_data->>'original_title',
            p_data->>'original_language',
            p_data->>'overview',
            p_data->>'tagline',
            NULLIF(p_data->>'release_date','')::DATE,
            p_data->>'status',
            COALESCE((p_data->>'revenue')::BIGINT, 0),
            COALESCE((p_data->>'budget')::BIGINT, 0),
            NULLIF(p_data->>'runtime','')::SMALLINT,
            COALESCE((p_data->>'popularity')::NUMERIC, 0),
            COALESCE((p_data->>'vote_average')::NUMERIC, 0),
            COALESCE((p_data->>'vote_count')::INTEGER, 0),
            p_data->>'poster_path',
            p_data->>'backdrop_path',
            p_data->>'homepage',
            COALESCE((p_data->>'adult')::BOOLEAN, FALSE),
            v_collection_id,
            NOW()
        )
        ON CONFLICT (tmdb_movie_id) DO UPDATE
            SET imdb_id           = EXCLUDED.imdb_id,
                title             = EXCLUDED.title,
                original_title    = EXCLUDED.original_title,
                original_language = EXCLUDED.original_language,
                overview          = EXCLUDED.overview,
                tagline           = EXCLUDED.tagline,
                release_date      = EXCLUDED.release_date,
                status            = EXCLUDED.status,
                revenue           = EXCLUDED.revenue,
                budget            = EXCLUDED.budget,
                runtime           = EXCLUDED.runtime,
                popularity        = EXCLUDED.popularity,
                vote_average      = EXCLUDED.vote_average,
                vote_count        = EXCLUDED.vote_count,
                poster_path       = EXCLUDED.poster_path,
                backdrop_path     = EXCLUDED.backdrop_path,
                homepage          = EXCLUDED.homepage,
                adult             = EXCLUDED.adult,
                collection_id     = EXCLUDED.collection_id,
                etl_synced_at     = NOW(),
                updated_at        = NOW()
        RETURNING movie_id INTO v_movie_id;

        CALL sp_SyncMovieMetadata(v_movie_id, p_data);

        IF p_data->'cast' IS NOT NULL THEN
            CALL sp_SyncMovieCast(v_movie_id, p_data->'cast');
        END IF;

        IF p_data->'crew' IS NOT NULL THEN
            CALL sp_SyncMovieCrew(v_movie_id, p_data->'crew');
        END IF;

        IF p_data->'watch_providers' IS NOT NULL THEN
            DELETE FROM Movie_Watch_Provider WHERE movie_id = v_movie_id;
            FOR v_item IN SELECT * FROM jsonb_array_elements(p_data->'watch_providers') LOOP
                CALL sp_InsertMovieWatchProvider(
                    v_movie_id,
                    (v_item->>'provider_id')::INTEGER,
                    v_item->>'iso_3166_1',
                    v_item->>'availability_type',
                    (v_item->>'display_priority')::SMALLINT
                );
            END LOOP;
        END IF;
    END;
    $$;
    """,
    """
    ALTER PROCEDURE public.sp_upsertmovie(IN p_data jsonb) OWNER TO postgres;
    """,
    # --- tables ---
    """
    CREATE TABLE public.movie (
        movie_id integer NOT NULL,
        tmdb_movie_id integer NOT NULL,
        imdb_id character varying(20),
        title character varying(500) NOT NULL,
        original_title character varying(500) NOT NULL,
        original_language character(2) NOT NULL,
        overview text,
        tagline character varying(500),
        release_date date,
        status character varying(50),
        revenue bigint DEFAULT 0 NOT NULL,
        budget bigint DEFAULT 0 NOT NULL,
        runtime smallint,
        popularity numeric(8,3) DEFAULT 0 NOT NULL,
        vote_average numeric(4,2) DEFAULT 0 NOT NULL,
        vote_count integer DEFAULT 0 NOT NULL,
        poster_path character varying(300),
        backdrop_path character varying(300),
        homepage character varying(500),
        adult boolean DEFAULT false NOT NULL,
        collection_id integer,
        etl_synced_at timestamp with time zone,
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        updated_at timestamp with time zone DEFAULT now() NOT NULL,
        CONSTRAINT chk_movie_budget CHECK ((budget >= 0)),
        CONSTRAINT chk_movie_popularity CHECK ((popularity >= (0)::numeric)),
        CONSTRAINT chk_movie_release_date CHECK (((release_date IS NULL) OR (release_date >= '1888-01-01'::date))),
        CONSTRAINT chk_movie_revenue CHECK ((revenue >= 0)),
        CONSTRAINT chk_movie_runtime CHECK (((runtime IS NULL) OR (runtime > 0))),
        CONSTRAINT chk_movie_status CHECK (((status)::text = ANY ((ARRAY['Rumored'::character varying, 'Planned'::character varying, 'In Production'::character varying, 'Post Production'::character varying, 'Released'::character varying, 'Canceled'::character varying])::text[]))),
        CONSTRAINT chk_movie_vote_average CHECK (((vote_average >= (0)::numeric) AND (vote_average <= (10)::numeric))),
        CONSTRAINT chk_movie_vote_count CHECK ((vote_count >= 0))
    );
    """,
    """
    ALTER TABLE public.movie OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.movie
        ADD CONSTRAINT movie_pkey PRIMARY KEY (movie_id);
    """,
    """
    ALTER TABLE ONLY public.movie
        ADD CONSTRAINT uq_movie_imdb_id UNIQUE (imdb_id);
    """,
    """
    ALTER TABLE ONLY public.movie
        ADD CONSTRAINT uq_movie_tmdb_id UNIQUE (tmdb_movie_id);
    """,
    """
    CREATE TABLE public.movie_cast (
        movie_id integer NOT NULL,
        person_id integer NOT NULL,
        cast_order smallint NOT NULL,
        character_name character varying(300) DEFAULT ''::character varying NOT NULL,
        credit_id character varying(50),
        CONSTRAINT chk_movie_cast_order CHECK ((cast_order > 0))
    );
    """,
    """
    ALTER TABLE public.movie_cast OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.movie_cast
        ADD CONSTRAINT movie_cast_pkey PRIMARY KEY (movie_id, person_id, cast_order);
    """,
    """
    ALTER TABLE ONLY public.movie_cast
        ADD CONSTRAINT uq_movie_cast_credit UNIQUE (credit_id);
    """,
    """
    CREATE TABLE public.movie_certification (
        movie_id integer NOT NULL,
        cert_std_id smallint NOT NULL,
        country_code character(2) NOT NULL,
        language_code character(2) NOT NULL,
        release_type smallint NOT NULL,
        descriptors text
    );
    """,
    """
    ALTER TABLE public.movie_certification OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.movie_certification
        ADD CONSTRAINT movie_certification_pkey PRIMARY KEY (movie_id, country_code, language_code, release_type);
    """,
    """
    CREATE TABLE public.movie_company (
        movie_id integer NOT NULL,
        company_id integer NOT NULL
    );
    """,
    """
    ALTER TABLE public.movie_company OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.movie_company
        ADD CONSTRAINT movie_company_pkey PRIMARY KEY (movie_id, company_id);
    """,
    """
    CREATE TABLE public.movie_country (
        movie_id integer NOT NULL,
        iso_3166_1 character(2) NOT NULL
    );
    """,
    """
    ALTER TABLE public.movie_country OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.movie_country
        ADD CONSTRAINT movie_country_pkey PRIMARY KEY (movie_id, iso_3166_1);
    """,
    """
    CREATE TABLE public.movie_crew (
        movie_id integer NOT NULL,
        person_id integer NOT NULL,
        department_id smallint NOT NULL,
        job_id smallint NOT NULL,
        credit_id character varying(50)
    );
    """,
    """
    ALTER TABLE public.movie_crew OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.movie_crew
        ADD CONSTRAINT movie_crew_pkey PRIMARY KEY (movie_id, person_id, department_id, job_id);
    """,
    """
    ALTER TABLE ONLY public.movie_crew
        ADD CONSTRAINT uq_movie_crew_credit UNIQUE (credit_id);
    """,
    """
    CREATE TABLE public.movie_genre (
        movie_id integer NOT NULL,
        genre_id integer NOT NULL
    );
    """,
    """
    ALTER TABLE public.movie_genre OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.movie_genre
        ADD CONSTRAINT movie_genre_pkey PRIMARY KEY (movie_id, genre_id);
    """,
    """
    CREATE TABLE public.movie_keyword (
        movie_id integer NOT NULL,
        keyword_id integer NOT NULL
    );
    """,
    """
    ALTER TABLE public.movie_keyword OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.movie_keyword
        ADD CONSTRAINT movie_keyword_pkey PRIMARY KEY (movie_id, keyword_id);
    """,
    """
    CREATE TABLE public.movie_language (
        movie_id integer NOT NULL,
        iso_639_1 character(2) NOT NULL,
        language_type character varying(10) NOT NULL,
        CONSTRAINT chk_movie_language_type CHECK (((language_type)::text = ANY ((ARRAY['spoken'::character varying, 'original'::character varying])::text[])))
    );
    """,
    """
    ALTER TABLE public.movie_language OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.movie_language
        ADD CONSTRAINT movie_language_pkey PRIMARY KEY (movie_id, iso_639_1, language_type);
    """,
    """
    CREATE TABLE public.movie_watch_provider (
        movie_id integer NOT NULL,
        provider_id integer NOT NULL,
        iso_3166_1 character(2) NOT NULL,
        availability_type character varying(10) NOT NULL,
        display_priority smallint NOT NULL,
        CONSTRAINT chk_watch_avail_movie CHECK (((availability_type)::text = ANY ((ARRAY['flatrate'::character varying, 'rent'::character varying, 'buy'::character varying, 'free'::character varying, 'ads'::character varying])::text[])))
    );
    """,
    """
    ALTER TABLE public.movie_watch_provider OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.movie_watch_provider
        ADD CONSTRAINT movie_watch_provider_pkey PRIMARY KEY (movie_id, provider_id, iso_3166_1, availability_type);
    """,
    # --- triggers ---
    """
    CREATE TRIGGER trg_audit_movie AFTER INSERT OR DELETE OR UPDATE ON public.movie FOR EACH ROW EXECUTE FUNCTION public.fn_trg_audit_log('movie_id');
    """,
    """
    CREATE TRIGGER trg_set_updated_at_movie BEFORE UPDATE ON public.movie FOR EACH ROW EXECUTE FUNCTION public.fn_trg_set_updated_at();
    """,
    # --- foreign keys ---
    """
    ALTER TABLE ONLY public.movie_certification
        ADD CONSTRAINT fk_cert_std FOREIGN KEY (cert_std_id) REFERENCES public.certification_standard(cert_std_id);
    """,
    """
    ALTER TABLE ONLY public.movie_cast
        ADD CONSTRAINT movie_cast_movie_id_fkey FOREIGN KEY (movie_id) REFERENCES public.movie(movie_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.movie_cast
        ADD CONSTRAINT movie_cast_person_id_fkey FOREIGN KEY (person_id) REFERENCES public.person(person_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.movie_certification
        ADD CONSTRAINT movie_certification_cert_std_id_fkey FOREIGN KEY (cert_std_id) REFERENCES public.certification_standard(cert_std_id);
    """,
    """
    ALTER TABLE ONLY public.movie_certification
        ADD CONSTRAINT movie_certification_movie_id_fkey FOREIGN KEY (movie_id) REFERENCES public.movie(movie_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.movie
        ADD CONSTRAINT movie_collection_id_fkey FOREIGN KEY (collection_id) REFERENCES public.collection(collection_id);
    """,
    """
    ALTER TABLE ONLY public.movie_company
        ADD CONSTRAINT movie_company_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.company(company_id);
    """,
    """
    ALTER TABLE ONLY public.movie_company
        ADD CONSTRAINT movie_company_movie_id_fkey FOREIGN KEY (movie_id) REFERENCES public.movie(movie_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.movie_country
        ADD CONSTRAINT movie_country_iso_3166_1_fkey FOREIGN KEY (iso_3166_1) REFERENCES public.country(iso_3166_1);
    """,
    """
    ALTER TABLE ONLY public.movie_country
        ADD CONSTRAINT movie_country_movie_id_fkey FOREIGN KEY (movie_id) REFERENCES public.movie(movie_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.movie_crew
        ADD CONSTRAINT movie_crew_department_id_fkey FOREIGN KEY (department_id) REFERENCES public.department(department_id);
    """,
    """
    ALTER TABLE ONLY public.movie_crew
        ADD CONSTRAINT movie_crew_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.job(job_id);
    """,
    """
    ALTER TABLE ONLY public.movie_crew
        ADD CONSTRAINT movie_crew_movie_id_fkey FOREIGN KEY (movie_id) REFERENCES public.movie(movie_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.movie_crew
        ADD CONSTRAINT movie_crew_person_id_fkey FOREIGN KEY (person_id) REFERENCES public.person(person_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.movie_genre
        ADD CONSTRAINT movie_genre_genre_id_fkey FOREIGN KEY (genre_id) REFERENCES public.genre(genre_id);
    """,
    """
    ALTER TABLE ONLY public.movie_genre
        ADD CONSTRAINT movie_genre_movie_id_fkey FOREIGN KEY (movie_id) REFERENCES public.movie(movie_id);
    """,
    """
    ALTER TABLE ONLY public.movie_keyword
        ADD CONSTRAINT movie_keyword_keyword_id_fkey FOREIGN KEY (keyword_id) REFERENCES public.keyword(keyword_id);
    """,
    """
    ALTER TABLE ONLY public.movie_keyword
        ADD CONSTRAINT movie_keyword_movie_id_fkey FOREIGN KEY (movie_id) REFERENCES public.movie(movie_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.movie_language
        ADD CONSTRAINT movie_language_iso_639_1_fkey FOREIGN KEY (iso_639_1) REFERENCES public.language(iso_639_1);
    """,
    """
    ALTER TABLE ONLY public.movie_language
        ADD CONSTRAINT movie_language_movie_id_fkey FOREIGN KEY (movie_id) REFERENCES public.movie(movie_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.movie
        ADD CONSTRAINT movie_original_language_fkey FOREIGN KEY (original_language) REFERENCES public.language(iso_639_1);
    """,
    """
    ALTER TABLE ONLY public.movie_watch_provider
        ADD CONSTRAINT movie_watch_provider_iso_3166_1_fkey FOREIGN KEY (iso_3166_1) REFERENCES public.country(iso_3166_1);
    """,
    """
    ALTER TABLE ONLY public.movie_watch_provider
        ADD CONSTRAINT movie_watch_provider_movie_id_fkey FOREIGN KEY (movie_id) REFERENCES public.movie(movie_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.movie_watch_provider
        ADD CONSTRAINT movie_watch_provider_provider_id_fkey FOREIGN KEY (provider_id) REFERENCES public.watch_provider(provider_id);
    """,
]


def run():
    """Execute all DDL statements for this module in order, inside one transaction."""
    with db_utils.db_transaction() as (conn, cur):
        for i, stmt in enumerate(DDL_STATEMENTS, start=1):
            try:
                cur.execute(stmt)
            except Exception:
                logger.error("Failed on statement #%d of %d in schema_movie.py", i, len(DDL_STATEMENTS))
                raise
    logger.info("schema_movie.py: executed %d statements successfully.", len(DDL_STATEMENTS))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
