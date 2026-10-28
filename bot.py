# -*- coding: utf-8 -*-
import atexit
from datetime import datetime, timedelta
import hashlib
import hmac
import json
import logging
import mimetypes
import os
import re
import shutil
import signal
import shlex
import sqlite3
import struct
import subprocess
try:
    import resource
except ImportError:
    resource = None
import sys
import tempfile
import threading
import time
import zipfile
import venv
from flask import Flask, request, jsonify
from flask_cors import CORS
from threading import Thread
import psutil
import requests
import telebot
from telebot import types

# --- Configurable Conversion Rate ---
USDT_BDT_RATE = 120.0  # 1 USDT = 120 BDT (change if needed)

# --- Flask Keep Alive ---
app = Flask("")
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024

# Allow the browser control panel to call the /api/v1 endpoints.
# Authentication remains enforced by X-API-Key on protected endpoints.
CORS(
    app,
    resources={r"/api/*": {"origins": "*"}},
    allow_headers=["Content-Type", "X-API-Key", "Authorization"],
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
)


@app.route("/")
def home():
    return "I'm Mukesh File Host"


def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    print("Flask Keep-Alive server started.")


# --- End Flask Keep Alive ---

# --- Configuration ---
TOKEN = os.environ.get("BOT_TOKEN", "9122199616:AAHDfgLPPHlz-HcK8lGZIWG_EVxRZ2XHKWY").strip()
if not TOKEN and os.path.isfile(os.path.join(os.path.dirname(__file__), "bot_token.txt")):
    with open(os.path.join(os.path.dirname(__file__), "bot_token.txt"), "r", encoding="utf-8") as _tf:
        TOKEN = _tf.read().strip()
OWNER_ID = 8907916745
ADMIN_ID = 8907916745
YOUR_USERNAME = "@MRPANELxh"
UPDATE_CHANNEL = "https://t.me/TBBSUPORT"

# Optional Binance Pay verification configuration.
# Leave these unset to disable Binance verification safely instead of raising
# a NameError when the payment handler is used.
BINANCE_API_KEY = os.environ.get("BINANCE_API_KEY", "").strip()
BINANCE_SECRET_KEY = os.environ.get("BINANCE_SECRET_KEY", "").strip()

# --- Bangladesh Manual Payment Configuration ---
# FAM / Nagad / Upay numbers can be changed from the Admin panel.
DEFAULT_PAYMENT_NUMBERS = {
    "FAM": "017XXXXXXX",
    "nagad": "018XXXXXXXX",
    "upay": "019XXXXXXXX",
}
# Folder setup - using absolute paths
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_BOTS_DIR = os.path.join(BASE_DIR, "upload_bots")
IROTECH_DIR = os.path.join(BASE_DIR, "inf")
DATABASE_PATH = os.path.join(IROTECH_DIR, "bot_data.db")

# File upload limits
FREE_USER_LIMIT = 0  # Default free limit
SUBSCRIBED_USER_LIMIT = 15
ADMIN_LIMIT = 999
OWNER_LIMIT = float("inf")

# Create necessary directories
os.makedirs(UPLOAD_BOTS_DIR, exist_ok=True)
os.makedirs(IROTECH_DIR, exist_ok=True)

# Initialize bot
if not TOKEN:
    raise RuntimeError("BOT_TOKEN is required. Set the BOT_TOKEN environment variable or create bot_token.txt.")

bot = telebot.TeleBot(TOKEN)

# --- Data structures ---
bot_scripts = {}
_runtime_alert_state = {}
_runtime_lock = threading.RLock()
user_subscriptions = {}
user_files = {}
active_users = set()
admin_ids = {ADMIN_ID, OWNER_ID}
bot_locked = False
user_selected_plan = {}  # Temp state for upload flow

# --- Malware Detection Configuration ---
MALWARE_SIGNATURES = [
    b"MZ",  # Windows executable
    b"\x7fELF",  # Linux executable
    b"\xfe\xed\xfa",  # Mach-O binary
    b"\xce\xfa\xed\xfe",  # Mach-O binary (reverse)
    b"Rar!",  # RAR archive
]

ENCRYPTED_FILE_INDICATORS = [
]

SUSPICIOUS_KEYWORDS = [
    b"ransomware",
    b"trojan",
    b"virus",
    b"malware",
    b"backdoor",
    b"exploit",
    b"botnet",
    b"keylogger",
    b"rootkit",
]

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# --- Command Button Layouts ---
COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["✨ 𝗨𝗽𝗱𝗮𝘁𝗲𝘀 𝗖𝗵𝗮𝗻𝗻𝗲𝗹 ✨"],
    ["🚀 𝗨𝗽𝗹𝗼𝗮𝗱 𝗙𝗶𝗹𝗲", "📁 𝗠𝗮𝗻𝗮𝗴𝗲 𝗙𝗶𝗹𝗲𝘀"],
    ["💳 𝗩𝗶𝗲𝘄 𝗣𝗹𝗮𝗻𝘀", "⚡ 𝗦𝗽𝗲𝗲𝗱 & 𝗣𝗶𝗻𝗴"],
    ["📊 𝗕𝗼𝘁 𝗦𝘁𝗮𝘁𝘀"],
]

ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC = [
    ["✨ 𝗨𝗽𝗱𝗮𝘁𝗲𝘀 𝗖𝗵𝗮𝗻𝗻𝗲𝗹 ✨"],
    ["🚀 𝗨𝗽𝗹𝗼𝗮d 𝗙𝗶𝗹𝗲", "📁 𝗠𝗮𝗻𝗮𝗴𝗲 𝗙𝗶𝗹𝗲𝘀"],
    ["💳 𝗩𝗶𝗲𝘄 𝗣𝗹𝗮𝗻𝘀", "🛡️ 𝗔𝗱𝗺𝗶𝗻 𝗣𝗮𝗻𝗲𝗹"],
    ["⚡ 𝗦𝗽𝗲𝗲𝗱 & 𝗣𝗶𝗻𝗴", "📊 𝗕𝗼𝘁 𝗦𝘁𝗮𝘁𝘀"],
]

# --- Database Setup ---
DB_LOCK = threading.Lock()


def init_db():
    """Initialize the database with required tables"""
    logger.info(f"Initializing database at: {DATABASE_PATH}")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute(
            """CREATE TABLE IF NOT EXISTS subscriptions
                     (user_id INTEGER PRIMARY KEY, plan_name TEXT, expiry TEXT)"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS user_files
                     (user_id INTEGER, file_name TEXT, file_type TEXT,
                      PRIMARY KEY (user_id, file_name))"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS active_users
                     (user_id INTEGER PRIMARY KEY)"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS admins
                     (user_id INTEGER PRIMARY KEY)"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS plans
                     (plan_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, file_limit INTEGER, price TEXT, duration INTEGER, buy_link TEXT)"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS plan_features
                     (plan_id INTEGER PRIMARY KEY, terminal_enabled INTEGER NOT NULL DEFAULT 0)"""
        )

        # 🆕 Table for tracking partial payments
        c.execute(
            """CREATE TABLE IF NOT EXISTS pending_payments
                     (user_id INTEGER, plan_id INTEGER, paid_amount REAL,
                      PRIMARY KEY (user_id, plan_id))"""
        )

        # 🆕 Table for tracking used TxIDs to prevent double spending
        c.execute(
            """CREATE TABLE IF NOT EXISTS used_txids
                     (tx_id TEXT PRIMARY KEY)"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS payment_settings
                     (method TEXT PRIMARY KEY, number TEXT NOT NULL)"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS payment_requests
                     (request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id INTEGER NOT NULL, user_name TEXT, plan_id INTEGER,
                      plan_name TEXT, method TEXT, amount REAL, tx_id TEXT UNIQUE,
                      status TEXT DEFAULT 'pending', created_at TEXT,
                      reviewed_at TEXT, reviewed_by INTEGER)"""
        )
        for _method, _number in DEFAULT_PAYMENT_NUMBERS.items():
            c.execute(
                "INSERT OR IGNORE INTO payment_settings (method, number) VALUES (?, ?)",
                (_method, _number),
            )

        c.execute(
            "INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (OWNER_ID,)
        )
        if ADMIN_ID != OWNER_ID:
            c.execute(
                "INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (ADMIN_ID,)
            )

        conn.commit()
        conn.close()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"❌ Database initialization error: {e}", exc_info=True)


def load_data():
    """Load data from database into memory"""
    logger.info("Loading data from database...")
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()

        c.execute("SELECT user_id, plan_name, expiry FROM subscriptions")
        for row in c.fetchall():
            user_id = row[0]
            plan_name = row[1] if len(row) > 2 else "Premium"
            expiry = row[-1]
            try:
                user_subscriptions[user_id] = {
                    "plan_name": plan_name,
                    "expiry": datetime.fromisoformat(expiry),
                }
            except ValueError:
                logger.warning(
                    f"⚠️ Invalid expiry date format for user {user_id}: {expiry}. Skipping."
                )

        c.execute("SELECT user_id, file_name, file_type FROM user_files")
        for user_id, file_name, file_type in c.fetchall():
            if user_id not in user_files:
                user_files[user_id] = []
            user_files[user_id].append((file_name, file_type))

        c.execute("SELECT user_id FROM active_users")
        active_users.update(user_id for (user_id,) in c.fetchall())

        c.execute("SELECT user_id FROM admins")
        admin_ids.update(user_id for (user_id,) in c.fetchall())

        conn.close()
        logger.info(f"Data loaded successfully.")
    except Exception as e:
        logger.error(f"❌ Error loading data: {e}", exc_info=True)


init_db()
load_data()


# --- Price Parser & Conversion Helper ---
def parse_price_to_usdt(price_str):
    """
    Extracts the amount and currency from a BDT or USD field and converts it to USDT.
    Example: '500 BDT' -> (4.17, '500 BDT (~4.17 USDT)')
    '5 USDT' -> (5.0, '5.0 USDT')
    """
    price_clean = str(price_str).upper().strip()
    numbers = re.findall(r"[-+]?\d*\.\d+|\d+", price_clean)
    if not numbers:
        return 0.0, price_str

    val = float(numbers[0])
    if "BDT" in price_clean or "TAKA" in price_clean or "TK" in price_clean:
        usdt_val = round(val / USDT_BDT_RATE, 2)
        return usdt_val, f"{price_str} (~{usdt_val} USDT)"
    elif "USDT" in price_clean or "$" in price_clean or "USD" in price_clean:
        return round(val, 2), f"{val} USDT"
    else:
        # If only a number is provided, it is treated as USDT by default
        return round(val, 2), f"{val} USDT"


# --- Database Helper Operations ---
def add_plan_db(name, file_limit, price, duration, buy_link, terminal_enabled=False):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute(
            "INSERT INTO plans (name, file_limit, price, duration, buy_link) VALUES (?, ?, ?, ?, ?)",
            (name, file_limit, price, duration, buy_link),
        )
        plan_id = c.lastrowid
        c.execute(
            "INSERT OR REPLACE INTO plan_features (plan_id, terminal_enabled) VALUES (?, ?)",
            (plan_id, 1 if terminal_enabled else 0),
        )
        conn.commit()
        conn.close()
        return plan_id


def get_all_plans():
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute(
        "SELECT plan_id, name, file_limit, price, duration, buy_link FROM plans"
    )
    plans = c.fetchall()
    conn.close()
    return plans


def get_plan_by_id(plan_id):
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute(
        "SELECT plan_id, name, file_limit, price, duration, buy_link FROM plans WHERE plan_id = ?",
        (plan_id,),
    )
    plan = c.fetchone()
    conn.close()
    return plan


def delete_plan_db(plan_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("DELETE FROM plans WHERE plan_id = ?", (plan_id,))
        conn.commit()
        conn.close()


# --- Partial Payment Helpers ---
def get_pending_payment(user_id, plan_id):
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute(
        "SELECT paid_amount FROM pending_payments WHERE user_id=? AND plan_id=?",
        (user_id, plan_id),
    )
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0.0


def update_pending_payment(user_id, plan_id, amount):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO pending_payments (user_id, plan_id, paid_amount) VALUES (?, ?, ?)",
            (user_id, plan_id, amount),
        )
        conn.commit()
        conn.close()


