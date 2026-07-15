"""Select CCbeauty's settings from the DJANGO_ENV environment variable."""

import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[2] / ".env")

DJANGO_ENVIRONMENT = os.environ.get("DJANGO_ENV", "development").strip().lower()

if DJANGO_ENVIRONMENT in {"development", "dev", "local"}:
    from .development import *  # noqa: F403
elif DJANGO_ENVIRONMENT in {"production", "prod"}:
    from .production import *  # noqa: F403
else:
    raise RuntimeError(
        "Unsupported DJANGO_ENV value. Use 'development' or 'production'."
    )

