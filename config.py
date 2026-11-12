"""Sozlamalar: .env fayldan yoki muhit o'zgaruvchilaridan o'qiladi."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        if not os.environ.get(key.strip()):  # bo'sh muhit o'zgaruvchisi .env ni to'smasin
            os.environ[key.strip()] = value


_load_dotenv(ROOT / ".env")


def _get(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.environ.get(name, default)
    if required and not value:
        raise SystemExit(f"❌ .env faylda {name} ko'rsatilmagan")
    return value or ""


class Settings:
    # --- Kalitlar ---
    GEMINI_API_KEY = _get("GEMINI_API_KEY")
    TELEGRAM_BOT_TOKEN = _get("TELEGRAM_BOT_TOKEN")

    # --- Telegram ---
    CHANNEL_ID = _get("CHANNEL_ID")            # @kanal_nomi yoki -100xxxxxxxxxx
    ADMIN_CHAT_ID = _get("ADMIN_CHAT_ID")      # hisobotlar va xatolar shu yerga keladi

    # --- Kontent ---
    RUBRIC = _get("RUBRIC", "Har kuni 1 ta predmet")
    LANGUAGE = _get("LANGUAGE", "o'zbek (lotin yozuvi)")
    CHANNEL_NAME = _get("CHANNEL_NAME", "Beka MLBB")
    # Har post oxiriga dastur o'zi qo'shadigan imzo (havola)
    SIGNATURE_TEXT = _get("SIGNATURE_TEXT", "Arzon donat qilish")
    SIGNATURE_URL = _get("SIGNATURE_URL", "https://t.me/Bekdonatbot")
    # Kanalga kirish so'rovlari
    AUTO_APPROVE = _get("AUTO_APPROVE", "true").lower() in ("1", "true", "yes", "ha")
    WELCOME_MESSAGE = _get("WELCOME_MESSAGE",
        "Salom! 👋 <b>Beka MLBB</b> kanaliga xush kelibsiz 🎮\n\n"
        "Har kuni 20:00 da yangi predmet darsi, har 3 kunda meta tahlili 🔥\n\n"
        "💎 Olmosni arzon olish: <a href=\"https://t.me/Bekdonatbot\">@Bekdonatbot</a>")
    IMAGE_FOOTER = _get("IMAGE_FOOTER", "Arzon donat: @Bekdonatbot")   # rasmlar pastidagi yozuv

    # --- Meta tahlili rubrikasi ---
    META_ENABLED = _get("META_ENABLED", "true").lower() in ("1", "true", "yes", "ha")
    META_EVERY_DAYS = int(_get("META_EVERY_DAYS", "3"))          # har necha kunda
    META_POST_TIME = _get("META_POST_TIME", "21:00")             # meta post vaqti
    META_MPL_REGIONS = _get("META_MPL_REGIONS", "ph,id,my")      # qaysi MPL turnirlari

    # --- Qaysi qismlar yoqilgan ---
    # Rasm va audio GENERATSIYA qilinmaydi — internetdan (MLBB Wiki) yoki media/ papkadan olinadi
    ENABLE_AUDIO = _get("ENABLE_AUDIO", "false").lower() in ("1", "true", "yes", "ha")

    # --- Modellar ---
    GEMINI_TEXT_MODEL = _get("GEMINI_TEXT_MODEL", "gemini-3.5-flash")
    # Bepul tarifda har model kuniga ~20 so'rov — limit tugasa navbatdagisiga o'tiladi
    GEMINI_FALLBACK_MODELS = _get("GEMINI_FALLBACK_MODELS",
                                  "gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-flash-lite-latest")

    # --- Vaqt ---
    TIMEZONE = _get("TIMEZONE", "Asia/Tashkent")
    POST_TIME = _get("POST_TIME", "20:00")               # kun predmeti, HH:MM
    PREPARE_MINUTES_BEFORE = int(_get("PREPARE_MINUTES_BEFORE", "20"))
    PREVIEW_MINUTES_BEFORE = int(_get("PREVIEW_MINUTES_BEFORE", "10"))   # admin'ga oldindan ko'rish
    MAX_REGENERATIONS = int(_get("MAX_REGENERATIONS", "5"))

    # --- Sifat nazorati ---
    QC_MIN_SCORE = int(_get("QC_MIN_SCORE", "7"))         # 1..10
    QC_MAX_ROUNDS = int(_get("QC_MAX_ROUNDS", "2"))       # nechta qayta yozish urinishi
    # Rasm va matn doim bitta xabarda — Telegram rasm izohi chegarasi 1024 belgi
    CAPTION_LIMIT = 1024

    # --- Fayllar ---
    STYLE_FILE = ROOT / "style.md"
    HISTORY_FILE = ROOT / "data" / "history.json"
    OUTPUT_DIR = ROOT / "output"

    def require(self, *names: str) -> None:
        missing = [n for n in names if not getattr(self, n)]
        if missing:
            raise SystemExit("❌ .env faylda yetishmayapti: " + ", ".join(missing))


settings = Settings()