def clear_pending_payment(user_id, plan_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute(
            "DELETE FROM pending_payments WHERE user_id=? AND plan_id=?",
            (user_id, plan_id),
        )
        conn.commit()
        conn.close()


def is_txid_used(tx_id):
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute(
        "SELECT tx_id FROM used_txids WHERE tx_id=?", (str(tx_id).strip(),)
    )
    row = c.fetchone()
    conn.close()
    return row is not None


def add_used_txid(tx_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute(
            "INSERT OR IGNORE INTO used_txids (tx_id) VALUES (?)",
            (str(tx_id).strip(),),
        )
        conn.commit()
        conn.close()


# --- Binance Pay Verification Function ---
def check_binance_payment(pay_order_id):
    """Verifies payment strictly via Binance Pay API"""
    if (
        not BINANCE_API_KEY
        or BINANCE_API_KEY == "YOUR_NEW_BINANCE_API_KEY_HERE"
    ):
        return False, 0.0, "Binance API Key is not configured."

    endpoint = "https://api.binance.com/sapi/v1/pay/transactions"
    timestamp = int(time.time() * 1000)
    query_string = f"timestamp={timestamp}"

    signature = hmac.new(
        BINANCE_SECRET_KEY.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    url = f"{endpoint}?{query_string}&signature={signature}"
    headers = {"X-MBX-APIKEY": BINANCE_API_KEY}

    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            transactions = (
                data.get("data", []) if isinstance(data, dict) else data
            )

            for item in transactions:
                order_id_str = str(
                    item.get("orderId", "") or item.get("transactionId", "")
                )
                if order_id_str.strip() == str(pay_order_id).strip():
                    amount = float(item.get("amount", 0.0))
                    currency = item.get("currency", "USDT")
                    return True, amount, f"{amount} {currency}"

            return (
                False,
                0.0,
                "This Order/Transaction ID was not found in your Binance Pay history.",
            )
        else:
            logger.error(f"Binance Pay API Error: {res.text}")
            return False, 0.0, "Binance Server Error or API permission issue."
    except Exception as e:
        logger.error(f"Binance Verification Error: {e}")
        return False, 0.0, f"Error: {str(e)}"


# --- Malware Detection Functions ---
def is_suspicious_file(file_content, file_name):
    file_lower = file_name.lower()
    suspicious_extensions = [
        ".exe",
        ".dll",
        ".bat",
        ".cmd",
        ".scr",
        ".com",
        ".pif",
        ".application",
        ".gadget",
        ".msi",
        ".msp",
        ".com",
        ".scr",
        ".hta",
        ".cpl",
        ".msc",
        ".jar",
        ".bin",
        ".deb",
        ".rpm",
        ".apk",
        ".app",
        ".dmg",
        ".iso",
        ".img",
    ]
    if any(file_lower.endswith(ext) for ext in suspicious_extensions):
        return True, f"Suspicious file extension: {file_name}"
    for signature in MALWARE_SIGNATURES:
        if file_content.startswith(signature):
            return True, f"Malware signature detected: {signature}"
    sample_size = min(len(file_content), 4096)
    file_sample = file_content[:sample_size]
    for indicator in ENCRYPTED_FILE_INDICATORS:
        if indicator in file_sample:
            return (
                True,
                f"Encrypted file indicator: {indicator.decode('utf-8', errors='ignore')}",
            )
    sample_text = file_sample.decode("utf-8", errors="ignore").lower()
    for keyword in SUSPICIOUS_KEYWORDS:
        if keyword.decode("utf-8").lower() in sample_text:
            return True, f"Suspicious keyword found: {keyword.decode('utf-8')}"
    return False, "File appears safe"


def _clamav_scan_bytes(file_content, file_name):
    """Optional ClamAV scan. If clamscan is unavailable, signature scanning still applies."""
    scanner = shutil.which("clamscan")
    if not scanner:
        return True, "ClamAV unavailable; signature scan completed"
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(prefix="scan_", suffix=os.path.splitext(file_name)[1], delete=False) as tmp:
            tmp.write(file_content)
            temp_path = tmp.name
        result = subprocess.run([scanner, "--no-summary", "--infected", temp_path], capture_output=True, text=True, timeout=30)
        if result.returncode == 1:
            return False, "ClamAV detected a malicious file"
        if result.returncode > 1:
            logger.warning("ClamAV scan error for %s: %s", file_name, (result.stderr or result.stdout)[-500:])
            return True, "ClamAV error; signature scan completed"
        return True, "ClamAV clean"
    except Exception as exc:
        logger.warning("ClamAV scan unavailable for %s: %s", file_name, exc)
        return True, "ClamAV unavailable; signature scan completed"
    finally:
        if temp_path:
            try: os.remove(temp_path)
            except OSError: pass


def scan_file_for_malware(file_content, file_name, user_id):
    # Security checks apply to every user, including owner/admin accounts.
    is_suspicious, reason = is_suspicious_file(file_content, file_name)
    if is_suspicious:
        logger.warning("🚨 Malware/suspicious file blocked: %s from user %s: %s", file_name, user_id, reason)
        return False, f"Security violation: {reason}"
    clean, av_reason = _clamav_scan_bytes(file_content, file_name)
    if not clean:
        logger.warning("🚨 Antivirus blocked %s from user %s: %s", file_name, user_id, av_reason)
        return False, f"Security violation: {av_reason}"
    return True, "File passed security checks"


# --- Helper Functions ---
def get_user_folder(user_id):
    user_folder = os.path.join(UPLOAD_BOTS_DIR, str(user_id))
    os.makedirs(user_folder, exist_ok=True)
    return user_folder


def get_user_plan(user_id):
    """Return the currently active plan row for a user, if any."""
    sub = user_subscriptions.get(user_id)
    if not sub or sub.get("expiry") <= datetime.now():
        return None
    return get_plan_by_name(sub.get("plan_name", ""))


def get_plan_by_name(name):
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute(
        "SELECT plan_id, name, file_limit, price, duration, buy_link FROM plans WHERE name = ? LIMIT 1",
        (str(name),),
    )
    row = c.fetchone()
    conn.close()
    return row


def get_plan_terminal_enabled(plan_id):
    row = enhanced_db("SELECT terminal_enabled FROM plan_features WHERE plan_id=?", (int(plan_id),), one=True) if 'enhanced_db' in globals() else None
    if row is not None:
        return bool(row["terminal_enabled"] if hasattr(row, "keys") else row[0])
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT terminal_enabled FROM plan_features WHERE plan_id=?", (int(plan_id),))
    value = c.fetchone()
    conn.close()
    return bool(value[0]) if value else False


def user_terminal_enabled(user_id):
    if user_id in admin_ids or user_id == OWNER_ID:
        return True
    plan = get_user_plan(user_id)
    return bool(plan and get_plan_terminal_enabled(plan[0]))


def get_user_file_limit(user_id):
    if user_id == OWNER_ID:
        return OWNER_LIMIT
    if user_id in admin_ids:
        return ADMIN_LIMIT
    plan = get_user_plan(user_id)
    if plan:
        try:
            return max(0, int(plan[2]))
        except (TypeError, ValueError):
            return SUBSCRIBED_USER_LIMIT
    return FREE_USER_LIMIT


def get_user_file_count(user_id):
    return len(user_files.get(user_id, []))


def is_bot_running(script_owner_id, file_name):
    script_key = f"{script_owner_id}_{file_name}"
    script_info = bot_scripts.get(script_key)
    if script_info and script_info.get("process"):
        try:
            proc = psutil.Process(script_info["process"].pid)
            is_running = (
                proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
            )
            if not is_running:
                if (
                    "log_file" in script_info
                    and hasattr(script_info["log_file"], "close")
                    and not script_info["log_file"].closed
                ):
                    try:
                        script_info["log_file"].close()
                    except Exception:
                        pass
                if script_key in bot_scripts:
                    del bot_scripts[script_key]
            return is_running
        except psutil.NoSuchProcess:
            if script_key in bot_scripts:
                del bot_scripts[script_key]
            return False
        except Exception:
            return False
    return False


def kill_process_tree(process_info):
    try:
        if (
            "log_file" in process_info
            and hasattr(process_info["log_file"], "close")
            and not process_info["log_file"].closed
        ):
            try:
                process_info["log_file"].close()
            except Exception:
                pass
        process = process_info.get("process")
        if process and hasattr(process, "pid"):
            pid = process.pid
            if pid:
                parent = psutil.Process(pid)
                for child in parent.children(recursive=True):
                    try:
                        child.terminate()
                    except Exception:
                        pass
                try:
                    parent.terminate()
                except Exception:
                    pass
    except Exception as e:
        logger.error(f"❌ Error killing process: {e}")


# --- Module / Package Mapping ---
TELEGRAM_MODULES = {
    "telebot": "pyTelegramBotAPI",
    "telegram": "python-telegram-bot",
    "python_telegram_bot": "python-telegram-bot",
    "aiogram": "aiogram",
    "pyrogram": "pyrogram",
    "telethon": "telethon",
    "bs4": "beautifulsoup4",
    "requests": "requests",
    "pillow": "Pillow",
    "cv2": "opencv-python",
    "flask": "Flask",
    "psutil": "psutil",
}


# --- Automatic & Guided Script Running ---
def monitor_and_guide_error(
    process, log_file_path, script_owner_id, file_name, message_obj_for_reply
):
    """Checks running scripts in the background and provides buttons when an error occurs."""
    time.sleep(3)
    if process.poll() is not None:
        try:
            with open(log_file_path, "r", encoding="utf-8", errors="ignore") as f:
                log_content = f.read()

            match_py = re.search(
                r"(?:ModuleNotFoundError|ImportError): No module named '(.+?)'",
                log_content,
            )
            match_js = re.search(r"Cannot find module '(.+?)'", log_content)

            missing_module = None
            if match_py:
                missing_module = match_py.group(1).split(".")[0].strip("'\"")
            elif match_js:
                missing_module = match_js.group(1).split("/")[0].strip("'\"")

            if missing_module:
                pkg_name = TELEGRAM_MODULES.get(
                    missing_module.lower(), missing_module
                )
                ext = os.path.splitext(file_name)[1].lower()
                cmd_text = (
                    f"npm install {pkg_name}"
                    if ext == ".js"
                    else f"pip install {pkg_name}"
                )

                error_msg = (
                    f"⚠️ **The file failed to start!**\n\n"
                    f"📄 **File:** `{file_name}`\n"
                    f"❌ **Problem:** Your code is missing `{missing_module}` module is missing.\n"
                    f"💻 **Required command:** `{cmd_text}`\n\n"
                    f"👇 *Press the button below to install the module directly:*"
                )

                markup = types.InlineKeyboardMarkup()
                markup.add(
                    types.InlineKeyboardButton(
                        f"📦 Install {pkg_name}",
                        callback_data=f"instmod_{script_owner_id}_{missing_module}_{file_name}",
                    )
                )
                markup.add(
                    types.InlineKeyboardButton(
                        "📄 View Error Logs",
                        callback_data=f"viewlog_{script_owner_id}_{file_name}",
                    )
                )

                if message_obj_for_reply is not None:
                    bot.reply_to(
                        message_obj_for_reply,
                        error_msg,
                        reply_markup=markup,
                        parse_mode="Markdown",
                    )
            else:
                error_msg = (
                    f"⚠️ **A Syntax/Runtime Error was detected in your code!**\n\n"
                    f"📄 **File:** `{file_name}`\n"
                    f"Click **View Logs** below to see the exact error."
                )
                markup = types.InlineKeyboardMarkup()
                markup.add(
                    types.InlineKeyboardButton(
                        "📄 View Error Logs",
                        callback_data=f"viewlog_{script_owner_id}_{file_name}",
                    )
                )
                if message_obj_for_reply is not None:
                    bot.reply_to(
                        message_obj_for_reply,
                        error_msg,
                        reply_markup=markup,
                        parse_mode="Markdown",
                    )
        except Exception as e:
            logger.error(f"Error checking log file: {e}")


def user_python_executable(user_id):
    """Return a per-user Python executable for dependency isolation."""
    env_dir = os.path.join(get_user_folder(user_id), ".venv")
    if os.name == "nt":
        exe = os.path.join(env_dir, "Scripts", "python.exe")
    else:
        exe = os.path.join(env_dir, "bin", "python")
    if not os.path.isfile(exe):
        venv.EnvBuilder(with_pip=True, clear=False).create(env_dir)
    return exe


def _sandbox_preexec():
    """Best-effort per-process limits on Unix hosts; filesystem isolation should be enforced by the container/host too."""
    if resource is None or os.name == "nt":
        return
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (300, 300))
        resource.setrlimit(resource.RLIMIT_FSIZE, (100 * 1024 * 1024, 100 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    except Exception:
        pass


def run_script(
    script_path, script_owner_id, user_folder, file_name, message_obj_for_reply
):
    script_key = f"{script_owner_id}_{file_name}"
    try:
        log_file_path = os.path.join(
            user_folder, f"{os.path.splitext(file_name)[0]}.log"
        )
        log_file = open(log_file_path, "w", encoding="utf-8", errors="ignore")
        python_exe = user_python_executable(script_owner_id)
        process = subprocess.Popen(
            [python_exe, script_path],
            cwd=user_folder,
            stdout=log_file,
            stderr=log_file,
            stdin=subprocess.PIPE,
            env=bot_runtime_env(script_owner_id, file_name),
            preexec_fn=_sandbox_preexec if os.name != "nt" else None,
        )

        bot_scripts[script_key] = {
            "process": process,
            "log_file": log_file,
            "file_name": file_name,
            "script_owner_id": script_owner_id,
            "start_time": datetime.now(),
            "user_folder": user_folder,
            "type": "py",
            "script_key": script_key,
            "restart_history": [],
            "manual_stop": False,
        }
        record_activity(script_owner_id, "START_BOT", f"{file_name} (PID {process.pid})")

        if message_obj_for_reply is not None:
            bot.reply_to(
                message_obj_for_reply,
                f"🚀 **Python Script Started!**\n📄 File: `{file_name}`\n🆔 PID: `{process.pid}`",
                parse_mode="Markdown",
            )

        threading.Thread(
            target=monitor_and_guide_error,
            args=(
                process,
                log_file_path,
                script_owner_id,
                file_name,
                message_obj_for_reply,
            ),
        ).start()

    except Exception as e:
        if message_obj_for_reply is not None:
            bot.reply_to(message_obj_for_reply, f"❌ Error running script: {str(e)}")


def run_js_script(
    script_path, script_owner_id, user_folder, file_name, message_obj_for_reply
):
    script_key = f"{script_owner_id}_{file_name}"
    try:
        log_file_path = os.path.join(
            user_folder, f"{os.path.splitext(file_name)[0]}.log"
        )
        log_file = open(log_file_path, "w", encoding="utf-8", errors="ignore")
        process = subprocess.Popen(
            ["node", script_path],
            cwd=user_folder,
            stdout=log_file,
            stderr=log_file,
            stdin=subprocess.PIPE,
            env=bot_runtime_env(script_owner_id, file_name),
            preexec_fn=_sandbox_preexec if os.name != "nt" else None,
        )

        bot_scripts[script_key] = {
            "process": process,
            "log_file": log_file,
            "file_name": file_name,
            "script_owner_id": script_owner_id,
            "start_time": datetime.now(),
            "user_folder": user_folder,
            "type": "js",
            "script_key": script_key,
            "restart_history": [],
            "manual_stop": False,
        }
        record_activity(script_owner_id, "START_BOT", f"{file_name} (PID {process.pid})")

        if message_obj_for_reply is not None:
            bot.reply_to(
                message_obj_for_reply,
                f"🚀 **JS Script Started!**\n📄 File: `{file_name}`\n🆔 PID: `{process.pid}`",
                parse_mode="Markdown",
            )

        threading.Thread(
            target=monitor_and_guide_error,
            args=(
                process,
                log_file_path,
                script_owner_id,
                file_name,
                message_obj_for_reply,
            ),
        ).start()

    except Exception as e:
        if message_obj_for_reply is not None:
            bot.reply_to(
                message_obj_for_reply, f"❌ Error running JS script: {str(e)}"
            )


# --- Professional Runtime Monitoring ---
def record_activity(user_id, action, details="", actor_id=None):
    try:
        enhanced_db("INSERT INTO activity_logs (user_id, actor_id, action, details, created_at) VALUES (?, ?, ?, ?, ?)",
                    (int(user_id), int(actor_id or user_id), str(action), str(details)[:1000], datetime.now().isoformat(timespec="seconds")))
    except Exception:
        logger.exception("Activity log write failed")


def notify_admins(text):
    for admin_id in list(admin_ids):
        try:
            bot.send_message(admin_id, text, parse_mode="Markdown")
        except Exception:
            logger.exception("Admin notification failed for %s", admin_id)


def _runtime_supervisor():
    """Monitor bot processes without automatically restarting them.

    A process that exits is simply removed from the active runtime registry.
    Users/admins can start it again manually when needed.
    """
    while True:
        try:
            for key, info in list(bot_scripts.items()):
                proc = info.get("process")
                if not proc or proc.poll() is None:
                    continue
                bot_scripts.pop(key, None)
                try:
                    if info.get("log_file"):
                        info["log_file"].close()
                except Exception:
                    pass
        except Exception:
            logger.exception("Runtime supervisor failed")
        time.sleep(15)


def _runtime_resource_monitor():
    while True:
        try:
            total_ram=max(psutil.virtual_memory().total,1)
            for key, info in list(bot_scripts.items()):
                proc=info.get("process")
                if not proc or proc.poll() is not None: continue
                try:
                    cpu=proc.cpu_percent(interval=0.03); ram=proc.memory_info().rss/(1024*1024)
                    if cpu>=85 or (ram*1024*1024)/total_ram>=0.30:
                        now=time.time(); last=_runtime_alert_state.get(key,0)
                        if now-last>=600:
                            _runtime_alert_state[key]=now; owner_id=int(info.get("script_owner_id",0)); fname=info.get("file_name",key)
                            record_activity(owner_id,"RESOURCE_ALERT",f"{fname}: CPU {cpu:.1f}% RAM {ram:.1f} MB")
                            notify_admins(f"🚨 **Resource Alert**\n\n👤 User: `{owner_id}`\n📄 File: `{fname}`\n⚙️ CPU: `{cpu:.1f}%`\n💾 RAM: `{ram:.1f} MB`")
                except (psutil.NoSuchProcess, psutil.AccessDenied): pass
        except Exception:
            logger.exception("Resource monitor failed")
        time.sleep(30)


def _format_uptime(start_time):
    sec=max(0,int((datetime.now()-start_time).total_seconds())); days,sec=divmod(sec,86400); hours,sec=divmod(sec,3600); mins,sec=divmod(sec,60)
    return f"{days}d {hours}h {mins}m" if days else (f"{hours}h {mins}m" if hours else f"{mins}m {sec}s")


def send_server_monitor(chat_id):
    vm=psutil.virtual_memory(); disk=psutil.disk_usage(BASE_DIR); cpu=psutil.cpu_percent(interval=0.15); lines=[]
    for info in list(bot_scripts.values()):
        proc=info.get("process")
        if not proc or proc.poll() is not None: continue
        try: lines.append(f"• `{info['file_name']}` — CPU `{proc.cpu_percent(interval=0.02):.1f}%`, RAM `{proc.memory_info().rss/1024**2:.1f} MB`, Uptime `{_format_uptime(info['start_time'])}`")
        except Exception: pass
    text=(f"📈 **Server Monitor**\n\n⚙️ CPU: `{cpu:.1f}%`\n💾 RAM: `{vm.percent:.1f}%` (`{vm.used/1024**3:.2f}/{vm.total/1024**3:.2f} GB`)\n💿 Disk: `{disk.percent:.1f}%`\n🚀 Running Bots: `{len(lines)}`\n\n"+("\n".join(lines[:20]) if lines else "No running bots."))
    bot.send_message(chat_id,text,parse_mode="Markdown")


def send_my_bot_monitor(chat_id,user_id):
    lines=[]
    for fname,_ in user_files.get(user_id,[]):
        info=bot_scripts.get(f"{user_id}_{fname}"); proc=info.get("process") if info else None
        if proc and proc.poll() is None:
            try: lines.append(f"📄 `{fname}`\n⚙️ CPU: `{proc.cpu_percent(interval=0.02):.1f}%` | 💾 RAM: `{proc.memory_info().rss/1024**2:.1f} MB`\n⏱️ Uptime: `{_format_uptime(info['start_time'])}`")
            except Exception: pass
    bot.send_message(chat_id,"🤖 **My Bot Monitor**\n\n"+("\n\n".join(lines) if lines else "No running bots."),parse_mode="Markdown")


def real_speed_ping(message):
    started=time.perf_counter()
    try:
        bot.get_me(); latency=max(1,int((time.perf_counter()-started)*1000)); vm=psutil.virtual_memory()
        bot.reply_to(message,f"⚡ **Server Status**\n\n📡 Telegram API: `{latency} ms`\n⚙️ CPU: `{psutil.cpu_percent(interval=0.1):.1f}%`\n💾 RAM: `{vm.percent:.1f}%`\n🟢 Status: `Online`",parse_mode="Markdown")
    except Exception as e: bot.reply_to(message,f"🔴 **Server Status**\n\n❌ Telegram API check failed: `{str(e)[:180]}`",parse_mode="Markdown")

# --- Database Operations ---
def save_user_file(user_id, file_name, file_type="py"):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO user_files (user_id, file_name, file_type) VALUES (?, ?, ?)",
            (user_id, file_name, file_type),
        )
        conn.commit()
        conn.close()
        if user_id not in user_files:
            user_files[user_id] = []
        user_files[user_id] = [
            (fn, ft) for fn, ft in user_files[user_id] if fn != file_name
        ]
        user_files[user_id].append((file_name, file_type))


def remove_user_file_db(user_id, file_name):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute(
            "DELETE FROM user_files WHERE user_id = ? AND file_name = ?",
            (user_id, file_name),
        )
        conn.commit()
        conn.close()
        if user_id in user_files:
            user_files[user_id] = [
                f for f in user_files[user_id] if f[0] != file_name
            ]


def add_active_user(user_id):
    active_users.add(user_id)
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute(
            "INSERT OR IGNORE INTO active_users (user_id) VALUES (?)", (user_id,)
        )
        conn.commit()
        conn.close()


def save_subscription(user_id, plan_name, expiry):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO subscriptions (user_id, plan_name, expiry) VALUES (?, ?, ?)",
            (user_id, plan_name, expiry.isoformat()),
        )
        conn.commit()
        conn.close()
        user_subscriptions[user_id] = {"plan_name": plan_name, "expiry": expiry}


def remove_subscription_db(user_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("DELETE FROM subscriptions WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
        if user_id in user_subscriptions:
            del user_subscriptions[user_id]


# --- Menu Creation ---
def create_reply_keyboard_main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    layout_to_use = (
        ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC
        if user_id in admin_ids
        else COMMAND_BUTTONS_LAYOUT_USER_SPEC
    )
    for row in layout_to_use:
        markup.add(*[types.KeyboardButton(text) for text in row])
    return markup


def create_admin_panel_inline():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("➕ 𝗔𝗱𝗱 𝗣𝗹𝗮𝗻", callback_data="add_plan_init"),
        types.InlineKeyboardButton("🗑️ 𝗠𝗮𝗻𝗮𝗴𝗲 𝗣𝗹𝗮𝗻𝘀", callback_data="manage_plans"),
    )
    markup.add(
        types.InlineKeyboardButton("💎 𝗔𝗱𝗱 𝗦𝘂𝗯𝘀𝗰𝗿𝗶𝗽𝘁𝗶𝗼𝗻", callback_data="add_subscription"),
        types.InlineKeyboardButton("❌ 𝗥𝗲𝗺𝗼𝘃𝗲 𝗦𝘂𝗯", callback_data="remove_subscription"),
    )
    markup.add(
        types.InlineKeyboardButton("💳 Payment Settings", callback_data="payment_settings"),
        types.InlineKeyboardButton("📥 Payment Requests", callback_data="payment_requests"),
    )
    markup.add(
        types.InlineKeyboardButton("👑 𝗔𝗱𝗱 𝗔𝗱𝗺𝗶𝗻", callback_data="add_admin"),
        types.InlineKeyboardButton("➖ 𝗥𝗲𝗺𝗼𝘃𝗲 𝗔𝗱𝗺𝗶𝗻", callback_data="remove_admin"),
    )
    markup.add(
        types.InlineKeyboardButton("📣 𝗕𝗿𝗼𝗮𝗱𝗰𝗮𝘀𝘁", callback_data="broadcast"),
        types.InlineKeyboardButton("🔐 𝗟𝗼𝗰𝗸/𝗨𝗻𝗹𝗼𝗰𝗸", callback_data="toggle_lock"),
    )
    markup.add(
        types.InlineKeyboardButton("⚙️ 𝗥𝘂𝗻 𝗔𝗹𝗹 𝗦𝗰𝗿𝗶𝗽𝘁𝘀", callback_data="run_all_scripts"),
        types.InlineKeyboardButton("📊 𝗕𝗼𝘁 𝗦𝘁𝗮𝘁𝘀", callback_data="stats"),
    )
    return markup


# --- Core User Logic ---
def _logic_send_welcome(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    user_name = message.from_user.first_name

    if bot_locked and user_id not in admin_ids:
        bot.send_message(chat_id, "⚠️ **Bot is temporarily locked by Admin.**")
        return

    if user_id not in active_users:
        add_active_user(user_id)

    if user_id == OWNER_ID:
        user_status = "👑 **Owner**"
    elif user_id in admin_ids:
        user_status = "🛡️ **Admin**"
    elif (
        user_id in user_subscriptions
        and user_subscriptions[user_id]["expiry"] > datetime.now()
    ):
        sub = user_subscriptions[user_id]
        days_left = (sub["expiry"] - datetime.now()).days
        user_status = f"💎 **{sub.get('plan_name', 'Premium')} Active** ({days_left} Days left)"
    else:
        user_status = "🆓 **No Active Plan**"

    welcome_msg = (
        f"✨ **𝗪𝗲𝗹𝗰𝗼𝗺𝗲, {user_name}!** ✨\n\n"
        f"🆔 **𝗬𝗼𝘂𝗿 𝗜𝗗:** `{user_id}`\n"
        f"🔰 **𝗦𝘁𝗮𝘁𝘂𝘀:** {user_status}\n"
        f"📁 **𝗨𝗽𝗹𝗼𝗮𝗱𝗲𝗱 𝗙𝗶𝗹𝗲𝘀:** `{get_user_file_count(user_id)}` / `{get_user_file_limit(user_id)}`\n\n"
        f"💡 **𝗛𝗼𝘀𝘁 & 𝗥𝘂𝗻 𝘆𝗼𝘂𝗿 𝗣𝘆𝘁𝗵𝗼𝗻 (.𝗽𝘆) & 𝗝𝗦 (.𝗷𝘀) 𝗯𝗼𝘁𝘀 𝟮𝟰/𝟳.**\n"
        f"👇 *Select an option from the menu below:* "
    )
    bot.send_message(
        chat_id,
        welcome_msg,
        reply_markup=create_reply_keyboard_main_menu(user_id),
        parse_mode="Markdown",
    )


def is_free_price(price_str):
    clean = str(price_str).strip().upper()
    if clean in {"FREE", "0", "0 BDT", "0 TK", "0 TAKA", "0 USDT", "$0", "0 USD"}:
        return True
    nums = re.findall(r"[-+]?\d*\.\d+|\d+", clean)
    return bool(nums) and float(nums[0]) == 0.0


def _activate_free_plan(user_id, plan_id, notify_admin=True):
    plan = get_plan_by_id(plan_id)
    if not plan or not is_free_price(plan[3]):
        return False, "This is not a free plan."
    _, name, limit, _, duration, _ = plan
    expiry = datetime.now() + timedelta(days=max(1, int(duration)))
    save_subscription(user_id, name, expiry)
    record_activity(user_id, "FREE_PLAN_ACTIVATED", f"{name} ({duration} days)")
    if notify_admin:
        try:
            notify_admins(
                f"🎁 **Free Plan Activated**\n\n👤 User: `{user_id}`\n📦 Plan: `{name}`\n📁 File Limit: `{limit}`\n⏱️ Duration: `{duration} Days`\n📅 Expiry: `{expiry.strftime('%Y-%m-%d %H:%M')}`"
            )
        except Exception:
            logger.exception("Free plan admin notification failed")
    return True, f"{name} activated until {expiry.strftime('%Y-%m-%d %H:%M')}."


def _logic_view_plans(message_or_call):
    chat_id = (
        message_or_call.chat.id
        if isinstance(message_or_call, telebot.types.Message)
        else message_or_call.message.chat.id
    )
    plans = get_all_plans()
    if not plans:
        bot.send_message(chat_id, "ℹ️ **No plans are currently available.**", parse_mode="Markdown")
        return
    bot.send_message(chat_id, "💳 **𝗔𝘃𝗮𝗶𝗹𝗮𝗯𝗹𝗲 𝗛𝗼𝘀𝘁𝗶𝗻𝗴 𝗣𝗹𝗮𝗻𝘀:**", parse_mode="Markdown")
    for plan in plans:
        plan_id, name, limit, price, duration, buy_link = plan
        bdt_amount, formatted_price = get_manual_payment_amount(price)
        terminal_status = "🟢 ON" if get_plan_terminal_enabled(plan_id) else "🔴 OFF"
        free_plan = is_free_price(price)
        price_line = "🎁 **Price:** `FREE`" if free_plan else f"💰 **Price:** `{formatted_price}`"
        card_text = (
            f"📦 **𝗣𝗹𝗮𝗻:** `{name}`\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"📁 **File Limit:** `{limit} Files`\n"
            f"💻 **Terminal:** `{terminal_status}`\n"
            f"⏱️ **Duration:** `{duration} Days`\n"
            f"{price_line}\n"
            f"━━━━━━━━━━━━━━━━━━━"
        )
        markup = types.InlineKeyboardMarkup()
        if free_plan:
            markup.add(types.InlineKeyboardButton(
                f"🎁 Activate {name}",
                callback_data=f"activate_free_{plan_id}",
            ))
        else:
            markup.add(types.InlineKeyboardButton(
                f"🛒 Buy {name} ({bdt_amount:.0f} BDT)",
                callback_data=f"buy_manual_{plan_id}",
            ))
        bot.send_message(chat_id, card_text, reply_markup=markup, parse_mode="Markdown")


def _logic_upload_file(message):
    user_id = message.from_user.id
    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, "⚠️ **Bot is locked by Admin.**")
        return

    has_active_plan = False
    plan_name = "None"

    if user_id in admin_ids or user_id == OWNER_ID:
        has_active_plan = True
        plan_name = "Admin / Owner Unlimited"
    elif user_id in user_subscriptions:
        sub = user_subscriptions[user_id]
        if sub["expiry"] > datetime.now():
            has_active_plan = True
            plan_name = sub.get("plan_name", "Premium Plan")

    if not has_active_plan:
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton(
                "💳 View Plans & Buy", callback_data="view_plans_cb"
            )
        )
        bot.reply_to(
            message,
            "❌ **You do not have an active plan!**\n\n"
            "You must subscribe to a plan before uploading files. "
            "Click the button below to view our plans and choose the plan you prefer.",
            reply_markup=markup,
            parse_mode="Markdown",
        )
        return

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton(
            f"✅ Continue with {plan_name}", callback_data="confirm_plan_upload"
        )
    )
    bot.reply_to(
        message,
        f"🔰 **𝗔𝗰𝘁𝗶𝘃𝗲 𝗣𝗹𝗮𝗻 𝗗𝗲𝘁𝗲𝗰𝘁𝗲𝗱:** `{plan_name}`\n\n"
        f"Select a button below to start file upload:",
        reply_markup=markup,
        parse_mode="Markdown",
    )


def _logic_check_files(message):
    user_id = message.from_user.id
    user_files_list = user_files.get(user_id, [])
    if not user_files_list:
        bot.reply_to(
            message,
            "📂 **Your Uploaded Files:**\n\n*(No files uploaded yet)*",
            parse_mode="Markdown",
        )
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for file_name, file_type in sorted(user_files_list):
        is_running = is_bot_running(user_id, file_name)
        status_icon = "🟢 Running" if is_running else "🔴 Stopped"
        btn_text = f"📄 {file_name} ({file_type}) - {status_icon}"
        markup.add(
            types.InlineKeyboardButton(
                btn_text, callback_data=f"file_{user_id}_{file_name}"
            )
        )
    bot.reply_to(
        message,
        "📁 **𝗠𝗮𝗻𝗮𝗴𝗲 𝗬𝗼𝘂𝗿 𝗙𝗶𝗹𝗲𝘀:**",
        reply_markup=markup,
        parse_mode="Markdown",
    )


def safe_extract_zip(zip_path, extract_dir, user_id=None):
    """Safely inspect and extract ZIP archives with traversal, symlink and bomb limits."""
    root = os.path.realpath(extract_dir)
    os.makedirs(root, exist_ok=True)
    max_members = 200
    max_uncompressed = 100 * 1024 * 1024
    total = 0
    with zipfile.ZipFile(zip_path, "r") as zf:
        members = zf.infolist()
        if len(members) > max_members:
            raise ValueError("ZIP contains too many files")
        for member in members:
            name = member.filename.replace("\\", "/")
            target = os.path.realpath(os.path.join(root, name))
            if target != root and not target.startswith(root + os.sep):
                raise ValueError("Unsafe ZIP path detected")
            mode = (member.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise ValueError("ZIP symbolic links are not allowed")
            total += member.file_size
            if total > max_uncompressed:
                raise ValueError("ZIP uncompressed size exceeds security limit")
            if member.is_dir():
                continue
            # Inspect every extracted file before writing it to disk.
            with zf.open(member, "r") as src:
                content = src.read(max_uncompressed + 1)
            if len(content) > max_uncompressed:
                raise ValueError("ZIP member exceeds security limit")
            if user_id is not None:
                safe, reason = scan_file_for_malware(content, name, user_id)
                if not safe:
                    raise ValueError(f"Unsafe file inside ZIP: {reason}")
        zf.extractall(root)


# --- Document Upload Processing ---
@bot.message_handler(content_types=["document"])
def handle_file_upload_doc(message):
    record_user(message)
    user_id = message.from_user.id
    if user_is_banned(user_id) and user_id not in admin_ids:
        bot.reply_to(message, "🚫 **Account Suspended.** Only Customer Support is available.", reply_markup=banned_keyboard(), parse_mode="Markdown")
        return
    chat_id = message.chat.id
    doc = message.document

    if user_id not in admin_ids and user_id != OWNER_ID:
        if (
            user_id not in user_subscriptions
            or user_subscriptions[user_id]["expiry"] <= datetime.now()
        ):
            bot.reply_to(
                message,
                "❌ **You do not have an active plan. Please purchase a plan to upload files.**",
                parse_mode="Markdown",
            )
            return

    file_name = os.path.basename(doc.file_name or "uploaded_file")
    file_ext = os.path.splitext(file_name)[1].lower()
    if file_ext not in [".py", ".js", ".zip"]:
        bot.reply_to(
            message,
            "⚠️ **Only `.py`, `.js`, and `.zip` files are supported!**",
            parse_mode="Markdown",
        )
        return

    try:
        # Enforce the plan's file limit before downloading the file.
        current_count = get_user_file_count(user_id)
        file_limit = get_user_file_limit(user_id)
        if user_id not in admin_ids and user_id != OWNER_ID and current_count >= file_limit:
            bot.reply_to(
                message,
                f"❌ **Your file limit has been reached.**\n\n📁 Usage: `{current_count}/{file_limit}`\n💳 To get a new or higher plan, press press **View Plans**.",
                parse_mode="Markdown",
            )
            return

        download_wait_msg = bot.reply_to(
            message,
            f"⏳ **Downloading `{file_name}`...**",
            parse_mode="Markdown",
        )
        file_info_tg_doc = bot.get_file(doc.file_id)
        downloaded_file_content = bot.download_file(file_info_tg_doc.file_path)

        is_safe, reason = scan_file_for_malware(downloaded_file_content, file_name, user_id)
        if not is_safe:
            bot.edit_message_text(
                f"🚨 **Security Alert:** {reason}",
                chat_id,
                download_wait_msg.message_id,
                parse_mode="Markdown",
            )
            return

        user_folder = get_user_folder(user_id)
        file_path = os.path.join(user_folder, file_name)
        with open(file_path, "wb") as f:
            f.write(downloaded_file_content)

        bot.edit_message_text(
            f"✅ **File `{file_name}` uploaded successfully!**",
            chat_id,
            download_wait_msg.message_id,
            parse_mode="Markdown",
        )

        if file_ext == ".js":
            save_user_file(user_id, file_name, "js")
            threading.Thread(
                target=run_js_script,
                args=(file_path, user_id, user_folder, file_name, message),
                daemon=True,
            ).start()
        elif file_ext == ".py":
            save_user_file(user_id, file_name, "py")
            threading.Thread(
                target=run_script,
                args=(file_path, user_id, user_folder, file_name, message),
                daemon=True,
            ).start()
        elif file_ext == ".zip":
            # Keep the ZIP in the user's file list and extract only regular files.
            save_user_file(user_id, file_name, "zip")
            extract_dir = os.path.join(user_folder, os.path.splitext(file_name)[0])
            os.makedirs(extract_dir, exist_ok=True)
            safe_extract_zip(file_path, extract_dir, user_id)

            # Prefer a root-level main.py / bot.py / index.js when present.
            candidates = [
                os.path.join(extract_dir, "main.py"),
                os.path.join(extract_dir, "bot.py"),
                os.path.join(extract_dir, "index.js"),
            ]
            entry = next((x for x in candidates if os.path.isfile(x)), None)
            if entry:
                entry_name = os.path.basename(entry)
                if entry.lower().endswith(".js"):
                    threading.Thread(
                        target=run_js_script,
                        args=(entry, user_id, extract_dir, entry_name, message),
                        daemon=True,
                    ).start()
                else:
                    threading.Thread(
                        target=run_script,
                        args=(entry, user_id, extract_dir, entry_name, message),
                        daemon=True,
                    ).start()
            else:
                bot.reply_to(
                    message,
                    "📦 **ZIP uploaded successfully.**\n⚠️ `main.py`, `bot.py` or `index.js` was not found, so auto-start was skipped.",
                    parse_mode="Markdown",
                )

    except Exception as e:
        bot.reply_to(message, f"❌ **Error:** {str(e)}")



# --- Admin helper / step handlers ---
def process_add_admin(message):
    if message.from_user.id not in admin_ids:
        return
    try:
        new_id = int((message.text or '').strip())
        admin_ids.add(new_id)
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            conn.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (new_id,))
            conn.commit(); conn.close()
        bot.reply_to(message, f"✅ Admin added: `{new_id}`", parse_mode="Markdown")
    except Exception:
        bot.reply_to(message, "❌ Please enter a valid Telegram User ID.")


def process_remove_admin(message):
    if message.from_user.id not in admin_ids:
        return
    try:
        remove_id = int((message.text or '').strip())
        if remove_id in (OWNER_ID, ADMIN_ID):
            bot.reply_to(message, "❌ The Primary Owner/Admin cannot be removed from this panel.")
            return
        admin_ids.discard(remove_id)
        with DB_LOCK:
            conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
            conn.execute("DELETE FROM admins WHERE user_id = ?", (remove_id,))
            conn.commit(); conn.close()
        bot.reply_to(message, f"✅ Admin removed: `{remove_id}`", parse_mode="Markdown")
    except Exception:
        bot.reply_to(message, "❌ Please enter a valid Telegram User ID.")


def process_remove_subscription(message):
    if message.from_user.id not in admin_ids:
        return
    try:
        target_id = int((message.text or '').strip())
        remove_subscription_db(target_id)
        bot.reply_to(message, f"✅ Subscription removed for `{target_id}`", parse_mode="Markdown")
        try:
            bot.send_message(target_id, "⚠️ Your hosting subscription has been removed by an Admin.")
        except Exception:
            pass
    except Exception:
        bot.reply_to(message, "❌ Please enter a valid Telegram User ID.")


def process_broadcast(message):
    if message.from_user.id not in admin_ids:
        return
    text = (message.text or '').strip()
    if not text:
        bot.reply_to(message, "❌ Broadcast message cannot be empty.")
        return
    sent = failed = 0
    for uid in list(active_users):
        try:
            bot.send_message(uid, f"📢 **Admin Announcement**\n\n{text}", parse_mode="Markdown")
            sent += 1
        except Exception:
            failed += 1
    bot.reply_to(message, f"📣 Broadcast complete.\n\n✅ Sent: `{sent}`\n❌ Failed: `{failed}`", parse_mode="Markdown")


def send_bot_stats(chat_id):
    running = sum(1 for uid in list(active_users) for fn, _ in user_files.get(uid, []) if is_bot_running(uid, fn))
    total_files = sum(len(v) for v in user_files.values())
    active_subs = sum(1 for sub in user_subscriptions.values() if sub.get('expiry') and sub['expiry'] > datetime.now())
    bot.send_message(
        chat_id,
        f"📊 **Bot Statistics**\n\n👥 Active Users: `{len(active_users)}`\n💎 Active Subscriptions: `{active_subs}`\n📁 Total Files: `{total_files}`\n🟢 Running Scripts: `{running}`\n🛡️ Admins: `{len(admin_ids)}`",
        parse_mode="Markdown",
    )


def run_all_user_scripts(chat_id):
    started = 0
    for uid, files in list(user_files.items()):
        for fname, ftype in list(files):
            if ftype not in ('py', 'js'):
                continue
            if is_bot_running(uid, fname):
                continue
            path = os.path.join(get_user_folder(uid), fname)
            if not os.path.isfile(path):
                continue
            try:
                if ftype == 'js':
                    threading.Thread(target=run_js_script, args=(path, uid, get_user_folder(uid), fname, None), daemon=True).start()
                else:
                    threading.Thread(target=run_script, args=(path, uid, get_user_folder(uid), fname, None), daemon=True).start()
                started += 1
            except Exception:
                pass
    bot.send_message(chat_id, f"⚙️ **Run All Complete**\n🚀 Started: `{started}`", parse_mode="Markdown")


# --- Callback Routing ---
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    if enhanced_callback_router(call):
        return
    user_id = call.from_user.id
    data = call.data
    if user_id not in admin_ids and user_is_banned(user_id):
        bot.answer_callback_query(call.id, "Account suspended. Customer Support only.", show_alert=True)
        return

    if data == "view_plans_cb":
        bot.answer_callback_query(call.id)
        _logic_view_plans(call)

    elif data == "confirm_plan_upload":
        bot.answer_callback_query(call.id, "✅ Plan Verified!")
        bot.send_message(
            call.message.chat.id,
            "🚀 **Now send your Python (.py), JS (.js), or ZIP (.zip) file in a message.**",
            parse_mode="Markdown",
        )

    # --- Interactive Module Installer Handler ---
    elif data.startswith("instmod_"):
        _, owner_id, mod_name, fname = data.split("_", 3)
        if user_id != int(owner_id) and user_id not in admin_ids:
            bot.answer_callback_query(
                call.id,
                "❌ You cannot customize another user's file!",
                show_alert=True,
            )
            return

        bot.answer_callback_query(call.id)
        pkg_name = TELEGRAM_MODULES.get(mod_name.lower(), mod_name)
        ext = os.path.splitext(fname)[1].lower()

        status_msg = bot.send_message(
            call.message.chat.id,
            f"⏳ **`{pkg_name}` module is being installed...**",
            parse_mode="Markdown",
        )

        def do_pip_install():
            if ext == ".js":
                cmd = ["npm", "install", "--ignore-scripts", "--no-audit", "--no-fund", pkg_name]
            else:
                try:
                    py = user_python_executable(int(owner_id))
                except Exception as exc:
                    bot.edit_message_text(
                        f"❌ **Could not prepare the user environment:** `{exc}`",
                        call.message.chat.id, status_msg.message_id, parse_mode="Markdown"
                    )
                    return
                cmd = [py, "-m", "pip", "install", "--disable-pip-version-check", pkg_name]

            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0:
                bot.edit_message_text(
                    f"✅ **`{pkg_name}` module was installed successfully!**\n\n📦 Package installation is complete.\n▶️ **Start the bot manually when you are ready.**",
                    call.message.chat.id,
                    status_msg.message_id,
                    parse_mode="Markdown",
                )
                return
            else:
                bot.edit_message_text(
                    f"❌ **Installation failed!**\n\n```\n{res.stderr[:300]}\n```",
                    call.message.chat.id,
                    status_msg.message_id,
                    parse_mode="Markdown",
                )

        threading.Thread(target=do_pip_install).start()

    # --- Error Log Viewer Handler ---
    elif data.startswith("viewlog_"):
        _, owner_id, fname = data.split("_", 2)
        ufolder = get_user_folder(int(owner_id))
        log_fpath = os.path.join(
            ufolder, f"{os.path.splitext(fname)[0]}.log"
        )
        if os.path.exists(log_fpath):
            with open(log_fpath, "r", encoding="utf-8", errors="ignore") as f:
                logs = f.read()[-2000:]
            bot.send_message(
                call.message.chat.id,
                f"📜 **Error Log for `{fname}`:**\n\n```\n{logs if logs else 'No logs recorded.'}\n```",
                parse_mode="Markdown",
            )
        else:
            bot.answer_callback_query(
                call.id, "No log file found!", show_alert=True
            )

    # --- Free plan activation (no payment required) ---
    elif data.startswith("activate_free_"):
        try:
            plan_id = int(data.split("_")[2])
        except (ValueError, IndexError):
            bot.answer_callback_query(call.id, "Invalid plan.", show_alert=True)
            return
        ok, result = _activate_free_plan(user_id, plan_id)
        bot.answer_callback_query(call.id, "Activated!" if ok else result, show_alert=not ok)
        if ok:
            plan = get_plan_by_id(plan_id)
            bot.send_message(call.message.chat.id, f"🎁 **Free plan activated!**\n\n📦 Plan: `{plan[1]}`\n📁 File Limit: `{plan[2]}`\n💻 Terminal: `{'ON' if get_plan_terminal_enabled(plan_id) else 'OFF'}`\n⏱️ Duration: `{plan[4]} Days`\n\n✅ No payment is required. You can upload your bot now.", reply_markup=create_reply_keyboard_main_menu(user_id), parse_mode="Markdown")

    # --- Bangladesh Manual Payment Handlers ---
    elif data.startswith("buy_manual_"):
        plan_id = int(data.split("_")[2])
        plan = get_plan_by_id(plan_id)
        if not plan:
            bot.answer_callback_query(call.id, "Plan not found!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        _, name, limit, price, duration, _ = plan
        if is_free_price(price):
            ok, result = _activate_free_plan(user_id, plan_id)
            bot.answer_callback_query(call.id, "Activated!" if ok else result, show_alert=not ok)
            if ok:
                bot.send_message(call.message.chat.id, f"🎁 **Free plan activated!**\n\n📦 Plan: `{name}`\n📁 File Limit: `{limit}`\n💻 Terminal: `{'ON' if get_plan_terminal_enabled(plan_id) else 'OFF'}`\n⏱️ Duration: `{duration} Days`\n\n✅ No payment required.", reply_markup=create_reply_keyboard_main_menu(user_id), parse_mode="Markdown")
            return
        amount_bdt, formatted_price = get_manual_payment_amount(price)
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("🟢 FAM", callback_data=f"paymethod_FAM_{plan_id}"),
            types.InlineKeyboardButton("🟠 Nagad", callback_data=f"paymethod_nagad_{plan_id}"),
            types.InlineKeyboardButton("🔵 Upay", callback_data=f"paymethod_upay_{plan_id}"),
        )
        bot.send_message(
            call.message.chat.id,
            f"💳 **Manual Payment**\n\n📦 **Plan:** `{name}`\n💰 **Amount:** `{amount_bdt:.2f} BDT`\n⏱️ **Duration:** `{duration} Days`\n\n👇 **Select your preferred payment method:**",
            reply_markup=markup, parse_mode="Markdown",
        )

    elif data.startswith("paymethod_"):
        parts = data.split("_")
        method, plan_id = parts[1], int(parts[2])
        plan = get_plan_by_id(plan_id)
        if not plan:
            bot.answer_callback_query(call.id, "Plan not found!", show_alert=True)
            return
        _, name, limit, price, duration, _ = plan
        amount_bdt, _ = get_manual_payment_amount(price)
        payment_number = get_payment_number(method)
        bot.answer_callback_query(call.id)
        method_name = payment_method_label(method)
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📤 Submit TxID", callback_data=f"submit_manual_{method}_{plan_id}"))
        bot.send_message(
            call.message.chat.id,
            f"{method_name} **Payment Instructions**\n\n📦 **Plan:** `{name}`\n💰 **Amount:** `{amount_bdt:.2f} BDT`\n📱 **Payment Number:** `{payment_number}`\n\n1️⃣ Send exactly `{amount_bdt:.2f} BDT` via Send Money.\n2️⃣ After payment succeeds, copy the Transaction ID (TxID).\n3️⃣ Press the **Submit TxID** button below.\n\n⚠️ **Your subscription will not become active until the Admin verifies the payment.**",
            reply_markup=markup, parse_mode="Markdown",
        )

    elif data.startswith("submit_manual_"):
        parts = data.split("_")
        method, plan_id = parts[2], int(parts[3])
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "📩 **Enter your Transaction ID / TxID:**", parse_mode="Markdown")
        bot.register_next_step_handler(msg, lambda m: process_manual_payment(m, plan_id, method))

    # --- Admin Callbacks ---
    elif data == "add_plan_init" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            call.message.chat.id,
            "📝 **Enter Plan Details in format:**\n`Name | FileLimit | Price | DurationInDays | Terminal | BuyLink`\n\n`Terminal: 1 = ON, 0 = OFF`\n\n*Paid example:* `Basic | 5 | 500 BDT | 30 | 1 | https://t.me/shiyam744`\n*Free example:* `Free | 2 | FREE | 30 | 0 | -`\n\nIf Terminal is `1`, the **💻 Terminal** button will automatically appear for users of that plan.",
            parse_mode="Markdown",
        )
        bot.register_next_step_handler(msg, process_add_plan)

    elif data == "manage_plans" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        plans = get_all_plans()
        if not plans:
            bot.send_message(call.message.chat.id, "No plans found.")
            return
        markup = types.InlineKeyboardMarkup()
        for p in plans:
            markup.add(
                types.InlineKeyboardButton(
                    f"🗑️ Delete {p[1]}", callback_data=f"del_plan_{p[0]}"
                )
            )
        bot.send_message(
            call.message.chat.id,
            "🗑️ **Select a Plan to Delete:**",
            reply_markup=markup,
        )

    elif data.startswith("del_plan_") and user_id in admin_ids:
        pid = int(data.split("_")[2])
        delete_plan_db(pid)
        bot.answer_callback_query(call.id, "Plan Deleted!")
        bot.send_message(call.message.chat.id, "✅ Plan successfully deleted.")

    elif data == "add_subscription" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            call.message.chat.id,
            "💎 **Enter User ID, Plan Name & Days:**\nFormat: `UserID PlanName Days`\n*Example:* `123456789 VIP 30`",
            parse_mode="Markdown",
        )
        bot.register_next_step_handler(msg, process_add_subscription)

    elif data == "payment_settings" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        markup = types.InlineKeyboardMarkup(row_width=1)
        for _m in ("FAM", "nagad", "upay"):
            markup.add(types.InlineKeyboardButton(
                f"{payment_method_label(_m)}: {get_payment_number(_m)}",
                callback_data=f"setpay_{_m}",
            ))
        bot.send_message(call.message.chat.id, "💳 **Payment Settings**\n\nPress a button below to change the payment number:", reply_markup=markup, parse_mode="Markdown")

    elif data.startswith("setpay_") and user_id in admin_ids:
        method = data.split("_")[1]
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, f"📱 **{payment_method_label(method)} Enter the payment number:**\nExample: `01712345678`", parse_mode="Markdown")
        bot.register_next_step_handler(msg, lambda m: process_payment_number(m, method))

    elif data == "payment_requests" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        send_payment_requests(call.message.chat.id)

    elif data.startswith("approve_pay_") and user_id in admin_ids:
        request_id = int(data.split("_")[2])
        approve_payment_request(call, request_id)

    elif data.startswith("cancel_pay_") and user_id in admin_ids:
        request_id = int(data.split("_")[2])
        cancel_payment_request(call, request_id)

    elif data == "add_admin" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "👑 Enter the Telegram User ID of the new Admin:")
        bot.register_next_step_handler(msg, process_add_admin)

    elif data == "remove_admin" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "➖ Enter the Telegram User ID of the Admin you want to remove:")
        bot.register_next_step_handler(msg, process_remove_admin)

    elif data == "remove_subscription" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "❌ Enter the Telegram User ID of the user whose subscription you want to remove:")
        bot.register_next_step_handler(msg, process_remove_subscription)

    elif data == "broadcast" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "📣 Enter the broadcast message:")
        bot.register_next_step_handler(msg, process_broadcast)

    elif data == "stats" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        send_bot_stats(call.message.chat.id)

    elif data == "run_all_scripts" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        run_all_user_scripts(call.message.chat.id)

    elif data == "toggle_lock" and user_id in admin_ids:
        global bot_locked
        bot_locked = not bot_locked
        bot.answer_callback_query(call.id, f"Bot Locked: {bot_locked}")
        bot.send_message(
            call.message.chat.id,
            f"🔐 **Bot status changed to:** `{'Locked' if bot_locked else 'Unlocked'}`",
            parse_mode="Markdown",
        )

    # --- File Management Callbacks ---
    elif data.startswith("file_"):
        _, owner_id, fname = data.split("_", 2)
        owner_id = int(owner_id)
        if user_id != owner_id and user_id not in admin_ids:
            bot.answer_callback_query(call.id, "❌ Access denied.", show_alert=True)
            return
        if fname not in [x[0] for x in user_files.get(owner_id, [])]:
            bot.answer_callback_query(call.id, "❌ File not found.", show_alert=True)
            return
        is_running = is_bot_running(owner_id, fname)
        markup = types.InlineKeyboardMarkup(row_width=2)
        if is_running:
            markup.add(types.InlineKeyboardButton("🛑 Stop", callback_data=f"stop_{owner_id}_{fname}"))
        else:
            markup.add(types.InlineKeyboardButton("▶️ Start", callback_data=f"start_{owner_id}_{fname}"))
        if user_id in admin_ids:
            markup.add(types.InlineKeyboardButton("☁️ Backup to Telegram", callback_data=f"backup_now_{owner_id}_{fname}"))
        markup.add(types.InlineKeyboardButton("🗑️ Delete", callback_data=f"del_{owner_id}_{fname}"))
        bot.answer_callback_query(call.id)
        bot.send_message(
            call.message.chat.id,
            f"📄 **File:** `{fname}`\n🚦 Status: `{'Running' if is_running else 'Stopped'}`",
            reply_markup=markup,
            parse_mode="Markdown",
        )

    elif data.startswith("start_"):
        _, owner_id, fname = data.split("_", 2)
        owner_id = int(owner_id)
        if user_id != owner_id and user_id not in admin_ids:
            bot.answer_callback_query(call.id, "❌ Access denied.", show_alert=True)
            return
        path = os.path.join(get_user_folder(owner_id), fname)
        if not os.path.isfile(path):
            bot.answer_callback_query(call.id, "❌ File not found.", show_alert=True)
            return
        if is_bot_running(owner_id, fname):
            bot.answer_callback_query(call.id, "Already running.")
            return
        ftype = next((ft for fn, ft in user_files.get(owner_id, []) if fn == fname), None)
        if ftype == 'js':
            threading.Thread(target=run_js_script, args=(path, owner_id, get_user_folder(owner_id), fname, call.message), daemon=True).start()
        elif ftype == 'py':
            threading.Thread(target=run_script, args=(path, owner_id, get_user_folder(owner_id), fname, call.message), daemon=True).start()
        else:
            bot.answer_callback_query(call.id, "ZIP file cannot be started directly.", show_alert=True)
            return
        bot.answer_callback_query(call.id, "▶️ Started!")

    elif data.startswith("stop_"):
        _, owner_id, fname = data.split("_", 2)
        owner_id = int(owner_id)
        if user_id != owner_id and user_id not in admin_ids:
            bot.answer_callback_query(call.id, "❌ Access denied.", show_alert=True)
            return
        skey = f"{owner_id}_{fname}"
        if skey in bot_scripts:
            kill_process_tree(bot_scripts[skey])
            del bot_scripts[skey]
        bot.answer_callback_query(call.id, "Stopped!")
        bot.send_message(call.message.chat.id, f"🛑 Script `{fname}` stopped.", parse_mode="Markdown")

    elif data.startswith("del_"):
        _, owner_id, fname = data.split("_", 2)
        owner_id = int(owner_id)
        if user_id != owner_id and user_id not in admin_ids:
            bot.answer_callback_query(call.id, "❌ Access denied.", show_alert=True)
            return
        skey = f"{owner_id}_{fname}"
        if skey in bot_scripts:
            kill_process_tree(bot_scripts[skey])
            del bot_scripts[skey]
        remove_user_file_db(owner_id, fname)
        fpath = os.path.join(get_user_folder(owner_id), fname)
        if os.path.exists(fpath):
            os.remove(fpath)
        bot.answer_callback_query(call.id, "Deleted!")
        bot.send_message(call.message.chat.id, f"🗑️ File `{fname}` deleted.", parse_mode="Markdown")

