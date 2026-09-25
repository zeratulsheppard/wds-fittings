import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

PORT = int(os.getenv("PORT", "3016"))
CORP_ID = int(os.getenv("CORP_ID", "98330748"))

DEV_CHARACTER_ID = os.getenv("DEV_CHARACTER_ID", "")
DEV_CHARACTER_NAME = os.getenv("DEV_CHARACTER_NAME", "")
DEV_CHARACTER_ROLES = os.getenv("DEV_CHARACTER_ROLES", "")
DEV_CHARACTER_TITLES = os.getenv("DEV_CHARACTER_TITLES", "")

SDE_SQLITE_PATH = BASE_DIR / os.getenv("SDE_SQLITE_PATH", "data/sde/sqlite-latest.sqlite")
SDE_DOWNLOAD_URL = os.getenv(
    "SDE_DOWNLOAD_URL",
    "https://www.fuzzwork.co.uk/dump/sqlite-latest.sqlite.bz2",
)

APP_DB_PATH = BASE_DIR / os.getenv("APP_DB_PATH", "data/fittings.db")

STATIC_DIR = BASE_DIR / "app" / "static"
TEMPLATES_DIR = BASE_DIR / "app" / "templates"
