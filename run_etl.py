"""
run_etl.py — command-line entry point for the TMDb → PostgreSQL ETL pipeline.

This file only orchestrates: it loads reference (lookup) data and runs the
movie / TV batch ETL functions defined in etl_reference.py, etl_movie.py and
etl_tv_series.py. It does not talk to TMDb or PostgreSQL directly.

Usage
-----
    # Load lookup tables only (languages, genres, departments/jobs, certifications).
    # Run this once before the very first movie/TV batch.
    python run_etl.py reference

    # Movie IDs given directly, or read from a file (one ID per line, '#' = comment)
    python run_etl.py movies 550 551 552
    python run_etl.py movies --file movie_ids.txt

    # Same idea for TV series
    python run_etl.py tv 1399 2316
    python run_etl.py tv --file tv_ids.txt

    # Reference data, then movies and/or TV series, in one call
    python run_etl.py all --movies 550 551 --tv 1399 2316
    python run_etl.py all --movies-file movie_ids.txt --tv-file tv_ids.txt

Any subcommand accepts --stop-on-error to abort a batch on the first failed
item (default: keep going and print a success/failure summary at the end).

Exit code is 0 only if every requested step succeeded; non-zero otherwise,
so this can be dropped straight into a cron job or CI step.
"""

import argparse
import logging
import sys
from pathlib import Path

from tmdb_etl_model_full_fledged.etl.movie import run_movies_etl
from tmdb_etl_model_full_fledged.etl.tv_series import run_tv_series_batch_etl
from tmdb_etl_model_full_fledged.etl.reference import (
    load_languages,
    load_genres_movie,
    load_genres_tv,
    load_departments_and_jobs,
    load_certifications_movie,
    load_certifications_tv,
)

logger = logging.getLogger(__name__)


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def load_ids_from_file(path: str) -> list[int]:
    """Read one TMDb ID per line. Blank lines and '#' comments are skipped."""
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"ID file not found: {path}")

    ids: list[int] = []
    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            ids.append(int(line))
        except ValueError:
            logger.warning("Skipping invalid ID in %s: %r", path, raw_line)
    return ids


def collect_ids(cli_ids, file_path) -> list[int]:
    """Merge CLI-provided IDs with IDs from a file, de-duplicated, order preserved."""
    ids: list[int] = list(cli_ids or [])
    if file_path:
        ids.extend(load_ids_from_file(file_path))

    seen = set()
    unique_ids = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            unique_ids.append(i)
    return unique_ids


def run_reference_etl() -> bool:
    """
    Load lookup/reference tables that movie & TV ETL rely on: languages,
    genres, departments/jobs, and certification standards. Movie/TV rows can
    still be inserted without this (foreign keys to those tables are mostly
    optional/nullable), but certifications in particular will be skipped with
    a warning if their standard hasn't been loaded yet — so run this first.
    """
    logger.info("=" * 60)
    logger.info("START: Reference data ETL")
    logger.info("=" * 60)

    steps = [
        ("languages", load_languages),
        ("genres (movie)", load_genres_movie),
        ("genres (tv)", load_genres_tv),
        ("departments & jobs", load_departments_and_jobs),
        ("certifications (movie)", load_certifications_movie),
        ("certifications (tv)", load_certifications_tv),
    ]

    all_ok = True
    for label, step_fn in steps:
        try:
            ok = step_fn()
            if ok:
                logger.info("  ✓ %s", label)
            else:
                all_ok = False
                logger.error("  ✗ %s failed", label)
        except Exception as e:
            all_ok = False
            logger.exception("  ✗ %s failed unexpectedly: %s", label, e)

    logger.info("=" * 60)
    logger.info("DONE: Reference data ETL (%s)", "OK" if all_ok else "completed with errors")
    logger.info("=" * 60)
    return all_ok


def cmd_reference(args: argparse.Namespace) -> int:
    return 0 if run_reference_etl() else 1


def cmd_movies(args: argparse.Namespace) -> int:
    ids = collect_ids(args.ids, args.file)
    if not ids:
        logger.error("No movie IDs provided. Pass IDs directly or use --file.")
        return 1
    _, failed = run_movies_etl(ids, stop_on_error=args.stop_on_error)
    return 0 if failed == 0 else 1


def cmd_tv(args: argparse.Namespace) -> int:
    ids = collect_ids(args.ids, args.file)
    if not ids:
        logger.error("No TV series IDs provided. Pass IDs directly or use --file.")
        return 1
    _, failed = run_tv_series_batch_etl(ids, stop_on_error=args.stop_on_error)
    return 0 if failed == 0 else 1


def cmd_all(args: argparse.Namespace) -> int:
    exit_code = 0

    if not args.skip_reference:
        if not run_reference_etl():
            exit_code = 1

    movie_ids = collect_ids(args.movies, args.movies_file)
    tv_ids = collect_ids(args.tv, args.tv_file)

    if movie_ids:
        _, failed = run_movies_etl(movie_ids, stop_on_error=args.stop_on_error)
        if failed:
            exit_code = 1
    else:
        logger.info("No movie IDs provided — skipping movie ETL.")

    if tv_ids:
        _, failed = run_tv_series_batch_etl(tv_ids, stop_on_error=args.stop_on_error)
        if failed:
            exit_code = 1
    else:
        logger.info("No TV series IDs provided — skipping TV ETL.")

    return exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_etl.py",
        description="TMDb -> PostgreSQL ETL pipeline runner.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_ref = subparsers.add_parser("reference", help="Load reference/lookup tables only.")
    p_ref.set_defaults(func=cmd_reference)

    p_movies = subparsers.add_parser("movies", help="Run ETL for one or more movies.")
    p_movies.add_argument("ids", nargs="*", type=int, help="TMDb movie IDs.")
    p_movies.add_argument("--file", help="Text file with one movie ID per line.")
    p_movies.add_argument(
        "--stop-on-error", action="store_true",
        help="Abort the batch on the first failed movie."
    )
    p_movies.set_defaults(func=cmd_movies)

    p_tv = subparsers.add_parser("tv", help="Run ETL for one or more TV series.")
    p_tv.add_argument("ids", nargs="*", type=int, help="TMDb TV series IDs.")
    p_tv.add_argument("--file", help="Text file with one series ID per line.")
    p_tv.add_argument(
        "--stop-on-error", action="store_true",
        help="Abort the batch on the first failed series."
    )
    p_tv.set_defaults(func=cmd_tv)

    p_all = subparsers.add_parser("all", help="Load reference data, then movies and/or TV series.")
    p_all.add_argument("--movies", nargs="*", type=int, default=[], help="TMDb movie IDs.")
    p_all.add_argument("--movies-file", help="Text file with one movie ID per line.")
    p_all.add_argument("--tv", nargs="*", type=int, default=[], help="TMDb TV series IDs.")
    p_all.add_argument("--tv-file", help="Text file with one TV series ID per line.")
    p_all.add_argument(
        "--skip-reference", action="store_true",
        help="Skip the reference-data step (use if it already ran)."
    )
    p_all.add_argument(
        "--stop-on-error", action="store_true",
        help="Abort each batch on its first failure."
    )
    p_all.set_defaults(func=cmd_all)

    return parser


def main() -> int:
    setup_logging()
    parser = build_parser()
    args = parser.parse_args()

    try:
        return args.func(args)
    except FileNotFoundError as e:
        logger.error(str(e))
        return 1
    except KeyboardInterrupt:
        logger.warning("Interrupted by user.")
        return 130
    except Exception as e:
        logger.exception("Unhandled error: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())