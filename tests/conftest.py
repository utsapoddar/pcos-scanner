import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "dummy-anon-key")
os.environ.setdefault("SUPABASE_DB_URL", "")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "")
