
SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

BEGIN;

CREATE FUNCTION public.fn_etl_needs_sync(p_synced_at timestamp with time zone, p_interval interval DEFAULT '7 days'::interval) RETURNS boolean
    LANGUAGE sql IMMUTABLE
    AS $$
    SELECT p_synced_at IS NULL OR p_synced_at < NOW() - p_interval;
$$;

ALTER FUNCTION public.fn_etl_needs_sync(p_synced_at timestamp with time zone, p_interval interval) OWNER TO postgres;

CREATE FUNCTION public.fn_get_image_url(p_path character varying, p_size character varying DEFAULT 'original'::character varying) RETURNS text
    LANGUAGE plpgsql STABLE
    AS $$
DECLARE
    v_base TEXT;
BEGIN
    IF p_path IS NULL OR p_path = '' THEN RETURN NULL; END IF;

    SELECT config_value INTO v_base
    FROM   System_Config
    WHERE  config_key = 'tmdb_secure_base_url';

    RETURN COALESCE(v_base, 'https://image.tmdb.org/t/p/') || p_size || p_path;
END;
$$;

ALTER FUNCTION public.fn_get_image_url(p_path character varying, p_size character varying) OWNER TO postgres;

CREATE FUNCTION public.fn_has_role(p_user_id integer, p_role_name character varying) RETURNS boolean
    LANGUAGE sql STABLE
    AS $$
    SELECT EXISTS (
        SELECT 1
        FROM   User_Role ur
        JOIN   Role r ON r.role_id = ur.role_id
        WHERE  ur.user_id   = p_user_id
          AND  r.role_name  = p_role_name
          AND  (ur.expires_at IS NULL OR ur.expires_at > NOW())
    );
$$;

ALTER FUNCTION public.fn_has_role(p_user_id integer, p_role_name character varying) OWNER TO postgres;

CREATE FUNCTION public.fn_is_user_active(p_user_id integer) RETURNS boolean
    LANGUAGE sql STABLE
    AS $$
    SELECT is_active FROM "User" WHERE user_id = p_user_id;
$$;

ALTER FUNCTION public.fn_is_user_active(p_user_id integer) OWNER TO postgres;

CREATE FUNCTION public.fn_trg_audit_log() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    AS $$
DECLARE
    v_record_id  TEXT;
    v_old_data   JSONB;
    v_new_data   JSONB;
    v_user_id    INTEGER;
    v_pk_col     TEXT := COALESCE(TG_ARGV[0], 'id');
BEGIN
    BEGIN
        v_user_id := current_setting('app.current_user_id', TRUE)::INTEGER;
    EXCEPTION WHEN OTHERS THEN
        v_user_id := NULL;
    END;

    IF TG_OP = 'DELETE' THEN
        v_record_id := (row_to_json(OLD)::JSONB) ->> v_pk_col;
        v_old_data  := row_to_json(OLD)::JSONB;
        v_new_data  := NULL;
    ELSIF TG_OP = 'INSERT' THEN
        v_record_id := (row_to_json(NEW)::JSONB) ->> v_pk_col;
        v_old_data  := NULL;
        v_new_data  := row_to_json(NEW)::JSONB;
    ELSE
        v_record_id := (row_to_json(NEW)::JSONB) ->> v_pk_col;
        v_old_data  := row_to_json(OLD)::JSONB;
        v_new_data  := row_to_json(NEW)::JSONB;
    END IF;

    IF TG_TABLE_NAME = 'user' THEN
        v_old_data := v_old_data - 'password_hash';
        v_new_data := v_new_data - 'password_hash';
    END IF;

    INSERT INTO Audit_Log (table_name, record_id, action, changed_by,
                           old_data, new_data, session_info)
    VALUES (
        TG_TABLE_NAME,
        v_record_id,
        TG_OP,
        v_user_id,
        v_old_data,
        v_new_data,
        jsonb_build_object(
            'app_user', current_user,
            'pid',      pg_backend_pid()
        )
    );

    IF TG_OP = 'DELETE' THEN RETURN OLD;
    ELSE RETURN NEW;
    END IF;
END;
$$;

ALTER FUNCTION public.fn_trg_audit_log() OWNER TO postgres;

CREATE FUNCTION public.fn_trg_episode_count_sync() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    v_season_id INTEGER;
BEGIN
    v_season_id := COALESCE(NEW.season_id, OLD.season_id);

    UPDATE TV_Season
    SET    episode_count = (
               SELECT COUNT(*) FROM TV_Episode WHERE season_id = v_season_id
           )
    WHERE  season_id = v_season_id;

    RETURN NULL; 
END;
$$;

ALTER FUNCTION public.fn_trg_episode_count_sync() OWNER TO postgres;

CREATE FUNCTION public.fn_trg_set_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

ALTER FUNCTION public.fn_trg_set_updated_at() OWNER TO postgres;

CREATE FUNCTION public.fn_trg_soft_delete_user() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    UPDATE "User"
    SET    is_active  = FALSE,
           updated_at = NOW()
    WHERE  user_id = OLD.user_id;

    RETURN NULL;
END;
$$;

ALTER FUNCTION public.fn_trg_soft_delete_user() OWNER TO postgres;

CREATE FUNCTION public.fn_trg_validate_review_rating() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF NEW.rating IS NOT NULL THEN
        IF NEW.rating < 0.5 OR NEW.rating > 10.0 THEN
            RAISE EXCEPTION 'Review rating (%) must be between 0.5 and 10.0.', NEW.rating;
        END IF;
        IF (NEW.rating * 2) <> FLOOR(NEW.rating * 2) THEN
            RAISE EXCEPTION 'Review rating (%) must be a multiple of 0.5.', NEW.rating;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

ALTER FUNCTION public.fn_trg_validate_review_rating() OWNER TO postgres;

CREATE FUNCTION public.fn_get_collection_avg_score(p_collection_id integer) RETURNS numeric
    LANGUAGE sql STABLE
    AS $$
    SELECT ROUND(AVG(vote_average)::NUMERIC, 2)
    FROM   Movie
    WHERE  collection_id = p_collection_id AND vote_count > 0;
$$;

ALTER FUNCTION public.fn_get_collection_avg_score(p_collection_id integer) OWNER TO postgres;

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

ALTER FUNCTION public.fn_person_filmography(p_person_id integer) OWNER TO postgres;

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

ALTER FUNCTION public.sp_getpersondetail(p_person_id integer) OWNER TO postgres;

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

ALTER PROCEDURE public.sp_insertlanguage(IN p_iso_639_1 character, IN p_english_name character varying, IN p_native_name character varying) OWNER TO postgres;

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

ALTER PROCEDURE public.sp_insertpersonaka(IN p_person_id integer, IN p_alias character varying) OWNER TO postgres;

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

ALTER PROCEDURE public.sp_upsertcollection(IN p_tmdb_collection_id integer, IN p_name character varying, IN p_original_name character varying, IN p_original_language character, IN p_overview text, IN p_poster_path character varying, IN p_backdrop_path character varying) OWNER TO postgres;

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

ALTER PROCEDURE public.sp_upsertcompany(IN p_tmdb_company_id integer, IN p_name character varying, IN p_description text, IN p_headquarters character varying, IN p_homepage character varying, IN p_logo_path character varying, IN p_origin_country character, IN p_parent_id integer) OWNER TO postgres;

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

ALTER PROCEDURE public.sp_upsertperson(IN p_tmdb_person_id integer, IN p_name character varying, IN p_original_name character varying, IN p_biography text, IN p_birthday date, IN p_deathday date, IN p_gender smallint, IN p_known_for_department character varying, IN p_place_of_birth character varying, IN p_popularity numeric, IN p_profile_path character varying, IN p_homepage character varying, IN p_imdb_id character varying, IN p_adult boolean) OWNER TO postgres;

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

ALTER TABLE public.certification_standard OWNER TO postgres;

CREATE SEQUENCE public.certification_standard_cert_std_id_seq
    AS smallint
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.certification_standard_cert_std_id_seq OWNER TO postgres;

ALTER SEQUENCE public.certification_standard_cert_std_id_seq OWNED BY public.certification_standard.cert_std_id;

ALTER TABLE ONLY public.certification_standard ALTER COLUMN cert_std_id SET DEFAULT nextval('public.certification_standard_cert_std_id_seq'::regclass);

ALTER TABLE ONLY public.certification_standard
    ADD CONSTRAINT certification_standard_pkey PRIMARY KEY (cert_std_id);

ALTER TABLE ONLY public.certification_standard
    ADD CONSTRAINT uq_cert_per_country UNIQUE (iso_3166_1, certification, media_type);

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

ALTER TABLE public.collection OWNER TO postgres;

ALTER TABLE ONLY public.collection
    ADD CONSTRAINT collection_pkey PRIMARY KEY (collection_id);

ALTER TABLE ONLY public.collection
    ADD CONSTRAINT uq_collection_tmdb_id UNIQUE (tmdb_collection_id);

CREATE TABLE public.collection_translation (
    collection_id integer NOT NULL,
    iso_3166_1 character(2) NOT NULL,
    iso_639_1 character(2) NOT NULL,
    title character varying(300),
    overview text,
    homepage character varying(500)
);

ALTER TABLE public.collection_translation OWNER TO postgres;

ALTER TABLE ONLY public.collection_translation
    ADD CONSTRAINT collection_translation_pkey PRIMARY KEY (collection_id, iso_3166_1, iso_639_1);

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

ALTER TABLE public.company OWNER TO postgres;

ALTER TABLE ONLY public.company
    ADD CONSTRAINT company_pkey PRIMARY KEY (company_id);

ALTER TABLE ONLY public.company
    ADD CONSTRAINT uq_company_name UNIQUE (name);

ALTER TABLE ONLY public.company
    ADD CONSTRAINT uq_company_tmdb_id UNIQUE (tmdb_company_id);

CREATE TABLE public.country (
    iso_3166_1 character(2) NOT NULL,
    english_name character varying(150) NOT NULL,
    native_name character varying(150) DEFAULT ''::character varying NOT NULL
);