# --- Step Handlers ---
def get_manual_payment_amount(price_str):
    clean = str(price_str).upper().strip()
    nums = re.findall(r"[-+]?\d*\.\d+|\d+", clean)
    val = float(nums[0]) if nums else 0.0
    if "USDT" in clean or "$" in clean or "USD" in clean:
        bdt = round(val * USDT_BDT_RATE, 2)
        return bdt, f"{val} USDT (~{bdt:.2f} BDT)"
    return round(val, 2), str(price_str)


def payment_method_label(method):
    return {"FAM": "🟢 FAM", "nagad": "🟠 Nagad", "upay": "🔵 Upay"}.get(method, method.title())


def get_payment_number(method):
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT number FROM payment_settings WHERE method=?", (method,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else DEFAULT_PAYMENT_NUMBERS.get(method, "Not Set")


def set_payment_number(method, number):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO payment_settings (method, number) VALUES (?, ?)", (method, number))
        conn.commit(); conn.close()


def process_payment_number(message, method):
    number = message.text.strip()
    if not re.fullmatch(r"(?:01[3-9]\d{8}|\+8801[3-9]\d{8})", number):
        bot.reply_to(message, "❌ Please enter a valid 11-digit Bangladesh phone number.")
        return
    set_payment_number(method, number)
    bot.reply_to(message, f"✅ **{payment_method_label(method)} number updated:** `{number}`", parse_mode="Markdown")


