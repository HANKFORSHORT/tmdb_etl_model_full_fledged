"""
Reference / lookup tables shared by both the movie and TV pipelines: people,
companies, countries, languages, genres, keywords, certifications, watch
providers, plus ETL bookkeeping (etl_log) and system_config.
Depends on: schema_shared.py

Auto-generated from a pg_dump schema export and split into domain modules
mirroring the etl_movie.py / etl_tv_series.py / etl_reference.py convention
used elsewhere in this repo. Run directly to create these objects in the
target database:

    python schema_reference.py

Uses db_utils.get_connection() / db_utils.db_transaction() for the actual
connection, same as the rest of the ETL codebase.
"""

import logging

import db_utils

logger = logging.getLogger(__name__)

DDL_STATEMENTS = [
    #
    """
    CREATE FUNCTION public.fn_get_collection_avg_score(p_collection_id integer) RETURNS numeric
        LANGUAGE sql STABLE
        AS $$
        SELECT ROUND(AVG(vote_average)::NUMERIC, 2)
        FROM   Movie
        WHERE  collection_id = p_collection_id AND vote_count > 0;
    $$;
    """,
    """
    ALTER FUNCTION public.fn_get_collection_avg_score(p_collection_id integer) OWNER TO postgres;
    """,
    """
    CREATE FUNCTION public.fn_person_filmography(p_person_id integer) RETURNS TABLE(o_seq integer, o_movie_id integer, o_title character varying, o_release_date date, o_role_type text, o_role_detail text, o_vote_average numeric, o_popularity numeric)
        LANGUAGE plpgsql
        AS $$
    DECLARE
        cur_films CURSOR FOR
            SELECT m.movie_id, m.title, m.release_date,
                   'cast'       AS role_type,
                   NULL::TEXT   AS role_detail,
                   mc.order_idx AS sort_order,
                   m.vote_average, m.popularity
            FROM   Movie_Cast mc
            JOIN   Movie m ON m.movie_id = mc.movie_id
            WHERE  mc.person_id = p_person_id

            UNION ALL

            SELECT m.movie_id, m.title, m.release_date,
                   'crew'       AS role_type,
                   mw.job       AS role_detail,
                   0            AS sort_order,
                   m.vote_average, m.popularity
            FROM   Movie_Crew mw
            JOIN   Movie m ON m.movie_id = mw.movie_id
            WHERE  mw.person_id = p_person_id

            ORDER  BY release_date ASC NULLS LAST, sort_order;

        rec   RECORD;
        v_seq INTEGER := 0;
    BEGIN
        OPEN cur_films;
        LOOP
            FETCH cur_films INTO rec;
            EXIT WHEN NOT FOUND;

            v_seq          := v_seq + 1;
            o_seq          := v_seq;
            o_movie_id     := rec.movie_id;
            o_title        := rec.title;
            o_release_date := rec.release_date;
            o_role_type    := rec.role_type;
            o_role_detail  := rec.role_detail;
            o_vote_average := rec.vote_average;
            o_popularity   := rec.popularity;

            RETURN NEXT;
        END LOOP;
        CLOSE cur_films;
    END;
    $$;
    """,
    """
    ALTER FUNCTION public.fn_person_filmography(p_person_id integer) OWNER TO postgres;
    """,
    """
    CREATE FUNCTION public.sp_getpersondetail(p_person_id integer) RETURNS TABLE(person_id integer, tmdb_person_id integer, name character varying, original_name character varying, biography text, birthday date, deathday date, gender smallint, known_for_department character varying, place_of_birth character varying, popularity numeric, profile_path character varying, homepage character varying, imdb_id character varying, adult boolean, movie_count integer)
        LANGUAGE sql STABLE
        AS $$
        SELECT
            p.person_id, p.tmdb_person_id, p.name, p.original_name, p.biography,
            p.birthday, p.deathday, p.gender, p.known_for_department, p.place_of_birth,
            p.popularity, p.profile_path, p.homepage, p.imdb_id, p.adult,
            fn_get_person_movie_count(p.person_id)
        FROM  Person p
        WHERE p.person_id = p_person_id;
    $$;
    """,
    """
    ALTER FUNCTION public.sp_getpersondetail(p_person_id integer) OWNER TO postgres;
    """,
    """
    CREATE PROCEDURE public.sp_insertlanguage(IN p_iso_639_1 character, IN p_english_name character varying, IN p_native_name character varying DEFAULT ''::character varying)
        LANGUAGE plpgsql
        AS $$
    BEGIN
        IF p_iso_639_1 IS NULL OR LENGTH(TRIM(p_iso_639_1)) <> 2 THEN
            RAISE EXCEPTION 'iso_639_1 phß║úi l├á chuß╗ùi CHAR(2): "%"', p_iso_639_1;
        END IF;
        INSERT INTO Language (iso_639_1, english_name, native_name)
        VALUES (LOWER(p_iso_639_1), p_english_name, COALESCE(p_native_name, ''))
        ON CONFLICT (iso_639_1) DO UPDATE
            SET english_name = EXCLUDED.english_name,
                native_name  = EXCLUDED.native_name;
    END;
    $$;
    """,
    """
    ALTER PROCEDURE public.sp_insertlanguage(IN p_iso_639_1 character, IN p_english_name character varying, IN p_native_name character varying) OWNER TO postgres;
    """,
    """
    CREATE PROCEDURE public.sp_insertpersonaka(IN p_person_id integer, IN p_alias character varying)
        LANGUAGE plpgsql
        AS $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM Person WHERE person_id = p_person_id) THEN
            RAISE EXCEPTION 'person_id=% kh├┤ng tß╗ôn tß║íi.', p_person_id;
        END IF;
        INSERT INTO Person_AKA (person_id, alias)
        VALUES (p_person_id, p_alias)
        ON CONFLICT DO NOTHING;
    END;
    $$;
    """,
    """
    ALTER PROCEDURE public.sp_insertpersonaka(IN p_person_id integer, IN p_alias character varying) OWNER TO postgres;
    """,
    """
    CREATE PROCEDURE public.sp_upsertcollection(IN p_tmdb_collection_id integer, IN p_name character varying, IN p_original_name character varying DEFAULT NULL::character varying, IN p_original_language character DEFAULT NULL::bpchar, IN p_overview text DEFAULT NULL::text, IN p_poster_path character varying DEFAULT NULL::character varying, IN p_backdrop_path character varying DEFAULT NULL::character varying)
        LANGUAGE plpgsql
        AS $$
    BEGIN
        INSERT INTO Collection (
            collection_id, tmdb_collection_id, name, original_name,
            original_language, overview, poster_path, backdrop_path
        )
        VALUES (
            p_tmdb_collection_id, p_tmdb_collection_id, p_name, p_original_name,
            p_original_language, p_overview, p_poster_path, p_backdrop_path
        )
        ON CONFLICT (tmdb_collection_id) DO UPDATE
            SET name              = EXCLUDED.name,
                original_name     = EXCLUDED.original_name,
                original_language = EXCLUDED.original_language,
                overview          = EXCLUDED.overview,
                poster_path       = EXCLUDED.poster_path,
                backdrop_path     = EXCLUDED.backdrop_path;
    END;
    $$;
    """,
    """
    ALTER PROCEDURE public.sp_upsertcollection(IN p_tmdb_collection_id integer, IN p_name character varying, IN p_original_name character varying, IN p_original_language character, IN p_overview text, IN p_poster_path character varying, IN p_backdrop_path character varying) OWNER TO postgres;
    """,
    """
    CREATE PROCEDURE public.sp_upsertcompany(IN p_tmdb_company_id integer, IN p_name character varying, IN p_description text DEFAULT NULL::text, IN p_headquarters character varying DEFAULT NULL::character varying, IN p_homepage character varying DEFAULT NULL::character varying, IN p_logo_path character varying DEFAULT NULL::character varying, IN p_origin_country character DEFAULT NULL::bpchar, IN p_parent_id integer DEFAULT NULL::integer)
        LANGUAGE plpgsql
        AS $$
    BEGIN
        IF p_parent_id IS NOT NULL AND p_parent_id = p_tmdb_company_id THEN
            RAISE EXCEPTION 'Company kh├┤ng thß╗â tß╗▒ l├á cha cß╗ºa ch├¡nh m├¼nh (id=%).', p_tmdb_company_id;
        END IF;

        INSERT INTO Company (
            company_id, tmdb_company_id, name, description, headquarters,
            homepage, logo_path, origin_country, parent_company_id
        )
        VALUES (
            p_tmdb_company_id, p_tmdb_company_id, p_name, p_description, p_headquarters,
            p_homepage, p_logo_path, p_origin_country, p_parent_id
        )
        ON CONFLICT (tmdb_company_id) DO UPDATE
            SET name              = EXCLUDED.name,
                description       = EXCLUDED.description,
                headquarters      = EXCLUDED.headquarters,
                homepage          = EXCLUDED.homepage,
                logo_path         = EXCLUDED.logo_path,
                origin_country    = EXCLUDED.origin_country,
                parent_company_id = EXCLUDED.parent_company_id,
                etl_synced_at     = NOW();
    END;
    $$;
    """,
    """
    ALTER PROCEDURE public.sp_upsertcompany(IN p_tmdb_company_id integer, IN p_name character varying, IN p_description text, IN p_headquarters character varying, IN p_homepage character varying, IN p_logo_path character varying, IN p_origin_country character, IN p_parent_id integer) OWNER TO postgres;
    """,
    """
    CREATE PROCEDURE public.sp_upsertperson(IN p_tmdb_person_id integer, IN p_name character varying, IN p_original_name character varying DEFAULT NULL::character varying, IN p_biography text DEFAULT NULL::text, IN p_birthday date DEFAULT NULL::date, IN p_deathday date DEFAULT NULL::date, IN p_gender smallint DEFAULT 0, IN p_known_for_department character varying DEFAULT NULL::character varying, IN p_place_of_birth character varying DEFAULT NULL::character varying, IN p_popularity numeric DEFAULT 0, IN p_profile_path character varying DEFAULT NULL::character varying, IN p_homepage character varying DEFAULT NULL::character varying, IN p_imdb_id character varying DEFAULT NULL::character varying, IN p_adult boolean DEFAULT false)
        LANGUAGE plpgsql
        AS $$
    BEGIN
        IF p_gender NOT IN (0, 1, 2, 3) THEN
            RAISE EXCEPTION 'gender kh├┤ng hß╗úp lß╗ç: %. Chß╗ë chß║Ñp nhß║¡n 0,1,2,3.', p_gender;
        END IF;

        INSERT INTO Person (
            person_id, tmdb_person_id, name, original_name, biography,
            birthday, deathday, gender, known_for_department, place_of_birth,
            popularity, profile_path, homepage, imdb_id, adult, etl_synced_at
        )
        VALUES (
            p_tmdb_person_id, p_tmdb_person_id, p_name, p_original_name, p_biography,
            p_birthday, p_deathday, p_gender, p_known_for_department, p_place_of_birth,
            p_popularity, p_profile_path, p_homepage, p_imdb_id, p_adult, NOW()
        )
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
                updated_at           = NOW();
    END;
    $$;
    """,
    """
    ALTER PROCEDURE public.sp_upsertperson(IN p_tmdb_person_id integer, IN p_name character varying, IN p_original_name character varying, IN p_biography text, IN p_birthday date, IN p_deathday date, IN p_gender smallint, IN p_known_for_department character varying, IN p_place_of_birth character varying, IN p_popularity numeric, IN p_profile_path character varying, IN p_homepage character varying, IN p_imdb_id character varying, IN p_adult boolean) OWNER TO postgres;
    """,
    # --- tables ---
    """
    CREATE TABLE public.certification_standard (
        cert_std_id smallint NOT NULL,
        iso_3166_1 character(2) NOT NULL,
        certification character varying(20) NOT NULL,
        meaning text,
        cert_order smallint NOT NULL,
        media_type character varying(10) NOT NULL,
        CONSTRAINT chk_cert_media_type CHECK (((media_type)::text = ANY ((ARRAY['movie'::character varying, 'tv'::character varying])::text[]))),
        CONSTRAINT chk_cert_order_positive CHECK ((cert_order > 0))
    );
    """,
    """
    ALTER TABLE public.certification_standard OWNER TO postgres;
    """,
    """
    CREATE SEQUENCE public.certification_standard_cert_std_id_seq
        AS smallint
        START WITH 1
        INCREMENT BY 1
        NO MINVALUE
        NO MAXVALUE
        CACHE 1;
    """,
    """
    ALTER SEQUENCE public.certification_standard_cert_std_id_seq OWNER TO postgres;
    """,
    """
    ALTER SEQUENCE public.certification_standard_cert_std_id_seq OWNED BY public.certification_standard.cert_std_id;
    """,
    """
    ALTER TABLE ONLY public.certification_standard ALTER COLUMN cert_std_id SET DEFAULT nextval('public.certification_standard_cert_std_id_seq'::regclass);
    """,
    """
    ALTER TABLE ONLY public.certification_standard
        ADD CONSTRAINT certification_standard_pkey PRIMARY KEY (cert_std_id);
    """,
    """
    ALTER TABLE ONLY public.certification_standard
        ADD CONSTRAINT uq_cert_per_country UNIQUE (iso_3166_1, certification, media_type);
    """,
    """
    CREATE TABLE public.collection (
        collection_id integer NOT NULL,
        tmdb_collection_id integer NOT NULL,
        name character varying(300) NOT NULL,
        original_name character varying(300),
        original_language character(2),
        overview text,
        poster_path character varying(300),
        backdrop_path character varying(300)
    );
    """,
    """
    ALTER TABLE public.collection OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.collection
        ADD CONSTRAINT collection_pkey PRIMARY KEY (collection_id);
    """,
    """
    ALTER TABLE ONLY public.collection
        ADD CONSTRAINT uq_collection_tmdb_id UNIQUE (tmdb_collection_id);
    """,
    """
    CREATE TABLE public.collection_translation (
        collection_id integer NOT NULL,
        iso_3166_1 character(2) NOT NULL,
        iso_639_1 character(2) NOT NULL,
        title character varying(300),
        overview text,
        homepage character varying(500)
    );
    """,
    """
    ALTER TABLE public.collection_translation OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.collection_translation
        ADD CONSTRAINT collection_translation_pkey PRIMARY KEY (collection_id, iso_3166_1, iso_639_1);
    """,
    """
    CREATE TABLE public.company (
        company_id integer NOT NULL,
        tmdb_company_id integer NOT NULL,
        name character varying(200) NOT NULL,
        description text,
        headquarters character varying(200),
        homepage character varying(500),
        logo_path character varying(300),
        origin_country character(2),
        parent_company_id integer,
        etl_synced_at timestamp with time zone,
        CONSTRAINT chk_company_no_self_parent CHECK (((parent_company_id IS NULL) OR (parent_company_id <> company_id)))
    );
    """,
    """
    ALTER TABLE public.company OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.company
        ADD CONSTRAINT company_pkey PRIMARY KEY (company_id);
    """,
    """
    ALTER TABLE ONLY public.company
        ADD CONSTRAINT uq_company_name UNIQUE (name);
    """,
    """
    ALTER TABLE ONLY public.company
        ADD CONSTRAINT uq_company_tmdb_id UNIQUE (tmdb_company_id);
    """,
    """
    CREATE TABLE public.country (
        iso_3166_1 character(2) NOT NULL,
        english_name character varying(150) NOT NULL,
        native_name character varying(150) DEFAULT ''::character varying NOT NULL
    );
    """,
    """
    ALTER TABLE public.country OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.country
        ADD CONSTRAINT country_pkey PRIMARY KEY (iso_3166_1);
    """,
    """
    CREATE TABLE public.department (
        department_id smallint NOT NULL,
        department_name character varying(100) NOT NULL
    );
    """,
    """
    ALTER TABLE public.department OWNER TO postgres;
    """,
    """
    CREATE SEQUENCE public.department_department_id_seq
        AS smallint
        START WITH 1
        INCREMENT BY 1
        NO MINVALUE
        NO MAXVALUE
        CACHE 1;
    """,
    """
    ALTER SEQUENCE public.department_department_id_seq OWNER TO postgres;
    """,
    """
    ALTER SEQUENCE public.department_department_id_seq OWNED BY public.department.department_id;
    """,
    """
    ALTER TABLE ONLY public.department ALTER COLUMN department_id SET DEFAULT nextval('public.department_department_id_seq'::regclass);
    """,
    """
    ALTER TABLE ONLY public.department
        ADD CONSTRAINT department_pkey PRIMARY KEY (department_id);
    """,
    """
    ALTER TABLE ONLY public.department
        ADD CONSTRAINT uq_dept_name UNIQUE (department_name);
    """,
    """
    CREATE TABLE public.etl_log (
        log_id bigint NOT NULL,
        endpoint character varying(200) NOT NULL,
        tmdb_id integer,
        media_type character varying(20),
        status character varying(20) NOT NULL,
        records_processed integer DEFAULT 0 NOT NULL,
        error_message text,
        started_at timestamp with time zone NOT NULL,
        finished_at timestamp with time zone,
        CONSTRAINT chk_etl_status CHECK (((status)::text = ANY ((ARRAY['success'::character varying, 'failed'::character varying, 'partial'::character varying])::text[])))
    );
    """,
    """
    ALTER TABLE public.etl_log OWNER TO postgres;
    """,
    """
    CREATE SEQUENCE public.etl_log_log_id_seq
        START WITH 1
        INCREMENT BY 1
        NO MINVALUE
        NO MAXVALUE
        CACHE 1;
    """,
    """
    ALTER SEQUENCE public.etl_log_log_id_seq OWNER TO postgres;
    """,
    """
    ALTER SEQUENCE public.etl_log_log_id_seq OWNED BY public.etl_log.log_id;
    """,
    """
    ALTER TABLE ONLY public.etl_log ALTER COLUMN log_id SET DEFAULT nextval('public.etl_log_log_id_seq'::regclass);
    """,
    """
    ALTER TABLE ONLY public.etl_log
        ADD CONSTRAINT etl_log_pkey PRIMARY KEY (log_id);
    """,
    """
    CREATE TABLE public.genre (
        genre_id integer NOT NULL,
        tmdb_id integer,
        name character varying(100) NOT NULL,
        media_type character(5)
    );
    """,
    """
    ALTER TABLE public.genre OWNER TO postgres;
    """,
    """
    ALTER TABLE public.genre ALTER COLUMN genre_id ADD GENERATED BY DEFAULT AS IDENTITY (
        SEQUENCE NAME public.genre_genre_id_seq
        START WITH 1
        INCREMENT BY 1
        NO MINVALUE
        NO MAXVALUE
        CACHE 1
    );
    """,
    """
    ALTER TABLE ONLY public.genre
        ADD CONSTRAINT genre_pkey PRIMARY KEY (genre_id);
    """,
    """
    ALTER TABLE ONLY public.genre
        ADD CONSTRAINT genre_tmdb_id_media_type_key UNIQUE (tmdb_id, media_type);
    """,
    """
    CREATE TABLE public.job (
        job_id smallint NOT NULL,
        department_id smallint NOT NULL,
        job_name character varying(150) NOT NULL
    );
    """,
    """
    ALTER TABLE public.job OWNER TO postgres;
    """,
    """
    CREATE SEQUENCE public.job_job_id_seq
        AS smallint
        START WITH 1
        INCREMENT BY 1
        NO MINVALUE
        NO MAXVALUE
        CACHE 1;
    """,
    """
    ALTER SEQUENCE public.job_job_id_seq OWNER TO postgres;
    """,
    """
    ALTER SEQUENCE public.job_job_id_seq OWNED BY public.job.job_id;
    """,
    """
    ALTER TABLE ONLY public.job ALTER COLUMN job_id SET DEFAULT nextval('public.job_job_id_seq'::regclass);
    """,
    """
    ALTER TABLE ONLY public.job
        ADD CONSTRAINT job_pkey PRIMARY KEY (job_id);
    """,
    """
    ALTER TABLE ONLY public.job
        ADD CONSTRAINT uq_job_per_dept UNIQUE (department_id, job_name);
    """,
    """
    CREATE TABLE public.keyword (
        keyword_id integer NOT NULL,
        name character varying(200) NOT NULL
    );
    """,
    """
    ALTER TABLE public.keyword OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.keyword
        ADD CONSTRAINT keyword_pkey PRIMARY KEY (keyword_id);
    """,
    """
    ALTER TABLE ONLY public.keyword
        ADD CONSTRAINT uq_keyword_name UNIQUE (name);
    """,
    """
    CREATE TABLE public.language (
        iso_639_1 character(2) NOT NULL,
        english_name character varying(100) NOT NULL,
        native_name character varying(100) DEFAULT ''::character varying NOT NULL
    );
    """,
    """
    ALTER TABLE public.language OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.language
        ADD CONSTRAINT language_pkey PRIMARY KEY (iso_639_1);
    """,
    """
    CREATE TABLE public.person (
        person_id integer NOT NULL,
        tmdb_person_id integer NOT NULL,
        name character varying(200) NOT NULL,
        original_name character varying(200),
        biography text,
        birthday date,
        deathday date,
        gender smallint,
        known_for_department character varying(50),
        place_of_birth character varying(200),
        popularity numeric(8,3) DEFAULT 0 NOT NULL,
        profile_path character varying(300),
        homepage character varying(500),
        imdb_id character varying(20),
        adult boolean DEFAULT false NOT NULL,
        etl_synced_at timestamp with time zone,
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        updated_at timestamp with time zone DEFAULT now() NOT NULL,
        CONSTRAINT chk_person_birthday CHECK (((birthday IS NULL) OR (birthday <= CURRENT_DATE))),
        CONSTRAINT chk_person_deathday CHECK (((deathday IS NULL) OR ((birthday IS NULL) OR (deathday > birthday)))),
        CONSTRAINT chk_person_gender CHECK ((gender = ANY (ARRAY[0, 1, 2, 3]))),
        CONSTRAINT chk_person_popularity CHECK ((popularity >= (0)::numeric))
    );
    """,
    """
    ALTER TABLE public.person OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.person
        ADD CONSTRAINT person_pkey PRIMARY KEY (person_id);
    """,
    """
    ALTER TABLE ONLY public.person
        ADD CONSTRAINT uq_person_imdb_id UNIQUE (imdb_id);
    """,
    """
    ALTER TABLE ONLY public.person
        ADD CONSTRAINT uq_person_tmdb_id UNIQUE (tmdb_person_id);
    """,
    """
    CREATE TABLE public.person_aka (
        aka_id integer NOT NULL,
        person_id integer NOT NULL,
        alias character varying(300) NOT NULL
    );
    """,
    """
    ALTER TABLE public.person_aka OWNER TO postgres;
    """,
    """
    CREATE SEQUENCE public.person_aka_aka_id_seq
        AS integer
        START WITH 1
        INCREMENT BY 1
        NO MINVALUE
        NO MAXVALUE
        CACHE 1;
    """,
    """
    ALTER SEQUENCE public.person_aka_aka_id_seq OWNER TO postgres;
    """,
    """
    ALTER SEQUENCE public.person_aka_aka_id_seq OWNED BY public.person_aka.aka_id;
    """,
    """
    ALTER TABLE ONLY public.person_aka ALTER COLUMN aka_id SET DEFAULT nextval('public.person_aka_aka_id_seq'::regclass);
    """,
    """
    ALTER TABLE ONLY public.person_aka
        ADD CONSTRAINT person_aka_pkey PRIMARY KEY (aka_id);
    """,
    """
    CREATE TABLE public.role (
        role_id smallint NOT NULL,
        role_name character varying(50) NOT NULL,
        description text,
        can_manage_movies boolean DEFAULT false NOT NULL,
        can_manage_users boolean DEFAULT false NOT NULL,
        can_view_audit boolean DEFAULT false NOT NULL,
        can_run_etl boolean DEFAULT false NOT NULL
    );
    """,
    """
    ALTER TABLE public.role OWNER TO postgres;
    """,
    """
    CREATE SEQUENCE public.role_role_id_seq
        AS smallint
        START WITH 1
        INCREMENT BY 1
        NO MINVALUE
        NO MAXVALUE
        CACHE 1;
    """,
    """
    ALTER SEQUENCE public.role_role_id_seq OWNER TO postgres;
    """,
    """
    ALTER SEQUENCE public.role_role_id_seq OWNED BY public.role.role_id;
    """,
    """
    ALTER TABLE ONLY public.role ALTER COLUMN role_id SET DEFAULT nextval('public.role_role_id_seq'::regclass);
    """,
    """
    ALTER TABLE ONLY public.role
        ADD CONSTRAINT role_pkey PRIMARY KEY (role_id);
    """,
    """
    ALTER TABLE ONLY public.role
        ADD CONSTRAINT uq_role_name UNIQUE (role_name);
    """,
    """
    CREATE TABLE public.system_config (
        config_key character varying(100) NOT NULL,
        config_value text NOT NULL,
        description text,
        updated_at timestamp with time zone DEFAULT now() NOT NULL
    );
    """,
    """
    ALTER TABLE public.system_config OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.system_config
        ADD CONSTRAINT system_config_pkey PRIMARY KEY (config_key);
    """,
    """
    CREATE TABLE public.watch_provider (
        provider_id integer NOT NULL,
        tmdb_provider_id integer NOT NULL,
        provider_name character varying(200) NOT NULL,
        logo_path character varying(300)
    );
    """,
    """
    ALTER TABLE public.watch_provider OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.watch_provider
        ADD CONSTRAINT uq_watch_provider_tmdb_id UNIQUE (tmdb_provider_id);
    """,
    """
    ALTER TABLE ONLY public.watch_provider
        ADD CONSTRAINT watch_provider_pkey PRIMARY KEY (provider_id);
    """,
    # --- triggers ---
    """
    CREATE TRIGGER trg_audit_company AFTER INSERT OR DELETE OR UPDATE ON public.company FOR EACH ROW EXECUTE FUNCTION public.fn_trg_audit_log('company_id');
    """,
    """
    CREATE TRIGGER trg_audit_person AFTER INSERT OR DELETE OR UPDATE ON public.person FOR EACH ROW EXECUTE FUNCTION public.fn_trg_audit_log('person_id');
    """,
    """
    CREATE TRIGGER trg_set_updated_at_person BEFORE UPDATE ON public.person FOR EACH ROW EXECUTE FUNCTION public.fn_trg_set_updated_at();
    """,
    """
    CREATE TRIGGER trg_set_updated_at_system_config BEFORE UPDATE ON public.system_config FOR EACH ROW EXECUTE FUNCTION public.fn_trg_set_updated_at();
    """,
    # --- foreign keys ---
    """
    ALTER TABLE ONLY public.certification_standard
        ADD CONSTRAINT certification_standard_iso_3166_1_fkey FOREIGN KEY (iso_3166_1) REFERENCES public.country(iso_3166_1);
    """,
    """
    ALTER TABLE ONLY public.collection
        ADD CONSTRAINT collection_original_language_fkey FOREIGN KEY (original_language) REFERENCES public.language(iso_639_1);
    """,
    """
    ALTER TABLE ONLY public.collection_translation
        ADD CONSTRAINT collection_translation_collection_id_fkey FOREIGN KEY (collection_id) REFERENCES public.collection(collection_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.collection_translation
        ADD CONSTRAINT collection_translation_iso_3166_1_fkey FOREIGN KEY (iso_3166_1) REFERENCES public.country(iso_3166_1);
    """,
    """
    ALTER TABLE ONLY public.collection_translation
        ADD CONSTRAINT collection_translation_iso_639_1_fkey FOREIGN KEY (iso_639_1) REFERENCES public.language(iso_639_1);
    """,
    """
    ALTER TABLE ONLY public.company
        ADD CONSTRAINT company_origin_country_fkey FOREIGN KEY (origin_country) REFERENCES public.country(iso_3166_1);
    """,
    """
    ALTER TABLE ONLY public.company
        ADD CONSTRAINT company_parent_company_id_fkey FOREIGN KEY (parent_company_id) REFERENCES public.company(company_id);
    """,
    """
    ALTER TABLE ONLY public.job
        ADD CONSTRAINT job_department_id_fkey FOREIGN KEY (department_id) REFERENCES public.department(department_id);
    """,
    """
    ALTER TABLE ONLY public.person_aka
        ADD CONSTRAINT person_aka_person_id_fkey FOREIGN KEY (person_id) REFERENCES public.person(person_id) ON DELETE CASCADE;
    """,
]


def run():
    """Execute all DDL statements for this module in order, inside one transaction."""
    with db_utils.db_transaction() as (conn, cur):
        for i, stmt in enumerate(DDL_STATEMENTS, start=1):
            try:
                cur.execute(stmt)
            except Exception:
                logger.error("Failed on statement #%d of %d in schema_reference.py", i, len(DDL_STATEMENTS))
                raise
    logger.info("schema_reference.py: executed %d statements successfully.", len(DDL_STATEMENTS))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