ALTER TABLE public.country OWNER TO postgres;

ALTER TABLE ONLY public.country
    ADD CONSTRAINT country_pkey PRIMARY KEY (iso_3166_1);

CREATE TABLE public.department (
    department_id smallint NOT NULL,
    department_name character varying(100) NOT NULL
);

ALTER TABLE public.department OWNER TO postgres;

CREATE SEQUENCE public.department_department_id_seq
    AS smallint
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.department_department_id_seq OWNER TO postgres;

ALTER SEQUENCE public.department_department_id_seq OWNED BY public.department.department_id;

ALTER TABLE ONLY public.department ALTER COLUMN department_id SET DEFAULT nextval('public.department_department_id_seq'::regclass);

ALTER TABLE ONLY public.department
    ADD CONSTRAINT department_pkey PRIMARY KEY (department_id);

ALTER TABLE ONLY public.department
    ADD CONSTRAINT uq_dept_name UNIQUE (department_name);

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

ALTER TABLE public.etl_log OWNER TO postgres;

CREATE SEQUENCE public.etl_log_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.etl_log_log_id_seq OWNER TO postgres;

ALTER SEQUENCE public.etl_log_log_id_seq OWNED BY public.etl_log.log_id;

ALTER TABLE ONLY public.etl_log ALTER COLUMN log_id SET DEFAULT nextval('public.etl_log_log_id_seq'::regclass);

ALTER TABLE ONLY public.etl_log
    ADD CONSTRAINT etl_log_pkey PRIMARY KEY (log_id);

CREATE TABLE public.genre (
    genre_id integer NOT NULL,
    tmdb_id integer,
    name character varying(100) NOT NULL,
    media_type character(5)
);

ALTER TABLE public.genre OWNER TO postgres;

ALTER TABLE public.genre ALTER COLUMN genre_id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME public.genre_genre_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

ALTER TABLE ONLY public.genre
    ADD CONSTRAINT genre_pkey PRIMARY KEY (genre_id);

ALTER TABLE ONLY public.genre
    ADD CONSTRAINT genre_tmdb_id_media_type_key UNIQUE (tmdb_id, media_type);

CREATE TABLE public.job (
    job_id smallint NOT NULL,
    department_id smallint NOT NULL,
    job_name character varying(150) NOT NULL
);

ALTER TABLE public.job OWNER TO postgres;

CREATE SEQUENCE public.job_job_id_seq
    AS smallint
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.job_job_id_seq OWNER TO postgres;

ALTER SEQUENCE public.job_job_id_seq OWNED BY public.job.job_id;

ALTER TABLE ONLY public.job ALTER COLUMN job_id SET DEFAULT nextval('public.job_job_id_seq'::regclass);

ALTER TABLE ONLY public.job
    ADD CONSTRAINT job_pkey PRIMARY KEY (job_id);

ALTER TABLE ONLY public.job
    ADD CONSTRAINT uq_job_per_dept UNIQUE (department_id, job_name);

CREATE TABLE public.keyword (
    keyword_id integer NOT NULL,
    name character varying(200) NOT NULL
);

ALTER TABLE public.keyword OWNER TO postgres;

ALTER TABLE ONLY public.keyword
    ADD CONSTRAINT keyword_pkey PRIMARY KEY (keyword_id);

ALTER TABLE ONLY public.keyword
    ADD CONSTRAINT uq_keyword_name UNIQUE (name);

CREATE TABLE public.language (
    iso_639_1 character(2) NOT NULL,
    english_name character varying(100) NOT NULL,
    native_name character varying(100) DEFAULT ''::character varying NOT NULL
);

ALTER TABLE public.language OWNER TO postgres;

ALTER TABLE ONLY public.language
    ADD CONSTRAINT language_pkey PRIMARY KEY (iso_639_1);

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

ALTER TABLE public.person OWNER TO postgres;

ALTER TABLE ONLY public.person
    ADD CONSTRAINT person_pkey PRIMARY KEY (person_id);

ALTER TABLE ONLY public.person
    ADD CONSTRAINT uq_person_imdb_id UNIQUE (imdb_id);

ALTER TABLE ONLY public.person
    ADD CONSTRAINT uq_person_tmdb_id UNIQUE (tmdb_person_id);

CREATE TABLE public.person_aka (
    aka_id integer NOT NULL,
    person_id integer NOT NULL,
    alias character varying(300) NOT NULL
);

ALTER TABLE public.person_aka OWNER TO postgres;

CREATE SEQUENCE public.person_aka_aka_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.person_aka_aka_id_seq OWNER TO postgres;

ALTER SEQUENCE public.person_aka_aka_id_seq OWNED BY public.person_aka.aka_id;

ALTER TABLE ONLY public.person_aka ALTER COLUMN aka_id SET DEFAULT nextval('public.person_aka_aka_id_seq'::regclass);

ALTER TABLE ONLY public.person_aka
    ADD CONSTRAINT person_aka_pkey PRIMARY KEY (aka_id);

CREATE TABLE public.role (
    role_id smallint NOT NULL,
    role_name character varying(50) NOT NULL,
    description text,
    can_manage_movies boolean DEFAULT false NOT NULL,
    can_manage_users boolean DEFAULT false NOT NULL,
    can_view_audit boolean DEFAULT false NOT NULL,
    can_run_etl boolean DEFAULT false NOT NULL
);

ALTER TABLE public.role OWNER TO postgres;

CREATE SEQUENCE public.role_role_id_seq
    AS smallint
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.role_role_id_seq OWNER TO postgres;

ALTER SEQUENCE public.role_role_id_seq OWNED BY public.role.role_id;

ALTER TABLE ONLY public.role ALTER COLUMN role_id SET DEFAULT nextval('public.role_role_id_seq'::regclass);

ALTER TABLE ONLY public.role
    ADD CONSTRAINT role_pkey PRIMARY KEY (role_id);

ALTER TABLE ONLY public.role
    ADD CONSTRAINT uq_role_name UNIQUE (role_name);