def process_manual_payment(message, plan_id, method):
    tx_id = message.text.strip()
    user_id = message.from_user.id
    if len(tx_id) < 4 or len(tx_id) > 100:
        bot.reply_to(message, "❌ Please enter a valid Transaction ID.")
        return
    plan = get_plan_by_id(plan_id)
    if not plan:
        bot.reply_to(message, "❌ Plan not found!")
        return
    _, name, limit, price, duration, _ = plan
    amount_bdt, _ = get_manual_payment_amount(price)
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT request_id FROM payment_requests WHERE tx_id=?", (tx_id,))
    if c.fetchone():
        conn.close()
        bot.reply_to(message, "❌ This Transaction ID has already been submitted.")
        return
    now = datetime.now().isoformat(timespec="seconds")
    c.execute("INSERT INTO payment_requests (user_id,user_name,plan_id,plan_name,method,amount,tx_id,status,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
              (user_id, message.from_user.first_name or "User", plan_id, name, method, amount_bdt, tx_id, "pending", now))
    request_id = c.lastrowid
    conn.commit(); conn.close()
    bot.reply_to(message, f"⏳ **Payment Request #{request_id} has been submitted.**\n\n💳 Method: `{payment_method_label(method)}`\n📦 Plan: `{name}`\n💰 Amount: `{amount_bdt:.2f} BDT`\n🧾 TxID: `{tx_id}`\n\nYour subscription will become active after Admin payment verification.", parse_mode="Markdown")
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_pay_{request_id}"),
               types.InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_pay_{request_id}"))
    admin_text = (
        f"🔔 **New Manual Payment Request #{request_id}**\n\n"
        f"👤 User: `{user_id}` ({message.from_user.first_name or 'User'})\n"
        f"📦 Plan: `{name}`\n"
        f"💳 Method: `{payment_method_label(method)}`\n"
        f"💰 Amount: `{amount_bdt:.2f} BDT`\n"
        f"🧾 TxID: `{tx_id}`\n"
        f"🕒 Time: `{now}`"
    )
    for admin_id in list(admin_ids):
        try:
            bot.send_message(admin_id, admin_text, reply_markup=markup, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Could not notify admin {admin_id}: {e}")


def get_payment_request(request_id):
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT request_id,user_id,user_name,plan_id,plan_name,method,amount,tx_id,status,created_at FROM payment_requests WHERE request_id=?", (request_id,))
    row = c.fetchone(); conn.close(); return row


def send_payment_requests(chat_id):
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM payment_requests WHERE status='pending'")
    pending = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM payment_requests WHERE status='approved'")
    approved = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM payment_requests WHERE status='cancelled'")
    cancelled = c.fetchone()[0]
    c.execute("SELECT request_id,user_id,plan_name,method,amount,tx_id,created_at FROM payment_requests WHERE status='pending' ORDER BY request_id DESC LIMIT 20")
    rows = c.fetchall(); conn.close()
    bot.send_message(chat_id, f"📥 **Payment Requests**\n\n⏳ Pending: `{pending}`\n✅ Approved: `{approved}`\n❌ Cancelled: `{cancelled}`")
    for rid, uid, pname, method, amount, tx, created in rows:
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_pay_{rid}"), types.InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_pay_{rid}"))
        bot.send_message(chat_id, f"🧾 **Request #{rid}**\n👤 User: `{uid}`\n📦 Plan: `{pname}`\n💳 Method: `{payment_method_label(method)}`\n💰 Amount: `{amount:.2f} BDT`\n🧾 TxID: `{tx}`\n🕒 `{created}`", reply_markup=markup, parse_mode="Markdown")


