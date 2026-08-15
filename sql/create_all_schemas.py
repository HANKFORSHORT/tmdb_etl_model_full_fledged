"""
Orchestrator: creates the full database schema by running each domain module
in dependency-safe order.

Order matters here because of foreign keys:
    1. schema_shared.py            - trigger/helper functions (no tables)
    2. schema_reference.py         - lookup tables (person, company, genre, ...)
    3. schema_movie.py             - movie tables (FK -> reference)
    4. schema_tv_series.py         - tv series tables (FK -> reference)
    5. schema_users_and_admin.py   - User/review/favorite/... (FK -> movie, tv_series, reference)

schema_grants.py is intentionally NOT run automatically -- it requires the
db_admin / db_moderator / db_user roles to already exist in the target
database. Run it manually afterward once those roles are set up:

    python schema_grants.py

Usage:
    python create_all_schemas.py
"""

import logging

import schema_shared
import schema_reference
import schema_movie
import schema_tv_series
import schema_users_and_admin

logger = logging.getLogger(__name__)

MODULES_IN_ORDER = [
    schema_shared,
    schema_reference,
    schema_movie,
    schema_tv_series,
    schema_users_and_admin,
]


def run():
    for module in MODULES_IN_ORDER:
        logger.info("Running %s ...", module.__name__)
        module.run()
    logger.info("All schema modules completed successfully.")
    logger.info("Note: schema_grants.py was NOT run automatically -- run it "
                "separately once db_admin/db_moderator/db_user roles exist.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
