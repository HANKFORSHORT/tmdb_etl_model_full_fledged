"""
TV series domain: TV_Series, seasons, episodes, and all TV_*/Episode_* join
tables (cast, crew, creators, genre, keyword, company, country, language,
certification, watch provider).
Depends on: schema_shared.py, schema_reference.py

Auto-generated from a pg_dump schema export and split into domain modules
mirroring the etl_movie.py / etl_tv_series.py / etl_reference.py convention
used elsewhere in this repo. Run directly to create these objects in the
target database:

    python schema_tv_series.py

Uses db_utils.get_connection() / db_utils.db_transaction() for the actual
connection, same as the rest of the ETL codebase.
"""

import logging

import db_utils

logger = logging.getLogger(__name__)

DDL_STATEMENTS = [
    #
    """
    CREATE FUNCTION public.fn_get_tv_runtime_fmt(p_series_id integer) RETURNS text
        LANGUAGE plpgsql STABLE
        AS $$
    DECLARE
        v_total INTEGER;
    BEGIN
        SELECT COALESCE(SUM(runtime), 0)
        INTO   v_total
        FROM   TV_Episode
        WHERE  series_id = p_series_id AND runtime IS NOT NULL;

        IF v_total = 0 THEN RETURN NULL; END IF;
        RETURN (v_total / 60)::TEXT || 'h ' || (v_total % 60)::TEXT || 'm';
    END;
    $$;
    """,
    """
    ALTER FUNCTION public.fn_get_tv_runtime_fmt(p_series_id integer) OWNER TO postgres;
    """,
    """
    CREATE FUNCTION public.sp_gettvseriesdetail(p_series_id integer) RETURNS TABLE(series_id integer, tmdb_series_id integer, name character varying, original_name character varying, original_language character, overview text, tagline character varying, first_air_date date, last_air_date date, status character varying, type character varying, in_production boolean, homepage character varying, popularity numeric, vote_average numeric, vote_count integer, poster_path character varying, backdrop_path character varying, adult boolean)
        LANGUAGE sql STABLE
        AS $$
        SELECT
            series_id, tmdb_series_id, name, original_name, original_language,
            overview, tagline, first_air_date, last_air_date, status, type,
            in_production, homepage, popularity, vote_average, vote_count,
            poster_path, backdrop_path, adult
        FROM  TV_Series
        WHERE series_id = p_series_id;
    $$;
    """,
    """
    ALTER FUNCTION public.sp_gettvseriesdetail(p_series_id integer) OWNER TO postgres;
    """,
    """
    CREATE FUNCTION public.sp_gettvseriesneedingetlsync(p_interval interval DEFAULT '7 days'::interval, p_limit integer DEFAULT 100) RETURNS TABLE(series_id integer, tmdb_series_id integer, etl_synced_at timestamp with time zone)
        LANGUAGE sql STABLE
        AS $$
        SELECT series_id, tmdb_series_id, etl_synced_at
        FROM   TV_Series
        WHERE  fn_etl_needs_sync(etl_synced_at, p_interval)
        ORDER  BY etl_synced_at NULLS FIRST
        LIMIT  p_limit;
    $$;
    """,
    """
    ALTER FUNCTION public.sp_gettvseriesneedingetlsync(p_interval interval, p_limit integer) OWNER TO postgres;
    """,
    """
    CREATE PROCEDURE public.sp_inserttvcast(IN p_series_id integer, IN p_person_id integer, IN p_cast_order smallint, IN p_character character varying DEFAULT ''::character varying, IN p_credit_id character varying DEFAULT NULL::character varying)
        LANGUAGE plpgsql
        AS $$
    BEGIN
        IF p_cast_order <= 0 THEN RAISE EXCEPTION 'cast_order phß║úi > 0'; END IF;
        INSERT INTO TV_Cast (series_id, person_id, cast_order, character_name, credit_id)
        VALUES (p_series_id, p_person_id, p_cast_order, COALESCE(p_character,''), p_credit_id)
        ON CONFLICT (series_id, person_id, cast_order) DO UPDATE
            SET character_name = EXCLUDED.character_name, credit_id = EXCLUDED.credit_id;
    END;
    $$;
    """,
    """
    ALTER PROCEDURE public.sp_inserttvcast(IN p_series_id integer, IN p_person_id integer, IN p_cast_order smallint, IN p_character character varying, IN p_credit_id character varying) OWNER TO postgres;
    """,
    """
    CREATE PROCEDURE public.sp_inserttvcreator(IN p_series_id integer, IN p_person_id integer, IN p_credit_id character varying DEFAULT NULL::character varying)
        LANGUAGE plpgsql
        AS $$
    BEGIN
        INSERT INTO TV_Creator (series_id, person_id, credit_id)
        VALUES (p_series_id, p_person_id, p_credit_id)
        ON CONFLICT (series_id, person_id) DO NOTHING;
    END;
    $$;
    """,
    """
    ALTER PROCEDURE public.sp_inserttvcreator(IN p_series_id integer, IN p_person_id integer, IN p_credit_id character varying) OWNER TO postgres;
    """,
    """
    CREATE PROCEDURE public.sp_inserttvcrew(IN p_series_id integer, IN p_person_id integer, IN p_department_id smallint, IN p_job_id smallint, IN p_credit_id character varying DEFAULT NULL::character varying)
        LANGUAGE plpgsql
        AS $$
    BEGIN
        INSERT INTO TV_Crew (series_id, person_id, department_id, job_id, credit_id)
        VALUES (p_series_id, p_person_id, p_department_id, p_job_id, p_credit_id)
        ON CONFLICT (series_id, person_id, department_id, job_id) DO UPDATE
            SET credit_id = EXCLUDED.credit_id;
    END;
    $$;
    """,
    """
    ALTER PROCEDURE public.sp_inserttvcrew(IN p_series_id integer, IN p_person_id integer, IN p_department_id smallint, IN p_job_id smallint, IN p_credit_id character varying) OWNER TO postgres;
    """,
    """
    CREATE PROCEDURE public.sp_synctvcast(IN p_series_id integer, IN p_cast jsonb)
        LANGUAGE plpgsql
        AS $$
    DECLARE
        v_item JSONB; v_new_ids TEXT[];
    BEGIN
        SELECT ARRAY(SELECT c->>'credit_id' FROM jsonb_array_elements(p_cast) c WHERE c->>'credit_id' IS NOT NULL) INTO v_new_ids;
        DELETE FROM TV_Cast WHERE series_id = p_series_id AND credit_id IS NOT NULL AND credit_id != ALL(v_new_ids);
        FOR v_item IN SELECT * FROM jsonb_array_elements(p_cast) LOOP
            CALL sp_InsertTVCast(p_series_id,(v_item->>'person_id')::INTEGER,(v_item->>'cast_order')::SMALLINT,
                COALESCE(v_item->>'character_name',''),v_item->>'credit_id');
        END LOOP;
    END;
    $$;
    """,
    """
    ALTER PROCEDURE public.sp_synctvcast(IN p_series_id integer, IN p_cast jsonb) OWNER TO postgres;
    """,
    """
    CREATE PROCEDURE public.sp_synctvcreators(IN p_series_id integer, IN p_creators jsonb)
        LANGUAGE plpgsql
        AS $$
    DECLARE v_item JSONB;
    BEGIN
        DELETE FROM TV_Creator WHERE series_id = p_series_id;
        FOR v_item IN SELECT * FROM jsonb_array_elements(p_creators) LOOP
            CALL sp_InsertTVCreator(p_series_id,(v_item->>'person_id')::INTEGER,v_item->>'credit_id');
        END LOOP;
    END;
    $$;
    """,
    """
    ALTER PROCEDURE public.sp_synctvcreators(IN p_series_id integer, IN p_creators jsonb) OWNER TO postgres;
    """,
    """
    CREATE PROCEDURE public.sp_synctvcrew(IN p_series_id integer, IN p_crew jsonb)
        LANGUAGE plpgsql
        AS $$
    DECLARE
        v_item JSONB; v_new_ids TEXT[];
    BEGIN
        SELECT ARRAY(SELECT c->>'credit_id' FROM jsonb_array_elements(p_crew) c WHERE c->>'credit_id' IS NOT NULL) INTO v_new_ids;
        DELETE FROM TV_Crew WHERE series_id = p_series_id AND credit_id IS NOT NULL AND credit_id != ALL(v_new_ids);
        FOR v_item IN SELECT * FROM jsonb_array_elements(p_crew) LOOP
            CALL sp_InsertTVCrew(p_series_id,(v_item->>'person_id')::INTEGER,(v_item->>'department_id')::SMALLINT,
                (v_item->>'job_id')::SMALLINT,v_item->>'credit_id');
        END LOOP;
    END;
    $$;
    """,
    """
    ALTER PROCEDURE public.sp_synctvcrew(IN p_series_id integer, IN p_crew jsonb) OWNER TO postgres;
    """,
    # --- tables ---
    """
    CREATE TABLE public.episode_cast (
        episode_id integer NOT NULL,
        person_id integer NOT NULL,
        cast_order smallint NOT NULL,
        character_name character varying(300) DEFAULT ''::character varying NOT NULL,
        credit_id character varying(50),
        is_guest boolean DEFAULT false NOT NULL,
        CONSTRAINT chk_episode_cast_order CHECK ((cast_order > 0))
    );
    """,
    """
    ALTER TABLE public.episode_cast OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.episode_cast
        ADD CONSTRAINT episode_cast_pkey PRIMARY KEY (episode_id, person_id, cast_order);
    """,
    """
    CREATE TABLE public.episode_crew (
        episode_id integer NOT NULL,
        person_id integer NOT NULL,
        department_id smallint NOT NULL,
        job_id smallint NOT NULL,
        credit_id character varying(50)
    );
    """,
    """
    ALTER TABLE public.episode_crew OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.episode_crew
        ADD CONSTRAINT episode_crew_pkey PRIMARY KEY (episode_id, person_id, department_id, job_id);
    """,
    """
    CREATE TABLE public.tv_cast (
        series_id integer NOT NULL,
        person_id integer NOT NULL,
        cast_order smallint NOT NULL,
        character_name character varying(300) DEFAULT ''::character varying NOT NULL,
        credit_id character varying(50),
        CONSTRAINT chk_tv_cast_order CHECK ((cast_order > 0))
    );
    """,
    """
    ALTER TABLE public.tv_cast OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.tv_cast
        ADD CONSTRAINT tv_cast_pkey PRIMARY KEY (series_id, person_id, cast_order);
    """,
    """
    ALTER TABLE ONLY public.tv_cast
        ADD CONSTRAINT uq_tv_cast_credit UNIQUE (credit_id);
    """,
    """
    CREATE TABLE public.tv_certification (
        series_id integer NOT NULL,
        iso_3166_1 character(2) NOT NULL,
        rating character varying(20) NOT NULL,
        descriptors text[],
        CONSTRAINT chk_tv_cert_rating_nonempty CHECK (((rating)::text <> ''::text))
    );
    """,
    """
    ALTER TABLE public.tv_certification OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.tv_certification
        ADD CONSTRAINT tv_certification_pkey PRIMARY KEY (series_id, iso_3166_1);
    """,
    """
    CREATE TABLE public.tv_company (
        series_id integer NOT NULL,
        company_id integer NOT NULL
    );
    """,
    """
    ALTER TABLE public.tv_company OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.tv_company
        ADD CONSTRAINT tv_company_pkey PRIMARY KEY (series_id, company_id);
    """,
    """
    CREATE TABLE public.tv_country (
        series_id integer NOT NULL,
        iso_3166_1 character(2) NOT NULL
    );
    """,
    """
    ALTER TABLE public.tv_country OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.tv_country
        ADD CONSTRAINT tv_country_pkey PRIMARY KEY (series_id, iso_3166_1);
    """,
    """
    CREATE TABLE public.tv_creator (
        series_id integer NOT NULL,
        person_id integer NOT NULL,
        credit_id character varying(50)
    );
    """,
    """
    ALTER TABLE public.tv_creator OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.tv_creator
        ADD CONSTRAINT tv_creator_pkey PRIMARY KEY (series_id, person_id);
    """,
    """
    ALTER TABLE ONLY public.tv_creator
        ADD CONSTRAINT uq_tv_creator_credit UNIQUE (credit_id);
    """,
    """
    CREATE TABLE public.tv_crew (
        series_id integer NOT NULL,
        person_id integer NOT NULL,
        department_id smallint NOT NULL,
        job_id smallint NOT NULL,
        credit_id character varying(50)
    );
    """,
    """
    ALTER TABLE public.tv_crew OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.tv_crew
        ADD CONSTRAINT tv_crew_pkey PRIMARY KEY (series_id, person_id, department_id, job_id);
    """,
    """
    ALTER TABLE ONLY public.tv_crew
        ADD CONSTRAINT uq_tv_crew_credit UNIQUE (credit_id);
    """,
    """
    CREATE TABLE public.tv_episode (
        episode_id integer NOT NULL,
        tmdb_episode_id integer,
        season_id integer NOT NULL,
        series_id integer NOT NULL,
        episode_number smallint NOT NULL,
        episode_type character varying(50),
        name character varying(300) NOT NULL,
        overview text,
        air_date date,
        runtime smallint,
        production_code character varying(100),
        still_path character varying(300),
        vote_average numeric(4,2),
        vote_count integer DEFAULT 0 NOT NULL,
        CONSTRAINT chk_episode_number CHECK ((episode_number > 0)),
        CONSTRAINT chk_episode_runtime CHECK (((runtime IS NULL) OR (runtime > 0))),
        CONSTRAINT chk_episode_vote CHECK (((vote_average IS NULL) OR ((vote_average >= (0)::numeric) AND (vote_average <= (10)::numeric)))),
        CONSTRAINT chk_episode_vote_count CHECK ((vote_count >= 0))
    );
    """,
    """
    ALTER TABLE public.tv_episode OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.tv_episode
        ADD CONSTRAINT tv_episode_pkey PRIMARY KEY (episode_id);
    """,
    """
    ALTER TABLE ONLY public.tv_episode
        ADD CONSTRAINT uq_episode_per_season UNIQUE (season_id, episode_number);
    """,
    """
    ALTER TABLE ONLY public.tv_episode
        ADD CONSTRAINT uq_episode_tmdb_id UNIQUE (tmdb_episode_id);
    """,
    """
    CREATE TABLE public.tv_genre (
        series_id integer NOT NULL,
        genre_id integer NOT NULL
    );
    """,
    """
    ALTER TABLE public.tv_genre OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.tv_genre
        ADD CONSTRAINT tv_genre_pkey PRIMARY KEY (series_id, genre_id);
    """,
    """
    CREATE TABLE public.tv_keyword (
        series_id integer NOT NULL,
        keyword_id integer NOT NULL
    );
    """,
    """
    ALTER TABLE public.tv_keyword OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.tv_keyword
        ADD CONSTRAINT tv_keyword_pkey PRIMARY KEY (series_id, keyword_id);
    """,
    """
    CREATE TABLE public.tv_language (
        series_id integer NOT NULL,
        iso_639_1 character(2) NOT NULL
    );
    """,
    """
    ALTER TABLE public.tv_language OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.tv_language
        ADD CONSTRAINT tv_language_pkey PRIMARY KEY (series_id, iso_639_1);
    """,
    """
    CREATE TABLE public.tv_season (
        season_id integer NOT NULL,
        tmdb_season_id integer,
        series_id integer NOT NULL,
        season_number smallint NOT NULL,
        name character varying(300),
        overview text,
        air_date date,
        poster_path character varying(300),
        vote_average numeric(4,2),
        episode_count smallint,
        CONSTRAINT chk_season_number CHECK ((season_number >= 0)),
        CONSTRAINT chk_season_vote CHECK (((vote_average IS NULL) OR ((vote_average >= (0)::numeric) AND (vote_average <= (10)::numeric))))
    );
    """,
    """
    ALTER TABLE public.tv_season OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.tv_season
        ADD CONSTRAINT tv_season_pkey PRIMARY KEY (season_id);
    """,
    """
    ALTER TABLE ONLY public.tv_season
        ADD CONSTRAINT uq_season_per_series UNIQUE (series_id, season_number);
    """,
    """
    ALTER TABLE ONLY public.tv_season
        ADD CONSTRAINT uq_season_tmdb_id UNIQUE (tmdb_season_id);
    """,
    """
    CREATE TABLE public.tv_series (
        series_id integer NOT NULL,
        tmdb_series_id integer NOT NULL,
        name character varying(500) NOT NULL,
        original_name character varying(500) NOT NULL,
        original_language character(2) NOT NULL,
        overview text,
        tagline character varying(500),
        first_air_date date,
        last_air_date date,
        status character varying(50),
        type character varying(50),
        in_production boolean DEFAULT false NOT NULL,
        homepage character varying(500),
        popularity numeric(8,3) DEFAULT 0 NOT NULL,
        vote_average numeric(4,2) DEFAULT 0 NOT NULL,
        vote_count integer DEFAULT 0 NOT NULL,
        poster_path character varying(300),
        backdrop_path character varying(300),
        adult boolean DEFAULT false NOT NULL,
        etl_synced_at timestamp with time zone,
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        updated_at timestamp with time zone DEFAULT now() NOT NULL,
        CONSTRAINT chk_tv_popularity CHECK ((popularity >= (0)::numeric)),
        CONSTRAINT chk_tv_status CHECK (((status)::text = ANY ((ARRAY['Returning Series'::character varying, 'Ended'::character varying, 'Canceled'::character varying, 'In Production'::character varying, 'Planned'::character varying, 'Pilot'::character varying])::text[]))),
        CONSTRAINT chk_tv_vote_average CHECK (((vote_average >= (0)::numeric) AND (vote_average <= (10)::numeric))),
        CONSTRAINT chk_tv_vote_count CHECK ((vote_count >= 0))
    );
    """,
    """
    ALTER TABLE public.tv_series OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.tv_series
        ADD CONSTRAINT tv_series_pkey PRIMARY KEY (series_id);
    """,
    """
    ALTER TABLE ONLY public.tv_series
        ADD CONSTRAINT uq_tv_tmdb_id UNIQUE (tmdb_series_id);
    """,
    """
    CREATE TABLE public.tv_watch_provider (
        series_id integer NOT NULL,
        provider_id integer NOT NULL,
        iso_3166_1 character(2) NOT NULL,
        availability_type character varying(10) NOT NULL,
        display_priority smallint NOT NULL,
        CONSTRAINT chk_watch_avail_tv CHECK (((availability_type)::text = ANY ((ARRAY['flatrate'::character varying, 'rent'::character varying, 'buy'::character varying, 'free'::character varying, 'ads'::character varying])::text[])))
    );
    """,
    """
    ALTER TABLE public.tv_watch_provider OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.tv_watch_provider
        ADD CONSTRAINT tv_watch_provider_pkey PRIMARY KEY (series_id, provider_id, iso_3166_1, availability_type);
    """,
    # --- triggers ---
    """
    CREATE TRIGGER trg_audit_tv_series AFTER INSERT OR DELETE OR UPDATE ON public.tv_series FOR EACH ROW EXECUTE FUNCTION public.fn_trg_audit_log('series_id');
    """,
    """
    CREATE TRIGGER trg_episode_count_sync AFTER INSERT OR DELETE ON public.tv_episode FOR EACH ROW EXECUTE FUNCTION public.fn_trg_episode_count_sync();
    """,
    """
    CREATE TRIGGER trg_set_updated_at_tv_series BEFORE UPDATE ON public.tv_series FOR EACH ROW EXECUTE FUNCTION public.fn_trg_set_updated_at();
    """,
    # --- foreign keys ---
    """
    ALTER TABLE ONLY public.episode_cast
        ADD CONSTRAINT episode_cast_episode_id_fkey FOREIGN KEY (episode_id) REFERENCES public.tv_episode(episode_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.episode_cast
        ADD CONSTRAINT episode_cast_person_id_fkey FOREIGN KEY (person_id) REFERENCES public.person(person_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.episode_crew
        ADD CONSTRAINT episode_crew_department_id_fkey FOREIGN KEY (department_id) REFERENCES public.department(department_id);
    """,
    """
    ALTER TABLE ONLY public.episode_crew
        ADD CONSTRAINT episode_crew_episode_id_fkey FOREIGN KEY (episode_id) REFERENCES public.tv_episode(episode_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.episode_crew
        ADD CONSTRAINT episode_crew_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.job(job_id);
    """,
    """
    ALTER TABLE ONLY public.episode_crew
        ADD CONSTRAINT episode_crew_person_id_fkey FOREIGN KEY (person_id) REFERENCES public.person(person_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.tv_cast
        ADD CONSTRAINT tv_cast_person_id_fkey FOREIGN KEY (person_id) REFERENCES public.person(person_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.tv_cast
        ADD CONSTRAINT tv_cast_series_id_fkey FOREIGN KEY (series_id) REFERENCES public.tv_series(series_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.tv_certification
        ADD CONSTRAINT tv_certification_iso_3166_1_fkey FOREIGN KEY (iso_3166_1) REFERENCES public.country(iso_3166_1);
    """,
    """
    ALTER TABLE ONLY public.tv_certification
        ADD CONSTRAINT tv_certification_series_id_fkey FOREIGN KEY (series_id) REFERENCES public.tv_series(series_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.tv_company
        ADD CONSTRAINT tv_company_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.company(company_id);
    """,
    """
    ALTER TABLE ONLY public.tv_company
        ADD CONSTRAINT tv_company_series_id_fkey FOREIGN KEY (series_id) REFERENCES public.tv_series(series_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.tv_country
        ADD CONSTRAINT tv_country_iso_3166_1_fkey FOREIGN KEY (iso_3166_1) REFERENCES public.country(iso_3166_1);
    """,
    """
    ALTER TABLE ONLY public.tv_country
        ADD CONSTRAINT tv_country_series_id_fkey FOREIGN KEY (series_id) REFERENCES public.tv_series(series_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.tv_creator
        ADD CONSTRAINT tv_creator_person_id_fkey FOREIGN KEY (person_id) REFERENCES public.person(person_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.tv_creator
        ADD CONSTRAINT tv_creator_series_id_fkey FOREIGN KEY (series_id) REFERENCES public.tv_series(series_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.tv_crew
        ADD CONSTRAINT tv_crew_department_id_fkey FOREIGN KEY (department_id) REFERENCES public.department(department_id);
    """,
    """
    ALTER TABLE ONLY public.tv_crew
        ADD CONSTRAINT tv_crew_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.job(job_id);
    """,
    """
    ALTER TABLE ONLY public.tv_crew
        ADD CONSTRAINT tv_crew_person_id_fkey FOREIGN KEY (person_id) REFERENCES public.person(person_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.tv_crew
        ADD CONSTRAINT tv_crew_series_id_fkey FOREIGN KEY (series_id) REFERENCES public.tv_series(series_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.tv_episode
        ADD CONSTRAINT tv_episode_season_id_fkey FOREIGN KEY (season_id) REFERENCES public.tv_season(season_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.tv_episode
        ADD CONSTRAINT tv_episode_series_id_fkey FOREIGN KEY (series_id) REFERENCES public.tv_series(series_id);
    """,
    """
    ALTER TABLE ONLY public.tv_genre
        ADD CONSTRAINT tv_genre_genre_id_fkey FOREIGN KEY (genre_id) REFERENCES public.genre(genre_id);
    """,
    """
    ALTER TABLE ONLY public.tv_genre
        ADD CONSTRAINT tv_genre_series_id_fkey FOREIGN KEY (series_id) REFERENCES public.tv_series(series_id);
    """,
    """
    ALTER TABLE ONLY public.tv_keyword
        ADD CONSTRAINT tv_keyword_keyword_id_fkey FOREIGN KEY (keyword_id) REFERENCES public.keyword(keyword_id);
    """,
    """
    ALTER TABLE ONLY public.tv_keyword
        ADD CONSTRAINT tv_keyword_series_id_fkey FOREIGN KEY (series_id) REFERENCES public.tv_series(series_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.tv_language
        ADD CONSTRAINT tv_language_iso_639_1_fkey FOREIGN KEY (iso_639_1) REFERENCES public.language(iso_639_1);
    """,
    """
    ALTER TABLE ONLY public.tv_language
        ADD CONSTRAINT tv_language_series_id_fkey FOREIGN KEY (series_id) REFERENCES public.tv_series(series_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.tv_season
        ADD CONSTRAINT tv_season_series_id_fkey FOREIGN KEY (series_id) REFERENCES public.tv_series(series_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.tv_series
        ADD CONSTRAINT tv_series_original_language_fkey FOREIGN KEY (original_language) REFERENCES public.language(iso_639_1);
    """,
    """
    ALTER TABLE ONLY public.tv_watch_provider
        ADD CONSTRAINT tv_watch_provider_iso_3166_1_fkey FOREIGN KEY (iso_3166_1) REFERENCES public.country(iso_3166_1);
    """,
    """
    ALTER TABLE ONLY public.tv_watch_provider
        ADD CONSTRAINT tv_watch_provider_provider_id_fkey FOREIGN KEY (provider_id) REFERENCES public.watch_provider(provider_id);
    """,
    """
    ALTER TABLE ONLY public.tv_watch_provider
        ADD CONSTRAINT tv_watch_provider_series_id_fkey FOREIGN KEY (series_id) REFERENCES public.tv_series(series_id) ON DELETE CASCADE;
    """,
]


def run():
    """Execute all DDL statements for this module in order, inside one transaction."""
    with db_utils.db_transaction() as (conn, cur):
        for i, stmt in enumerate(DDL_STATEMENTS, start=1):
            try:
                cur.execute(stmt)
            except Exception:
                logger.error("Failed on statement #%d of %d in schema_tv_series.py", i, len(DDL_STATEMENTS))
                raise
    logger.info("schema_tv_series.py: executed %d statements successfully.", len(DDL_STATEMENTS))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