def update_payment_request_status(request_id, status, reviewer_id):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("UPDATE payment_requests SET status=?, reviewed_at=?, reviewed_by=? WHERE request_id=? AND status='pending'", (status, datetime.now().isoformat(timespec="seconds"), reviewer_id, request_id))
        changed = c.rowcount
        conn.commit(); conn.close()
        return changed == 1


def approve_payment_request(call, request_id):
    row = get_payment_request(request_id)
    if not row or row[8] != "pending":
        bot.answer_callback_query(call.id, "Request already processed.", show_alert=True); return
    _, uid, uname, plan_id, pname, method, amount, tx_id, status, created = row
    plan = get_plan_by_id(plan_id)
    if not plan:
        bot.answer_callback_query(call.id, "Plan no longer exists.", show_alert=True); return
    duration = plan[4]
    if not update_payment_request_status(request_id, "approved", call.from_user.id):
        bot.answer_callback_query(call.id, "Request already processed.", show_alert=True); return
    expiry = datetime.now() + timedelta(days=duration)
    save_subscription(uid, pname, expiry)
    bot.answer_callback_query(call.id, "Approved!")
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.send_message(call.message.chat.id, f"✅ **Payment #{request_id} Approved**\nUser `{uid}` for `{pname}` has been activated.", parse_mode="Markdown")
    bot.send_message(uid, f"🎉 **Payment Approved!**\n\n💎 Plan: `{pname}`\n💰 Amount: `{amount:.2f} BDT`\n💳 Method: `{payment_method_label(method)}`\n🧾 TxID: `{tx_id}`\n📅 Expiry: `{expiry.strftime('%Y-%m-%d %H:%M')}`\n\n🚀 Your subscription is now active.", reply_markup=create_reply_keyboard_main_menu(uid), parse_mode="Markdown")


def cancel_payment_request(call, request_id):
    row = get_payment_request(request_id)
    if not row or row[8] != "pending":
        bot.answer_callback_query(call.id, "Request already processed.", show_alert=True); return
    _, uid, uname, plan_id, pname, method, amount, tx_id, status, created = row
    if not update_payment_request_status(request_id, "cancelled", call.from_user.id):
        bot.answer_callback_query(call.id, "Request already processed.", show_alert=True); return
    bot.answer_callback_query(call.id, "Cancelled!")
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.send_message(call.message.chat.id, f"❌ **Payment #{request_id} Cancelled**", parse_mode="Markdown")
    bot.send_message(uid, f"❌ **Payment Request Cancelled**\n\n📦 Plan: `{pname}`\n💳 Method: `{payment_method_label(method)}`\n🧾 TxID: `{tx_id}`\n\nThe Admin did not approve your payment request. Submit a new TxID with a valid payment if needed.", parse_mode="Markdown")


def process_add_plan(message):
    try:
        parts = [p.strip() for p in (message.text or "").split("|")]
        if len(parts) == 5:
            # Backward-compatible format: Terminal defaults to OFF.
            name, limit, price, duration, buy_link = parts
            terminal_raw = "0"
        elif len(parts) == 6:
            name, limit, price, duration, terminal_raw, buy_link = parts
        else:
            raise ValueError("Use: Name | FileLimit | Price | DurationInDays | Terminal(1/0) | BuyLink")

        limit = int(limit)
        duration = int(duration)
        if not name or limit < 0 or duration <= 0:
            raise ValueError("Invalid plan name, file limit, or duration.")
        terminal_key = terminal_raw.strip().upper().replace("=", "")
        terminal_enabled = terminal_key in {"1", "ON", "YES", "TRUE"}
        if terminal_key not in {"0", "1", "ON", "OFF", "YES", "NO", "TRUE", "FALSE"}:
            raise ValueError("Terminal must be 1/0 or ON/OFF.")
        add_plan_db(name, limit, price, duration, buy_link, terminal_enabled)
        bot.reply_to(
            message,
            f"✅ **Plan `{name}` added successfully!**\n\n📁 File Limit: `{limit}`\n💻 Terminal: `{'ON' if terminal_enabled else 'OFF'}`\n⏱️ Duration: `{duration} Days`\n💰 Price: `{'FREE' if is_free_price(price) else price}`",
            parse_mode="Markdown",
        )
    except Exception as e:
        bot.reply_to(message, f"❌ Invalid Format! `{e}`", parse_mode="Markdown")


def process_add_subscription(message):
    try:
        parts = message.text.split()
        sub_uid, pname, days = int(parts[0]), parts[1], int(parts[2])
        exp = datetime.now() + timedelta(days=days)
        save_subscription(sub_uid, pname, exp)
        bot.reply_to(
            message,
            f"✅ **Subscription active for User `{sub_uid}` under Plan `{pname}` for {days} days!**",
            parse_mode="Markdown",
        )
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {e}")



# --- Telegram Backup System ---
BACKUP_ROOT = os.path.join(BASE_DIR, "backups")
os.makedirs(BACKUP_ROOT, exist_ok=True)
BACKUP_MAX_BYTES = 45 * 1024 * 1024
_backup_state = {}
_backup_lock = threading.Lock()


def _safe_file_path(user_id, file_name):
    """Return a validated path inside the user's hosting directory."""
    safe_name = os.path.basename(str(file_name))
    if not safe_name or safe_name in {".", ".."} or safe_name != str(file_name):
        return None
    base = os.path.realpath(get_user_folder(int(user_id)))
    target = os.path.realpath(os.path.join(base, safe_name))
    if target != base and not target.startswith(base + os.sep):
        return None
    return target


def _backup_dir(user_id):
    path = os.path.join(BACKUP_ROOT, str(int(user_id)))
    os.makedirs(path, exist_ok=True)
    return path


def _make_backup_copy(user_id, file_name):
    """Create a timestamped local backup copy and return its path."""
    source = _safe_file_path(user_id, file_name)
    if not source or not os.path.isfile(source):
        return None, "File not found."
    size = os.path.getsize(source)
    if size > BACKUP_MAX_BYTES:
        return None, "File is too large for Telegram backup."

    target_dir = _backup_dir(user_id)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = os.path.basename(file_name)
    target = os.path.join(target_dir, f"{stamp}_{safe_name}")
    shutil.copy2(source, target)
    return target, None


