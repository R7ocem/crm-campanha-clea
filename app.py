from __future__ import annotations

import csv
import base64
import hashlib
import hmac
import os
import secrets
import sqlite3
import re
import unicodedata
from datetime import date, datetime, timedelta
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import json


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(os.environ.get("DB_PATH", DATA_DIR / "crm_campanha.sqlite3"))
STATIC_DIR = BASE_DIR / "static"
SESSION_COOKIE = "crm_campanha_session"
APP_ENV = os.environ.get("APP_ENV", "development").lower()
PUBLIC_APP_URL = os.environ.get("PUBLIC_APP_URL", "").rstrip("/")
SESSION_MAX_HOURS = int(os.environ.get("SESSION_MAX_HOURS", "12"))
LOGIN_RATE_LIMIT_MAX_ATTEMPTS = int(os.environ.get("LOGIN_RATE_LIMIT_MAX_ATTEMPTS", "6"))
LOGIN_RATE_LIMIT_WINDOW_MINUTES = int(os.environ.get("LOGIN_RATE_LIMIT_WINDOW_MINUTES", "15"))

REGIONS = [
    "Plano Piloto", "Gama", "Taguatinga", "Brazlandia", "Sobradinho",
    "Planaltina", "Paranoa", "Nucleo Bandeirante", "Ceilandia", "Guara",
    "Cruzeiro", "Samambaia", "Santa Maria", "Sao Sebastiao", "Recanto das Emas",
    "Lago Sul", "Riacho Fundo", "Lago Norte", "Candangolandia", "Aguas Claras",
    "Riacho Fundo II", "Sudoeste/Octogonal", "Varjao", "Park Way", "SCIA",
    "Sobradinho II", "Jardim Botanico", "Itapoa", "SIA", "Vicente Pires",
    "Fercal", "Sol Nascente/Pôr do Sol", "Arniqueira",
]

STATUSES = [
    "Novo",
    "Em acompanhamento",
    "Participante ativo",
    "Voluntario",
    "Multiplicador",
    "Inativo",
    "Nao contatar",
]

EVENT_TYPES = [
    "reuniao de condominio",
    "caminhada",
    "visita a comercio",
    "reuniao comunitaria",
    "evento",
    "panfletagem",
    "reuniao com lideranca",
    "outro",
]

SOURCES = ["Conversa presencial", "Indicacao", "Evento/Acao", "WhatsApp", "Instagram", "Facebook", "TikTok", "Condominio", "Comercio", "Lideranca", "Outro"]
PUBLIC_SOURCES = ["whatsapp", "instagram", "facebook", "tiktok", "evento", "reuniao", "condominio", "comercio", "amigo/conhecido", "lideranca comunitaria", "equipe da campanha", "outro"]
SOURCE_ALIASES = {
    "qr": "QR Code",
    "qr-code": "QR Code",
    "qrcode": "QR Code",
    "instagram": "Instagram",
    "insta": "Instagram",
    "whatsapp": "WhatsApp",
    "zap": "WhatsApp",
    "facebook": "Facebook",
    "tiktok": "TikTok",
    "evento": "Evento",
    "evento-acao": "Evento/Acao",
    "conversa-presencial": "Conversa presencial",
    "indicacao": "Indicacao",
    "amigo-conhecido": "Indicacao",
    "equipe-da-campanha": "Equipe",
    "equipe": "Equipe",
    "site": "Direto",
    "direto": "Direto",
    "outro": "Outros",
    "outros": "Outros",
}
ROLE_ORDER = {"Administrador": 4, "Coordenacao": 3, "Equipe de campo": 2, "Leitura": 1}
CONSENT_TEXT_VERSION = "public-signup-v1"
RATE_LIMIT_WINDOW_MINUTES = 10
RATE_LIMIT_MAX_ATTEMPTS = 8


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def today_iso() -> str:
    return date.today().isoformat()


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, digest = stored.split("$", 1)
    except ValueError:
        return False
    return hmac.compare_digest(hash_password(password, salt), stored)


def referral_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(6))


def normalize_brazilian_phone(phone: str) -> str | None:
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if digits.startswith("55") and len(digits) in [12, 13]:
        digits = digits[2:]
    if len(digits) not in [10, 11]:
        return None
    ddd = int(digits[:2])
    if ddd < 11 or ddd > 99:
        return None
    if len(digits) == 11 and digits[2] != "9":
        return None
    return "55" + digits


