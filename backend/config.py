"""Đọc cấu hình từ file .env (xem .env.example)."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
load_dotenv(BASE_DIR / ".env")


def env(name: str, default: str = "") -> str:
    """Biến để trống ("") được coi như chưa đặt → dùng giá trị mặc định."""
    v = (os.getenv(name) or "").strip()
    return v or default


# Khi chạy trên Render, Render tự cung cấp RENDER_EXTERNAL_URL (vd https://momo-techday.onrender.com)
_DEFAULT_URL = env("RENDER_EXTERNAL_URL", "http://localhost:8000")
# URL công khai của backend (Render hoặc ngrok). Dùng cho ipnUrl để MoMo gọi về.
PUBLIC_BASE_URL = env("PUBLIC_BASE_URL", _DEFAULT_URL).rstrip("/")
# URL trình duyệt mở sau khi thanh toán xong.
APP_BASE_URL = env("APP_BASE_URL", _DEFAULT_URL).rstrip("/")

# ---- MoMo ----
MOMO_PARTNER_CODE = env("MOMO_PARTNER_CODE")
MOMO_ACCESS_KEY = env("MOMO_ACCESS_KEY")
MOMO_SECRET_KEY = env("MOMO_SECRET_KEY")
MOMO_ENDPOINT = env("MOMO_ENDPOINT", "https://test-payment.momo.vn/v2/gateway/api/create")
MOMO_REQUEST_TYPE = env("MOMO_REQUEST_TYPE", "captureWallet")
# "momo" = gọi MoMo sandbox thật; "simulate" = giả lập thanh toán (dự phòng khi demo)
PAYMENT_MODE = env("PAYMENT_MODE", "momo" if MOMO_SECRET_KEY else "simulate").lower()

# ---- Blockchain (Polygon Amoy testnet) ----
POLYGON_RPC_URL = env("POLYGON_RPC_URL", "https://rpc-amoy.polygon.technology")
CHAIN_ID = int(env("CHAIN_ID", "80002"))
PRIVATE_KEY = env("PRIVATE_KEY")
CONTRACT_ADDRESS = env("CONTRACT_ADDRESS")
EXPLORER_URL = env("EXPLORER_URL", "https://amoy.polygonscan.com").rstrip("/")
CONTRACT_JSON = ROOT_DIR / "contracts" / "DonationLedger.json"

# ---- LLM (API tương thích OpenAI: OpenAI, Gemini, Groq, OpenRouter...) ----
LLM_BASE_URL = env("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
LLM_API_KEY = env("LLM_API_KEY")
LLM_MODEL = env("LLM_MODEL", "gpt-4o-mini")

# Mã bí mật để quỹ ghi khoản chi (demo)
ADMIN_TOKEN = env("ADMIN_TOKEN", "doi-ma-nay")

DATA_DIR = BASE_DIR / "data"
FUNDS_XLSX = DATA_DIR / "funds.xlsx"  # file Excel danh sách quỹ (nguồn dữ liệu chính)
ORDERS_FILE = DATA_DIR / "orders.json"
FRONTEND_DIR = ROOT_DIR / "frontend"
