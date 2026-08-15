"""
Optional: GRANT statements for db_admin / db_moderator / db_user roles.

These roles (db_admin, db_moderator, db_user) are NOT created by this script
they must already exist in the target database (created separately, e.g. by a
DBA setup script or CREATE ROLE statements run beforehand). Running this file
against a fresh database where those roles don't exist will fail.

Also note: the original schema dump only includes GRANTs for a subset of
tables. The following tables have NO grant statements in the source dump and
are consequently NOT covered here: User, role, user_role, user_review,
user_movie_favorite, user_movie_rating, user_movie_watchlist,
user_episode_rating, user_tv_favorite, user_tv_rating, user_tv_watchlist,
audit_log, etl_log, system_config, genre, movie_genre, tv_genre.
If those tables need role-based access, add GRANT statements for them
separately
something this generator invented.

Run directly:

    python schema_grants.py
"""

import logging

import db_utils

logger = logging.getLogger(__name__)

GRANT_STATEMENTS = [
    """
    GRANT ALL ON SCHEMA public TO db_admin;
    """,
    """
    GRANT USAGE ON SCHEMA public TO db_moderator;
    """,
    """
    GRANT USAGE ON SCHEMA public TO db_user;
    """,
    """
    GRANT ALL ON TABLE public.certification_standard TO db_admin;
    """,
    """
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.certification_standard TO db_moderator;
    """,
    """
    GRANT SELECT ON TABLE public.certification_standard TO db_user;
    """,
    """
    GRANT ALL ON TABLE public.collection TO db_admin;
    """,
    """
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.collection TO db_moderator;
    """,
    """
    GRANT SELECT ON TABLE public.collection TO db_user;
    """,
    """
    GRANT ALL ON TABLE public.collection_translation TO db_admin;
    """,
    """
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.collection_translation TO db_moderator;
    """,
    """
    GRANT SELECT ON TABLE public.collection_translation TO db_user;
    """,
    """
    GRANT ALL ON TABLE public.company TO db_admin;
    """,
    """
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.company TO db_moderator;
    """,
    """
    GRANT SELECT ON TABLE public.company TO db_user;
    """,
    """
    GRANT ALL ON TABLE public.country TO db_admin;
    """,
    """
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.country TO db_moderator;
    """,
    """
    GRANT SELECT ON TABLE public.country TO db_user;
    """,
    """
    GRANT ALL ON TABLE public.department TO db_admin;
    """,
    """
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.department TO db_moderator;
    """,
    """
    GRANT SELECT ON TABLE public.department TO db_user;
    """,
    """
    GRANT ALL ON TABLE public.job TO db_admin;
    """,
    """
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.job TO db_moderator;
    """,
    """
    GRANT SELECT ON TABLE public.job TO db_user;
    """,
    """
    GRANT ALL ON TABLE public.keyword TO db_admin;
    """,
    """
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.keyword TO db_moderator;
    """,
    """
    GRANT SELECT ON TABLE public.keyword TO db_user;
    """,
    """
    GRANT ALL ON TABLE public.language TO db_admin;
    """,
    """
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.language TO db_moderator;
    """,
    """
    GRANT SELECT ON TABLE public.language TO db_user;
    """,
    """
    GRANT ALL ON TABLE public.person TO db_admin;
    """,
    """
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.person TO db_moderator;
    """,
    """
    GRANT SELECT ON TABLE public.person TO db_user;
    """,
    """
    GRANT ALL ON TABLE public.person_aka TO db_admin;
    """,
    """
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.person_aka TO db_moderator;
    """,
    """
    GRANT SELECT ON TABLE public.person_aka TO db_user;
    """,
    """
    GRANT ALL ON TABLE public.watch_provider TO db_admin;
    """,
    """
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.watch_provider TO db_moderator;
    """,
    """
    GRANT SELECT ON TABLE public.watch_provider TO db_user;
    """,
    """
    GRANT ALL ON TABLE public.movie TO db_admin;
    """,
    """
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.movie TO db_moderator;
    """,
    """
    GRANT SELECT ON TABLE public.movie TO db_user;
    """,
    """
    GRANT ALL ON TABLE public.movie_cast TO db_admin;
    """,
    """
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.movie_cast TO db_moderator;
    """,
    """
    GRANT SELECT ON TABLE public.movie_cast TO db_user;
    """,
    """
    GRANT ALL ON TABLE public.movie_certification TO db_admin;
    """,
    """
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.movie_certification TO db_moderator;
    """,
    """
    GRANT SELECT ON TABLE public.movie_certification TO db_user;
    """,
    """
    GRANT ALL ON TABLE public.movie_company TO db_admin;
    """,
    """
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.movie_company TO db_moderator;
    """,
    """
    GRANT SELECT ON TABLE public.movie_company TO db_user;
    """,
    """
    GRANT ALL ON TABLE public.movie_country TO db_admin;
    """,
    """
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.movie_country TO db_moderator;
    """,
    """
    GRANT SELECT ON TABLE public.movie_country TO db_user;
    """,
    """
    GRANT ALL ON TABLE public.movie_crew TO db_admin;
    """,
    """
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.movie_crew TO db_moderator;
    """,
    """
    GRANT SELECT ON TABLE public.movie_crew TO db_user;
    """,
    """
    GRANT ALL ON TABLE public.movie_keyword TO db_admin;
    """,
    """
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.movie_keyword TO db_moderator;
    """,
    """
    GRANT SELECT ON TABLE public.movie_keyword TO db_user;
    """,
    """
    GRANT ALL ON TABLE public.movie_language TO db_admin;
    """,
    """
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.movie_language TO db_moderator;
    """,
    """
    GRANT SELECT ON TABLE public.movie_language TO db_user;
    """,
    """
    GRANT ALL ON TABLE public.movie_watch_provider TO db_admin;
    """,
    """
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.movie_watch_provider TO db_moderator;
    """,
    """
    GRANT SELECT ON TABLE public.movie_watch_provider TO db_user;
    """,
    """
    GRANT ALL ON TABLE public.episode_cast TO db_admin;
    """,
    """
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.episode_cast TO db_moderator;
    """,
    """
    GRANT SELECT ON TABLE public.episode_cast TO db_user;
    """,
    """
    GRANT ALL ON TABLE public.episode_crew TO db_admin;
    """,
    """
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.episode_crew TO db_moderator;
    """,
    """
    GRANT SELECT ON TABLE public.episode_crew TO db_user;
    """,
    """
    GRANT ALL ON TABLE public.tv_cast TO db_admin;
    """,
    """
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.tv_cast TO db_moderator;
    """,
    """
    GRANT SELECT ON TABLE public.tv_cast TO db_user;
    """,
    """
    GRANT ALL ON TABLE public.tv_certification TO db_admin;
    """,
    """
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.tv_certification TO db_moderator;
    """,
    """
    GRANT SELECT ON TABLE public.tv_certification TO db_user;
    """,
    """
    GRANT ALL ON TABLE public.tv_company TO db_admin;
    """,
    """
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.tv_company TO db_moderator;
    """,
    """
    GRANT SELECT ON TABLE public.tv_company TO db_user;
    """,
    """
    GRANT ALL ON TABLE public.tv_country TO db_admin;
    """,
    """
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.tv_country TO db_moderator;
    """,
    """
    GRANT SELECT ON TABLE public.tv_country TO db_user;
    """,
    """
    GRANT ALL ON TABLE public.tv_creator TO db_admin;
    """,
    """
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.tv_creator TO db_moderator;
    """,
    """
    GRANT SELECT ON TABLE public.tv_creator TO db_user;
    """,
    """
    GRANT ALL ON TABLE public.tv_crew TO db_admin;
    """,
    """
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.tv_crew TO db_moderator;
    """,
    """
    GRANT SELECT ON TABLE public.tv_crew TO db_user;
    """,
    """
    GRANT ALL ON TABLE public.tv_episode TO db_admin;
    """,
    """
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.tv_episode TO db_moderator;
    """,
    """
    GRANT SELECT ON TABLE public.tv_episode TO db_user;
    """,
    """
    GRANT ALL ON TABLE public.tv_keyword TO db_admin;
    """,
    """
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.tv_keyword TO db_moderator;
    """,
    """
    GRANT SELECT ON TABLE public.tv_keyword TO db_user;
    """,
    """
    GRANT ALL ON TABLE public.tv_language TO db_admin;
    """,
    """
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.tv_language TO db_moderator;
    """,
    """
    GRANT SELECT ON TABLE public.tv_language TO db_user;
    """,
    """
    GRANT ALL ON TABLE public.tv_season TO db_admin;
    """,
    """
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.tv_season TO db_moderator;
    """,
    """
    GRANT SELECT ON TABLE public.tv_season TO db_user;
    """,
    """
    GRANT ALL ON TABLE public.tv_series TO db_admin;
    """,
    """
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.tv_series TO db_moderator;
    """,
    """
    GRANT SELECT ON TABLE public.tv_series TO db_user;
    """,
    """
    GRANT ALL ON TABLE public.tv_watch_provider TO db_admin;
    """,
    """
    GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.tv_watch_provider TO db_moderator;
    """,
    """
    GRANT SELECT ON TABLE public.tv_watch_provider TO db_user;
    """,
]


def run():
    """Execute all GRANT statements inside one transaction."""
    with db_utils.db_transaction() as (conn, cur):
        for i, stmt in enumerate(GRANT_STATEMENTS, start=1):
            try:
                cur.execute(stmt)
            except Exception:
                logger.error("Failed on grant statement #%d of %d", i, len(GRANT_STATEMENTS))
                raise
    logger.info("schema_grants.py: executed %d GRANT statements successfully.", len(GRANT_STATEMENTS))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
