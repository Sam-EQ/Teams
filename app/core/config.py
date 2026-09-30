import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DATA_DIR = Path(os.getenv("DATA_DIR", ROOT / "data"))
MODEL_ID = "nvidia/Nemotron-3-Diarization"
MODEL_DIR = Path(os.getenv("MODEL_DIR", ROOT / "models" / "nemotron-3-diarization"))
DEVICE = os.getenv("DEVICE") or None
DIARIZATION_MODE = os.getenv("DIARIZATION_MODE", "offline")
DIARIZATION_THRESHOLD = float(os.getenv("DIARIZATION_THRESHOLD", "0.2"))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
TRANSCRIBE_MODEL = os.getenv("TRANSCRIBE_MODEL", "gpt-4o-transcribe-diarize")
MINUTES_MODEL = os.getenv("MINUTES_MODEL", "gpt-5.6-sol")
OPENAI_TIMEOUT_SECONDS = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "600"))
OPENAI_MAX_RETRIES = int(os.getenv("OPENAI_MAX_RETRIES", "3"))
TRANSCRIBE_CONCURRENCY = int(os.getenv("TRANSCRIBE_CONCURRENCY", "4"))

SAMPLE_RATE = 16000
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "2048")) * 1024 * 1024

CHUNK_TARGET_SECONDS = 600
CHUNK_WINDOW_SECONDS = 60
CHUNK_MAX_SECONDS = 720
SILENCE_NOISE_DB = -35
SILENCE_MIN_SECONDS = 0.5

GAP_MIN_SECONDS = float(os.getenv("GAP_MIN_SECONDS", "1.0"))
GAP_MAX_COVERAGE = 0.2
REGION_JOIN_SECONDS = 0.5
TURN_GAP_SECONDS = 1.0

TEAMS_TENANT_ID = os.getenv("TEAMS_TENANT_ID", "")
TEAMS_CLIENT_ID = os.getenv("TEAMS_CLIENT_ID", "")
TEAMS_CLIENT_SECRET = os.getenv("TEAMS_CLIENT_SECRET", "")
TEAMS_ORGANIZER_ID = os.getenv("TEAMS_ORGANIZER_ID", "")
TEAMS_LOGIN_URL = os.getenv("TEAMS_LOGIN_URL", "https://login.microsoftonline.com").rstrip("/")
TEAMS_GRAPH_URL = os.getenv("TEAMS_GRAPH_URL", "https://graph.microsoft.com/v1.0").rstrip("/")
TEAMS_ENABLED = all([TEAMS_TENANT_ID, TEAMS_CLIENT_ID, TEAMS_CLIENT_SECRET, TEAMS_ORGANIZER_ID])
NAME_MIN_SECONDS = 1.0