def _send_backup_to_telegram(user_id, file_name, chat_id=None, automatic=False):
    backup_path, error = _make_backup_copy(user_id, file_name)
    if error:
        return False, error

    destination = int(chat_id or user_id)
    try:
        with open(backup_path, "rb") as handle:
            caption = (
                f"🗄️ **Automatic Backup**\nFile: `{os.path.basename(file_name)}`\n"
                f"Time: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
                if automatic
                else
                f"🗄️ **Backup**\nFile: `{os.path.basename(file_name)}`\n"
                f"Time: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`"
            )
            bot.send_document(destination, handle, caption=caption, parse_mode="Markdown")
        return True, backup_path
    except Exception as exc:
        logger.exception("Telegram backup failed for %s/%s", user_id, file_name)
        return False, str(exc)


def send_user_backups(message):
    """Show backup files to administrators only."""
    user_id = message.from_user.id
    if user_id not in admin_ids:
        bot.reply_to(message, "Admin access required.")
        return
    backup_dir = _backup_dir(user_id)
    files = [
        name for name in os.listdir(backup_dir)
        if os.path.isfile(os.path.join(backup_dir, name))
    ]
    files.sort(reverse=True)

    if not files:
        bot.reply_to(
            message,
            "🗄️ **Backups**\n\nNo backup files are available yet.\n\n"
            "Open **Manage Files**, select a file and use **Backup to Telegram**.",
            parse_mode="Markdown",
        )
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    for name in files[:50]:
        markup.add(types.InlineKeyboardButton(
            f"📦 {name[:48]}",
            callback_data=f"backup_get_{user_id}_{name}",
        ))
    bot.reply_to(
        message,
        f"🗄️ **Backups**\n\nAvailable backups: `{len(files)}`",
        reply_markup=markup,
        parse_mode="Markdown",
    )


def _automatic_backup_worker():
    """Check hosted files every 60 seconds and backup only changed files."""
    while True:
        try:
            for uid, entries in list(user_files.items()):
                try:
                    uid = int(uid)
                except Exception:
                    continue
                if user_is_banned(uid) and uid not in admin_ids:
                    continue
                for file_name, _ in list(entries):
                    path = _safe_file_path(uid, file_name)
                    if not path or not os.path.isfile(path):
                        continue
                    try:
                        stat = os.stat(path)
                        signature = (stat.st_mtime_ns, stat.st_size)
                        key = f"{uid}:{file_name}"
                        with _backup_lock:
                            previous = _backup_state.get(key)
                            _backup_state[key] = signature
                        # Do not send an initial backup immediately after restart.
                        if previous is None or previous == signature:
                            continue
                        for admin_chat_id in list(admin_ids):
                            _send_backup_to_telegram(uid, file_name, admin_chat_id, automatic=True)
                    except Exception:
                        logger.exception("Automatic backup check failed for %s/%s", uid, file_name)
        except Exception:
            logger.exception("Automatic backup worker failed")
        time.sleep(60)


# Main menu entry for the backup manager.

# --- Text Handler Mapping ---
BUTTON_MAPPING = {
    "✨ 𝗨𝗽𝗱𝗮𝘁𝗲𝘀 𝗖𝗵𝗮𝗻𝗻𝗲𝗹 ✨": lambda m: bot.reply_to(
        m, f"📢 **Join channel:** {UPDATE_CHANNEL}"
    ),
    "🚀 𝗨𝗽𝗹𝗼𝗮𝗱 𝗙𝗶𝗹𝗲": _logic_upload_file,
    "🚀 𝗨𝗽𝗹𝗼𝗮d 𝗙𝗶𝗹𝗲": _logic_upload_file,
    "📁 𝗠𝗮𝗻𝗮𝗴𝗲 𝗙𝗶𝗹𝗲𝘀": _logic_check_files,
    "💳 𝗩𝗶𝗲𝘄 𝗣𝗹𝗮𝗻𝘀": _logic_view_plans,
    "⚡ 𝗦𝗽𝗲𝗲𝗱 & 𝗣𝗶𝗻𝗴": real_speed_ping,
    "📊 𝗕𝗼𝘁 𝗦𝘁𝗮𝘁𝘀": lambda m: bot.reply_to(
        m, f"📊 **Active Users:** `{len(active_users)}`"
    ),
    "🛡️ 𝗔𝗱𝗺𝗶𝗻 𝗣𝗮𝗻𝗲𝗹": lambda m: bot.reply_to(
        m,
        "🛡️ **𝗔𝗱𝗺𝗶𝗻 𝗖𝗼𝗻𝘁𝗿𝗼𝗹 𝗣𝗮𝗻𝗲𝗹:**",
        reply_markup=create_admin_panel_inline(),
        parse_mode="Markdown",
    ),
}


@bot.message_handler(func=lambda m: m.text in BUTTON_MAPPING)
def handle_main_buttons(message):
    # Banned users may access Customer Support only.
    if message.from_user.id not in admin_ids and user_is_banned(message.from_user.id):
        if message.text == "🆘 Customer Support":
            BUTTON_MAPPING[message.text](message)
        else:
            bot.send_message(message.chat.id, "🚫 Account suspended. Only Customer Support is available.", reply_markup=banned_keyboard())
        return
    BUTTON_MAPPING[message.text](message)


@bot.message_handler(commands=["start"])
def start_cmd(message):
    _logic_send_welcome(message)


# --- Enhanced User / API / Ban / Support System ---
import secrets
from flask import request, jsonify

API_PREFIX = "/api/v1"
API_KEY_PREFIX = "bth_"


def enhanced_db(query, params=(), fetch=False, one=False):
    with DB_LOCK:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(query, params)
        result = cur.fetchone() if one else (cur.fetchall() if fetch else None)
        conn.commit()
        conn.close()
        return result