def sanitize_text(value: str, limit: int = 180) -> str:
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f<>]", "", value or "").strip()
    return cleaned[:limit]


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS regions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                slug TEXT,
                active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                event_date TEXT NOT NULL,
                event_time TEXT,
                location TEXT,
                region_id INTEGER,
                responsible_user_id INTEGER,
                team TEXT,
                notes TEXT,
                created_by INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY(region_id) REFERENCES regions(id),
                FOREIGN KEY(responsible_user_id) REFERENCES users(id),
                FOREIGN KEY(created_by) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                whatsapp TEXT,
                region_id INTEGER,
                neighborhood TEXT,
                source TEXT,
                first_contact_date TEXT,
                responsible_user_id INTEGER,
                referred_by_contact_id INTEGER,
                origin_event_id INTEGER,
                notes TEXT,
                consent INTEGER NOT NULL DEFAULT 0,
                consent_date TEXT,
                status TEXT NOT NULL DEFAULT 'Novo',
                last_contact_date TEXT,
                next_action TEXT,
                next_action_date TEXT,
                is_community_leader INTEGER NOT NULL DEFAULT 0,
                is_building_manager INTEGER NOT NULL DEFAULT 0,
                is_merchant INTEGER NOT NULL DEFAULT 0,
                is_association_rep INTEGER NOT NULL DEFAULT 0,
                is_volunteer INTEGER NOT NULL DEFAULT 0,
                is_multiplier INTEGER NOT NULL DEFAULT 0,
                acting_region TEXT,
                created_by INTEGER,
                updated_by INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(region_id) REFERENCES regions(id),
                FOREIGN KEY(responsible_user_id) REFERENCES users(id),
                FOREIGN KEY(referred_by_contact_id) REFERENCES contacts(id),
                FOREIGN KEY(origin_event_id) REFERENCES events(id),
                FOREIGN KEY(created_by) REFERENCES users(id),
                FOREIGN KEY(updated_by) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS contact_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_id INTEGER NOT NULL,
                user_id INTEGER,
                action TEXT NOT NULL,
                old_status TEXT,
                new_status TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(contact_id) REFERENCES contacts(id) ON DELETE CASCADE,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_contact_id INTEGER NOT NULL,
                referred_contact_id INTEGER NOT NULL UNIQUE,
                created_by INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY(referrer_contact_id) REFERENCES contacts(id),
                FOREIGN KEY(referred_contact_id) REFERENCES contacts(id),
                FOREIGN KEY(created_by) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS event_contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                contact_id INTEGER NOT NULL,
                created_by INTEGER,
                created_at TEXT NOT NULL,
                UNIQUE(event_id, contact_id),
                FOREIGN KEY(event_id) REFERENCES events(id) ON DELETE CASCADE,
                FOREIGN KEY(contact_id) REFERENCES contacts(id) ON DELETE CASCADE,
                FOREIGN KEY(created_by) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                metric TEXT NOT NULL,
                target INTEGER NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                created_by INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY(created_by) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                entity_type TEXT NOT NULL,
                entity_id INTEGER,
                action TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS contact_acquisitions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_id INTEGER NOT NULL,
                source TEXT,
                manual_source TEXT,
                event_id INTEGER,
                utm_source TEXT,
                utm_medium TEXT,
                utm_campaign TEXT,
                utm_content TEXT,
                utm_term TEXT,
                referral_code_used TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(contact_id) REFERENCES contacts(id) ON DELETE CASCADE,
                FOREIGN KEY(event_id) REFERENCES events(id)
            );

            CREATE TABLE IF NOT EXISTS contact_consents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_id INTEGER NOT NULL,
                consent_type TEXT NOT NULL,
                granted INTEGER NOT NULL,
                consent_text_version TEXT NOT NULL,
                ip_hash TEXT,
                user_agent TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(contact_id) REFERENCES contacts(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS public_analytics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_name TEXT NOT NULL,
                contact_id INTEGER,
                source TEXT,
                referral_code TEXT,
                ip_hash TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(contact_id) REFERENCES contacts(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS security_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_name TEXT NOT NULL,
                ip_hash TEXT,
                details TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS rate_limits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip_hash TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_contacts_phone ON contacts(phone);
            CREATE INDEX IF NOT EXISTS idx_contacts_region ON contacts(region_id);
            CREATE INDEX IF NOT EXISTS idx_contacts_status ON contacts(status);
            CREATE INDEX IF NOT EXISTS idx_contacts_created_at ON contacts(created_at);
            CREATE INDEX IF NOT EXISTS idx_contacts_responsible ON contacts(responsible_user_id);
            CREATE INDEX IF NOT EXISTS idx_contacts_referred_by ON contacts(referred_by_contact_id);
            CREATE INDEX IF NOT EXISTS idx_history_contact ON contact_history(contact_id);
            CREATE INDEX IF NOT EXISTS idx_events_region_date ON events(region_id, event_date);
            CREATE INDEX IF NOT EXISTS idx_goals_metric ON goals(metric);
            CREATE INDEX IF NOT EXISTS idx_acquisitions_contact ON contact_acquisitions(contact_id);
            CREATE INDEX IF NOT EXISTS idx_acquisitions_source ON contact_acquisitions(source);
            CREATE INDEX IF NOT EXISTS idx_analytics_event_created ON public_analytics(event_name, created_at);
            """
        )
        ensure_columns(conn)
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_contacts_referral_code ON contacts(referral_code)")
        for region in REGIONS:
            conn.execute("INSERT OR IGNORE INTO regions(name, slug, active) VALUES (?, ?, 1)", (region, slugify(region)))
            conn.execute("UPDATE regions SET slug = COALESCE(slug, ?), active = COALESCE(active, 1) WHERE name = ?", (slugify(region), region))
        admin_count = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        if admin_count == 0:
            admin_email = os.environ.get("ADMIN_EMAIL", "admin@campanha.local")
            admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
            conn.execute(
                "INSERT INTO users(name, email, role, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
                ("Administrador", admin_email, "Administrador", hash_password(admin_password), now_iso()),
            )
        backfill_referral_codes(conn)
        conn.execute("PRAGMA optimize")


def ensure_columns(conn: sqlite3.Connection) -> None:
    wanted = {
        "contacts": {
            "referral_code": "TEXT",
            "phone_verified": "INTEGER NOT NULL DEFAULT 0",
            "communication_consent": "INTEGER NOT NULL DEFAULT 0",
            "communication_consent_at": "TEXT",
            "communication_consent_source": "TEXT",
            "volunteer_interest": "INTEGER NOT NULL DEFAULT 0",
            "event_interest": "INTEGER NOT NULL DEFAULT 0",
            "mobilizer_interest": "INTEGER NOT NULL DEFAULT 0",
            "declared_support": "INTEGER NOT NULL DEFAULT 0",
            "next_action_type": "TEXT",
            "next_action_status": "TEXT NOT NULL DEFAULT 'Pendente'",
        },
        "regions": {
            "slug": "TEXT",
            "active": "INTEGER NOT NULL DEFAULT 1",
        },
        "referrals": {
            "referral_code": "TEXT",
        },
    }
    for table, columns in wanted.items():
        existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        for name, spec in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {spec}")


def backfill_referral_codes(conn: sqlite3.Connection) -> None:
    rows = conn.execute("SELECT id FROM contacts WHERE referral_code IS NULL OR referral_code = ''").fetchall()
    for row in rows:
        code = referral_code()
        while conn.execute("SELECT 1 FROM contacts WHERE referral_code = ?", (code,)).fetchone():
            code = referral_code()
        conn.execute("UPDATE contacts SET referral_code = ? WHERE id = ?", (code, row["id"]))


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row else None


def rows_to_dicts(rows) -> list[dict]:
    return [dict(row) for row in rows]


def parse_body(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    raw = handler.rfile.read(length) if length else b"{}"
    ctype = handler.headers.get("Content-Type", "")
    if "application/json" in ctype:
        return json.loads(raw.decode("utf-8") or "{}")
    return {k: v[0] for k, v in parse_qs(raw.decode("utf-8")).items()}


def normalize_phone(phone: str) -> str:
    return "".join(ch for ch in (phone or "") if ch.isdigit())


def ip_hash_for(handler: BaseHTTPRequestHandler) -> str:
    raw_ip = handler.headers.get("X-Forwarded-For", handler.client_address[0]).split(",")[0].strip()
    return hashlib.sha256((raw_ip + "|crm-campanha").encode()).hexdigest()[:32]


def public_url(handler: BaseHTTPRequestHandler, code: str) -> str:
    if PUBLIC_APP_URL:
        return f"{PUBLIC_APP_URL}/cadastro?ref={code}"
    proto = handler.headers.get("X-Forwarded-Proto", "http")
    host = handler.headers.get("Host", "127.0.0.1:8765")
    return f"{proto}://{host}/cadastro?ref={code}"


def public_base_url(handler: BaseHTTPRequestHandler) -> str:
    if PUBLIC_APP_URL:
        return PUBLIC_APP_URL
    proto = handler.headers.get("X-Forwarded-Proto", "http")
    host = handler.headers.get("Host", "127.0.0.1:8765")
    return f"{proto}://{host}"


def safe_source(value: str) -> str:
    value = slugify(value or "")
    allowed = {slugify(item): item for item in PUBLIC_SOURCES}
    return SOURCE_ALIASES.get(value) or SOURCE_ALIASES.get(slugify(allowed.get(value, value))) or (allowed.get(value, value[:40]) if value else "Direto")


class App(BaseHTTPRequestHandler):
    server_version = "CRMCampanha/1.0"

    def log_message(self, fmt, *args):
        return

    def send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path: Path, content_type: str):
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def set_session(self, token: str):
        secure = "; Secure" if APP_ENV == "production" else ""
        max_age = SESSION_MAX_HOURS * 60 * 60
        self.send_header("Set-Cookie", f"{SESSION_COOKIE}={token}; HttpOnly; SameSite=Lax; Path=/; Max-Age={max_age}{secure}")

    def clear_session(self):
        secure = "; Secure" if APP_ENV == "production" else ""
        self.send_header("Set-Cookie", f"{SESSION_COOKIE}=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0{secure}")

    def current_user(self) -> dict | None:
        jar = cookies.SimpleCookie(self.headers.get("Cookie"))
        token = jar.get(SESSION_COOKIE)
        if not token:
            return None
        with db() as conn:
            row = conn.execute(
                """
                SELECT users.id, users.name, users.email, users.role
                FROM sessions JOIN users ON users.id = sessions.user_id
                WHERE sessions.token = ? AND users.active = 1
                  AND datetime(sessions.created_at) >= datetime('now', ?)
                """,
                (token.value, f"-{SESSION_MAX_HOURS} hours"),
            ).fetchone()
        return row_to_dict(row)

    def require_user(self):
        user = self.current_user()
        if not user:
            self.send_json({"error": "Login necessario"}, 401)
            return None
        return user

    def can_write(self, user: dict) -> bool:
        return ROLE_ORDER.get(user["role"], 0) >= ROLE_ORDER["Equipe de campo"]

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ["/", "/cadastro", "/cadastro/sucesso", "/privacidade"]:
            return self.send_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
        if path.startswith("/static/"):
            static_path = (STATIC_DIR / path.removeprefix("/static/")).resolve()
            if STATIC_DIR.resolve() not in static_path.parents and static_path != STATIC_DIR.resolve():
                return self.send_error(403)
            if not static_path.exists():
                return self.send_error(404)
            suffix = static_path.suffix.lower()
            ctype = {
                ".css": "text/css; charset=utf-8",
                ".js": "application/javascript; charset=utf-8",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
            }.get(suffix, "application/octet-stream")
            return self.send_file(static_path, ctype)
        if path.startswith("/api/"):
            return self.handle_api_get(path, parse_qs(parsed.query))
        self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            return self.handle_api_post(parsed.path)
        self.send_error(404)

    def handle_api_get(self, path: str, query: dict):
        if path == "/api/public-options":
            return self.api_public_options()
        if path == "/api/referral":
            return self.api_referral(query)
        if path == "/api/me":
            return self.send_json({"user": self.current_user()})
        user = self.require_user()
        if not user:
            return
        routes = {
            "/api/bootstrap": self.api_bootstrap,
            "/api/dashboard": self.api_dashboard,
            "/api/contacts": self.api_contacts,
            "/api/events": self.api_events,
            "/api/goals": self.api_goals,
            "/api/alerts": self.api_alerts,
            "/api/daily-summary": self.api_daily_summary,
            "/api/referrals": self.api_referrals,
            "/api/origins": self.api_origins,
            "/api/regions-report": self.api_regions_report,
            "/api/reports": self.api_reports,
            "/api/export/contacts.csv": self.api_export_contacts,
        }
        if path in routes:
            return routes[path](user, query)
        if path.startswith("/api/contacts/"):
            return self.api_contact_detail(user, path.rsplit("/", 1)[-1])
        self.send_error(404)

    def handle_api_post(self, path: str):
        if path == "/api/public-signup":
            return self.api_public_signup()
        if path == "/api/public-analytics":
            return self.api_public_analytics()
        if path == "/api/login":
            return self.api_login()
        if path == "/api/logout":
            return self.api_logout()
        user = self.require_user()
        if not user:
            return
        if not self.can_write(user):
            return self.send_json({"error": "Perfil sem permissao de escrita"}, 403)
        if path == "/api/contacts":
            return self.api_save_contact(user)
        if path == "/api/events":
            return self.api_save_event(user)
        if path == "/api/goals":
            return self.api_save_goal(user)
        if path == "/api/users" and user["role"] == "Administrador":
            return self.api_save_user(user)
        self.send_error(404)

    def api_public_options(self):
        with db() as conn:
            payload = {
                "regions": rows_to_dicts(conn.execute("SELECT id, name, slug FROM regions WHERE active = 1 ORDER BY name")),
                "sources": PUBLIC_SOURCES,
            }
        self.send_json(payload)

    def api_referral(self, query):
        code = sanitize_text(query.get("ref", [""])[0], 12).upper()
        if not code:
            return self.send_json({"valid": False})
        with db() as conn:
            found = conn.execute("SELECT id FROM contacts WHERE referral_code = ?", (code,)).fetchone()
        self.send_json({"valid": bool(found)})

    def api_public_analytics(self):
        data = parse_body(self)
        event_name = sanitize_text(data.get("event_name", ""), 60)
        allowed = {
            "registration_page_view",
            "registration_started",
            "share_clicked",
            "whatsapp_share_clicked",
        }
        if event_name not in allowed:
            return self.send_json({"ok": False}, 400)
        with db() as conn:
            conn.execute(
                "INSERT INTO public_analytics(event_name, source, referral_code, ip_hash, created_at) VALUES (?, ?, ?, ?, ?)",
                (event_name, safe_source(data.get("source", "")), sanitize_text(data.get("referral_code", ""), 12).upper(), ip_hash_for(self), now_iso()),
            )
        self.send_json({"ok": True})

    def public_rate_limited(self, conn: sqlite3.Connection) -> bool:
        ip_hash = ip_hash_for(self)
        cutoff = (datetime.now() - timedelta(minutes=RATE_LIMIT_WINDOW_MINUTES)).isoformat(sep=" ")
        conn.execute("DELETE FROM rate_limits WHERE created_at < ?", (cutoff,))
        attempts = conn.execute(
            "SELECT COUNT(*) FROM rate_limits WHERE ip_hash = ? AND endpoint = 'public-signup' AND created_at >= ?",
            (ip_hash, cutoff),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO rate_limits(ip_hash, endpoint, created_at) VALUES (?, 'public-signup', ?)",
            (ip_hash, now_iso()),
        )
        if attempts >= RATE_LIMIT_MAX_ATTEMPTS:
            conn.execute(
                "INSERT INTO security_events(event_name, ip_hash, details, created_at) VALUES ('rate_limit_public_signup', ?, ?, ?)",
                (ip_hash, "excesso de tentativas no cadastro publico", now_iso()),
            )
            return True
        return False

    def login_rate_limited(self, conn: sqlite3.Connection, email: str) -> bool:
        ip_hash = ip_hash_for(self)
        cutoff = (datetime.now() - timedelta(minutes=LOGIN_RATE_LIMIT_WINDOW_MINUTES)).isoformat(sep=" ")
        conn.execute("DELETE FROM rate_limits WHERE created_at < ?", (cutoff,))
        attempts = conn.execute(
            "SELECT COUNT(*) FROM rate_limits WHERE ip_hash = ? AND endpoint = 'login' AND created_at >= ?",
            (ip_hash, cutoff),
        ).fetchone()[0]
        if attempts >= LOGIN_RATE_LIMIT_MAX_ATTEMPTS:
            conn.execute(
                "INSERT INTO security_events(event_name, ip_hash, details, created_at) VALUES ('rate_limit_login', ?, ?, ?)",
                (ip_hash, json.dumps({"email": sanitize_text(email, 120)}, ensure_ascii=False), now_iso()),
            )
            return True
        return False

    def record_login_attempt(self, conn: sqlite3.Connection, email: str, ok: bool) -> None:
        ip_hash = ip_hash_for(self)
        conn.execute(
            "INSERT INTO rate_limits(ip_hash, endpoint, created_at) VALUES (?, 'login', ?)",
            (ip_hash, now_iso()),
        )
        conn.execute(
            "INSERT INTO security_events(event_name, ip_hash, details, created_at) VALUES (?, ?, ?, ?)",
            (
                "login_success" if ok else "login_failed",
                ip_hash,
                json.dumps({"email": sanitize_text(email, 120)}, ensure_ascii=False),
                now_iso(),
            ),
        )

    def resolve_referrer(self, conn: sqlite3.Connection, code: str, phone: str) -> sqlite3.Row | None:
        code = sanitize_text(code, 12).upper()
        if not code:
            return None
        row = conn.execute("SELECT id, phone FROM contacts WHERE referral_code = ?", (code,)).fetchone()
        if not row or row["phone"] == phone:
            return None
        return row

    def resolve_event(self, conn: sqlite3.Connection, event_value: str) -> sqlite3.Row | None:
        event_value = sanitize_text(event_value, 80)
        if not event_value:
            return None
        if event_value.isdigit():
            return conn.execute("SELECT id FROM events WHERE id = ?", (event_value,)).fetchone()
        slug = slugify(event_value)
        for row in conn.execute("SELECT id, name FROM events"):
            if slugify(row["name"]) == slug:
                return row
        return None

    def api_public_signup(self):
        data = parse_body(self)
        if data.get("company"):
            with db() as conn:
                conn.execute(
                    "INSERT INTO security_events(event_name, ip_hash, details, created_at) VALUES ('honeypot_public_signup', ?, 'campo invisivel preenchido', ?)",
                    (ip_hash_for(self), now_iso()),
                )
            return self.send_json({"ok": True})

        name = sanitize_text(data.get("name", ""), 120)
        phone = normalize_brazilian_phone(data.get("phone", ""))
        if not name:
            return self.send_json({"error": "Informe seu nome."}, 400)
        if not phone:
            return self.send_json({"error": "Informe um WhatsApp valido com DDD."}, 400)
        region_id = data.get("region_id")
        if not region_id:
            return self.send_json({"error": "Selecione sua Regiao Administrativa."}, 400)

        consent = 1 if data.get("communication_consent") else 0
        wants_volunteer = 1 if data.get("volunteer_interest") else 0
        wants_events = 1 if data.get("event_interest") else 0
        wants_mobilizer = 1 if data.get("mobilizer_interest") else 0
        declared_support = 1 if data.get("declared_support") else 0
        status = "Novo"
        manual_source = safe_source(data.get("manual_source", ""))
        technical_source = safe_source(data.get("source", "") or data.get("utm_source", "") or manual_source or "direto")
        utm = {key: sanitize_text(data.get(key, ""), 120) for key in ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"]}
        ref_code = sanitize_text(data.get("ref", ""), 12).upper()
        notes = f"Auto cadastro publico. Origem tecnica: {technical_source}. Origem informada: {manual_source}."

        with db() as conn:
            if self.public_rate_limited(conn):
                return self.send_json({"error": "Muitas tentativas em pouco tempo. Tente novamente em alguns minutos."}, 429)
            region = conn.execute("SELECT id FROM regions WHERE id = ? AND active = 1", (region_id,)).fetchone()
            if not region:
                return self.send_json({"error": "Selecione sua Regiao Administrativa."}, 400)
            referrer = self.resolve_referrer(conn, ref_code, phone)
            event = self.resolve_event(conn, data.get("event", ""))
            existing = conn.execute("SELECT id, referral_code, referred_by_contact_id, status FROM contacts WHERE phone = ?", (phone,)).fetchone()
            if existing:
                contact_id = existing["id"]
                conn.execute(
                    """
                    UPDATE contacts
                    SET whatsapp = COALESCE(NULLIF(whatsapp, ''), phone),
                        region_id = COALESCE(region_id, ?),
                        neighborhood = COALESCE(NULLIF(neighborhood, ''), ?),
                        consent = CASE WHEN ? = 1 THEN 1 ELSE consent END,
                        consent_date = CASE WHEN ? = 1 AND consent_date IS NULL THEN ? ELSE consent_date END,
                        communication_consent = CASE WHEN ? = 1 THEN 1 ELSE communication_consent END,
                        communication_consent_at = CASE WHEN ? = 1 AND communication_consent_at IS NULL THEN ? ELSE communication_consent_at END,
                        communication_consent_source = CASE WHEN ? = 1 THEN 'public_signup' ELSE communication_consent_source END,
                        is_volunteer = CASE WHEN ? = 1 THEN 1 ELSE is_volunteer END,
                        volunteer_interest = CASE WHEN ? = 1 THEN 1 ELSE volunteer_interest END,
                        event_interest = CASE WHEN ? = 1 THEN 1 ELSE event_interest END,
                        mobilizer_interest = CASE WHEN ? = 1 THEN 1 ELSE mobilizer_interest END,
                        declared_support = CASE WHEN ? = 1 THEN 1 ELSE declared_support END,
                        status = status,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        data.get("region_id") or None,
                        sanitize_text(data.get("neighborhood", ""), 120),
                        consent,
                        consent,
                        now_iso(),
                        consent,
                        consent,
                        now_iso(),
                        consent,
                        wants_volunteer,
                        wants_volunteer,
                        wants_events,
                        wants_mobilizer,
                        declared_support,
                        now_iso(),
                        contact_id,
                    ),
                )
                if referrer and not existing["referred_by_contact_id"]:
                    conn.execute("UPDATE contacts SET referred_by_contact_id = ? WHERE id = ?", (referrer["id"], contact_id))
                    conn.execute(
                        "INSERT OR IGNORE INTO referrals(referrer_contact_id, referred_contact_id, referral_code, created_at) VALUES (?, ?, ?, ?)",
                        (referrer["id"], contact_id, ref_code, now_iso()),
                    )
                conn.execute(
                    "INSERT INTO contact_history(contact_id, action, old_status, new_status, notes, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (contact_id, "contact_already_existed", existing["status"], status if declared_support else existing["status"], f"new_source={technical_source}; new_interaction_at={now_iso()}", now_iso()),
                )
                code = existing["referral_code"] or referral_code()
                if not existing["referral_code"]:
                    conn.execute("UPDATE contacts SET referral_code = ? WHERE id = ?", (code, contact_id))
                duplicate = True

            else:
                code = referral_code()
                while conn.execute("SELECT 1 FROM contacts WHERE referral_code = ?", (code,)).fetchone():
                    code = referral_code()
                cur = conn.execute(
                    """
                    INSERT INTO contacts(
                        name, phone, whatsapp, region_id, neighborhood, source, first_contact_date,
                        referred_by_contact_id, origin_event_id, notes, consent, consent_date,
                        communication_consent, communication_consent_at, communication_consent_source,
                        status, is_volunteer, volunteer_interest, event_interest, mobilizer_interest, declared_support,
                        referral_code, phone_verified, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, 'auto cadastro', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                    """,
                    (
                        name,
                        phone,
                        phone,
                        region_id,
                        sanitize_text(data.get("neighborhood", ""), 120),
                        today_iso(),
                        referrer["id"] if referrer else None,
                        event["id"] if event else None,
                        notes,
                        consent,
                        today_iso() if consent else None,
                        consent,
                        now_iso() if consent else None,
                        "public_signup" if consent else None,
                        status,
                        wants_volunteer,
                        wants_volunteer,
                        wants_events,
                        wants_mobilizer,
                        declared_support,
                        code,
                        now_iso(),
                        now_iso(),
                    ),
                )
                contact_id = cur.lastrowid
                if referrer:
                    conn.execute(
                        "INSERT OR IGNORE INTO referrals(referrer_contact_id, referred_contact_id, referral_code, created_at) VALUES (?, ?, ?, ?)",
                        (referrer["id"], contact_id, ref_code, now_iso()),
                    )
                conn.execute(
                    "INSERT INTO contact_history(contact_id, action, old_status, new_status, notes, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (contact_id, "Cadastro criado pelo link publico", None, status, notes, now_iso()),
                )
                duplicate = False

            conn.execute(
                """
                INSERT INTO contact_acquisitions(
                    contact_id, source, manual_source, event_id, utm_source, utm_medium, utm_campaign,
                    utm_content, utm_term, referral_code_used, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (contact_id, technical_source, manual_source, event["id"] if event else None, utm["utm_source"], utm["utm_medium"], utm["utm_campaign"], utm["utm_content"], utm["utm_term"], ref_code or None, now_iso()),
            )
            if event:
                conn.execute(
                    "INSERT OR IGNORE INTO event_contacts(event_id, contact_id, created_by, created_at) VALUES (?, ?, NULL, ?)",
                    (event["id"], contact_id, now_iso()),
                )
            conn.execute(
                "INSERT INTO contact_consents(contact_id, consent_type, granted, consent_text_version, ip_hash, user_agent, created_at) VALUES (?, 'communication', ?, ?, ?, ?, ?)",
                (contact_id, consent, CONSENT_TEXT_VERSION, ip_hash_for(self), sanitize_text(self.headers.get("User-Agent", ""), 180), now_iso()),
            )
            conn.execute(
                "INSERT INTO activities(entity_type, entity_id, action, created_at) VALUES ('contact', ?, 'Auto cadastro publico', ?)",
                (contact_id, now_iso()),
            )
            conn.execute(
                "INSERT INTO public_analytics(event_name, contact_id, source, referral_code, ip_hash, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                ("referral_registration_completed" if referrer else "registration_completed", contact_id, technical_source, ref_code or None, ip_hash_for(self), now_iso()),
            )
        self.send_json({"ok": True, "id": contact_id, "duplicate": duplicate, "referral_code": code, "referral_link": public_url(self, code), "communication_consent": bool(consent)})

    def api_login(self):
        data = parse_body(self)
        email = sanitize_text(data.get("email", ""), 120).lower()
        with db() as conn:
            if self.login_rate_limited(conn, email):
                return self.send_json({"error": "Muitas tentativas. Aguarde alguns minutos e tente novamente."}, 429)
            user = conn.execute("SELECT * FROM users WHERE lower(email) = ? AND active = 1", (email,)).fetchone()
            if not user or not verify_password(data.get("password", ""), user["password_hash"]):
                self.record_login_attempt(conn, email, False)
                return self.send_json({"error": "Email ou senha invalidos"}, 401)
            conn.execute(
                "CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, user_id INTEGER NOT NULL, created_at TEXT NOT NULL, FOREIGN KEY(user_id) REFERENCES users(id))"
            )
            token = secrets.token_urlsafe(32)
            conn.execute("INSERT INTO sessions(token, user_id, created_at) VALUES (?, ?, ?)", (token, user["id"], now_iso()))
            self.record_login_attempt(conn, email, True)
            payload = {"user": {"id": user["id"], "name": user["name"], "email": user["email"], "role": user["role"]}}
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.set_session(token)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def api_logout(self):
        jar = cookies.SimpleCookie(self.headers.get("Cookie"))
        token = jar.get(SESSION_COOKIE)
        if token:
            with db() as conn:
                conn.execute("DELETE FROM sessions WHERE token = ?", (token.value,))
        self.send_response(204)
        self.clear_session()
        self.end_headers()

    def api_bootstrap(self, user, query):
        with db() as conn:
            payload = {
                "user": user,
                "regions": rows_to_dicts(conn.execute("SELECT * FROM regions ORDER BY name")),
                "users": rows_to_dicts(conn.execute("SELECT id, name, email, role FROM users WHERE active = 1 ORDER BY name")),
                "events": rows_to_dicts(conn.execute("SELECT id, name, event_date FROM events ORDER BY event_date DESC, id DESC LIMIT 200")),
                "statuses": STATUSES,
                "sources": SOURCES,
                "eventTypes": EVENT_TYPES,
            }
        self.send_json(payload)

    def api_contacts(self, user, query):
        filters = []
        params = []
        q = (query.get("q", [""])[0] or "").strip()
        for field, column in [("status", "c.status"), ("region", "c.region_id"), ("source", "c.source"), ("responsible", "c.responsible_user_id"), ("event", "c.origin_event_id")]:
            value = query.get(field, [""])[0]
            if value:
                filters.append(f"{column} = ?")
                params.append(value)
        if q:
            filters.append("(c.name LIKE ? OR c.phone LIKE ? OR c.neighborhood LIKE ? OR r.name LIKE ?)")
            params += [f"%{q}%", f"%{normalize_phone(q)}%", f"%{q}%", f"%{q}%"]
        if query.get("leadership", [""])[0] == "1":
            filters.append("(c.is_community_leader = 1 OR c.is_building_manager = 1 OR c.is_merchant = 1 OR c.is_association_rep = 1 OR c.is_multiplier = 1)")
        if query.get("volunteer", [""])[0] == "1":
            filters.append("(c.is_volunteer = 1 OR c.volunteer_interest = 1)")
        if query.get("event_interest", [""])[0] == "1":
            filters.append("c.event_interest = 1")
        if query.get("mobilizer", [""])[0] == "1":
            filters.append("c.mobilizer_interest = 1")
        if query.get("whatsapp_consent", [""])[0] == "1":
            filters.append("(c.communication_consent = 1 OR c.consent = 1)")
        if query.get("declared_support", [""])[0] == "1":
            filters.append("c.declared_support = 1")
        where = "WHERE " + " AND ".join(filters) if filters else ""
        with db() as conn:
            rows = conn.execute(
                f"""
                SELECT c.*, r.name AS region_name, u.name AS responsible_name,
                       e.name AS event_name,
                       (SELECT COUNT(*) FROM referrals rf WHERE rf.referrer_contact_id = c.id) AS referral_count
                FROM contacts c
                LEFT JOIN regions r ON r.id = c.region_id
                LEFT JOIN users u ON u.id = c.responsible_user_id
                LEFT JOIN events e ON e.id = c.origin_event_id
                {where}
                ORDER BY c.updated_at DESC
                LIMIT 300
                """,
                params,
            ).fetchall()
        self.send_json({"contacts": rows_to_dicts(rows)})

    def api_contact_detail(self, user, contact_id):
        with db() as conn:
            contact = conn.execute(
                """
                SELECT c.*, r.name AS region_name, u.name AS responsible_name,
                       ref.name AS referred_by_name, e.name AS event_name
                FROM contacts c
                LEFT JOIN regions r ON r.id = c.region_id
                LEFT JOIN users u ON u.id = c.responsible_user_id
                LEFT JOIN contacts ref ON ref.id = c.referred_by_contact_id
                LEFT JOIN events e ON e.id = c.origin_event_id
                WHERE c.id = ?
                """,
                (contact_id,),
            ).fetchone()
            history = conn.execute(
                """
                SELECT h.*, u.name AS user_name FROM contact_history h
                LEFT JOIN users u ON u.id = h.user_id
                WHERE h.contact_id = ? ORDER BY h.created_at DESC
                """,
                (contact_id,),
            ).fetchall()
            referrals = conn.execute("SELECT id, name, phone, status FROM contacts WHERE referred_by_contact_id = ? ORDER BY created_at DESC", (contact_id,)).fetchall()
        self.send_json({"contact": row_to_dict(contact), "history": rows_to_dicts(history), "referrals": rows_to_dicts(referrals)})

    def api_save_contact(self, user):
        data = parse_body(self)
        phone = normalize_phone(data.get("phone", ""))
        if not data.get("name") or len(phone) < 8:
            return self.send_json({"error": "Nome e telefone valido sao obrigatorios"}, 400)
        contact_id = data.get("id")
        fields = {
            "name": data.get("name", "").strip(),
            "phone": phone,
            "whatsapp": normalize_phone(data.get("whatsapp", "")) or phone,
            "region_id": data.get("region_id") or None,
            "neighborhood": data.get("neighborhood", "").strip(),
            "source": data.get("source") or "outros",
            "first_contact_date": data.get("first_contact_date") or today_iso(),
            "responsible_user_id": data.get("responsible_user_id") or user["id"],
            "referred_by_contact_id": data.get("referred_by_contact_id") or None,
            "origin_event_id": data.get("origin_event_id") or None,
            "notes": data.get("notes", "").strip(),
            "consent": 1 if data.get("communication_consent") else 0,
            "consent_date": data.get("consent_date") or (today_iso() if data.get("communication_consent") else None),
            "communication_consent": 1 if data.get("communication_consent") else 0,
            "communication_consent_at": data.get("communication_consent_at") or (now_iso() if data.get("communication_consent") else None),
            "communication_consent_source": "crm_manual" if data.get("communication_consent") else None,
            "status": data.get("status") or "Novo",
            "last_contact_date": data.get("last_contact_date") or None,
            "next_action": data.get("next_action", "").strip(),
            "next_action_date": data.get("next_action_date") or None,
            "next_action_type": data.get("next_action_type") or None,
            "next_action_status": data.get("next_action_status") or "Pendente",
            "is_community_leader": 1 if data.get("is_community_leader") else 0,
            "is_building_manager": 1 if data.get("is_building_manager") else 0,
            "is_merchant": 1 if data.get("is_merchant") else 0,
            "is_association_rep": 1 if data.get("is_association_rep") else 0,
            "is_volunteer": 1 if data.get("is_volunteer") else 0,
            "volunteer_interest": 1 if data.get("volunteer_interest") else 0,
            "event_interest": 1 if data.get("event_interest") else 0,
            "mobilizer_interest": 1 if data.get("mobilizer_interest") else 0,
            "declared_support": 1 if data.get("declared_support") else 0,
            "is_multiplier": 1 if data.get("is_multiplier") else 0,
            "acting_region": data.get("acting_region", "").strip(),
        }
        with db() as conn:
            existing = conn.execute("SELECT id, name FROM contacts WHERE phone = ? AND (? IS NULL OR id != ?)", (phone, contact_id, contact_id)).fetchone()
            if existing:
                return self.send_json({"error": "Telefone ja cadastrado", "duplicate": row_to_dict(existing)}, 409)
            old = conn.execute("SELECT status FROM contacts WHERE id = ?", (contact_id,)).fetchone() if contact_id else None
            if contact_id:
                assignments = ", ".join([f"{key}=?" for key in fields])
                conn.execute(f"UPDATE contacts SET {assignments}, updated_by=?, updated_at=? WHERE id=?", [*fields.values(), user["id"], now_iso(), contact_id])
                action = "Contato atualizado"
            else:
                code = referral_code()
                while conn.execute("SELECT 1 FROM contacts WHERE referral_code = ?", (code,)).fetchone():
                    code = referral_code()
                fields["referral_code"] = code
                keys = ", ".join([*fields.keys(), "created_by", "updated_by", "created_at", "updated_at"])
                marks = ", ".join(["?"] * (len(fields) + 4))
                cur = conn.execute(f"INSERT INTO contacts({keys}) VALUES ({marks})", [*fields.values(), user["id"], user["id"], now_iso(), now_iso()])
                contact_id = cur.lastrowid
                action = "Cadastro criado"
                conn.execute(
                    """
                    INSERT INTO contact_acquisitions(contact_id, source, manual_source, event_id, referral_code_used, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (contact_id, fields["source"], fields["source"], fields["origin_event_id"], None, now_iso()),
                )
            if fields["referred_by_contact_id"]:
                conn.execute(
                    "INSERT OR IGNORE INTO referrals(referrer_contact_id, referred_contact_id, created_by, created_at) VALUES (?, ?, ?, ?)",
                    (fields["referred_by_contact_id"], contact_id, user["id"], now_iso()),
                )
            if fields["origin_event_id"]:
                conn.execute(
                    "INSERT OR IGNORE INTO event_contacts(event_id, contact_id, created_by, created_at) VALUES (?, ?, ?, ?)",
                    (fields["origin_event_id"], contact_id, user["id"], now_iso()),
                )
            old_status = old["status"] if old else None
            conn.execute(
                "INSERT INTO contact_history(contact_id, user_id, action, old_status, new_status, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (contact_id, user["id"], "Alteracao de status" if old_status and old_status != fields["status"] else action, old_status, fields["status"], fields["notes"], now_iso()),
            )
            conn.execute("INSERT INTO activities(user_id, entity_type, entity_id, action, created_at) VALUES (?, 'contact', ?, ?, ?)", (user["id"], contact_id, action, now_iso()))
        self.send_json({"ok": True, "id": contact_id})

    def api_events(self, user, query):
        with db() as conn:
            rows = conn.execute(
                """
                SELECT e.*, r.name AS region_name, u.name AS responsible_name,
                       COUNT(ec.contact_id) AS contact_count,
                       SUM(CASE WHEN c.is_volunteer = 1 OR c.status = 'Voluntario' THEN 1 ELSE 0 END) AS volunteer_count,
                       SUM(CASE WHEN c.mobilizer_interest = 1 OR c.status = 'Multiplicador' THEN 1 ELSE 0 END) AS mobilizer_count
                FROM events e
                LEFT JOIN regions r ON r.id = e.region_id
                LEFT JOIN users u ON u.id = e.responsible_user_id
                LEFT JOIN event_contacts ec ON ec.event_id = e.id
                LEFT JOIN contacts c ON c.id = ec.contact_id
                GROUP BY e.id
                ORDER BY e.event_date DESC, e.id DESC
                """
            ).fetchall()
        self.send_json({"events": rows_to_dicts(rows)})

    def api_save_event(self, user):
        data = parse_body(self)
        if not data.get("name") or not data.get("event_date"):
            return self.send_json({"error": "Nome e data sao obrigatorios"}, 400)
        with db() as conn:
            cur = conn.execute(
                """
                INSERT INTO events(name, type, event_date, event_time, location, region_id, responsible_user_id, team, notes, created_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data.get("name"), data.get("type") or "outro", data.get("event_date"), data.get("event_time"),
                    data.get("location"), data.get("region_id") or None, data.get("responsible_user_id") or user["id"],
                    data.get("team"), data.get("notes"), user["id"], now_iso(),
                ),
            )
            conn.execute("INSERT INTO activities(user_id, entity_type, entity_id, action, created_at) VALUES (?, 'event', ?, 'Evento criado', ?)", (user["id"], cur.lastrowid, now_iso()))
        self.send_json({"ok": True, "id": cur.lastrowid})

    def api_goals(self, user, query):
        with db() as conn:
            goals = rows_to_dicts(conn.execute("SELECT * FROM goals ORDER BY end_date ASC"))
        today = date.today()
        for goal in goals:
            realized = self.metric_value(goal["metric"], goal["start_date"], goal["end_date"])
            start = date.fromisoformat(goal["start_date"])
            end = date.fromisoformat(goal["end_date"])
            total_days = max((end - start).days + 1, 1)
            elapsed = min(max((today - start).days + 1, 0), total_days)
            remaining_days = max((end - today).days + 1, 0)
            goal["realized"] = realized
            goal["percent"] = round((realized / goal["target"]) * 100, 1) if goal["target"] else 0
            goal["projection"] = round((realized / elapsed) * total_days) if elapsed else 0
            goal["needed_per_day"] = round(max(goal["target"] - realized, 0) / remaining_days, 1) if remaining_days else 0
        self.send_json({"goals": goals})

    def api_save_goal(self, user):
        data = parse_body(self)
        with db() as conn:
            cur = conn.execute(
                "INSERT INTO goals(name, metric, target, start_date, end_date, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (data.get("name"), data.get("metric"), int(data.get("target") or 0), data.get("start_date"), data.get("end_date"), user["id"], now_iso()),
            )
        self.send_json({"ok": True, "id": cur.lastrowid})

    def api_save_user(self, user):
        data = parse_body(self)
        if not data.get("name") or not data.get("email") or not data.get("password"):
            return self.send_json({"error": "Nome, email e senha inicial sao obrigatorios"}, 400)
        with db() as conn:
            cur = conn.execute(
                "INSERT INTO users(name, email, role, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
                (data.get("name"), data.get("email"), data.get("role") or "Equipe de campo", hash_password(data.get("password")), now_iso()),
            )
        self.send_json({"ok": True, "id": cur.lastrowid})

    def api_dashboard(self, user, query):
        start7 = (date.today() - timedelta(days=6)).isoformat()
        with db() as conn:
            one = lambda sql, p=(): conn.execute(sql, p).fetchone()[0] or 0
            latest_goal = conn.execute(
                """
                SELECT * FROM goals
                WHERE metric = 'contacts' AND date(end_date) >= date('now', 'localtime')
                ORDER BY end_date ASC, id DESC LIMIT 1
                """
            ).fetchone()
            contacts7 = one("SELECT COUNT(*) FROM contacts WHERE date(created_at) >= ?", (start7,))
            first_contact = conn.execute("SELECT MIN(date(created_at)) AS d FROM contacts").fetchone()["d"]
            days_considered = 7
            if first_contact:
                days_considered = min(7, max((date.today() - date.fromisoformat(first_contact)).days + 1, 1))
            cards = {
                "contactsTotal": one("SELECT COUNT(*) FROM contacts"),
                "contactsToday": one("SELECT COUNT(*) FROM contacts WHERE date(created_at) = date('now', 'localtime')"),
                "contactsYesterday": one("SELECT COUNT(*) FROM contacts WHERE date(created_at) = date('now', 'localtime', '-1 day')"),
                "contacts7": contacts7,
                "dailyAverage7": round(contacts7 / days_considered, 1),
                "averageDaysConsidered": days_considered,
                "consent": one("SELECT COUNT(*) FROM contacts WHERE consent = 1"),
                "whatsappConsent": one("SELECT COUNT(*) FROM contacts WHERE communication_consent = 1 OR consent = 1"),
                "support": one("SELECT COUNT(*) FROM contacts WHERE declared_support = 1"),
                "volunteerInterest": one("SELECT COUNT(*) FROM contacts WHERE volunteer_interest = 1 OR is_volunteer = 1 OR status = 'Voluntario'"),
                "eventInterest": one("SELECT COUNT(*) FROM contacts WHERE event_interest = 1"),
                "mobilizerInterest": one("SELECT COUNT(*) FROM contacts WHERE mobilizer_interest = 1"),
                "volunteers": one("SELECT COUNT(*) FROM contacts WHERE is_volunteer = 1 OR volunteer_interest = 1 OR status = 'Voluntario'"),
                "leaders": one("SELECT COUNT(*) FROM contacts WHERE is_community_leader = 1 OR is_building_manager = 1 OR is_merchant = 1 OR is_association_rep = 1 OR is_multiplier = 1 OR status = 'Multiplicador'"),
                "referrals": one("SELECT COUNT(*) FROM contacts WHERE referred_by_contact_id IS NOT NULL"),
                "referralBasePercent": round((one("SELECT COUNT(*) FROM contacts WHERE referred_by_contact_id IS NOT NULL") / max(one("SELECT COUNT(*) FROM contacts"), 1)) * 100, 1),
                "pageViews": one("SELECT COUNT(*) FROM public_analytics WHERE event_name = 'registration_page_view'"),
                "registrations": one("SELECT COUNT(*) FROM public_analytics WHERE event_name = 'registration_completed' OR event_name = 'referral_registration_completed'"),
                "shares": one("SELECT COUNT(*) FROM public_analytics WHERE event_name = 'share_clicked' OR event_name = 'whatsapp_share_clicked'"),
                "pending": one("SELECT COUNT(*) FROM contacts WHERE next_action_date IS NOT NULL AND date(next_action_date) <= date('now', 'localtime') AND status != 'Nao contatar'"),
                "events": one("SELECT COUNT(*) FROM events"),
            }
            cards["completionRate"] = round((cards["registrations"] / max(cards["pageViews"], 1)) * 100, 1)
            main_goal = None
            if latest_goal:
                realized = self.metric_value(latest_goal["metric"], latest_goal["start_date"], latest_goal["end_date"])
                start = date.fromisoformat(latest_goal["start_date"])
                end = date.fromisoformat(latest_goal["end_date"])
                total_days = max((end - start).days + 1, 1)
                elapsed = min(max((date.today() - start).days + 1, 0), total_days)
                remaining_days = max((end - date.today()).days + 1, 0)
                needed = round(max(latest_goal["target"] - realized, 0) / remaining_days, 1) if remaining_days else 0
                avg7 = cards["dailyAverage7"]
                diff = round(avg7 - needed, 1)
                ratio = (avg7 / needed) if needed else 1
                # Regra de ritmo: >=100% do necessario = acima/no ritmo; 90%-99% = atencao; <90% = atrasado.
                status = "ACIMA DO RITMO" if ratio > 1 else "NO RITMO"
                if needed and ratio < 0.9:
                    status = "ATRASADO"
                elif needed and ratio < 1:
                    status = "ATENCAO"
                period_closed = date.today() > end
                main_goal = {
                    "name": latest_goal["name"],
                    "target": latest_goal["target"],
                    "realized": realized,
                    "remaining": max(latest_goal["target"] - realized, 0),
                    "daysRemaining": remaining_days,
                    "periodClosed": period_closed,
                    "neededPerDay": needed,
                    "average7": avg7,
                    "difference": diff,
                    "status": "PERIODO ENCERRADO" if period_closed else status,
                    "rule": ">=100% do necessario: no ritmo/acima; 90%-99%: atencao; <90%: atrasado",
                }
            attention = {
                "withoutResponsible": one("SELECT COUNT(*) FROM contacts WHERE responsible_user_id IS NULL"),
                "overdueReturns": one("SELECT COUNT(*) FROM contacts WHERE next_action_date IS NOT NULL AND date(next_action_date) < date('now', 'localtime') AND status != 'Nao contatar'"),
                "eventsWithoutReport": one("SELECT COUNT(*) FROM (SELECT e.id FROM events e LEFT JOIN event_contacts ec ON ec.event_id=e.id GROUP BY e.id HAVING COUNT(ec.contact_id)=0)"),
                "suspectedDuplicates": one("SELECT COUNT(*) FROM (SELECT substr(phone, -8) suffix FROM contacts GROUP BY suffix HAVING COUNT(*) > 1)"),
                "withoutRegion": one("SELECT COUNT(*) FROM contacts WHERE region_id IS NULL"),
                "withoutSource": one("SELECT COUNT(*) FROM contacts WHERE source IS NULL OR source = '' OR source = 'outros'"),
            }
            acquisition = {
                "organic": one("SELECT COUNT(*) FROM contact_acquisitions WHERE COALESCE(referral_code_used, '') = '' AND COALESCE(event_id, '') = ''"),
                "referral": one("SELECT COUNT(*) FROM contact_acquisitions WHERE COALESCE(referral_code_used, '') != ''"),
                "event": one("SELECT COUNT(*) FROM contact_acquisitions WHERE event_id IS NOT NULL"),
            }
            acquisition["other"] = max(cards["contactsTotal"] - acquisition["organic"] - acquisition["referral"] - acquisition["event"], 0)
            acquisition["referralPercent"] = round((acquisition["referral"] / max(cards["contactsTotal"], 1)) * 100, 1)
            charts = {
                "daily": rows_to_dicts(conn.execute("SELECT date(created_at) AS label, COUNT(*) AS value FROM contacts GROUP BY date(created_at) ORDER BY label DESC LIMIT 30")),
                "sources": rows_to_dicts(conn.execute("SELECT COALESCE(NULLIF(source, ''), 'Outros') AS label, COUNT(*) AS value FROM contact_acquisitions GROUP BY COALESCE(NULLIF(source, ''), 'Outros') HAVING COUNT(*) > 0 ORDER BY value DESC")),
                "regions": rows_to_dicts(conn.execute("SELECT r.name AS label, COUNT(c.id) AS value FROM regions r LEFT JOIN contacts c ON c.region_id = r.id GROUP BY r.id ORDER BY value DESC, r.name LIMIT 5")),
                "regionsLow": rows_to_dicts(conn.execute("SELECT r.name AS label, COUNT(c.id) AS value FROM regions r LEFT JOIN contacts c ON c.region_id = r.id GROUP BY r.id HAVING COUNT(c.id) > 0 ORDER BY value ASC, r.name LIMIT 5")),
                "regions7": rows_to_dicts(conn.execute("SELECT r.name AS label, COUNT(c.id) AS value FROM regions r LEFT JOIN contacts c ON c.region_id = r.id AND date(c.created_at) >= ? GROUP BY r.id ORDER BY value DESC, r.name LIMIT 12", (start7,))),
                "team": rows_to_dicts(conn.execute("SELECT u.name AS label, COUNT(c.id) AS value FROM users u LEFT JOIN contacts c ON c.created_by = u.id GROUP BY u.id ORDER BY value DESC")),
                "events": rows_to_dicts(conn.execute("SELECT e.name AS label, COUNT(ec.contact_id) AS value FROM events e LEFT JOIN event_contacts ec ON ec.event_id = e.id GROUP BY e.id ORDER BY value DESC LIMIT 10")),
                "funnel": rows_to_dicts(conn.execute("SELECT status AS label, COUNT(*) AS value FROM contacts GROUP BY status ORDER BY value DESC")),
                "publicFunnel": [
                    {"label": "Visitas", "value": cards["pageViews"]},
                    {"label": "Cadastros concluídos", "value": cards["registrations"]},
                    {"label": "Autorizaram WhatsApp", "value": cards["whatsappConsent"]},
                    {"label": "Interesse voluntariado", "value": cards["volunteerInterest"]},
                    {"label": "Interesse em eventos", "value": cards["eventInterest"]},
                    {"label": "Interesse em mobilização", "value": cards["mobilizerInterest"]},
                    {"label": "Apoio declarado", "value": cards["support"]},
                    {"label": "Geraram indicações", "value": one("SELECT COUNT(DISTINCT referrer_contact_id) FROM referrals")},
                ],
                "multipliers": rows_to_dicts(conn.execute("""
                    SELECT c.name AS label, COUNT(r.id) AS value
                    FROM referrals r
                    JOIN contacts c ON c.id = r.referrer_contact_id
                    GROUP BY c.id
                    ORDER BY value DESC
                    LIMIT 10
                """)),
            }
        self.send_json({"cards": cards, "charts": charts, "mainGoal": main_goal, "attention": attention, "acquisition": acquisition, "publicBaseUrl": public_base_url(self)})

    def api_alerts(self, user, query):
        cutoff = (date.today() - timedelta(days=5)).isoformat()
        with db() as conn:
            total_contacts = conn.execute("SELECT COUNT(*) c FROM contacts").fetchone()["c"] or 0
            total_events = conn.execute("SELECT COUNT(*) c FROM events").fetchone()["c"] or 0
            alerts = []
            for r in conn.execute("SELECT COUNT(*) c FROM contacts WHERE responsible_user_id IS NULL"):
                if r["c"]:
                    alerts.append({"level": "alto", "category": "CRITICO", "message": f"{r['c']} contato(s) sem responsavel"})
            for r in conn.execute("SELECT COUNT(*) c FROM contacts WHERE next_action_date IS NOT NULL AND date(next_action_date) < ? AND status != 'Nao contatar'", (cutoff,)):
                if r["c"]:
                    alerts.append({"level": "alto", "category": "CRITICO", "message": f"{r['c']} retorno(s) vencido(s)"})
            if total_events >= 3:
                alerts += [{"level": "medio", "category": "ATENCAO", "message": f"Acao sem resultado registrado: {r['name']}"} for r in conn.execute("SELECT e.name FROM events e LEFT JOIN event_contacts ec ON ec.event_id=e.id GROUP BY e.id HAVING COUNT(ec.contact_id)=0 LIMIT 3")]
            if total_contacts >= 30:
                alerts += [{"level": "medio", "category": "ATENCAO", "message": f"Possivel duplicidade no telefone final {r['suffix']}"} for r in conn.execute("SELECT substr(phone, -8) suffix, COUNT(*) c FROM contacts GROUP BY suffix HAVING c > 1 LIMIT 3")]
            if total_contacts >= 100:
                alerts += [{"level": "baixo", "category": "INFORMATIVO", "message": f"{r['c']} contato(s) sem origem clara"} for r in conn.execute("SELECT COUNT(*) c FROM contacts WHERE source IS NULL OR source='' OR source='outros'") if r["c"]]
        self.send_json({"alerts": alerts[:5]})

    def api_daily_summary(self, user, query):
        today = today_iso()
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        start7 = (date.today() - timedelta(days=6)).isoformat()
        prev7 = (date.today() - timedelta(days=13)).isoformat()
        with db() as conn:
            count = lambda sql, p: conn.execute(sql, p).fetchone()[0] or 0
            payload = {
                "today": {
                    "newContacts": count("SELECT COUNT(*) FROM contacts WHERE date(created_at)=?", (today,)),
                    "worked": count("SELECT COUNT(DISTINCT contact_id) FROM contact_history WHERE date(created_at)=?", (today,)),
                    "volunteers": count("SELECT COUNT(*) FROM contacts WHERE date(created_at)=? AND (is_volunteer=1 OR status='Voluntario')", (today,)),
                    "leaders": count("SELECT COUNT(*) FROM contacts WHERE date(created_at)=? AND (is_community_leader=1 OR is_multiplier=1 OR status='Multiplicador')", (today,)),
                    "referrals": count("SELECT COUNT(*) FROM referrals WHERE date(created_at)=?", (today,)),
                    "events": count("SELECT COUNT(*) FROM events WHERE event_date=?", (today,)),
                },
                "yesterdayContacts": count("SELECT COUNT(*) FROM contacts WHERE date(created_at)=?", (yesterday,)),
                "last7Contacts": count("SELECT COUNT(*) FROM contacts WHERE date(created_at)>=?", (start7,)),
                "previous7Contacts": count("SELECT COUNT(*) FROM contacts WHERE date(created_at)>=? AND date(created_at)<?", (prev7, start7)),
                "regions": rows_to_dicts(conn.execute("SELECT r.name AS label, COUNT(c.id) AS value FROM regions r LEFT JOIN contacts c ON c.region_id=r.id AND date(c.created_at)=? GROUP BY r.id ORDER BY value DESC LIMIT 8", (today,))),
                "team": rows_to_dicts(conn.execute("SELECT u.name AS label, COUNT(c.id) AS value FROM users u LEFT JOIN contacts c ON c.created_by=u.id AND date(c.created_at)=? GROUP BY u.id ORDER BY value DESC", (today,))),
            }
        self.send_json(payload)

    def api_referrals(self, user, query):
        start7 = (date.today() - timedelta(days=6)).isoformat()
        with db() as conn:
            one = lambda sql, p=(): conn.execute(sql, p).fetchone()[0] or 0
            total_contacts = one("SELECT COUNT(*) FROM contacts")
            payload = {
                "cards": {
                    "total": one("SELECT COUNT(*) FROM referrals"),
                    "percent": round((one("SELECT COUNT(*) FROM contacts WHERE referred_by_contact_id IS NOT NULL") / max(total_contacts, 1)) * 100, 1),
                    "today": one("SELECT COUNT(*) FROM referrals WHERE date(created_at) = date('now', 'localtime')"),
                    "last7": one("SELECT COUNT(*) FROM referrals WHERE date(created_at) >= ?", (start7,)),
                    "average": round(one("SELECT COUNT(*) FROM referrals") / max(one("SELECT COUNT(DISTINCT referrer_contact_id) FROM referrals"), 1), 1),
                },
                "multipliers": rows_to_dicts(conn.execute(
                    """
                    SELECT c.id, c.name, c.phone, r.name AS region_name,
                           COUNT(ref.id) AS direct_referrals,
                           COUNT(ref.id) AS generated_contacts,
                           MAX(ref.created_at) AS last_referral,
                           c.created_at
                    FROM contacts c
                    JOIN referrals ref ON ref.referrer_contact_id = c.id
                    LEFT JOIN regions r ON r.id = c.region_id
                    GROUP BY c.id
                    ORDER BY direct_referrals DESC, last_referral DESC
                    LIMIT 50
                    """
                )),
                "active7": rows_to_dicts(conn.execute(
                    """
                    SELECT c.id, c.name, r.name AS region_name, COUNT(ref.id) AS direct_referrals, MAX(ref.created_at) AS last_referral
                    FROM referrals ref
                    JOIN contacts c ON c.id = ref.referrer_contact_id
                    LEFT JOIN regions r ON r.id = c.region_id
                    WHERE date(ref.created_at) >= ?
                    GROUP BY c.id
                    ORDER BY direct_referrals DESC, last_referral DESC
                    LIMIT 20
                    """,
                    (start7,),
                )),
            }
        self.send_json(payload)

    def api_origins(self, user, query):
        with db() as conn:
            total_contacts = conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0] or 0
            rows = rows_to_dicts(conn.execute(
                """
                SELECT COALESCE(NULLIF(ca.source, ''), COALESCE(NULLIF(c.source, ''), 'outros')) AS source,
                       COUNT(DISTINCT c.id) AS contacts,
                       SUM(CASE WHEN c.communication_consent = 1 OR c.consent = 1 THEN 1 ELSE 0 END) AS whatsapp,
                       SUM(CASE WHEN c.volunteer_interest = 1 OR c.is_volunteer = 1 THEN 1 ELSE 0 END) AS volunteers,
                       SUM(CASE WHEN c.mobilizer_interest = 1 THEN 1 ELSE 0 END) AS mobilizers,
                       SUM(CASE WHEN date(c.created_at) >= date('now', 'localtime', '-6 days') THEN 1 ELSE 0 END) AS last7
                FROM contacts c
                LEFT JOIN contact_acquisitions ca ON ca.contact_id = c.id
                GROUP BY COALESCE(NULLIF(ca.source, ''), COALESCE(NULLIF(c.source, ''), 'outros'))
                HAVING COUNT(DISTINCT c.id) > 0
                ORDER BY contacts DESC
                """
            ))
        for row in rows:
            row["source"] = safe_source(row["source"])
        grouped = {}
        for row in rows:
            item = grouped.setdefault(row["source"], {"source": row["source"], "contacts": 0, "whatsapp": 0, "volunteers": 0, "mobilizers": 0, "last7": 0})
            for key in ["contacts", "whatsapp", "volunteers", "mobilizers", "last7"]:
                item[key] += row[key] or 0
        origins = sorted(grouped.values(), key=lambda item: item["contacts"], reverse=True)
        for row in origins:
            row["percent"] = round((row["contacts"] / max(total_contacts, 1)) * 100, 1)
        self.send_json({"origins": origins})

    def api_regions_report(self, user, query):
        with db() as conn:
            rows = rows_to_dicts(conn.execute(
                """
                SELECT r.name,
                       COUNT(c.id) AS contacts,
                       SUM(CASE WHEN date(c.created_at) >= date('now', 'localtime', '-6 days') THEN 1 ELSE 0 END) AS last7,
                       SUM(CASE WHEN c.volunteer_interest = 1 OR c.is_volunteer = 1 THEN 1 ELSE 0 END) AS volunteers,
                       SUM(CASE WHEN c.mobilizer_interest = 1 THEN 1 ELSE 0 END) AS mobilizers,
                       COUNT(DISTINCT e.id) AS events,
                       COUNT(DISTINCT ref.id) AS referrals,
                       MAX(e.event_date) AS last_event
                FROM regions r
                LEFT JOIN contacts c ON c.region_id = r.id
                LEFT JOIN events e ON e.region_id = r.id
                LEFT JOIN referrals ref ON ref.referred_contact_id = c.id
                GROUP BY r.id
                ORDER BY contacts DESC, r.name
                """
            ))
        self.send_json({"regions": rows})

    def api_reports(self, user, query):
        with db() as conn:
            payload = {
                "exports": rows_to_dicts(conn.execute(
                    "SELECT u.name AS user_name, a.action, a.created_at FROM activities a LEFT JOIN users u ON u.id=a.user_id WHERE a.entity_type='export' ORDER BY a.created_at DESC LIMIT 50"
                )),
                "security": rows_to_dicts(conn.execute(
                    "SELECT event_name, details, created_at FROM security_events ORDER BY created_at DESC LIMIT 80"
                )),
                "quality": {
                    "duplicates": conn.execute("SELECT COUNT(*) FROM (SELECT substr(phone, -8) suffix FROM contacts GROUP BY suffix HAVING COUNT(*) > 1)").fetchone()[0] or 0,
                    "incomplete": conn.execute("SELECT COUNT(*) FROM contacts WHERE name = '' OR phone = ''").fetchone()[0] or 0,
                    "withoutRegion": conn.execute("SELECT COUNT(*) FROM contacts WHERE region_id IS NULL").fetchone()[0] or 0,
                    "withoutSource": conn.execute("SELECT COUNT(*) FROM contacts WHERE source IS NULL OR source = '' OR source = 'outros'").fetchone()[0] or 0,
                    "withoutResponsible": conn.execute("SELECT COUNT(*) FROM contacts WHERE responsible_user_id IS NULL").fetchone()[0] or 0,
                },
            }
        self.send_json(payload)

    def metric_value(self, metric: str, start: str, end: str) -> int:
        queries = {
            "contacts": "SELECT COUNT(*) FROM contacts WHERE date(created_at) BETWEEN ? AND ?",
            "volunteers": "SELECT COUNT(*) FROM contacts WHERE date(created_at) BETWEEN ? AND ? AND (is_volunteer=1 OR status='Voluntario')",
            "leaders": "SELECT COUNT(*) FROM contacts WHERE date(created_at) BETWEEN ? AND ? AND (is_community_leader=1 OR is_multiplier=1 OR status='Multiplicador')",
            "events": "SELECT COUNT(*) FROM events WHERE date(event_date) BETWEEN ? AND ?",
        }
        sql = queries.get(metric)
        if not sql:
            return 0
        with db() as conn:
            return conn.execute(sql, (start, end)).fetchone()[0] or 0

    def api_export_contacts(self, user, query):
        with db() as conn:
            rows = rows_to_dicts(conn.execute("SELECT * FROM contacts ORDER BY created_at DESC"))
            conn.execute(
                "INSERT INTO activities(user_id, entity_type, entity_id, action, created_at) VALUES (?, 'export', NULL, ?, ?)",
                (user["id"], "Exportacao de contatos CSV", now_iso()),
            )
        output = []
        headers = ["id", "name", "phone", "whatsapp", "status", "source", "consent", "created_at", "next_action_date"]
        output.append(",".join(headers))
        for row in rows:
            output.append(",".join(csv_escape(row.get(h)) for h in headers))
        data = "\n".join(output).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", "attachment; filename=contatos-campanha.csv")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def csv_escape(value) -> str:
    value = "" if value is None else str(value)
    if any(ch in value for ch in [",", '"', "\n"]):
        return '"' + value.replace('"', '""') + '"'
    return value


def main():
    init_db()
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8765"))
    print(f"CRM Campanha 2026 rodando em http://{host}:{port}")
    ThreadingHTTPServer((host, port), App).serve_forever()


if __name__ == "__main__":
    main()
