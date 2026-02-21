import os
import sys


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-0123456789-0123456789")
os.environ.setdefault("ADMIN_EMAIL", "admin@example.com")
os.environ.setdefault("ADMIN_PASSWORD", "admin-password")
os.environ.setdefault("ALLOW_DEV_DEFAULTS", "true")

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()