def ensure_enhanced_db():
    enhanced_db("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        chat_id INTEGER,
        username TEXT,
        first_name TEXT,
        joined_at TEXT,
        last_active TEXT
    )""")
    enhanced_db("""CREATE TABLE IF NOT EXISTS bans (
        user_id INTEGER PRIMARY KEY,
        expires_at TEXT,
        reason TEXT,
        banned_by INTEGER,
        created_at TEXT
    )""")
    enhanced_db("""CREATE TABLE IF NOT EXISTS activity_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, actor_id INTEGER, action TEXT, details TEXT, created_at TEXT
    )""")
    enhanced_db("""CREATE TABLE IF NOT EXISTS api_keys (
        user_id INTEGER PRIMARY KEY,
        key_hash TEXT UNIQUE,
        key_prefix TEXT,
        created_at TEXT,
        last_used TEXT,
        active INTEGER DEFAULT 1
    )""")
    enhanced_db("""CREATE TABLE IF NOT EXISTS support_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        admin_id INTEGER,
        direction TEXT,
        message TEXT,
        created_at TEXT
    )""")
    enhanced_db("""CREATE TABLE IF NOT EXISTS bot_configs (
        user_id INTEGER,
        file_name TEXT,
        bot_token TEXT,
        chat_id TEXT,
        auto_reply TEXT,
        PRIMARY KEY(user_id, file_name)
    )""")


def record_user(message):
    u = message.from_user
    now = datetime.now().isoformat()
    existing = enhanced_db("SELECT joined_at FROM users WHERE user_id=?", (u.id,), one=True)
    joined = existing["joined_at"] if existing else now
    enhanced_db("""INSERT OR REPLACE INTO users
        (user_id, chat_id, username, first_name, joined_at, last_active)
        VALUES (?, ?, ?, ?, ?, ?)""",
        (u.id, message.chat.id, u.username or "", u.first_name or "", joined, now))


def get_ban_info(user_id):
    row = enhanced_db("SELECT * FROM bans WHERE user_id=?", (user_id,), one=True)
    if not row:
        return None
    expires = row["expires_at"]
    if expires:
        try:
            if datetime.fromisoformat(expires) <= datetime.now():
                enhanced_db("DELETE FROM bans WHERE user_id=?", (user_id,))
                return None
        except ValueError:
            pass
    return dict(row)


def user_is_banned(user_id):
    return get_ban_info(user_id) is not None


def stop_all_user_bots(user_id):
    for key, info in list(bot_scripts.items()):
        if info.get("script_owner_id") == user_id:
            kill_process_tree(info)
            bot_scripts.pop(key, None)


def apply_ban(user_id, days, reason, admin_id):
    if user_id in (OWNER_ID,):
        return False, "The owner cannot be banned."
    expires = None if days == 0 else (datetime.now() + timedelta(days=days)).isoformat()
    enhanced_db("""INSERT OR REPLACE INTO bans
        (user_id, expires_at, reason, banned_by, created_at)
        VALUES (?, ?, ?, ?, ?)""",
        (user_id, expires, reason or "No reason provided", admin_id, datetime.now().isoformat()))
    stop_all_user_bots(user_id)
    return True, "User banned successfully."


def remove_ban(user_id):
    enhanced_db("DELETE FROM bans WHERE user_id=?", (user_id,))


def banned_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    markup.add(types.KeyboardButton("🆘 Customer Support"))
    return markup


def profile_text(user_id):
    row = enhanced_db("SELECT * FROM users WHERE user_id=?", (user_id,), one=True)
    sub = user_subscriptions.get(user_id)
    ban = get_ban_info(user_id)
    api = enhanced_db("SELECT key_prefix FROM api_keys WHERE user_id=? AND active=1", (user_id,), one=True)
    running = sum(1 for fn, _ in user_files.get(user_id, []) if is_bot_running(user_id, fn))
    username = "@" + row["username"] if row and row["username"] else "Not set"
    expiry = sub["expiry"].strftime("%Y-%m-%d %H:%M") if sub else "None"
    return (
        "👤 **User Profile**\n\n"
        f"🆔 **Telegram User ID:** `{user_id}`\n"
        f"💬 **Chat ID:** `{row['chat_id'] if row else 'Not recorded'}`\n"
        f"👨 **Name:** `{row['first_name'] if row else 'Unknown'}`\n"
        f"🔗 **Username:** `{username}`\n"
        f"📅 **Joined:** `{row['joined_at'][:19] if row else 'Unknown'}`\n"
        f"🟢 **Last Active:** `{row['last_active'][:19] if row else 'Unknown'}`\n"
        f"📁 **Files:** `{get_user_file_count(user_id)}`\n"
        f"🚀 **Running Bots:** `{running}`\n"
        f"💎 **Subscription:** `{expiry}`\n"
        f"🔑 **API Key:** `{api['key_prefix'] if api else 'Not created'}`\n"
        f"🚫 **Account Status:** `{'Banned' if ban else 'Active'}`"
    )


def create_api_key(user_id):
    raw = API_KEY_PREFIX + secrets.token_urlsafe(32)
    digest = hashlib.sha256(raw.encode()).hexdigest()
    prefix = raw[:12]
    enhanced_db("INSERT OR REPLACE INTO api_keys (user_id, key_hash, key_prefix, created_at, last_used, active) VALUES (?, ?, ?, ?, NULL, 1)",
        (user_id, digest, prefix, datetime.now().isoformat()))
    return raw


def authenticate_api():
    raw = request.headers.get("X-API-Key", "").strip()
    if not raw:
        return None
    digest = hashlib.sha256(raw.encode()).hexdigest()
    row = enhanced_db("SELECT * FROM api_keys WHERE key_hash=? AND active=1", (digest,), one=True)
    if not row:
        return None
    user_id = int(row["user_id"])
    if user_is_banned(user_id):
        return None
    enhanced_db("UPDATE api_keys SET last_used=? WHERE user_id=?", (datetime.now().isoformat(), user_id))
    return user_id


def api_bots_for(user_id):
    result = []
    for file_name, file_type in user_files.get(user_id, []):
        running = is_bot_running(user_id, file_name)
        info = bot_scripts.get(f"{user_id}_{file_name}", {})
        result.append({
            "file": file_name,
            "type": file_type,
            "status": "running" if running else "stopped",
            "pid": info.get("process").pid if running and info.get("process") else None,
        })
    return result


def api_control_bot(user_id, file_name, action):
    file_name = os.path.basename(file_name or "")
    if not file_name or file_name != os.path.basename(file_name):
        return False, "Invalid file name."
    if file_name not in [x[0] for x in user_files.get(user_id, [])]:
        return False, "File not found."
    key = f"{user_id}_{file_name}"
    if action in ("stop", "restart") and key in bot_scripts:
        kill_process_tree(bot_scripts[key])
        bot_scripts.pop(key, None)
    if action == "stop":
        return True, "Bot stopped."
    if action in ("start", "restart"):
        file_type = next(ft for fn, ft in user_files[user_id] if fn == file_name)
        if file_type not in ("py", "js"):
            return False, "Only Python and JavaScript files can be started."
        path = os.path.join(get_user_folder(user_id), file_name)
        runner = run_js_script if file_type == "js" else run_script
        threading.Thread(target=runner, args=(path, user_id, get_user_folder(user_id), file_name, None), daemon=True).start()
        return True, "Bot started."
    return False, "Unsupported action."


def send_user_list(chat_id):
    rows = enhanced_db("SELECT user_id, username, first_name, last_active FROM users ORDER BY last_active DESC LIMIT 50", fetch=True)
    if not rows:
        bot.send_message(chat_id, "No users have interacted with the bot yet.")
        return
    markup = types.InlineKeyboardMarkup(row_width=1)
    for row in rows:
        name = row["first_name"] or "User"
        suffix = " @" + row["username"] if row["username"] else ""
        markup.add(types.InlineKeyboardButton(f"{name} | {row['user_id']}{suffix}"[:64], callback_data=f"um_view_{row['user_id']}"))
    bot.send_message(chat_id, "👥 **User Management**\n\nSelect a user:", reply_markup=markup, parse_mode="Markdown")



def send_admin_profile(chat_id, user_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("🚫 Ban User", callback_data=f"um_ban_{user_id}"),
               types.InlineKeyboardButton("♻️ Unban User", callback_data=f"um_unban_{user_id}"))
    markup.add(types.InlineKeyboardButton("📁 User Files", callback_data=f"um_files_{user_id}"),
               types.InlineKeyboardButton("🚀 Running Bots", callback_data=f"um_bots_{user_id}"))
    markup.add(types.InlineKeyboardButton("🔑 Create API Key", callback_data=f"um_api_{user_id}"))
    bot.send_message(chat_id, profile_text(user_id), reply_markup=markup, parse_mode="Markdown")


def process_ban_request(message, target_user_id, admin_id):
    try:
        parts = [x.strip() for x in (message.text or "").split("|", 1)]
        days = int(parts[0])
        if days < 0:
            raise ValueError
        reason = parts[1] if len(parts) > 1 else "No reason provided"
        ok, result = apply_ban(target_user_id, days, reason, admin_id)
        bot.reply_to(message, ("✅ " + result) if ok else ("❌ " + result))
        if ok:
            try:
                expiry = "Permanent" if days == 0 else f"{days} day(s)"
                bot.send_message(target_user_id,
                    f"🚫 **Account Suspended**\n\nReason: `{reason}`\nDuration: `{expiry}`\n\nOnly Customer Support is available.",
                    reply_markup=banned_keyboard(), parse_mode="Markdown")
            except Exception:
                pass
    except Exception:
        bot.reply_to(message, "❌ Invalid format. Use: `days | reason` (use `0` for permanent).", parse_mode="Markdown")


def process_support_message(message):
    user_id = message.from_user.id
    text = (message.text or "").strip()
    if not text:
        return
    enhanced_db("INSERT INTO support_messages(user_id, admin_id, direction, message, created_at) VALUES(?,?,?,?,?)",
                (user_id, None, "user_to_admin", text, datetime.now().isoformat()))
    for admin_id in list(admin_ids):
        try:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("↩️ Reply", callback_data=f"support_reply_{user_id}"))
            bot.send_message(admin_id,
                f"🆘 **Customer Support**\n\n👤 User ID: `{user_id}`\n💬 Message:\n{text}",
                reply_markup=markup, parse_mode="Markdown")
        except Exception:
            pass
    bot.send_message(message.chat.id, "✅ Your support message has been sent to an admin.")


def process_support_reply(message, target_user_id, admin_id):
    text = (message.text or "").strip()
    if not text:
        return
    enhanced_db("INSERT INTO support_messages(user_id, admin_id, direction, message, created_at) VALUES(?,?,?,?,?)",
                (target_user_id, admin_id, "admin_to_user", text, datetime.now().isoformat()))
    try:
        bot.send_message(target_user_id, f"🆘 **Support Reply**\n\n{text}", parse_mode="Markdown")
        bot.reply_to(message, "✅ Reply sent.")
    except Exception as exc:
        bot.reply_to(message, f"❌ Could not send reply: {exc}")


def get_bot_config(user_id, file_name):
    row = enhanced_db("SELECT * FROM bot_configs WHERE user_id=? AND file_name=?", (user_id, file_name), one=True)
    return dict(row) if row else {"bot_token": "", "chat_id": "", "auto_reply": ""}


def bot_runtime_env(user_id, file_name):
    """Build a minimal runtime environment so hosted code does not inherit host secrets."""
    user_folder = get_user_folder(user_id)
    env = {
        "PATH": os.environ.get("PATH", ""),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
        "HOME": user_folder,
        "TMPDIR": os.path.join(user_folder, ".tmp"),
        # Deliberately do not inherit BOT_TOKEN or other host secrets.
    }
    os.makedirs(env["TMPDIR"], exist_ok=True)
    cfg = get_bot_config(user_id, file_name)
    if cfg.get("bot_token"): env["BOT_TOKEN"] = cfg["bot_token"]
    if cfg.get("chat_id"): env["CHAT_ID"] = cfg["chat_id"]
    if cfg.get("auto_reply"): env["AUTO_REPLY"] = cfg["auto_reply"]
    return env


def enhanced_callback_router(call):
    user_id = call.from_user.id
    data = call.data or ""
    if data.startswith("backup_now_"):
        try:
            _, _, owner_text, file_name = data.split("_", 3)
            owner_id = int(owner_text)
        except (ValueError, TypeError):
            bot.answer_callback_query(call.id, "Invalid backup request.", show_alert=True)
            return True
        if user_id not in admin_ids:
            bot.answer_callback_query(call.id, "Admin access required.", show_alert=True)
            return True
        ok, result = _send_backup_to_telegram(owner_id, file_name, user_id, automatic=False)
        bot.answer_callback_query(call.id, "Backup sent." if ok else "Backup failed.", show_alert=not ok)
        if not ok:
            bot.send_message(call.message.chat.id, f"❌ Backup failed: {result}")
        return True
    if data.startswith("backup_get_"):
        parts = data.split("_", 3)
        if len(parts) != 4:
            bot.answer_callback_query(call.id, "Invalid backup request.", show_alert=True)
            return True
        try:
            owner_id = int(parts[2])
        except ValueError:
            bot.answer_callback_query(call.id, "Invalid user ID.", show_alert=True)
            return True
        backup_name = os.path.basename(parts[3])
        if user_id not in admin_ids:
            bot.answer_callback_query(call.id, "Admin access required.", show_alert=True)
            return True
        target = os.path.realpath(os.path.join(_backup_dir(owner_id), backup_name))
        base = os.path.realpath(_backup_dir(owner_id))
        if not target.startswith(base + os.sep) or not os.path.isfile(target):
            bot.answer_callback_query(call.id, "Backup not found.", show_alert=True)
            return True
        try:
            with open(target, "rb") as handle:
                bot.send_document(call.message.chat.id, handle, caption=f"🗄️ Backup: `{backup_name}`", parse_mode="Markdown")
            bot.answer_callback_query(call.id, "Backup sent.")
        except Exception:
            logger.exception("Backup download failed")
            bot.answer_callback_query(call.id, "Failed to send backup.", show_alert=True)
        return True
    if data == "server_monitor" and user_id in admin_ids:
        bot.answer_callback_query(call.id); send_server_monitor(call.message.chat.id); return True
    if data == "activity_logs" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        rows=enhanced_db("SELECT user_id, actor_id, action, details, created_at FROM activity_logs ORDER BY id DESC LIMIT 30",fetch=True)
        text="📜 **Recent Activity Logs**\n\n"+(("\n\n".join(f"`{r['created_at']}` | User `{r['user_id']}` | `{r['action']}`\n{r['details'][:180]}" for r in rows)) if rows else "No activity recorded yet.")
        bot.send_message(call.message.chat.id,text,parse_mode="Markdown"); return True
    if data == "user_management" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("👥 User List", callback_data="user_list"))
        bot.send_message(call.message.chat.id, "👥 **User Management**", reply_markup=markup, parse_mode="Markdown")
        return True
    if data == "user_list" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        send_user_list(call.message.chat.id)
        return True
    if data.startswith("um_view_") and user_id in admin_ids:
        target = int(data.split("_", 2)[2])
        bot.answer_callback_query(call.id)
        send_admin_profile(call.message.chat.id, target)
        return True
    if data.startswith("um_files_") and user_id in admin_ids:
        target = int(data.split("_", 2)[2])
        bot.answer_callback_query(call.id)
        items = user_files.get(target, [])
        if not items:
            bot.send_message(call.message.chat.id, f"📁 No files for user `{target}`.", parse_mode="Markdown")
        else:
            markup = types.InlineKeyboardMarkup(row_width=1)
            for name, kind in items:
                markup.add(types.InlineKeyboardButton(f"{name} ({kind})", callback_data=f"file_{target}_{name}"))
            bot.send_message(call.message.chat.id, f"📁 **Files for User `{target}`**", reply_markup=markup, parse_mode="Markdown")
        return True
    if data.startswith("um_bots_") and user_id in admin_ids:
        target = int(data.split("_", 2)[2])
        bot.answer_callback_query(call.id)
        running = [name for name, _ in user_files.get(target, []) if is_bot_running(target, name)]
        text = "\n".join(f"• `{x}`" for x in running) if running else "No running bots."
        bot.send_message(call.message.chat.id, f"🚀 **Running Bots for `{target}`**\n\n{text}", parse_mode="Markdown")
        return True
    if data.startswith("um_api_") and user_id in admin_ids:
        target = int(data.split("_", 2)[2])
        key = create_api_key(target)
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id,
            f"🔑 **API Key Created**\n\nUser ID: `{target}`\nAPI Key: `{key}`\n\nAPI Base: `{API_PREFIX}`\n\nSave the full key now. It is stored hashed and cannot be recovered later.",
            parse_mode="Markdown")
        return True
    if data.startswith("um_ban_") and user_id in admin_ids:
        target = int(data.split("_", 2)[2])
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id,
            f"Enter ban duration and reason for `{target}`. Format: `days | reason`\nUse `0 | reason` for a permanent ban.", parse_mode="Markdown")
        bot.register_next_step_handler(msg, lambda m: process_ban_request(m, target, user_id))
        return True
    if data.startswith("um_unban_") and user_id in admin_ids:
        target = int(data.split("_", 2)[2])
        remove_ban(target)
        bot.answer_callback_query(call.id, "User unbanned")
        bot.send_message(call.message.chat.id, f"✅ User `{target}` has been unbanned.", parse_mode="Markdown")
        return True
    if data.startswith("support_reply_") and user_id in admin_ids:
        target = int(data.split("_", 2)[2])
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, f"Reply to User `{target}`:", parse_mode="Markdown")
        bot.register_next_step_handler(msg, lambda m: process_support_reply(m, target, user_id))
        return True
    if data == "support_inbox" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        rows = enhanced_db("SELECT user_id, message, created_at FROM support_messages WHERE direction='user_to_admin' ORDER BY id DESC LIMIT 20", fetch=True)
        if not rows:
            bot.send_message(call.message.chat.id, "🆘 **Support Inbox**\n\nNo support messages.", parse_mode="Markdown")
        else:
            bot.send_message(call.message.chat.id, "🆘 **Support Inbox**\n\n" + "\n".join(f"• `{r['user_id']}` — {r['message'][:120]}" for r in rows), parse_mode="Markdown")
        return True
    if data == "api_management" and user_id in admin_ids:
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "Enter Telegram User ID to create or regenerate an API key:")
        bot.register_next_step_handler(msg, lambda m: process_api_user_id(m))
        return True
    return False


def process_api_user_id(message):
    if message.from_user.id not in admin_ids:
        return
    try:
        target = int((message.text or "").strip())
        key = create_api_key(target)
        bot.reply_to(message,
            f"🔑 **API Key Created**\n\nUser ID: `{target}`\nAPI Key: `{key}`\nAPI Base: `{API_PREFIX}`\n\nSave the full key now. It is stored hashed and cannot be recovered later.",
            parse_mode="Markdown")
    except ValueError:
        bot.reply_to(message, "❌ Invalid Telegram User ID.")



@app.before_request
def api_preflight():
    if request.method == "OPTIONS" and request.path.startswith(API_PREFIX):
        return ("", 204)

@app.get(API_PREFIX)
def enhanced_api_home():
    return jsonify({"service": "Bot Hosting API", "version": "1.0", "base": API_PREFIX})


@app.get(API_PREFIX + "/profile")
def enhanced_api_profile():
    user_id = authenticate_api()
    if not user_id:
        return jsonify({"error": "Invalid or inactive API key"}), 401
    row = enhanced_db("SELECT * FROM users WHERE user_id=?", (user_id,), one=True)
    return jsonify({
        "user_id": user_id,
        "chat_id": row["chat_id"] if row else None,
        "username": row["username"] if row else None,
        "files": get_user_file_count(user_id),
        "running_bots": sum(1 for fn, _ in user_files.get(user_id, []) if is_bot_running(user_id, fn)),
    })


@app.get(API_PREFIX + "/bots")
def enhanced_api_bots():
    user_id = authenticate_api()
    if not user_id:
        return jsonify({"error": "Invalid or inactive API key"}), 401
    return jsonify({"bots": api_bots_for(user_id)})


def _api_file_allowed(user_id, file_name):
    file_name = os.path.basename(file_name or "")
    if not file_name or file_name != os.path.basename(file_name):
        return False, "Invalid file name."
    ext = os.path.splitext(file_name)[1].lower()
    if ext not in (".py", ".js", ".zip"):
        return False, "Only .py, .js and .zip files are supported."
    if user_id not in admin_ids and user_id != OWNER_ID:
        sub = user_subscriptions.get(user_id)
        if not sub or sub["expiry"] <= datetime.now():
            return False, "Active hosting plan required."
        limit = get_user_file_limit(user_id)
        if get_user_file_count(user_id) >= limit:
            return False, f"File limit reached ({limit})."
    return True, "OK"


def _api_store_file(user_id, file_name, content):
    ok, reason = scan_file_for_malware(content, file_name, user_id)
    if not ok:
        return False, reason
    folder = get_user_folder(user_id)
    path = os.path.join(folder, file_name)
    with open(path, "wb") as handle:
        handle.write(content)
    ext = os.path.splitext(file_name)[1].lower()
    save_user_file(user_id, file_name, ext[1:])
    if ext == ".zip":
        extract_dir = os.path.join(folder, os.path.splitext(file_name)[0])
        os.makedirs(extract_dir, exist_ok=True)
        safe_extract_zip(path, extract_dir)
    return True, "File uploaded successfully."


@app.post(API_PREFIX + "/files/upload")
@app.post(API_PREFIX + "/files/import")
def enhanced_api_upload():
    user_id = authenticate_api()
    if not user_id:
        return jsonify({"error": "Invalid or inactive API key"}), 401
    incoming = request.files.get("file")
    if incoming is None or not incoming.filename:
        return jsonify({"error": "multipart/form-data field 'file' is required"}), 400
    file_name = os.path.basename(incoming.filename)
    ok, reason = _api_file_allowed(user_id, file_name)
    if not ok:
        return jsonify({"success": False, "error": reason}), 400
    content = incoming.read()
    if len(content) > 25 * 1024 * 1024:
        return jsonify({"success": False, "error": "Maximum upload size is 25 MB."}), 413
    try:
        ok, reason = _api_store_file(user_id, file_name, content)
        if not ok:
            return jsonify({"success": False, "error": reason}), 400
        record_activity(user_id, "API_UPLOAD", file_name)
        return jsonify({"success": True, "file": file_name, "message": reason})
    except zipfile.BadZipFile:
        return jsonify({"success": False, "error": "Invalid ZIP file."}), 400
    except Exception as exc:
        logger.exception("API upload failed")
        return jsonify({"success": False, "error": str(exc)}), 500


@app.get(API_PREFIX + "/files")
def enhanced_api_files():
    user_id = authenticate_api()
    if not user_id:
        return jsonify({"error": "Invalid or inactive API key"}), 401
    return jsonify({"files": [{"file": n, "type": t, "running": is_bot_running(user_id, n)} for n, t in user_files.get(user_id, [])]})


@app.delete(API_PREFIX + "/files/delete")
def enhanced_api_delete_file():
    user_id = authenticate_api()
    if not user_id:
        return jsonify({"error": "Invalid or inactive API key"}), 401
    payload = request.get_json(silent=True) or {}
    file_name = os.path.basename(str(payload.get("file", "")))
    if not file_name or file_name != os.path.basename(str(payload.get("file", ""))):
        return jsonify({"error": "Invalid file name"}), 400
    if file_name not in [n for n, _ in user_files.get(user_id, [])]:
        return jsonify({"error": "File not found"}), 404
    key = f"{user_id}_{file_name}"
    if key in bot_scripts:
        kill_process_tree(bot_scripts[key])
        bot_scripts.pop(key, None)
    folder = get_user_folder(user_id)
    path = os.path.join(folder, file_name)
    if os.path.isfile(path):
        os.remove(path)
    stem = os.path.splitext(file_name)[0]
    extracted = os.path.join(folder, stem)
    if os.path.isdir(extracted):
        shutil.rmtree(extracted, ignore_errors=True)
    user_files[user_id] = [(n, t) for n, t in user_files.get(user_id, []) if n != file_name]
    enhanced_db("DELETE FROM user_files WHERE user_id=? AND file_name=?", (user_id, file_name))
    record_activity(user_id, "API_DELETE", file_name)
    return jsonify({"success": True, "message": "File deleted."})


# --- Restricted Bot Terminal -------------------------------------------------
# The terminal is intentionally NOT a general-purpose shell.  Commands are
# parsed with shlex and executed without shell=True, always inside the user's
# own bot directory.  Package installation remains available because bot
# dependencies commonly require it.
TERMINAL_TIMEOUT = 45
TERMINAL_MAX_OUTPUT = 12000
TERMINAL_DENY_NAMES = {
    "sudo", "su", "doas", "bash", "sh", "zsh", "fish", "dash", "ash",
    "powershell", "pwsh", "cmd", "cmd.exe", "curl", "wget", "nc", "ncat",
    "netcat", "telnet", "ssh", "scp", "sftp", "ftp", "apt", "apt-get",
    "apk", "yum", "dnf", "pacman", "systemctl", "service", "mount",
    "umount", "chmod", "chown", "chgrp", "dd", "mkfs", "fdisk", "kill",
    "pkill", "killall", "reboot", "shutdown", "iptables", "ufw", "crontab",
    "docker", "podman", "git", "gcc", "g++", "make", "cmake"
}
TERMINAL_ALLOWED = {"pwd", "ls", "dir", "find", "cat", "head", "tail", "grep",
                    "python", "python3", "pip", "pip3", "node", "npm", "npm3"}
PACKAGE_NAME_RE = re.compile(r"^[A-Za-z0-9_.@+\-/\[\],=<>!~]{1,160}$")


def _safe_user_path(user_id, supplied):
    """Resolve a path while guaranteeing it remains inside the user's folder."""
    root = os.path.realpath(get_user_folder(int(user_id)))
    raw = str(supplied or ".").strip() or "."
    if os.path.isabs(raw):
        candidate = os.path.realpath(raw)
    else:
        candidate = os.path.realpath(os.path.join(root, raw))
    if candidate != root and not candidate.startswith(root + os.sep):
        raise ValueError("Path is outside your bot directory.")
    return candidate


def _terminal_validate(tokens):
    if not tokens:
        raise ValueError("Enter a command.")
    # No shell operators, substitutions, redirections, pipelines or command
    # chaining. The command is always passed as an argv list to subprocess.
    forbidden_tokens = {";", "&&", "||", "|", ">", ">>", "<", "2>", "2>>", "&"}
    if any(t in forbidden_tokens for t in tokens):
        raise ValueError("Shell operators and redirection are not allowed.")
    command = os.path.basename(tokens[0]).lower()
    if command in TERMINAL_DENY_NAMES:
        raise ValueError(f"Command '{command}' is blocked for security.")
    if command not in TERMINAL_ALLOWED:
        raise ValueError(f"Command '{command}' is not allowed in the hosting terminal.")
    return command


