"""
User-facing and admin tables: User accounts, roles, reviews, favorites,
ratings, watchlists, plus Audit_Log.
Depends on: schema_shared.py, schema_reference.py, schema_movie.py, schema_tv_series.py
(user_* tables reference movie/tv_series rows).

Auto-generated from a pg_dump schema export and split into domain modules
mirroring the etl_movie.py / etl_tv_series.py / etl_reference.py convention
used elsewhere in this repo. Run directly to create these objects in the
target database:

    python schema_users_and_admin.py

Uses db_utils.get_connection() / db_utils.db_transaction() for the actual
connection, same as the rest of the ETL codebase.
"""

import logging

import db_utils

logger = logging.getLogger(__name__)

DDL_STATEMENTS = [
    #
    """
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
    """,
    """
    ALTER FUNCTION public.fn_user_activity_report(p_year integer, p_month integer) OWNER TO postgres;
    """,
    """
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
    """,
    """
    ALTER FUNCTION public.sp_getauditlog(p_table_name character varying, p_from_ts timestamp with time zone, p_to_ts timestamp with time zone, p_page integer, p_page_size integer) OWNER TO postgres;
    """,
    """
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
    """,
    """
    ALTER FUNCTION public.sp_getetllog(p_status character varying, p_page integer, p_page_size integer) OWNER TO postgres;
    """,
    """
    CREATE FUNCTION public.sp_getsystemconfig(p_key character varying DEFAULT NULL::character varying) RETURNS TABLE(config_key character varying, config_value text, description text, updated_at timestamp with time zone)
        LANGUAGE sql STABLE
        AS $$
        SELECT config_key, config_value, description, updated_at
        FROM   System_Config
        WHERE  p_key IS NULL OR config_key = p_key
        ORDER  BY config_key;
    $$;
    """,
    """
    ALTER FUNCTION public.sp_getsystemconfig(p_key character varying) OWNER TO postgres;
    """,
    """
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
    """,
    """
    ALTER FUNCTION public.sp_getusermoviefavorites(p_user_id integer, p_page integer, p_page_size integer) OWNER TO postgres;
    """,
    """
    CREATE FUNCTION public.sp_getuserprofile(p_user_id integer) RETURNS TABLE(user_id integer, username character varying, name character varying, email character varying, iso_639_1 character, iso_3166_1 character, is_active boolean, created_at timestamp with time zone, last_login_at timestamp with time zone)
        LANGUAGE sql STABLE
        AS $$
        SELECT user_id, username, name, email, iso_639_1, iso_3166_1, is_active, created_at, last_login_at
        FROM   "User"
        WHERE  user_id = p_user_id;
    $$;
    """,
    """
    ALTER FUNCTION public.sp_getuserprofile(p_user_id integer) OWNER TO postgres;
    """,
    """
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
    """,
    """
    ALTER FUNCTION public.sp_getuserreviews(p_user_id integer, p_page integer, p_page_size integer) OWNER TO postgres;
    """,
    """
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
    """,
    """
    ALTER FUNCTION public.sp_getusertvfavorites(p_user_id integer, p_page integer, p_page_size integer) OWNER TO postgres;
    """,
    """
    CREATE PROCEDURE public.sp_insertuser(IN p_username character varying, IN p_email character varying, IN p_password_hash character varying, IN p_name character varying DEFAULT NULL::character varying, IN p_iso_639_1 character DEFAULT NULL::bpchar, IN p_iso_3166_1 character DEFAULT NULL::bpchar)
        LANGUAGE plpgsql
        AS $_$
    DECLARE
        v_user_id INTEGER;
        v_default_role_id SMALLINT;
    BEGIN
        IF p_email !~ '^[A-Za-z0-9._%+\\-]+@[A-Za-z0-9.\\-]+\\.[A-Za-z]{2,}$' THEN
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
    """,
    """
    ALTER PROCEDURE public.sp_insertuser(IN p_username character varying, IN p_email character varying, IN p_password_hash character varying, IN p_name character varying, IN p_iso_639_1 character, IN p_iso_3166_1 character) OWNER TO postgres;
    """,
    """
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
    """,
    """
    ALTER PROCEDURE public.sp_insertuserreview(IN p_user_id integer, IN p_media_type character varying, IN p_movie_id integer, IN p_series_id integer, IN p_content text, IN p_rating numeric, IN p_tmdb_review_id character varying) OWNER TO postgres;
    """,
    # --- tables ---
    """
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
        CONSTRAINT chk_user_email_format CHECK (((email)::text ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$'::text))
    );
    """,
    """
    ALTER TABLE public."User" OWNER TO postgres;
    """,
    """
    CREATE SEQUENCE public."User_user_id_seq"
        AS integer
        START WITH 1
        INCREMENT BY 1
        NO MINVALUE
        NO MAXVALUE
        CACHE 1;
    """,
    """
    ALTER SEQUENCE public."User_user_id_seq" OWNER TO postgres;
    """,
    """
    ALTER SEQUENCE public."User_user_id_seq" OWNED BY public."User".user_id;
    """,
    """
    ALTER TABLE ONLY public."User" ALTER COLUMN user_id SET DEFAULT nextval('public."User_user_id_seq"'::regclass);
    """,
    """
    ALTER TABLE ONLY public."User"
        ADD CONSTRAINT "User_pkey" PRIMARY KEY (user_id);
    """,
    """
    ALTER TABLE ONLY public."User"
        ADD CONSTRAINT uq_user_email UNIQUE (email);
    """,
    """
    ALTER TABLE ONLY public."User"
        ADD CONSTRAINT uq_user_tmdb_account UNIQUE (tmdb_account_id);
    """,
    """
    ALTER TABLE ONLY public."User"
        ADD CONSTRAINT uq_user_username UNIQUE (username);
    """,
    """
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
    """,
    """
    ALTER TABLE public.audit_log OWNER TO postgres;
    """,
    """
    CREATE SEQUENCE public.audit_log_audit_id_seq
        START WITH 1
        INCREMENT BY 1
        NO MINVALUE
        NO MAXVALUE
        CACHE 1;
    """,
    """
    ALTER SEQUENCE public.audit_log_audit_id_seq OWNER TO postgres;
    """,
    """
    ALTER SEQUENCE public.audit_log_audit_id_seq OWNED BY public.audit_log.audit_id;
    """,
    """
    ALTER TABLE ONLY public.audit_log ALTER COLUMN audit_id SET DEFAULT nextval('public.audit_log_audit_id_seq'::regclass);
    """,
    """
    ALTER TABLE ONLY public.audit_log
        ADD CONSTRAINT audit_log_pkey PRIMARY KEY (audit_id);
    """,
    """
    CREATE TABLE public.user_episode_rating (
        user_id integer NOT NULL,
        episode_id integer NOT NULL,
        rating numeric(3,1) NOT NULL,
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        updated_at timestamp with time zone DEFAULT now() NOT NULL,
        CONSTRAINT chk_user_ep_rating CHECK (((rating >= 0.5) AND (rating <= 10.0)))
    );
    """,
    """
    ALTER TABLE public.user_episode_rating OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.user_episode_rating
        ADD CONSTRAINT user_episode_rating_pkey PRIMARY KEY (user_id, episode_id);
    """,
    """
    CREATE TABLE public.user_movie_favorite (
        user_id integer NOT NULL,
        movie_id integer NOT NULL,
        created_at timestamp with time zone DEFAULT now() NOT NULL
    );
    """,
    """
    ALTER TABLE public.user_movie_favorite OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.user_movie_favorite
        ADD CONSTRAINT user_movie_favorite_pkey PRIMARY KEY (user_id, movie_id);
    """,
    """
    CREATE TABLE public.user_movie_rating (
        user_id integer NOT NULL,
        movie_id integer NOT NULL,
        rating numeric(3,1) NOT NULL,
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        updated_at timestamp with time zone DEFAULT now() NOT NULL,
        CONSTRAINT chk_user_movie_rating CHECK (((rating >= 0.5) AND (rating <= 10.0)))
    );
    """,
    """
    ALTER TABLE public.user_movie_rating OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.user_movie_rating
        ADD CONSTRAINT user_movie_rating_pkey PRIMARY KEY (user_id, movie_id);
    """,
    """
    CREATE TABLE public.user_movie_watchlist (
        user_id integer NOT NULL,
        movie_id integer NOT NULL,
        created_at timestamp with time zone DEFAULT now() NOT NULL
    );
    """,
    """
    ALTER TABLE public.user_movie_watchlist OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.user_movie_watchlist
        ADD CONSTRAINT user_movie_watchlist_pkey PRIMARY KEY (user_id, movie_id);
    """,
    """
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
    """,
    """
    ALTER TABLE public.user_review OWNER TO postgres;
    """,
    """
    CREATE SEQUENCE public.user_review_review_id_seq
        AS integer
        START WITH 1
        INCREMENT BY 1
        NO MINVALUE
        NO MAXVALUE
        CACHE 1;
    """,
    """
    ALTER SEQUENCE public.user_review_review_id_seq OWNER TO postgres;
    """,
    """
    ALTER SEQUENCE public.user_review_review_id_seq OWNED BY public.user_review.review_id;
    """,
    """
    ALTER TABLE ONLY public.user_review ALTER COLUMN review_id SET DEFAULT nextval('public.user_review_review_id_seq'::regclass);
    """,
    """
    ALTER TABLE ONLY public.user_review
        ADD CONSTRAINT uq_review_tmdb_id UNIQUE (tmdb_review_id);
    """,
    """
    ALTER TABLE ONLY public.user_review
        ADD CONSTRAINT user_review_pkey PRIMARY KEY (review_id);
    """,
    """
    CREATE TABLE public.user_role (
        user_id integer NOT NULL,
        role_id smallint NOT NULL,
        assigned_at timestamp with time zone DEFAULT now() NOT NULL,
        assigned_by integer,
        expires_at timestamp with time zone
    );
    """,
    """
    ALTER TABLE public.user_role OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.user_role
        ADD CONSTRAINT user_role_pkey PRIMARY KEY (user_id, role_id);
    """,
    """
    CREATE TABLE public.user_tv_favorite (
        user_id integer NOT NULL,
        series_id integer NOT NULL,
        created_at timestamp with time zone DEFAULT now() NOT NULL
    );
    """,
    """
    ALTER TABLE public.user_tv_favorite OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.user_tv_favorite
        ADD CONSTRAINT user_tv_favorite_pkey PRIMARY KEY (user_id, series_id);
    """,
    """
    CREATE TABLE public.user_tv_rating (
        user_id integer NOT NULL,
        series_id integer NOT NULL,
        rating numeric(3,1) NOT NULL,
        created_at timestamp with time zone DEFAULT now() NOT NULL,
        updated_at timestamp with time zone DEFAULT now() NOT NULL,
        CONSTRAINT chk_user_tv_rating CHECK (((rating >= 0.5) AND (rating <= 10.0)))
    );
    """,
    """
    ALTER TABLE public.user_tv_rating OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.user_tv_rating
        ADD CONSTRAINT user_tv_rating_pkey PRIMARY KEY (user_id, series_id);
    """,
    """
    CREATE TABLE public.user_tv_watchlist (
        user_id integer NOT NULL,
        series_id integer NOT NULL,
        created_at timestamp with time zone DEFAULT now() NOT NULL
    );
    """,
    """
    ALTER TABLE public.user_tv_watchlist OWNER TO postgres;
    """,
    """
    ALTER TABLE ONLY public.user_tv_watchlist
        ADD CONSTRAINT user_tv_watchlist_pkey PRIMARY KEY (user_id, series_id);
    """,
    # --- triggers ---
    """
    CREATE TRIGGER trg_audit_user AFTER UPDATE ON public."User" FOR EACH ROW EXECUTE FUNCTION public.fn_trg_audit_log('user_id');
    """,
    """
    CREATE TRIGGER trg_set_updated_at_ep_rating BEFORE UPDATE ON public.user_episode_rating FOR EACH ROW EXECUTE FUNCTION public.fn_trg_set_updated_at();
    """,
    """
    CREATE TRIGGER trg_set_updated_at_movie_rating BEFORE UPDATE ON public.user_movie_rating FOR EACH ROW EXECUTE FUNCTION public.fn_trg_set_updated_at();
    """,
    """
    CREATE TRIGGER trg_set_updated_at_tv_rating BEFORE UPDATE ON public.user_tv_rating FOR EACH ROW EXECUTE FUNCTION public.fn_trg_set_updated_at();
    """,
    """
    CREATE TRIGGER trg_set_updated_at_user BEFORE UPDATE ON public."User" FOR EACH ROW EXECUTE FUNCTION public.fn_trg_set_updated_at();
    """,
    """
    CREATE TRIGGER trg_set_updated_at_user_review BEFORE UPDATE ON public.user_review FOR EACH ROW EXECUTE FUNCTION public.fn_trg_set_updated_at();
    """,
    """
    CREATE TRIGGER trg_soft_delete_user BEFORE DELETE ON public."User" FOR EACH ROW EXECUTE FUNCTION public.fn_trg_soft_delete_user();
    """,
    """
    CREATE TRIGGER trg_validate_review_rating BEFORE INSERT OR UPDATE ON public.user_review FOR EACH ROW EXECUTE FUNCTION public.fn_trg_validate_review_rating();
    """,
    # --- foreign keys ---
    """
    ALTER TABLE ONLY public."User"
        ADD CONSTRAINT "User_iso_3166_1_fkey" FOREIGN KEY (iso_3166_1) REFERENCES public.country(iso_3166_1);
    """,
    """
    ALTER TABLE ONLY public."User"
        ADD CONSTRAINT "User_iso_639_1_fkey" FOREIGN KEY (iso_639_1) REFERENCES public.language(iso_639_1);
    """,
    """
    ALTER TABLE ONLY public.audit_log
        ADD CONSTRAINT audit_log_changed_by_fkey FOREIGN KEY (changed_by) REFERENCES public."User"(user_id);
    """,
    """
    ALTER TABLE ONLY public.user_episode_rating
        ADD CONSTRAINT user_episode_rating_episode_id_fkey FOREIGN KEY (episode_id) REFERENCES public.tv_episode(episode_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.user_episode_rating
        ADD CONSTRAINT user_episode_rating_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."User"(user_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.user_movie_favorite
        ADD CONSTRAINT user_movie_favorite_movie_id_fkey FOREIGN KEY (movie_id) REFERENCES public.movie(movie_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.user_movie_favorite
        ADD CONSTRAINT user_movie_favorite_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."User"(user_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.user_movie_rating
        ADD CONSTRAINT user_movie_rating_movie_id_fkey FOREIGN KEY (movie_id) REFERENCES public.movie(movie_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.user_movie_rating
        ADD CONSTRAINT user_movie_rating_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."User"(user_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.user_movie_watchlist
        ADD CONSTRAINT user_movie_watchlist_movie_id_fkey FOREIGN KEY (movie_id) REFERENCES public.movie(movie_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.user_movie_watchlist
        ADD CONSTRAINT user_movie_watchlist_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."User"(user_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.user_review
        ADD CONSTRAINT user_review_movie_id_fkey FOREIGN KEY (movie_id) REFERENCES public.movie(movie_id);
    """,
    """
    ALTER TABLE ONLY public.user_review
        ADD CONSTRAINT user_review_series_id_fkey FOREIGN KEY (series_id) REFERENCES public.tv_series(series_id);
    """,
    """
    ALTER TABLE ONLY public.user_review
        ADD CONSTRAINT user_review_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."User"(user_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.user_role
        ADD CONSTRAINT user_role_assigned_by_fkey FOREIGN KEY (assigned_by) REFERENCES public."User"(user_id);
    """,
    """
    ALTER TABLE ONLY public.user_role
        ADD CONSTRAINT user_role_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.role(role_id);
    """,
    """
    ALTER TABLE ONLY public.user_role
        ADD CONSTRAINT user_role_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."User"(user_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.user_tv_favorite
        ADD CONSTRAINT user_tv_favorite_series_id_fkey FOREIGN KEY (series_id) REFERENCES public.tv_series(series_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.user_tv_favorite
        ADD CONSTRAINT user_tv_favorite_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."User"(user_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.user_tv_rating
        ADD CONSTRAINT user_tv_rating_series_id_fkey FOREIGN KEY (series_id) REFERENCES public.tv_series(series_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.user_tv_rating
        ADD CONSTRAINT user_tv_rating_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."User"(user_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.user_tv_watchlist
        ADD CONSTRAINT user_tv_watchlist_series_id_fkey FOREIGN KEY (series_id) REFERENCES public.tv_series(series_id) ON DELETE CASCADE;
    """,
    """
    ALTER TABLE ONLY public.user_tv_watchlist
        ADD CONSTRAINT user_tv_watchlist_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."User"(user_id) ON DELETE CASCADE;
    """,
]


def run():
    """Execute all DDL statements for this module in order, inside one transaction."""
    with db_utils.db_transaction() as (conn, cur):
        for i, stmt in enumerate(DDL_STATEMENTS, start=1):
            try:
                cur.execute(stmt)
            except Exception:
                logger.error("Failed on statement #%d of %d in schema_users_and_admin.py", i, len(DDL_STATEMENTS))
                raise
    logger.info("schema_users_and_admin.py: executed %d statements successfully.", len(DDL_STATEMENTS))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