CREATE TABLE public.system_config (
    config_key character varying(100) NOT NULL,
    config_value text NOT NULL,
    description text,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

ALTER TABLE public.system_config OWNER TO postgres;

ALTER TABLE ONLY public.system_config
    ADD CONSTRAINT system_config_pkey PRIMARY KEY (config_key);

CREATE TABLE public.watch_provider (
    provider_id integer NOT NULL,
    tmdb_provider_id integer NOT NULL,
    provider_name character varying(200) NOT NULL,
    logo_path character varying(300)
);

ALTER TABLE public.watch_provider OWNER TO postgres;

ALTER TABLE ONLY public.watch_provider
    ADD CONSTRAINT uq_watch_provider_tmdb_id UNIQUE (tmdb_provider_id);

ALTER TABLE ONLY public.watch_provider
    ADD CONSTRAINT watch_provider_pkey PRIMARY KEY (provider_id);

CREATE TRIGGER trg_audit_company AFTER INSERT OR DELETE OR UPDATE ON public.company FOR EACH ROW EXECUTE FUNCTION public.fn_trg_audit_log('company_id');

CREATE TRIGGER trg_audit_person AFTER INSERT OR DELETE OR UPDATE ON public.person FOR EACH ROW EXECUTE FUNCTION public.fn_trg_audit_log('person_id');

CREATE TRIGGER trg_set_updated_at_person BEFORE UPDATE ON public.person FOR EACH ROW EXECUTE FUNCTION public.fn_trg_set_updated_at();

CREATE TRIGGER trg_set_updated_at_system_config BEFORE UPDATE ON public.system_config FOR EACH ROW EXECUTE FUNCTION public.fn_trg_set_updated_at();

ALTER TABLE ONLY public.certification_standard
    ADD CONSTRAINT certification_standard_iso_3166_1_fkey FOREIGN KEY (iso_3166_1) REFERENCES public.country(iso_3166_1);

ALTER TABLE ONLY public.collection
    ADD CONSTRAINT collection_original_language_fkey FOREIGN KEY (original_language) REFERENCES public.language(iso_639_1);

ALTER TABLE ONLY public.collection_translation
    ADD CONSTRAINT collection_translation_collection_id_fkey FOREIGN KEY (collection_id) REFERENCES public.collection(collection_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.collection_translation
    ADD CONSTRAINT collection_translation_iso_3166_1_fkey FOREIGN KEY (iso_3166_1) REFERENCES public.country(iso_3166_1);

ALTER TABLE ONLY public.collection_translation
    ADD CONSTRAINT collection_translation_iso_639_1_fkey FOREIGN KEY (iso_639_1) REFERENCES public.language(iso_639_1);

ALTER TABLE ONLY public.company
    ADD CONSTRAINT company_origin_country_fkey FOREIGN KEY (origin_country) REFERENCES public.country(iso_3166_1);

ALTER TABLE ONLY public.company
    ADD CONSTRAINT company_parent_company_id_fkey FOREIGN KEY (parent_company_id) REFERENCES public.company(company_id);

ALTER TABLE ONLY public.job
    ADD CONSTRAINT job_department_id_fkey FOREIGN KEY (department_id) REFERENCES public.department(department_id);

ALTER TABLE ONLY public.person_aka
    ADD CONSTRAINT person_aka_person_id_fkey FOREIGN KEY (person_id) REFERENCES public.person(person_id) ON DELETE CASCADE;

CREATE FUNCTION public.fn_get_movie_cast_count(p_movie_id integer) RETURNS integer
    LANGUAGE sql STABLE
    AS $$
    SELECT COUNT(*)::INTEGER FROM Movie_Cast WHERE movie_id = p_movie_id;
$$;

ALTER FUNCTION public.fn_get_movie_cast_count(p_movie_id integer) OWNER TO postgres;

CREATE FUNCTION public.fn_get_movie_crew_count(p_movie_id integer) RETURNS integer
    LANGUAGE sql STABLE
    AS $$
    SELECT COUNT(*)::INTEGER FROM Movie_Crew WHERE movie_id = p_movie_id;
$$;

ALTER FUNCTION public.fn_get_movie_crew_count(p_movie_id integer) OWNER TO postgres;

CREATE FUNCTION public.fn_get_movie_review_count(p_movie_id integer) RETURNS integer
    LANGUAGE sql STABLE
    AS $$
    SELECT COUNT(*)::INTEGER FROM User_Review WHERE movie_id = p_movie_id;
$$;

ALTER FUNCTION public.fn_get_movie_review_count(p_movie_id integer) OWNER TO postgres;

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

ALTER FUNCTION public.fn_get_movie_runtime_fmt(p_movie_id integer) OWNER TO postgres;

CREATE FUNCTION public.fn_get_movie_user_avg(p_movie_id integer) RETURNS numeric
    LANGUAGE sql STABLE
    AS $$
    SELECT ROUND(AVG(rating)::NUMERIC, 2)
    FROM   User_Movie_Rating
    WHERE  movie_id = p_movie_id;
$$;

ALTER FUNCTION public.fn_get_movie_user_avg(p_movie_id integer) OWNER TO postgres;

CREATE FUNCTION public.fn_get_movie_vote_avg(p_movie_id integer) RETURNS numeric
    LANGUAGE sql STABLE
    AS $$
    SELECT vote_average FROM Movie WHERE movie_id = p_movie_id;
$$;

ALTER FUNCTION public.fn_get_movie_vote_avg(p_movie_id integer) OWNER TO postgres;

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

ALTER FUNCTION public.fn_get_person_movie_count(p_person_id integer) OWNER TO postgres;

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

ALTER FUNCTION public.fn_top_rated_movies(p_genre_id integer, p_top_n integer) OWNER TO postgres;

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

ALTER PROCEDURE public.sp_cur_top_rated_movies(IN p_genre_id integer, IN p_top_n integer) OWNER TO postgres;

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

ALTER FUNCTION public.sp_getmoviedetail(p_movie_id integer) OWNER TO postgres;

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

ALTER FUNCTION public.sp_getmoviesbygenre(p_genre_id integer, p_page integer, p_page_size integer) OWNER TO postgres;

CREATE FUNCTION public.sp_getmoviesneedingetlsync(p_interval interval DEFAULT '7 days'::interval, p_limit integer DEFAULT 100) RETURNS TABLE(movie_id integer, tmdb_movie_id integer, etl_synced_at timestamp with time zone)
    LANGUAGE sql STABLE
    AS $$
    SELECT movie_id, tmdb_movie_id, etl_synced_at
    FROM   Movie
    WHERE  fn_etl_needs_sync(etl_synced_at, p_interval)
    ORDER  BY etl_synced_at NULLS FIRST
    LIMIT  p_limit;
$$;

ALTER FUNCTION public.sp_getmoviesneedingetlsync(p_interval interval, p_limit integer) OWNER TO postgres;

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

ALTER PROCEDURE public.sp_insertmoviecast(IN p_movie_id integer, IN p_person_id integer, IN p_cast_order smallint, IN p_character_name character varying, IN p_credit_id character varying) OWNER TO postgres;

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

ALTER PROCEDURE public.sp_insertmoviecertification(IN p_movie_id integer, IN p_cert_std_id smallint) OWNER TO postgres;

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

ALTER PROCEDURE public.sp_insertmoviecompany(IN p_movie_id integer, IN p_company_id integer) OWNER TO postgres;

CREATE PROCEDURE public.sp_insertmoviecountry(IN p_movie_id integer, IN p_iso_3166_1 character)
    LANGUAGE plpgsql
    AS $$
BEGIN
    INSERT INTO Movie_Country (movie_id, iso_3166_1) VALUES (p_movie_id, p_iso_3166_1) ON CONFLICT DO NOTHING;
END;
$$;

ALTER PROCEDURE public.sp_insertmoviecountry(IN p_movie_id integer, IN p_iso_3166_1 character) OWNER TO postgres;

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

ALTER PROCEDURE public.sp_insertmoviegenre(IN p_movie_id integer, IN p_genre_id integer) OWNER TO postgres;

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

ALTER PROCEDURE public.sp_insertmoviekeyword(IN p_movie_id integer, IN p_keyword_id integer, IN p_keyword_name character varying) OWNER TO postgres;

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

ALTER PROCEDURE public.sp_insertmovielanguage(IN p_movie_id integer, IN p_iso_639_1 character, IN p_language_type character varying) OWNER TO postgres;

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

ALTER PROCEDURE public.sp_insertmoviewatchprovider(IN p_movie_id integer, IN p_provider_id integer, IN p_iso_3166_1 character, IN p_availability_type character varying, IN p_display_priority smallint) OWNER TO postgres;

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

ALTER PROCEDURE public.sp_syncmoviecast(IN p_movie_id integer, IN p_cast jsonb) OWNER TO postgres;

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

ALTER PROCEDURE public.sp_syncmoviecrew(IN p_movie_id integer, IN p_crew jsonb) OWNER TO postgres;

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

ALTER PROCEDURE public.sp_syncmoviemetadata(IN p_movie_id integer, IN p_data jsonb) OWNER TO postgres;

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

ALTER PROCEDURE public.sp_togglemoviefavorite(IN p_user_id integer, IN p_movie_id integer) OWNER TO postgres;

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

ALTER PROCEDURE public.sp_togglemoviewatchlist(IN p_user_id integer, IN p_movie_id integer) OWNER TO postgres;

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

ALTER PROCEDURE public.sp_upsertmovie(IN p_data jsonb) OWNER TO postgres;

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

ALTER TABLE public.movie OWNER TO postgres;

ALTER TABLE ONLY public.movie
    ADD CONSTRAINT movie_pkey PRIMARY KEY (movie_id);

ALTER TABLE ONLY public.movie
    ADD CONSTRAINT uq_movie_imdb_id UNIQUE (imdb_id);

ALTER TABLE ONLY public.movie
    ADD CONSTRAINT uq_movie_tmdb_id UNIQUE (tmdb_movie_id);

CREATE TABLE public.movie_cast (
    movie_id integer NOT NULL,
    person_id integer NOT NULL,
    cast_order smallint NOT NULL,
    character_name character varying(300) DEFAULT ''::character varying NOT NULL,
    credit_id character varying(50),
    CONSTRAINT chk_movie_cast_order CHECK ((cast_order > 0))
);

ALTER TABLE public.movie_cast OWNER TO postgres;

ALTER TABLE ONLY public.movie_cast
    ADD CONSTRAINT movie_cast_pkey PRIMARY KEY (movie_id, person_id, cast_order);

ALTER TABLE ONLY public.movie_cast
    ADD CONSTRAINT uq_movie_cast_credit UNIQUE (credit_id);

CREATE TABLE public.movie_certification (
    movie_id integer NOT NULL,
    cert_std_id smallint NOT NULL,
    country_code character(2) NOT NULL,
    language_code character(2) NOT NULL,
    release_type smallint NOT NULL,
    descriptors text
);

ALTER TABLE public.movie_certification OWNER TO postgres;

ALTER TABLE ONLY public.movie_certification
    ADD CONSTRAINT movie_certification_pkey PRIMARY KEY (movie_id, country_code, language_code, release_type);

CREATE TABLE public.movie_company (
    movie_id integer NOT NULL,
    company_id integer NOT NULL
);

ALTER TABLE public.movie_company OWNER TO postgres;

ALTER TABLE ONLY public.movie_company
    ADD CONSTRAINT movie_company_pkey PRIMARY KEY (movie_id, company_id);

CREATE TABLE public.movie_country (
    movie_id integer NOT NULL,
    iso_3166_1 character(2) NOT NULL
);

ALTER TABLE public.movie_country OWNER TO postgres;

ALTER TABLE ONLY public.movie_country
    ADD CONSTRAINT movie_country_pkey PRIMARY KEY (movie_id, iso_3166_1);

CREATE TABLE public.movie_crew (
    movie_id integer NOT NULL,
    person_id integer NOT NULL,
    department_id smallint NOT NULL,
    job_id smallint NOT NULL,
    credit_id character varying(50)
);

ALTER TABLE public.movie_crew OWNER TO postgres;

ALTER TABLE ONLY public.movie_crew
    ADD CONSTRAINT movie_crew_pkey PRIMARY KEY (movie_id, person_id, department_id, job_id);

ALTER TABLE ONLY public.movie_crew
    ADD CONSTRAINT uq_movie_crew_credit UNIQUE (credit_id);

CREATE TABLE public.movie_genre (
    movie_id integer NOT NULL,
    genre_id integer NOT NULL
);

ALTER TABLE public.movie_genre OWNER TO postgres;

ALTER TABLE ONLY public.movie_genre
    ADD CONSTRAINT movie_genre_pkey PRIMARY KEY (movie_id, genre_id);

CREATE TABLE public.movie_keyword (
    movie_id integer NOT NULL,
    keyword_id integer NOT NULL
);

ALTER TABLE public.movie_keyword OWNER TO postgres;

ALTER TABLE ONLY public.movie_keyword
    ADD CONSTRAINT movie_keyword_pkey PRIMARY KEY (movie_id, keyword_id);

CREATE TABLE public.movie_language (
    movie_id integer NOT NULL,
    iso_639_1 character(2) NOT NULL,
    language_type character varying(10) NOT NULL,
    CONSTRAINT chk_movie_language_type CHECK (((language_type)::text = ANY ((ARRAY['spoken'::character varying, 'original'::character varying])::text[])))
);

ALTER TABLE public.movie_language OWNER TO postgres;

ALTER TABLE ONLY public.movie_language
    ADD CONSTRAINT movie_language_pkey PRIMARY KEY (movie_id, iso_639_1, language_type);

CREATE TABLE public.movie_watch_provider (
    movie_id integer NOT NULL,
    provider_id integer NOT NULL,
    iso_3166_1 character(2) NOT NULL,
    availability_type character varying(10) NOT NULL,
    display_priority smallint NOT NULL,
    CONSTRAINT chk_watch_avail_movie CHECK (((availability_type)::text = ANY ((ARRAY['flatrate'::character varying, 'rent'::character varying, 'buy'::character varying, 'free'::character varying, 'ads'::character varying])::text[])))
);

ALTER TABLE public.movie_watch_provider OWNER TO postgres;

ALTER TABLE ONLY public.movie_watch_provider
    ADD CONSTRAINT movie_watch_provider_pkey PRIMARY KEY (movie_id, provider_id, iso_3166_1, availability_type);

CREATE TRIGGER trg_audit_movie AFTER INSERT OR DELETE OR UPDATE ON public.movie FOR EACH ROW EXECUTE FUNCTION public.fn_trg_audit_log('movie_id');

CREATE TRIGGER trg_set_updated_at_movie BEFORE UPDATE ON public.movie FOR EACH ROW EXECUTE FUNCTION public.fn_trg_set_updated_at();

ALTER TABLE ONLY public.movie_certification
    ADD CONSTRAINT fk_cert_std FOREIGN KEY (cert_std_id) REFERENCES public.certification_standard(cert_std_id);

ALTER TABLE ONLY public.movie_cast
    ADD CONSTRAINT movie_cast_movie_id_fkey FOREIGN KEY (movie_id) REFERENCES public.movie(movie_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.movie_cast
    ADD CONSTRAINT movie_cast_person_id_fkey FOREIGN KEY (person_id) REFERENCES public.person(person_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.movie_certification
    ADD CONSTRAINT movie_certification_cert_std_id_fkey FOREIGN KEY (cert_std_id) REFERENCES public.certification_standard(cert_std_id);

ALTER TABLE ONLY public.movie_certification
    ADD CONSTRAINT movie_certification_movie_id_fkey FOREIGN KEY (movie_id) REFERENCES public.movie(movie_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.movie
    ADD CONSTRAINT movie_collection_id_fkey FOREIGN KEY (collection_id) REFERENCES public.collection(collection_id);

ALTER TABLE ONLY public.movie_company
    ADD CONSTRAINT movie_company_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.company(company_id);

ALTER TABLE ONLY public.movie_company
    ADD CONSTRAINT movie_company_movie_id_fkey FOREIGN KEY (movie_id) REFERENCES public.movie(movie_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.movie_country
    ADD CONSTRAINT movie_country_iso_3166_1_fkey FOREIGN KEY (iso_3166_1) REFERENCES public.country(iso_3166_1);

ALTER TABLE ONLY public.movie_country
    ADD CONSTRAINT movie_country_movie_id_fkey FOREIGN KEY (movie_id) REFERENCES public.movie(movie_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.movie_crew
    ADD CONSTRAINT movie_crew_department_id_fkey FOREIGN KEY (department_id) REFERENCES public.department(department_id);

ALTER TABLE ONLY public.movie_crew
    ADD CONSTRAINT movie_crew_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.job(job_id);

ALTER TABLE ONLY public.movie_crew
    ADD CONSTRAINT movie_crew_movie_id_fkey FOREIGN KEY (movie_id) REFERENCES public.movie(movie_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.movie_crew
    ADD CONSTRAINT movie_crew_person_id_fkey FOREIGN KEY (person_id) REFERENCES public.person(person_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.movie_genre
    ADD CONSTRAINT movie_genre_genre_id_fkey FOREIGN KEY (genre_id) REFERENCES public.genre(genre_id);

ALTER TABLE ONLY public.movie_genre
    ADD CONSTRAINT movie_genre_movie_id_fkey FOREIGN KEY (movie_id) REFERENCES public.movie(movie_id);

ALTER TABLE ONLY public.movie_keyword
    ADD CONSTRAINT movie_keyword_keyword_id_fkey FOREIGN KEY (keyword_id) REFERENCES public.keyword(keyword_id);

ALTER TABLE ONLY public.movie_keyword
    ADD CONSTRAINT movie_keyword_movie_id_fkey FOREIGN KEY (movie_id) REFERENCES public.movie(movie_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.movie_language
    ADD CONSTRAINT movie_language_iso_639_1_fkey FOREIGN KEY (iso_639_1) REFERENCES public.language(iso_639_1);

ALTER TABLE ONLY public.movie_language
    ADD CONSTRAINT movie_language_movie_id_fkey FOREIGN KEY (movie_id) REFERENCES public.movie(movie_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.movie
    ADD CONSTRAINT movie_original_language_fkey FOREIGN KEY (original_language) REFERENCES public.language(iso_639_1);

ALTER TABLE ONLY public.movie_watch_provider
    ADD CONSTRAINT movie_watch_provider_iso_3166_1_fkey FOREIGN KEY (iso_3166_1) REFERENCES public.country(iso_3166_1);

ALTER TABLE ONLY public.movie_watch_provider
    ADD CONSTRAINT movie_watch_provider_movie_id_fkey FOREIGN KEY (movie_id) REFERENCES public.movie(movie_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.movie_watch_provider
    ADD CONSTRAINT movie_watch_provider_provider_id_fkey FOREIGN KEY (provider_id) REFERENCES public.watch_provider(provider_id);

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

ALTER FUNCTION public.fn_get_tv_runtime_fmt(p_series_id integer) OWNER TO postgres;

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

ALTER FUNCTION public.sp_gettvseriesdetail(p_series_id integer) OWNER TO postgres;

CREATE FUNCTION public.sp_gettvseriesneedingetlsync(p_interval interval DEFAULT '7 days'::interval, p_limit integer DEFAULT 100) RETURNS TABLE(series_id integer, tmdb_series_id integer, etl_synced_at timestamp with time zone)
    LANGUAGE sql STABLE
    AS $$
    SELECT series_id, tmdb_series_id, etl_synced_at
    FROM   TV_Series
    WHERE  fn_etl_needs_sync(etl_synced_at, p_interval)
    ORDER  BY etl_synced_at NULLS FIRST
    LIMIT  p_limit;
$$;

ALTER FUNCTION public.sp_gettvseriesneedingetlsync(p_interval interval, p_limit integer) OWNER TO postgres;

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

ALTER PROCEDURE public.sp_inserttvcast(IN p_series_id integer, IN p_person_id integer, IN p_cast_order smallint, IN p_character character varying, IN p_credit_id character varying) OWNER TO postgres;

CREATE PROCEDURE public.sp_inserttvcreator(IN p_series_id integer, IN p_person_id integer, IN p_credit_id character varying DEFAULT NULL::character varying)
    LANGUAGE plpgsql
    AS $$
BEGIN
    INSERT INTO TV_Creator (series_id, person_id, credit_id)
    VALUES (p_series_id, p_person_id, p_credit_id)
    ON CONFLICT (series_id, person_id) DO NOTHING;
END;
$$;

ALTER PROCEDURE public.sp_inserttvcreator(IN p_series_id integer, IN p_person_id integer, IN p_credit_id character varying) OWNER TO postgres;

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

ALTER PROCEDURE public.sp_inserttvcrew(IN p_series_id integer, IN p_person_id integer, IN p_department_id smallint, IN p_job_id smallint, IN p_credit_id character varying) OWNER TO postgres;

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

ALTER PROCEDURE public.sp_synctvcast(IN p_series_id integer, IN p_cast jsonb) OWNER TO postgres;

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

ALTER PROCEDURE public.sp_synctvcreators(IN p_series_id integer, IN p_creators jsonb) OWNER TO postgres;

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

ALTER PROCEDURE public.sp_synctvcrew(IN p_series_id integer, IN p_crew jsonb) OWNER TO postgres;

CREATE TABLE public.episode_cast (
    episode_id integer NOT NULL,
    person_id integer NOT NULL,
    cast_order smallint NOT NULL,
    character_name character varying(300) DEFAULT ''::character varying NOT NULL,
    credit_id character varying(50),
    is_guest boolean DEFAULT false NOT NULL,
    CONSTRAINT chk_episode_cast_order CHECK ((cast_order > 0))
);

ALTER TABLE public.episode_cast OWNER TO postgres;

ALTER TABLE ONLY public.episode_cast
    ADD CONSTRAINT episode_cast_pkey PRIMARY KEY (episode_id, person_id, cast_order);

CREATE TABLE public.episode_crew (
    episode_id integer NOT NULL,
    person_id integer NOT NULL,
    department_id smallint NOT NULL,
    job_id smallint NOT NULL,
    credit_id character varying(50)
);

ALTER TABLE public.episode_crew OWNER TO postgres;

ALTER TABLE ONLY public.episode_crew
    ADD CONSTRAINT episode_crew_pkey PRIMARY KEY (episode_id, person_id, department_id, job_id);

CREATE TABLE public.tv_cast (
    series_id integer NOT NULL,
    person_id integer NOT NULL,
    cast_order smallint NOT NULL,
    character_name character varying(300) DEFAULT ''::character varying NOT NULL,
    credit_id character varying(50),
    CONSTRAINT chk_tv_cast_order CHECK ((cast_order > 0))
);

ALTER TABLE public.tv_cast OWNER TO postgres;

ALTER TABLE ONLY public.tv_cast
    ADD CONSTRAINT tv_cast_pkey PRIMARY KEY (series_id, person_id, cast_order);

ALTER TABLE ONLY public.tv_cast
    ADD CONSTRAINT uq_tv_cast_credit UNIQUE (credit_id);

CREATE TABLE public.tv_certification (
    series_id integer NOT NULL,
    iso_3166_1 character(2) NOT NULL,
    rating character varying(20) NOT NULL,
    descriptors text[],
    CONSTRAINT chk_tv_cert_rating_nonempty CHECK (((rating)::text <> ''::text))
);

ALTER TABLE public.tv_certification OWNER TO postgres;

ALTER TABLE ONLY public.tv_certification
    ADD CONSTRAINT tv_certification_pkey PRIMARY KEY (series_id, iso_3166_1);

CREATE TABLE public.tv_company (
    series_id integer NOT NULL,
    company_id integer NOT NULL
);

ALTER TABLE public.tv_company OWNER TO postgres;

ALTER TABLE ONLY public.tv_company
    ADD CONSTRAINT tv_company_pkey PRIMARY KEY (series_id, company_id);

CREATE TABLE public.tv_country (
    series_id integer NOT NULL,
    iso_3166_1 character(2) NOT NULL
);

ALTER TABLE public.tv_country OWNER TO postgres;

ALTER TABLE ONLY public.tv_country
    ADD CONSTRAINT tv_country_pkey PRIMARY KEY (series_id, iso_3166_1);

CREATE TABLE public.tv_creator (
    series_id integer NOT NULL,
    person_id integer NOT NULL,
    credit_id character varying(50)
);

ALTER TABLE public.tv_creator OWNER TO postgres;

ALTER TABLE ONLY public.tv_creator
    ADD CONSTRAINT tv_creator_pkey PRIMARY KEY (series_id, person_id);

ALTER TABLE ONLY public.tv_creator
    ADD CONSTRAINT uq_tv_creator_credit UNIQUE (credit_id);

CREATE TABLE public.tv_crew (
    series_id integer NOT NULL,
    person_id integer NOT NULL,
    department_id smallint NOT NULL,
    job_id smallint NOT NULL,
    credit_id character varying(50)
);

ALTER TABLE public.tv_crew OWNER TO postgres;

ALTER TABLE ONLY public.tv_crew
    ADD CONSTRAINT tv_crew_pkey PRIMARY KEY (series_id, person_id, department_id, job_id);

ALTER TABLE ONLY public.tv_crew
    ADD CONSTRAINT uq_tv_crew_credit UNIQUE (credit_id);

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

ALTER TABLE public.tv_episode OWNER TO postgres;

ALTER TABLE ONLY public.tv_episode
    ADD CONSTRAINT tv_episode_pkey PRIMARY KEY (episode_id);

ALTER TABLE ONLY public.tv_episode
    ADD CONSTRAINT uq_episode_per_season UNIQUE (season_id, episode_number);

ALTER TABLE ONLY public.tv_episode
    ADD CONSTRAINT uq_episode_tmdb_id UNIQUE (tmdb_episode_id);

CREATE TABLE public.tv_genre (
    series_id integer NOT NULL,
    genre_id integer NOT NULL
);

ALTER TABLE public.tv_genre OWNER TO postgres;

ALTER TABLE ONLY public.tv_genre
    ADD CONSTRAINT tv_genre_pkey PRIMARY KEY (series_id, genre_id);

CREATE TABLE public.tv_keyword (
    series_id integer NOT NULL,
    keyword_id integer NOT NULL
);

ALTER TABLE public.tv_keyword OWNER TO postgres;

ALTER TABLE ONLY public.tv_keyword
    ADD CONSTRAINT tv_keyword_pkey PRIMARY KEY (series_id, keyword_id);

CREATE TABLE public.tv_language (
    series_id integer NOT NULL,
    iso_639_1 character(2) NOT NULL
);

ALTER TABLE public.tv_language OWNER TO postgres;

ALTER TABLE ONLY public.tv_language
    ADD CONSTRAINT tv_language_pkey PRIMARY KEY (series_id, iso_639_1);

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

ALTER TABLE public.tv_season OWNER TO postgres;

ALTER TABLE ONLY public.tv_season
    ADD CONSTRAINT tv_season_pkey PRIMARY KEY (season_id);

ALTER TABLE ONLY public.tv_season
    ADD CONSTRAINT uq_season_per_series UNIQUE (series_id, season_number);

ALTER TABLE ONLY public.tv_season
    ADD CONSTRAINT uq_season_tmdb_id UNIQUE (tmdb_season_id);

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

ALTER TABLE public.tv_series OWNER TO postgres;

ALTER TABLE ONLY public.tv_series
    ADD CONSTRAINT tv_series_pkey PRIMARY KEY (series_id);

ALTER TABLE ONLY public.tv_series
    ADD CONSTRAINT uq_tv_tmdb_id UNIQUE (tmdb_series_id);

CREATE TABLE public.tv_watch_provider (
    series_id integer NOT NULL,
    provider_id integer NOT NULL,
    iso_3166_1 character(2) NOT NULL,
    availability_type character varying(10) NOT NULL,
    display_priority smallint NOT NULL,
    CONSTRAINT chk_watch_avail_tv CHECK (((availability_type)::text = ANY ((ARRAY['flatrate'::character varying, 'rent'::character varying, 'buy'::character varying, 'free'::character varying, 'ads'::character varying])::text[])))
);

ALTER TABLE public.tv_watch_provider OWNER TO postgres;

ALTER TABLE ONLY public.tv_watch_provider
    ADD CONSTRAINT tv_watch_provider_pkey PRIMARY KEY (series_id, provider_id, iso_3166_1, availability_type);

CREATE TRIGGER trg_audit_tv_series AFTER INSERT OR DELETE OR UPDATE ON public.tv_series FOR EACH ROW EXECUTE FUNCTION public.fn_trg_audit_log('series_id');

CREATE TRIGGER trg_episode_count_sync AFTER INSERT OR DELETE ON public.tv_episode FOR EACH ROW EXECUTE FUNCTION public.fn_trg_episode_count_sync();

CREATE TRIGGER trg_set_updated_at_tv_series BEFORE UPDATE ON public.tv_series FOR EACH ROW EXECUTE FUNCTION public.fn_trg_set_updated_at();

ALTER TABLE ONLY public.episode_cast
    ADD CONSTRAINT episode_cast_episode_id_fkey FOREIGN KEY (episode_id) REFERENCES public.tv_episode(episode_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.episode_cast
    ADD CONSTRAINT episode_cast_person_id_fkey FOREIGN KEY (person_id) REFERENCES public.person(person_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.episode_crew
    ADD CONSTRAINT episode_crew_department_id_fkey FOREIGN KEY (department_id) REFERENCES public.department(department_id);

ALTER TABLE ONLY public.episode_crew
    ADD CONSTRAINT episode_crew_episode_id_fkey FOREIGN KEY (episode_id) REFERENCES public.tv_episode(episode_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.episode_crew
    ADD CONSTRAINT episode_crew_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.job(job_id);

ALTER TABLE ONLY public.episode_crew
    ADD CONSTRAINT episode_crew_person_id_fkey FOREIGN KEY (person_id) REFERENCES public.person(person_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.tv_cast
    ADD CONSTRAINT tv_cast_person_id_fkey FOREIGN KEY (person_id) REFERENCES public.person(person_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.tv_cast
    ADD CONSTRAINT tv_cast_series_id_fkey FOREIGN KEY (series_id) REFERENCES public.tv_series(series_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.tv_certification
    ADD CONSTRAINT tv_certification_iso_3166_1_fkey FOREIGN KEY (iso_3166_1) REFERENCES public.country(iso_3166_1);

ALTER TABLE ONLY public.tv_certification
    ADD CONSTRAINT tv_certification_series_id_fkey FOREIGN KEY (series_id) REFERENCES public.tv_series(series_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.tv_company
    ADD CONSTRAINT tv_company_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.company(company_id);

ALTER TABLE ONLY public.tv_company
    ADD CONSTRAINT tv_company_series_id_fkey FOREIGN KEY (series_id) REFERENCES public.tv_series(series_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.tv_country
    ADD CONSTRAINT tv_country_iso_3166_1_fkey FOREIGN KEY (iso_3166_1) REFERENCES public.country(iso_3166_1);

ALTER TABLE ONLY public.tv_country
    ADD CONSTRAINT tv_country_series_id_fkey FOREIGN KEY (series_id) REFERENCES public.tv_series(series_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.tv_creator
    ADD CONSTRAINT tv_creator_person_id_fkey FOREIGN KEY (person_id) REFERENCES public.person(person_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.tv_creator
    ADD CONSTRAINT tv_creator_series_id_fkey FOREIGN KEY (series_id) REFERENCES public.tv_series(series_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.tv_crew
    ADD CONSTRAINT tv_crew_department_id_fkey FOREIGN KEY (department_id) REFERENCES public.department(department_id);

ALTER TABLE ONLY public.tv_crew
    ADD CONSTRAINT tv_crew_job_id_fkey FOREIGN KEY (job_id) REFERENCES public.job(job_id);

ALTER TABLE ONLY public.tv_crew
    ADD CONSTRAINT tv_crew_person_id_fkey FOREIGN KEY (person_id) REFERENCES public.person(person_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.tv_crew
    ADD CONSTRAINT tv_crew_series_id_fkey FOREIGN KEY (series_id) REFERENCES public.tv_series(series_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.tv_episode
    ADD CONSTRAINT tv_episode_season_id_fkey FOREIGN KEY (season_id) REFERENCES public.tv_season(season_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.tv_episode
    ADD CONSTRAINT tv_episode_series_id_fkey FOREIGN KEY (series_id) REFERENCES public.tv_series(series_id);

ALTER TABLE ONLY public.tv_genre
    ADD CONSTRAINT tv_genre_genre_id_fkey FOREIGN KEY (genre_id) REFERENCES public.genre(genre_id);

ALTER TABLE ONLY public.tv_genre
    ADD CONSTRAINT tv_genre_series_id_fkey FOREIGN KEY (series_id) REFERENCES public.tv_series(series_id);

ALTER TABLE ONLY public.tv_keyword
    ADD CONSTRAINT tv_keyword_keyword_id_fkey FOREIGN KEY (keyword_id) REFERENCES public.keyword(keyword_id);

ALTER TABLE ONLY public.tv_keyword
    ADD CONSTRAINT tv_keyword_series_id_fkey FOREIGN KEY (series_id) REFERENCES public.tv_series(series_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.tv_language
    ADD CONSTRAINT tv_language_iso_639_1_fkey FOREIGN KEY (iso_639_1) REFERENCES public.language(iso_639_1);

ALTER TABLE ONLY public.tv_language
    ADD CONSTRAINT tv_language_series_id_fkey FOREIGN KEY (series_id) REFERENCES public.tv_series(series_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.tv_season
    ADD CONSTRAINT tv_season_series_id_fkey FOREIGN KEY (series_id) REFERENCES public.tv_series(series_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.tv_series
    ADD CONSTRAINT tv_series_original_language_fkey FOREIGN KEY (original_language) REFERENCES public.language(iso_639_1);

ALTER TABLE ONLY public.tv_watch_provider
    ADD CONSTRAINT tv_watch_provider_iso_3166_1_fkey FOREIGN KEY (iso_3166_1) REFERENCES public.country(iso_3166_1);

ALTER TABLE ONLY public.tv_watch_provider
    ADD CONSTRAINT tv_watch_provider_provider_id_fkey FOREIGN KEY (provider_id) REFERENCES public.watch_provider(provider_id);

ALTER TABLE ONLY public.tv_watch_provider
    ADD CONSTRAINT tv_watch_provider_series_id_fkey FOREIGN KEY (series_id) REFERENCES public.tv_series(series_id) ON DELETE CASCADE;

CREATE FUNCTION public.fn_user_activity_report(p_year integer DEFAULT (EXTRACT(year FROM now()))::integer, p_month integer DEFAULT (EXTRACT(month FROM now()))::integer) RETURNS TABLE(o_user_id integer, o_username character varying, o_period date, o_review_count bigint, o_fav_count bigint, o_watchlist_count bigint, o_avg_rating numeric)
    LANGUAGE plpgsql
    AS $$
DECLARE
    cur_users CURSOR FOR
        SELECT u.user_id, u.username
        FROM   "User" u
        WHERE  u.is_active = TRUE
        ORDER  BY u.user_id;

    rec      RECORD;
    v_period DATE;
BEGIN
    v_period := make_date(p_year, p_month, 1);

    OPEN cur_users;
    LOOP
        FETCH cur_users INTO rec;
        EXIT WHEN NOT FOUND;

        o_user_id := rec.user_id;
        o_username := rec.username;
        o_period   := v_period;

        SELECT COUNT(*) INTO o_review_count
        FROM   User_Review ur
        WHERE  ur.user_id = rec.user_id
          AND  DATE_TRUNC('month', ur.created_at) = v_period;

        SELECT COUNT(*) INTO o_fav_count
        FROM   User_Movie_Favorite f
        WHERE  f.user_id = rec.user_id
          AND  DATE_TRUNC('month', f.created_at) = v_period;

        SELECT COUNT(*) INTO o_watchlist_count
        FROM   User_Movie_Watchlist w
        WHERE  w.user_id = rec.user_id
          AND  DATE_TRUNC('month', w.created_at) = v_period;

        SELECT ROUND(AVG(ur.rating), 2) INTO o_avg_rating
        FROM   User_Review ur
        WHERE  ur.user_id = rec.user_id
          AND  ur.rating IS NOT NULL;

        RETURN NEXT;
    END LOOP;
    CLOSE cur_users;
END;
$$;

ALTER FUNCTION public.fn_user_activity_report(p_year integer, p_month integer) OWNER TO postgres;

CREATE FUNCTION public.sp_getauditlog(p_table_name character varying DEFAULT NULL::character varying, p_from_ts timestamp with time zone DEFAULT (now() - '7 days'::interval), p_to_ts timestamp with time zone DEFAULT now(), p_page integer DEFAULT 1, p_page_size integer DEFAULT 50) RETURNS TABLE(audit_id bigint, table_name character varying, record_id text, action character varying, changed_by integer, username character varying, changed_at timestamp with time zone)
    LANGUAGE sql STABLE
    AS $$
    SELECT
        al.audit_id, al.table_name, al.record_id, al.action,
        al.changed_by, u.username, al.changed_at
    FROM   Audit_Log al
    LEFT JOIN "User" u ON u.user_id = al.changed_by
    WHERE (p_table_name IS NULL OR al.table_name = p_table_name)
      AND  al.changed_at BETWEEN p_from_ts AND p_to_ts
    ORDER  BY al.changed_at DESC
    LIMIT  p_page_size OFFSET (p_page-1)*p_page_size;
$$;

ALTER FUNCTION public.sp_getauditlog(p_table_name character varying, p_from_ts timestamp with time zone, p_to_ts timestamp with time zone, p_page integer, p_page_size integer) OWNER TO postgres;

CREATE FUNCTION public.sp_getetllog(p_status character varying DEFAULT NULL::character varying, p_page integer DEFAULT 1, p_page_size integer DEFAULT 50) RETURNS TABLE(log_id bigint, endpoint character varying, tmdb_id integer, media_type character varying, status character varying, records_processed integer, error_message text, started_at timestamp with time zone, finished_at timestamp with time zone, duration_seconds numeric)
    LANGUAGE sql STABLE
    AS $$
    SELECT
        log_id, endpoint, tmdb_id, media_type, status,
        records_processed, error_message, started_at, finished_at,
        ROUND(EXTRACT(EPOCH FROM (finished_at - started_at))::NUMERIC, 2)
    FROM   ETL_Log
    WHERE (p_status IS NULL OR status = p_status)
    ORDER  BY started_at DESC
    LIMIT  p_page_size OFFSET (p_page-1)*p_page_size;
$$;

ALTER FUNCTION public.sp_getetllog(p_status character varying, p_page integer, p_page_size integer) OWNER TO postgres;

CREATE FUNCTION public.sp_getsystemconfig(p_key character varying DEFAULT NULL::character varying) RETURNS TABLE(config_key character varying, config_value text, description text, updated_at timestamp with time zone)
    LANGUAGE sql STABLE
    AS $$
    SELECT config_key, config_value, description, updated_at
    FROM   System_Config
    WHERE  p_key IS NULL OR config_key = p_key
    ORDER  BY config_key;
$$;

ALTER FUNCTION public.sp_getsystemconfig(p_key character varying) OWNER TO postgres;

CREATE FUNCTION public.sp_getusermoviefavorites(p_user_id integer, p_page integer DEFAULT 1, p_page_size integer DEFAULT 20) RETURNS TABLE(movie_id integer, title character varying, poster_path character varying, added_at timestamp with time zone)
    LANGUAGE sql STABLE
    AS $$
    SELECT m.movie_id, m.title, m.poster_path, f.created_at
    FROM   User_Movie_Favorite f
    JOIN   Movie m ON m.movie_id = f.movie_id
    WHERE  f.user_id = p_user_id
    ORDER  BY f.created_at DESC
    LIMIT  p_page_size OFFSET (p_page-1)*p_page_size;
$$;

ALTER FUNCTION public.sp_getusermoviefavorites(p_user_id integer, p_page integer, p_page_size integer) OWNER TO postgres;

CREATE FUNCTION public.sp_getuserprofile(p_user_id integer) RETURNS TABLE(user_id integer, username character varying, name character varying, email character varying, iso_639_1 character, iso_3166_1 character, is_active boolean, created_at timestamp with time zone, last_login_at timestamp with time zone)
    LANGUAGE sql STABLE
    AS $$
    SELECT user_id, username, name, email, iso_639_1, iso_3166_1, is_active, created_at, last_login_at
    FROM   "User"
    WHERE  user_id = p_user_id;
$$;

ALTER FUNCTION public.sp_getuserprofile(p_user_id integer) OWNER TO postgres;

CREATE FUNCTION public.sp_getuserreviews(p_user_id integer, p_page integer DEFAULT 1, p_page_size integer DEFAULT 10) RETURNS TABLE(review_id integer, media_type character varying, title text, content text, rating numeric, created_at timestamp with time zone)
    LANGUAGE sql STABLE
    AS $$
    SELECT
        r.review_id,
        r.media_type,
        COALESCE(m.title, s.name)::TEXT,
        r.content,
        r.rating,
        r.created_at
    FROM   User_Review r
    LEFT JOIN Movie     m ON m.movie_id   = r.movie_id
    LEFT JOIN TV_Series s ON s.series_id  = r.series_id
    WHERE  r.user_id = p_user_id
    ORDER  BY r.created_at DESC
    LIMIT  p_page_size OFFSET (p_page-1)*p_page_size;
$$;

ALTER FUNCTION public.sp_getuserreviews(p_user_id integer, p_page integer, p_page_size integer) OWNER TO postgres;

CREATE FUNCTION public.sp_getusertvfavorites(p_user_id integer, p_page integer DEFAULT 1, p_page_size integer DEFAULT 20) RETURNS TABLE(series_id integer, name character varying, poster_path character varying, added_at timestamp with time zone)
    LANGUAGE sql STABLE
    AS $$
    SELECT s.series_id, s.name, s.poster_path, f.created_at
    FROM   User_TV_Favorite f
    JOIN   TV_Series s ON s.series_id = f.series_id
    WHERE  f.user_id = p_user_id
    ORDER  BY f.created_at DESC
    LIMIT  p_page_size OFFSET (p_page-1)*p_page_size;
$$;

ALTER FUNCTION public.sp_getusertvfavorites(p_user_id integer, p_page integer, p_page_size integer) OWNER TO postgres;

CREATE PROCEDURE public.sp_insertuser(IN p_username character varying, IN p_email character varying, IN p_password_hash character varying, IN p_name character varying DEFAULT NULL::character varying, IN p_iso_639_1 character DEFAULT NULL::bpchar, IN p_iso_3166_1 character DEFAULT NULL::bpchar)
    LANGUAGE plpgsql
    AS $_$
DECLARE
    v_user_id INTEGER;
    v_default_role_id SMALLINT;
BEGIN
    IF p_email !~ '^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$' THEN
        RAISE EXCEPTION 'Email kh├┤ng hß╗úp lß╗ç: "%"', p_email;
    END IF;

    INSERT INTO "User" (username, email, password_hash, name, iso_639_1, iso_3166_1)
    VALUES (p_username, LOWER(p_email), p_password_hash, p_name, p_iso_639_1, p_iso_3166_1)
    RETURNING user_id INTO v_user_id;

    SELECT role_id INTO v_default_role_id FROM Role WHERE role_name = 'user';
    IF v_default_role_id IS NOT NULL THEN
        INSERT INTO User_Role (user_id, role_id) VALUES (v_user_id, v_default_role_id)
        ON CONFLICT DO NOTHING;
    END IF;
END;
$_$;

ALTER PROCEDURE public.sp_insertuser(IN p_username character varying, IN p_email character varying, IN p_password_hash character varying, IN p_name character varying, IN p_iso_639_1 character, IN p_iso_3166_1 character) OWNER TO postgres;

CREATE PROCEDURE public.sp_insertuserreview(IN p_user_id integer, IN p_media_type character varying, IN p_movie_id integer DEFAULT NULL::integer, IN p_series_id integer DEFAULT NULL::integer, IN p_content text DEFAULT ''::text, IN p_rating numeric DEFAULT NULL::numeric, IN p_tmdb_review_id character varying DEFAULT NULL::character varying)
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF NOT fn_is_user_active(p_user_id) THEN
        RAISE EXCEPTION 'User user_id=% kh├┤ng active.', p_user_id;
    END IF;
    IF p_movie_id IS NULL AND p_series_id IS NULL THEN
        RAISE EXCEPTION 'Phß║úi cung cß║Ñp movie_id hoß║╖c series_id.';
    END IF;
    IF p_rating IS NOT NULL AND (p_rating < 0.5 OR p_rating > 10.0 OR (p_rating*2) <> FLOOR(p_rating*2)) THEN
        RAISE EXCEPTION 'rating (%) kh├┤ng hß╗úp lß╗ç ΓÇö phß║úi l├á bß╗Öi sß╗æ cß╗ºa 0.5 trong [0.5..10].', p_rating;
    END IF;

    INSERT INTO User_Review (tmdb_review_id, user_id, media_type, movie_id, series_id, content, rating)
    VALUES (p_tmdb_review_id, p_user_id, p_media_type, p_movie_id, p_series_id, p_content, p_rating)
    ON CONFLICT (tmdb_review_id) DO NOTHING;
END;
$$;

ALTER PROCEDURE public.sp_insertuserreview(IN p_user_id integer, IN p_media_type character varying, IN p_movie_id integer, IN p_series_id integer, IN p_content text, IN p_rating numeric, IN p_tmdb_review_id character varying) OWNER TO postgres;

CREATE TABLE public."User" (
    user_id integer NOT NULL,
    tmdb_account_id integer,
    username character varying(100) NOT NULL,
    email character varying(254) NOT NULL,
    password_hash character varying(255) NOT NULL,
    name character varying(200),
    iso_639_1 character(2),
    iso_3166_1 character(2),
    avatar_gravatar_hash character varying(64),
    avatar_tmdb_path character varying(300),
    include_adult boolean DEFAULT false NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    last_login_at timestamp with time zone,
    CONSTRAINT chk_user_email_format CHECK (((email)::text ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'::text))
);

ALTER TABLE public."User" OWNER TO postgres;

CREATE SEQUENCE public."User_user_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public."User_user_id_seq" OWNER TO postgres;

ALTER SEQUENCE public."User_user_id_seq" OWNED BY public."User".user_id;

ALTER TABLE ONLY public."User" ALTER COLUMN user_id SET DEFAULT nextval('public."User_user_id_seq"'::regclass);

ALTER TABLE ONLY public."User"
    ADD CONSTRAINT "User_pkey" PRIMARY KEY (user_id);

ALTER TABLE ONLY public."User"
    ADD CONSTRAINT uq_user_email UNIQUE (email);

ALTER TABLE ONLY public."User"
    ADD CONSTRAINT uq_user_tmdb_account UNIQUE (tmdb_account_id);

ALTER TABLE ONLY public."User"
    ADD CONSTRAINT uq_user_username UNIQUE (username);

CREATE TABLE public.audit_log (
    audit_id bigint NOT NULL,
    table_name character varying(100) NOT NULL,
    record_id text NOT NULL,
    action character varying(10) NOT NULL,
    changed_by integer,
    changed_at timestamp with time zone DEFAULT now() NOT NULL,
    old_data jsonb,
    new_data jsonb,
    session_info jsonb,
    CONSTRAINT chk_audit_action CHECK (((action)::text = ANY ((ARRAY['INSERT'::character varying, 'UPDATE'::character varying, 'DELETE'::character varying])::text[])))
);

ALTER TABLE public.audit_log OWNER TO postgres;

CREATE SEQUENCE public.audit_log_audit_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.audit_log_audit_id_seq OWNER TO postgres;

ALTER SEQUENCE public.audit_log_audit_id_seq OWNED BY public.audit_log.audit_id;

ALTER TABLE ONLY public.audit_log ALTER COLUMN audit_id SET DEFAULT nextval('public.audit_log_audit_id_seq'::regclass);

ALTER TABLE ONLY public.audit_log
    ADD CONSTRAINT audit_log_pkey PRIMARY KEY (audit_id);

CREATE TABLE public.user_episode_rating (
    user_id integer NOT NULL,
    episode_id integer NOT NULL,
    rating numeric(3,1) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_user_ep_rating CHECK (((rating >= 0.5) AND (rating <= 10.0)))
);

ALTER TABLE public.user_episode_rating OWNER TO postgres;

ALTER TABLE ONLY public.user_episode_rating
    ADD CONSTRAINT user_episode_rating_pkey PRIMARY KEY (user_id, episode_id);

CREATE TABLE public.user_movie_favorite (
    user_id integer NOT NULL,
    movie_id integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

ALTER TABLE public.user_movie_favorite OWNER TO postgres;

ALTER TABLE ONLY public.user_movie_favorite
    ADD CONSTRAINT user_movie_favorite_pkey PRIMARY KEY (user_id, movie_id);

CREATE TABLE public.user_movie_rating (
    user_id integer NOT NULL,
    movie_id integer NOT NULL,
    rating numeric(3,1) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_user_movie_rating CHECK (((rating >= 0.5) AND (rating <= 10.0)))
);

ALTER TABLE public.user_movie_rating OWNER TO postgres;

ALTER TABLE ONLY public.user_movie_rating
    ADD CONSTRAINT user_movie_rating_pkey PRIMARY KEY (user_id, movie_id);

CREATE TABLE public.user_movie_watchlist (
    user_id integer NOT NULL,
    movie_id integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

ALTER TABLE public.user_movie_watchlist OWNER TO postgres;

ALTER TABLE ONLY public.user_movie_watchlist
    ADD CONSTRAINT user_movie_watchlist_pkey PRIMARY KEY (user_id, movie_id);

CREATE TABLE public.user_review (
    review_id integer NOT NULL,
    tmdb_review_id character varying(50),
    user_id integer NOT NULL,
    media_type character varying(10) NOT NULL,
    movie_id integer,
    series_id integer,
    content text NOT NULL,
    rating numeric(3,1),
    tmdb_url character varying(500),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_review_has_media CHECK (((movie_id IS NOT NULL) OR (series_id IS NOT NULL))),
    CONSTRAINT chk_review_media_type CHECK (((media_type)::text = ANY ((ARRAY['movie'::character varying, 'tv'::character varying])::text[]))),
    CONSTRAINT chk_review_rating CHECK (((rating IS NULL) OR (((rating >= 0.5) AND (rating <= 10.0)) AND ((rating * (2)::numeric) = floor((rating * (2)::numeric))))))
);

ALTER TABLE public.user_review OWNER TO postgres;

CREATE SEQUENCE public.user_review_review_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.user_review_review_id_seq OWNER TO postgres;

ALTER SEQUENCE public.user_review_review_id_seq OWNED BY public.user_review.review_id;

ALTER TABLE ONLY public.user_review ALTER COLUMN review_id SET DEFAULT nextval('public.user_review_review_id_seq'::regclass);

ALTER TABLE ONLY public.user_review
    ADD CONSTRAINT uq_review_tmdb_id UNIQUE (tmdb_review_id);

ALTER TABLE ONLY public.user_review
    ADD CONSTRAINT user_review_pkey PRIMARY KEY (review_id);

CREATE TABLE public.user_role (
    user_id integer NOT NULL,
    role_id smallint NOT NULL,
    assigned_at timestamp with time zone DEFAULT now() NOT NULL,
    assigned_by integer,
    expires_at timestamp with time zone
);

ALTER TABLE public.user_role OWNER TO postgres;

ALTER TABLE ONLY public.user_role
    ADD CONSTRAINT user_role_pkey PRIMARY KEY (user_id, role_id);

CREATE TABLE public.user_tv_favorite (
    user_id integer NOT NULL,
    series_id integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

ALTER TABLE public.user_tv_favorite OWNER TO postgres;

ALTER TABLE ONLY public.user_tv_favorite
    ADD CONSTRAINT user_tv_favorite_pkey PRIMARY KEY (user_id, series_id);

CREATE TABLE public.user_tv_rating (
    user_id integer NOT NULL,
    series_id integer NOT NULL,
    rating numeric(3,1) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT chk_user_tv_rating CHECK (((rating >= 0.5) AND (rating <= 10.0)))
);

ALTER TABLE public.user_tv_rating OWNER TO postgres;

ALTER TABLE ONLY public.user_tv_rating
    ADD CONSTRAINT user_tv_rating_pkey PRIMARY KEY (user_id, series_id);

CREATE TABLE public.user_tv_watchlist (
    user_id integer NOT NULL,
    series_id integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

ALTER TABLE public.user_tv_watchlist OWNER TO postgres;

ALTER TABLE ONLY public.user_tv_watchlist
    ADD CONSTRAINT user_tv_watchlist_pkey PRIMARY KEY (user_id, series_id);

CREATE TRIGGER trg_audit_user AFTER UPDATE ON public."User" FOR EACH ROW EXECUTE FUNCTION public.fn_trg_audit_log('user_id');

CREATE TRIGGER trg_set_updated_at_ep_rating BEFORE UPDATE ON public.user_episode_rating FOR EACH ROW EXECUTE FUNCTION public.fn_trg_set_updated_at();

CREATE TRIGGER trg_set_updated_at_movie_rating BEFORE UPDATE ON public.user_movie_rating FOR EACH ROW EXECUTE FUNCTION public.fn_trg_set_updated_at();

CREATE TRIGGER trg_set_updated_at_tv_rating BEFORE UPDATE ON public.user_tv_rating FOR EACH ROW EXECUTE FUNCTION public.fn_trg_set_updated_at();

CREATE TRIGGER trg_set_updated_at_user BEFORE UPDATE ON public."User" FOR EACH ROW EXECUTE FUNCTION public.fn_trg_set_updated_at();

CREATE TRIGGER trg_set_updated_at_user_review BEFORE UPDATE ON public.user_review FOR EACH ROW EXECUTE FUNCTION public.fn_trg_set_updated_at();

CREATE TRIGGER trg_soft_delete_user BEFORE DELETE ON public."User" FOR EACH ROW EXECUTE FUNCTION public.fn_trg_soft_delete_user();

CREATE TRIGGER trg_validate_review_rating BEFORE INSERT OR UPDATE ON public.user_review FOR EACH ROW EXECUTE FUNCTION public.fn_trg_validate_review_rating();

ALTER TABLE ONLY public."User"
    ADD CONSTRAINT "User_iso_3166_1_fkey" FOREIGN KEY (iso_3166_1) REFERENCES public.country(iso_3166_1);

ALTER TABLE ONLY public."User"
    ADD CONSTRAINT "User_iso_639_1_fkey" FOREIGN KEY (iso_639_1) REFERENCES public.language(iso_639_1);

ALTER TABLE ONLY public.audit_log
    ADD CONSTRAINT audit_log_changed_by_fkey FOREIGN KEY (changed_by) REFERENCES public."User"(user_id);

ALTER TABLE ONLY public.user_episode_rating
    ADD CONSTRAINT user_episode_rating_episode_id_fkey FOREIGN KEY (episode_id) REFERENCES public.tv_episode(episode_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.user_episode_rating
    ADD CONSTRAINT user_episode_rating_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."User"(user_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.user_movie_favorite
    ADD CONSTRAINT user_movie_favorite_movie_id_fkey FOREIGN KEY (movie_id) REFERENCES public.movie(movie_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.user_movie_favorite
    ADD CONSTRAINT user_movie_favorite_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."User"(user_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.user_movie_rating
    ADD CONSTRAINT user_movie_rating_movie_id_fkey FOREIGN KEY (movie_id) REFERENCES public.movie(movie_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.user_movie_rating
    ADD CONSTRAINT user_movie_rating_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."User"(user_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.user_movie_watchlist
    ADD CONSTRAINT user_movie_watchlist_movie_id_fkey FOREIGN KEY (movie_id) REFERENCES public.movie(movie_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.user_movie_watchlist
    ADD CONSTRAINT user_movie_watchlist_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."User"(user_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.user_review
    ADD CONSTRAINT user_review_movie_id_fkey FOREIGN KEY (movie_id) REFERENCES public.movie(movie_id);

ALTER TABLE ONLY public.user_review
    ADD CONSTRAINT user_review_series_id_fkey FOREIGN KEY (series_id) REFERENCES public.tv_series(series_id);

ALTER TABLE ONLY public.user_review
    ADD CONSTRAINT user_review_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."User"(user_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.user_role
    ADD CONSTRAINT user_role_assigned_by_fkey FOREIGN KEY (assigned_by) REFERENCES public."User"(user_id);

ALTER TABLE ONLY public.user_role
    ADD CONSTRAINT user_role_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.role(role_id);

ALTER TABLE ONLY public.user_role
    ADD CONSTRAINT user_role_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."User"(user_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.user_tv_favorite
    ADD CONSTRAINT user_tv_favorite_series_id_fkey FOREIGN KEY (series_id) REFERENCES public.tv_series(series_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.user_tv_favorite
    ADD CONSTRAINT user_tv_favorite_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."User"(user_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.user_tv_rating
    ADD CONSTRAINT user_tv_rating_series_id_fkey FOREIGN KEY (series_id) REFERENCES public.tv_series(series_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.user_tv_rating
    ADD CONSTRAINT user_tv_rating_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."User"(user_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.user_tv_watchlist
    ADD CONSTRAINT user_tv_watchlist_series_id_fkey FOREIGN KEY (series_id) REFERENCES public.tv_series(series_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.user_tv_watchlist
    ADD CONSTRAINT user_tv_watchlist_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."User"(user_id) ON DELETE CASCADE;

COMMIT;

BEGIN;

GRANT ALL ON SCHEMA public TO db_admin;

GRANT USAGE ON SCHEMA public TO db_moderator;

GRANT USAGE ON SCHEMA public TO db_user;

GRANT ALL ON TABLE public.certification_standard TO db_admin;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.certification_standard TO db_moderator;

GRANT SELECT ON TABLE public.certification_standard TO db_user;

GRANT ALL ON TABLE public.collection TO db_admin;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.collection TO db_moderator;

GRANT SELECT ON TABLE public.collection TO db_user;

GRANT ALL ON TABLE public.collection_translation TO db_admin;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.collection_translation TO db_moderator;

GRANT SELECT ON TABLE public.collection_translation TO db_user;

GRANT ALL ON TABLE public.company TO db_admin;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.company TO db_moderator;

GRANT SELECT ON TABLE public.company TO db_user;

GRANT ALL ON TABLE public.country TO db_admin;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.country TO db_moderator;

GRANT SELECT ON TABLE public.country TO db_user;

GRANT ALL ON TABLE public.department TO db_admin;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.department TO db_moderator;

GRANT SELECT ON TABLE public.department TO db_user;

GRANT ALL ON TABLE public.job TO db_admin;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.job TO db_moderator;

GRANT SELECT ON TABLE public.job TO db_user;

GRANT ALL ON TABLE public.keyword TO db_admin;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.keyword TO db_moderator;

GRANT SELECT ON TABLE public.keyword TO db_user;

GRANT ALL ON TABLE public.language TO db_admin;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.language TO db_moderator;

GRANT SELECT ON TABLE public.language TO db_user;

GRANT ALL ON TABLE public.person TO db_admin;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.person TO db_moderator;

GRANT SELECT ON TABLE public.person TO db_user;

GRANT ALL ON TABLE public.person_aka TO db_admin;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.person_aka TO db_moderator;

GRANT SELECT ON TABLE public.person_aka TO db_user;

GRANT ALL ON TABLE public.watch_provider TO db_admin;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.watch_provider TO db_moderator;

GRANT SELECT ON TABLE public.watch_provider TO db_user;

GRANT ALL ON TABLE public.movie TO db_admin;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.movie TO db_moderator;

GRANT SELECT ON TABLE public.movie TO db_user;

GRANT ALL ON TABLE public.movie_cast TO db_admin;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.movie_cast TO db_moderator;

GRANT SELECT ON TABLE public.movie_cast TO db_user;

GRANT ALL ON TABLE public.movie_certification TO db_admin;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.movie_certification TO db_moderator;

GRANT SELECT ON TABLE public.movie_certification TO db_user;

GRANT ALL ON TABLE public.movie_company TO db_admin;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.movie_company TO db_moderator;

GRANT SELECT ON TABLE public.movie_company TO db_user;

GRANT ALL ON TABLE public.movie_country TO db_admin;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.movie_country TO db_moderator;

GRANT SELECT ON TABLE public.movie_country TO db_user;

GRANT ALL ON TABLE public.movie_crew TO db_admin;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.movie_crew TO db_moderator;

GRANT SELECT ON TABLE public.movie_crew TO db_user;

GRANT ALL ON TABLE public.movie_keyword TO db_admin;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.movie_keyword TO db_moderator;

GRANT SELECT ON TABLE public.movie_keyword TO db_user;

GRANT ALL ON TABLE public.movie_language TO db_admin;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.movie_language TO db_moderator;

GRANT SELECT ON TABLE public.movie_language TO db_user;

GRANT ALL ON TABLE public.movie_watch_provider TO db_admin;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.movie_watch_provider TO db_moderator;

GRANT SELECT ON TABLE public.movie_watch_provider TO db_user;

GRANT ALL ON TABLE public.episode_cast TO db_admin;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.episode_cast TO db_moderator;

GRANT SELECT ON TABLE public.episode_cast TO db_user;

GRANT ALL ON TABLE public.episode_crew TO db_admin;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.episode_crew TO db_moderator;

GRANT SELECT ON TABLE public.episode_crew TO db_user;

GRANT ALL ON TABLE public.tv_cast TO db_admin;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.tv_cast TO db_moderator;

GRANT SELECT ON TABLE public.tv_cast TO db_user;

GRANT ALL ON TABLE public.tv_certification TO db_admin;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.tv_certification TO db_moderator;

GRANT SELECT ON TABLE public.tv_certification TO db_user;

GRANT ALL ON TABLE public.tv_company TO db_admin;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.tv_company TO db_moderator;

GRANT SELECT ON TABLE public.tv_company TO db_user;

GRANT ALL ON TABLE public.tv_country TO db_admin;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.tv_country TO db_moderator;

GRANT SELECT ON TABLE public.tv_country TO db_user;

GRANT ALL ON TABLE public.tv_creator TO db_admin;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.tv_creator TO db_moderator;

GRANT SELECT ON TABLE public.tv_creator TO db_user;

GRANT ALL ON TABLE public.tv_crew TO db_admin;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.tv_crew TO db_moderator;

GRANT SELECT ON TABLE public.tv_crew TO db_user;

GRANT ALL ON TABLE public.tv_episode TO db_admin;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.tv_episode TO db_moderator;

GRANT SELECT ON TABLE public.tv_episode TO db_user;

GRANT ALL ON TABLE public.tv_keyword TO db_admin;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.tv_keyword TO db_moderator;

GRANT SELECT ON TABLE public.tv_keyword TO db_user;

GRANT ALL ON TABLE public.tv_language TO db_admin;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.tv_language TO db_moderator;

GRANT SELECT ON TABLE public.tv_language TO db_user;

GRANT ALL ON TABLE public.tv_season TO db_admin;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.tv_season TO db_moderator;

GRANT SELECT ON TABLE public.tv_season TO db_user;

GRANT ALL ON TABLE public.tv_series TO db_admin;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.tv_series TO db_moderator;

GRANT SELECT ON TABLE public.tv_series TO db_user;

GRANT ALL ON TABLE public.tv_watch_provider TO db_admin;

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.tv_watch_provider TO db_moderator;

GRANT SELECT ON TABLE public.tv_watch_provider TO db_user;

COMMIT;