def _validate_terminal_args(command, args, cwd):
    # Keep all file arguments inside cwd/user root. Options are deliberately
    # limited so commands cannot turn into arbitrary system queries.
    dangerous_flags = {"--exec", "--execute", "-exec", "-delete", "--delete",
                       "--help", "-h"}
    if any(a in dangerous_flags for a in args):
        raise ValueError("That terminal option is disabled.")

    if command in {"pip", "pip3"}:
        if not args:
            return
        sub = args[0].lower()
        if sub == "install":
            if len(args) < 2 or any(a.startswith("-") and a not in {"--upgrade"} for a in args[1:]):
                raise ValueError("Only normal package names (and --upgrade) are allowed for pip install.")
            for pkg in args[1:]:
                if pkg == "--upgrade":
                    continue
                if not PACKAGE_NAME_RE.fullmatch(pkg) or pkg.startswith("-") or ":" in pkg:
                    raise ValueError(f"Invalid package name: {pkg}")
        elif sub in {"list", "freeze", "show", "check"}:
            if sub == "show" and len(args) > 1:
                for pkg in args[1:]:
                    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", pkg):
                        raise ValueError("Invalid package name.")
        elif sub == "uninstall":
            if len(args) < 3 or args[1] != "-y":
                raise ValueError("Package uninstall requires: pip uninstall -y PACKAGE")
            for pkg in args[2:]:
                if not re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", pkg):
                    raise ValueError("Invalid package name.")
        else:
            raise ValueError("Allowed pip commands: install, uninstall -y, list, freeze, show, check.")

    elif command in {"npm", "npm3"}:
        if not args or args[0].lower() not in {"install", "update", "list", "ls", "outdated", "view"}:
            raise ValueError("Allowed npm commands: install, update, list, outdated, view.")
        if args[0].lower() == "install":
            for pkg in args[1:]:
                if pkg in {"--ignore-scripts", "--no-audit", "--no-fund"}:
                    continue
                if pkg.startswith("-") or not PACKAGE_NAME_RE.fullmatch(pkg) or ":" in pkg:
                    raise ValueError(f"Invalid npm package: {pkg}")

    elif command in {"python", "python3"}:
        # Version is allowed. Running a bot must use the hosting Start control,
        # so the terminal cannot create unmanaged processes.
        if args and args not in (["--version"], ["-V"]):
            raise ValueError("Use the Bot Start button to run a bot. Terminal only supports Python version check.")
    elif command == "node":
        if args and args not in (["--version"], ["-v"]):
            raise ValueError("Terminal only supports Node.js version check.")
    elif command in {"pwd", "ls", "dir"}:
        for a in args:
            if a.startswith("-") and a not in {"-l", "-la", "-a"}:
                raise ValueError("That option is disabled.")
            if not a.startswith("-"):
                _safe_user_path(current_user_for_terminal.get(), a)
    elif command in {"cat", "head", "tail", "grep", "find"}:
        # File arguments are checked below by the caller after parsing.
        if any(a in {"-exec", "-delete", "--exec", "--exclude-from"} for a in args):
            raise ValueError("That file-search option is disabled.")


def execute_restricted_terminal(user_id, command_text, cwd_rel="."):
    try:
        tokens = shlex.split(str(command_text or ""), posix=(os.name != "nt"))
    except ValueError as exc:
        return False, f"Invalid command syntax: {exc}"
    try:
        command = _terminal_validate(tokens)
        cwd = _safe_user_path(user_id, cwd_rel)
        if not os.path.isdir(cwd):
            return False, "Directory not found."

        # Validate command-specific arguments. A tiny context holder avoids
        # exposing path resolution as a public helper.
        current_user_for_terminal.set(int(user_id)) if hasattr(current_user_for_terminal, "set") else None
        _validate_terminal_args(command, tokens[1:], cwd)

        args = list(tokens)
        if command in {"pip", "pip3"}:
            py = user_python_executable(int(user_id))
            args = [py, "-m", "pip"] + tokens[1:]
            if len(tokens) > 1 and tokens[1].lower() == "install":
                args.insert(3, "--disable-pip-version-check")
        elif command == "npm":
            args = ["npm"] + tokens[1:]
            if len(tokens) > 1 and tokens[1].lower() == "install":
                args[1:1] = ["--ignore-scripts", "--no-audit", "--no-fund"]
        elif command == "npm3":
            args = ["npm"] + tokens[1:]
        elif command in {"python", "python3"}:
            args = [user_python_executable(int(user_id)), "--version"]
        elif command == "node":
            args = ["node"] + tokens[1:]
        else:
            # Validate every non-option path-like argument is inside the user root.
            for a in tokens[1:]:
                if not a.startswith("-"):
                    # grep has a pattern plus file; find has a path plus options.
                    # Any existing path must remain under the user's directory.
                    if os.path.exists(os.path.join(cwd, a)) or os.path.isabs(a) or ".." in a.split(os.sep):
                        _safe_user_path(user_id, a if os.path.isabs(a) else os.path.relpath(os.path.join(cwd, a), get_user_folder(user_id)))

        result = subprocess.run(
            args, cwd=cwd, shell=False, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=TERMINAL_TIMEOUT,
            env=bot_runtime_env(int(user_id), "terminal"),
            preexec_fn=_sandbox_preexec if os.name != "nt" else None,
        )
        output = ((result.stdout or "") + ("\n" + result.stderr if result.stderr else "")).strip()
        output = output[-TERMINAL_MAX_OUTPUT:]
        record_activity(int(user_id), "TERMINAL_CMD", command_text[:1000])
        return result.returncode == 0, output or f"Command finished with exit code {result.returncode}"
    except subprocess.TimeoutExpired:
        return False, f"Command timed out after {TERMINAL_TIMEOUT} seconds."
    except Exception as exc:
        logger.warning("Restricted terminal error for user %s: %s", user_id, exc)
        return False, str(exc)


# Lightweight context holder used only while validating terminal paths.
try:
    from contextvars import ContextVar
    current_user_for_terminal = ContextVar("current_user_for_terminal", default=None)
except Exception:
    current_user_for_terminal = None


@app.post(API_PREFIX + "/terminal")
def enhanced_api_terminal():
    user_id = authenticate_api()
    if not user_id:
        return jsonify({"error": "Invalid or inactive API key"}), 401
    if not user_terminal_enabled(user_id):
        return jsonify({"success": False, "error": "Terminal is not included in your current hosting plan."}), 403
    payload = request.get_json(silent=True) or {}
    command = str(payload.get("command", "")).strip()
    cwd = str(payload.get("cwd", ".")).strip() or "."
    if len(command) > 500:
        return jsonify({"success": False, "error": "Command is too long."}), 400
    ok, output = execute_restricted_terminal(user_id, command, cwd)
    return jsonify({"success": ok, "output": output}), (200 if ok else 400)


@app.post(API_PREFIX + "/packages/install")
def enhanced_api_install_package():
    user_id = authenticate_api()
    if not user_id:
        return jsonify({"error": "Invalid or inactive API key"}), 401
    payload = request.get_json(silent=True) or {}
    package = str(payload.get("package", "")).strip()
    file_name = os.path.basename(str(payload.get("file", "")))
    if (not package or package.startswith("-") or
            not re.fullmatch(r"[A-Za-z0-9_.@+\-/\[\],=<>!~]{1,160}", package) or
            ":" in package):
        return jsonify({"success": False, "error": "Invalid package name."}), 400
    if file_name and file_name not in [n for n, _ in user_files.get(user_id, [])]:
        return jsonify({"success": False, "error": "File not found."}), 404
    ext = os.path.splitext(file_name)[1].lower() if file_name else ".py"
    try:
        folder = get_user_folder(user_id)
        if ext == ".js":
            cmd = ["npm", "install", "--ignore-scripts", "--no-audit", "--no-fund", package]
        else:
            py = user_python_executable(user_id)
            cmd = [py, "-m", "pip", "install", "--disable-pip-version-check", package]
        result = subprocess.run(cmd, cwd=folder, capture_output=True, text=True, timeout=180)
        success = result.returncode == 0
        record_activity(user_id, "API_INSTALL", f"{package} ({ext})")
        return jsonify({"success": success, "package": package, "output": (result.stdout or result.stderr)[-6000:]}), (200 if success else 400)
    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "error": "Package installation timed out after 180 seconds."}), 408
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@app.get(API_PREFIX + "/status")
def enhanced_api_status():
    user_id = authenticate_api()
    if not user_id:
        return jsonify({"error": "Invalid or inactive API key"}), 401
    return jsonify({"status": "ok", "files": get_user_file_count(user_id), "running_bots": sum(1 for n, _ in user_files.get(user_id, []) if is_bot_running(user_id, n))})


def enhanced_api_action(action):
    user_id = authenticate_api()
    if not user_id:
        return jsonify({"error": "Invalid or inactive API key"}), 401
    payload = request.get_json(silent=True) or {}
    ok, message = api_control_bot(user_id, str(payload.get("file", "")), action)
    return jsonify({"success": ok, "message": message}), (200 if ok else 400)


@app.post(API_PREFIX + "/bots/start")
def enhanced_api_start():
    return enhanced_api_action("start")


@app.post(API_PREFIX + "/bots/stop")
def enhanced_api_stop():
    return enhanced_api_action("stop")


@app.post(API_PREFIX + "/bots/restart")
def enhanced_api_restart():
    return enhanced_api_action("restart")


@app.get(API_PREFIX + "/bots/logs")
def enhanced_api_logs():
    user_id = authenticate_api()
    if not user_id:
        return jsonify({"error": "Invalid or inactive API key"}), 401
    file_name = os.path.basename(request.args.get("file", ""))
    if file_name not in [x[0] for x in user_files.get(user_id, [])]:
        return jsonify({"error": "File not found"}), 404
    path = os.path.join(get_user_folder(user_id), f"{os.path.splitext(file_name)[0]}.log")
    if not os.path.isfile(path):
        return jsonify({"file": file_name, "logs": ""})
    with open(path, "r", encoding="utf-8", errors="ignore") as handle:
        logs = handle.read()[-12000:]
    return jsonify({"file": file_name, "logs": logs})




def start_user_terminal(message):
    user_id = message.from_user.id
    if not user_terminal_enabled(user_id):
        bot.reply_to(message, "🔒 **Terminal is not included in your current plan.**\n\n💳 Open **View Plans** to choose a plan with Terminal enabled.", parse_mode="Markdown")
        return
    prompt = bot.reply_to(
        message,
        "💻 **Terminal**",
        parse_mode="Markdown",
    )
    bot.register_next_step_handler(prompt, process_user_terminal_command)


def process_user_terminal_command(message):
    user_id = message.from_user.id
    if not user_terminal_enabled(user_id):
        bot.reply_to(message, "🔒 Terminal is not available for your current plan.")
        return

    command = (message.text or "").strip()

    # Any normal main-menu button automatically closes the active terminal
    # session first, then runs that button's normal action. This prevents a
    # button press from accidentally being interpreted as a terminal command.
    # The Terminal button itself opens a fresh terminal session.
    terminal_button = "💻 𝗧𝗲𝗿𝗺𝗶𝗻𝗮𝗹"
    if command != terminal_button and command in BUTTON_MAPPING:
        try:
            BUTTON_MAPPING[command](message)
        finally:
            return

    # start/exit/quit close only the terminal session; the hosted bot keeps
    # running normally.
    if command.lower() in {"exit", "quit", "start", "/start"}:
        bot.reply_to(message, "✅ Terminal closed. Your bot will continue running normally.")
        return

    ok, output = execute_restricted_terminal(user_id, command, ".")
    status = "✅" if ok else "❌"
    text = f"{status} **Terminal**\n\n```\n{output[:12000]}\n```"
    bot.reply_to(message, text, parse_mode="Markdown")
    bot.register_next_step_handler(message, process_user_terminal_command)



def enhanced_main_menu(user_id):
    if user_is_banned(user_id) and user_id not in admin_ids:
        return banned_keyboard()
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    base_layout = ADMIN_COMMAND_BUTTONS_LAYOUT_USER_SPEC if user_id in admin_ids else COMMAND_BUTTONS_LAYOUT_USER_SPEC
    # My Bot Monitor is intentionally removed from the user panel.
    layout = [list(row) for row in base_layout if "𝗠𝘆 𝗕𝗼𝘁 𝗠𝗼𝗻𝗶𝘁𝗼𝗿" not in " ".join(row)]
    for row in layout:
        markup.add(*[types.KeyboardButton(text) for text in row])
    if user_terminal_enabled(user_id):
        markup.add(types.KeyboardButton("💻 𝗧𝗲𝗿𝗺𝗶𝗻𝗮𝗹"))
    return markup


# Install enhancements into the original bot without replacing its existing systems.
ensure_enhanced_db()

# Extend the existing main menu mapping used by the original message handler.
BUTTON_MAPPING["👤 User Profile"] = lambda m: bot.reply_to(m, profile_text(m.from_user.id), parse_mode="Markdown")
BUTTON_MAPPING["🆘 Customer Support"] = lambda m: start_support_flow(m)
BUTTON_MAPPING["💻 𝗧𝗲𝗿𝗺𝗶𝗻𝗮𝗹"] = start_user_terminal


def start_support_flow(message):
    if not user_is_banned(message.from_user.id):
        bot.send_message(message.chat.id, "🆘 **Customer Support**\n\nSend your message to contact an admin.", parse_mode="Markdown")
    else:
        prompt = bot.send_message(message.chat.id, "🆘 **Customer Support**\n\nSend your message. An admin will receive it and can reply.", parse_mode="Markdown")
        bot.register_next_step_handler(prompt, process_support_message)


# Add enhanced admin buttons to the existing admin panel function by wrapping it.
_original_admin_panel = create_admin_panel_inline

def create_admin_panel_inline():
    markup = _original_admin_panel()
    markup.add(types.InlineKeyboardButton("👥 User Management", callback_data="user_management"),
               types.InlineKeyboardButton("🔑 API Management", callback_data="api_management"))
    markup.add(types.InlineKeyboardButton("🆘 Support Inbox", callback_data="support_inbox"))
    markup.add(types.InlineKeyboardButton("📈 Server Monitor", callback_data="server_monitor"),
               types.InlineKeyboardButton("📜 Activity Logs", callback_data="activity_logs"))
    return markup

# Record every /start and enforce the banned-user state before the original welcome flow.
_original_logic_send_welcome = _logic_send_welcome

def _logic_send_welcome(message):
    record_user(message)
    user_id = message.from_user.id
    if user_is_banned(user_id) and user_id not in admin_ids:
        ban = get_ban_info(user_id)
        expiry = ban["expires_at"] if ban and ban["expires_at"] else "Permanent"
        bot.send_message(message.chat.id,
            f"🚫 **Account Suspended**\n\nReason: `{ban['reason']}`\nExpiry: `{expiry}`\n\nOnly Customer Support is available.",
            reply_markup=banned_keyboard(), parse_mode="Markdown")
        return
    _original_logic_send_welcome(message)

# Patch the globals used by the original handlers.
globals()["create_reply_keyboard_main_menu"] = enhanced_main_menu
globals()["_logic_send_welcome"] = _logic_send_welcome


# Start the 60-second automatic backup monitor after all functions are defined.
_backup_thread = threading.Thread(target=_automatic_backup_worker, name="backup-worker", daemon=True)
_backup_thread.start()
_runtime_supervisor_thread = threading.Thread(target=_runtime_supervisor, name="runtime-supervisor", daemon=True)
_runtime_supervisor_thread.start()
_runtime_resource_thread = threading.Thread(target=_runtime_resource_monitor, name="resource-monitor", daemon=True)
_runtime_resource_thread.start()

# --- Cleanup & Start ---
def cleanup():
    for key in list(bot_scripts.keys()):
        kill_process_tree(bot_scripts[key])


atexit.register(cleanup)

if __name__ == "__main__":
    logger.info("🤖 Starting Bot with Manual Bangladesh Payment System...")
    keep_alive()
    bot.infinity_polling(timeout=60, long_polling_timeout=30)
