"""
Cross-cutting trigger functions and helper functions used by every other schema
module (audit logging, updated_at stamping, soft-delete, role/active checks).
Must run before any module below, since their triggers call these functions.

Auto-generated from a pg_dump schema export and split into domain modules
mirroring the etl_movie.py / etl_tv_series.py / etl_reference.py convention
used elsewhere in this repo. Run directly to create these objects in the
target database:

    python schema_shared.py

Uses db_utils.get_connection() / db_utils.db_transaction() for the actual
connection, same as the rest of the ETL codebase.
"""

import logging

import db_utils

logger = logging.getLogger(__name__)

DDL_STATEMENTS = [
    #
    """
    CREATE FUNCTION public.fn_etl_needs_sync(p_synced_at timestamp with time zone, p_interval interval DEFAULT '7 days'::interval) RETURNS boolean
        LANGUAGE sql IMMUTABLE
        AS $$
        SELECT p_synced_at IS NULL OR p_synced_at < NOW() - p_interval;
    $$;
    """,
    """
    ALTER FUNCTION public.fn_etl_needs_sync(p_synced_at timestamp with time zone, p_interval interval) OWNER TO postgres;
    """,
    """
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
    """,
    """
    ALTER FUNCTION public.fn_get_image_url(p_path character varying, p_size character varying) OWNER TO postgres;
    """,
    """
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
    """,
    """
    ALTER FUNCTION public.fn_has_role(p_user_id integer, p_role_name character varying) OWNER TO postgres;
    """,
    """
    CREATE FUNCTION public.fn_is_user_active(p_user_id integer) RETURNS boolean
        LANGUAGE sql STABLE
        AS $$
        SELECT is_active FROM "User" WHERE user_id = p_user_id;
    $$;
    """,
    """
    ALTER FUNCTION public.fn_is_user_active(p_user_id integer) OWNER TO postgres;
    """,
    """
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
    """,
    """
    ALTER FUNCTION public.fn_trg_audit_log() OWNER TO postgres;
    """,
    """
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
    """,
    """
    ALTER FUNCTION public.fn_trg_episode_count_sync() OWNER TO postgres;
    """,
    """
    CREATE FUNCTION public.fn_trg_set_updated_at() RETURNS trigger
        LANGUAGE plpgsql
        AS $$
    BEGIN
        NEW.updated_at = NOW();
        RETURN NEW;
    END;
    $$;
    """,
    """
    ALTER FUNCTION public.fn_trg_set_updated_at() OWNER TO postgres;
    """,
    """
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
    """,
    """
    ALTER FUNCTION public.fn_trg_soft_delete_user() OWNER TO postgres;
    """,
    """
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
    """,
    """
    ALTER FUNCTION public.fn_trg_validate_review_rating() OWNER TO postgres;
    """,
]


def run():
    """Execute all DDL statements for this module in order, inside one transaction."""
    with db_utils.db_transaction() as (conn, cur):
        for i, stmt in enumerate(DDL_STATEMENTS, start=1):
            try:
                cur.execute(stmt)
            except Exception:
                logger.error("Failed on statement #%d of %d in schema_shared.py", i, len(DDL_STATEMENTS))
                raise
    logger.info("schema_shared.py: executed %d statements successfully.", len(DDL_STATEMENTS))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
