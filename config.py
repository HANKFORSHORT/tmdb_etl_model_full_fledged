# Connection -------
import os
from dotenv import load_dotenv

DB_CONFIG = {
    "dbname":   os.environ["DB_NAME"],
    "user":     os.environ["DB_USER"],
    "password": os.environ["DB_PASSWORD"],
    "host":     os.environ.get("DB_HOST", "localhost"),
    "port":     os.environ.get("DB_PORT", "5432"),
}

# API -------
TMDB_API_TOKEN = os.environ["TMDB_API_TOKEN"]
TMDB_BASE_URL  = os.environ.get("TMDB_BASE_URL", "https://api.themoviedb.org/3")


# config -------
FETCH_FULL_PERSON_DETAIL = FalseIMPORT_REVIEWS = False
TMDB_SYSTEM_USER_ID = 1
API_DELAY_SECONDS = 0.05
ENABLE_ETL_LOG = True

