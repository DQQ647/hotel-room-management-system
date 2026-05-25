from __future__ import annotations

import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import sqlite3
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import pymysql
import pymysql.cursors


BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
DB_PATH = Path(os.environ.get("HOTEL_DB_PATH", BASE_DIR / "hotel.db"))
SCHEMA_PATH = BASE_DIR / "schema.sql"
DB_ENGINE = os.environ.get("HOTEL_DB_ENGINE", "mysql").lower()
MYSQL_CONFIG_PATH = BASE_DIR / "db_config.json"
DEFAULT_MYSQL_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "",
    "database": "hotel_room_system",
}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ID_CARD_RE = re.compile(
    r"^[1-9]\d{5}(18|19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dX]$"
)
PHONE_RE = re.compile(r"^(?:1[3-9]\d{9}|0\d{2,3}-?\d{7,8})$")
ID_CARD_WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
ID_CARD_CHECK_CODES = "10X98765432"
CUSTOMER_SOURCES = {"walk_in", "member", "ota", "company", "travel_agency", "other"}
ROOM_STATUSES = {"free", "occupied", "maintenance", "reserved"}
TOKENS: dict[str, dict] = {}


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class DbRow(dict):
    def __init__(self, data: dict):
        converted = {key: self._convert(value) for key, value in data.items()}
        super().__init__(converted)
        self._values = list(converted.values())

    @staticmethod
    def _convert(value):
        if isinstance(value, (datetime, date)):
            return value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        return value

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return super().__getitem__(key)


class DbCursor:
    def __init__(self, cursor):
        self.cursor = cursor

    @property
    def lastrowid(self):
        return self.cursor.lastrowid

    def fetchone(self):
        row = self.cursor.fetchone()
        if row is None:
            return None
        return DbRow(row) if isinstance(row, dict) else row

    def fetchall(self):
        rows = self.cursor.fetchall()
        return [DbRow(row) if isinstance(row, dict) else row for row in rows]

    def __iter__(self):
        return iter(self.fetchall())


class MySQLConnection:
    def __init__(self, config: dict):
        self._conn = pymysql.connect(
            host=config["host"],
            port=int(config["port"]),
            user=config["user"],
            password=config["password"],
            database=config["database"],
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self._conn.rollback()
        else:
            self._conn.commit()
        self._conn.close()

    def execute(self, sql: str, params: tuple = ()):
        cursor = self._conn.cursor()
        cursor.execute(translate_sql(sql), params)
        return DbCursor(cursor)

    def executescript(self, script: str):
        cursor = self._conn.cursor()
        for statement in script.split(";"):
            statement = statement.strip()
            if statement:
                cursor.execute(translate_sql(statement))
        return DbCursor(cursor)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()


def load_mysql_config() -> dict:
    config = DEFAULT_MYSQL_CONFIG.copy()
    if MYSQL_CONFIG_PATH.exists():
        config.update(json.loads(MYSQL_CONFIG_PATH.read_text(encoding="utf-8")))
    for key in ["host", "port", "user", "password", "database"]:
        env_key = f"HOTEL_MYSQL_{key.upper()}"
        if os.environ.get(env_key):
            config[key] = os.environ[env_key]
    config["port"] = int(config["port"])
    return config


def translate_sql(sql: str) -> str:
    sql = sql.strip()
    if sql.upper() == "BEGIN IMMEDIATE":
        return "START TRANSACTION"
    sql = sql.replace("datetime('now', 'localtime')", "NOW()")
    sql = sql.replace("date('now', 'localtime')", "CURDATE()")
    sql = sql.replace("strftime('%Y-%m', 'now', 'localtime')", "DATE_FORMAT(NOW(), '%%Y-%%m')")
    sql = sql.replace("strftime('%Y-%m', paid_at)", "DATE_FORMAT(paid_at, '%%Y-%%m')")
    return sql.replace("?", "%s")


def connect():
    if DB_ENGINE == "mysql":
        return MySQLConnection(load_mysql_config())
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def safe_print(message: str) -> None:
    stream = getattr(sys, "stdout", None)
    if not stream:
        return
    try:
        print(message)
    except (OSError, UnicodeEncodeError):
        pass


def as_dict(row: Any | None) -> dict | None:
    return dict(row) if row else None


def fetch_all(conn: Any, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def fetch_one(conn: Any, sql: str, params: tuple = ()) -> dict | None:
    return as_dict(conn.execute(sql, params).fetchone())


def today_iso() -> str:
    return date.today().isoformat()


def parse_date(value: str, field: str) -> date:
    if not value or not DATE_RE.match(str(value)):
        raise ApiError(400, f"{field} 必须是 YYYY-MM-DD 格式")
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ApiError(400, f"{field} 不是有效日期") from exc


def money(value, field: str, minimum: float = 0) -> float:
    try:
        number = float(value if value not in (None, "") else 0)
    except (TypeError, ValueError) as exc:
        raise ApiError(400, f"{field} 必须是数字") from exc
    if number < minimum:
        raise ApiError(400, f"{field} 不能小于 {minimum}")
    return round(number, 2)


def required(data: dict, *fields: str) -> None:
    missing = [field for field in fields if data.get(field) in (None, "")]
    if missing:
        raise ApiError(400, "缺少必填字段：" + "、".join(missing))


def validate_id_card(value: str) -> str:
    id_card = str(value or "").strip().upper()
    if not ID_CARD_RE.match(id_card):
        raise ApiError(400, "身份证号必须是18位大陆居民身份证格式，不能只填5位或8位。")

    birth_text = id_card[6:14]
    try:
        birth_date = datetime.strptime(birth_text, "%Y%m%d").date()
    except ValueError as exc:
        raise ApiError(400, "身份证号中的出生日期不存在，请检查年月日。") from exc

    today = date.today()
    if birth_date > today:
        raise ApiError(400, "身份证号中的出生日期不能晚于今天。")
    age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    if age > 120:
        raise ApiError(400, "身份证号推算出的年龄超过120岁，请检查证件号码。")

    check_sum = sum(int(id_card[index]) * ID_CARD_WEIGHTS[index] for index in range(17))
    expected_code = ID_CARD_CHECK_CODES[check_sum % 11]
    if id_card[-1] != expected_code:
        raise ApiError(400, "身份证号校验码不正确，请检查最后一位。")
    return id_card


def validate_phone(value: str) -> str:
    phone = re.sub(r"\s+", "", str(value or "").strip())
    if not PHONE_RE.match(phone):
        raise ApiError(400, "联系电话格式不正确，请填写11位手机号或带区号的固定电话。")
    return phone


def validate_customer_data(data: dict) -> dict:
    required(data, "id_card", "name", "phone")
    name = str(data.get("name") or "").strip()
    if not re.match(r"^[\u4e00-\u9fa5A-Za-z·\s]{2,30}$", name):
        raise ApiError(400, "客户姓名需为2-30个中文、英文或间隔号字符。")

    source = data.get("source") or "walk_in"
    if source not in CUSTOMER_SOURCES:
        raise ApiError(400, "客户来源不在允许范围内。")

    notes = str(data.get("notes") or "").strip()
    if len(notes) > 500:
        raise ApiError(400, "备注不能超过500个字符。")

    return {
        "id_card": validate_id_card(data["id_card"]),
        "name": name,
        "phone": validate_phone(data["phone"]),
        "source": source,
        "notes": notes,
    }


def validate_room_data(data: dict, existing: dict | None = None) -> dict:
    required(data, "room_number", "floor", "room_type", "price")

    room_number = str(data.get("room_number") or "").strip()
    if not room_number:
        raise ApiError(400, "房号不能为空")
    if len(room_number) > 20:
        raise ApiError(400, "房号不能超过20个字符")

    room_type = str(data.get("room_type") or "").strip()
    if not room_type:
        raise ApiError(400, "房型不能为空")
    if len(room_type) > 80:
        raise ApiError(400, "房型不能超过80个字符")

    try:
        floor = int(data.get("floor"))
    except (TypeError, ValueError) as exc:
        raise ApiError(400, "楼层必须是数字") from exc
    if floor < 1 or floor > 99:
        raise ApiError(400, "楼层必须在1到99之间")

    try:
        bed_count = int(data.get("bed_count") or (existing or {}).get("bed_count") or 1)
    except (TypeError, ValueError) as exc:
        raise ApiError(400, "床位数必须是数字") from exc
    if bed_count < 1 or bed_count > 6:
        raise ApiError(400, "床位数必须在1到6之间")

    status = data.get("status") or (existing or {}).get("status") or "free"
    if status not in ROOM_STATUSES:
        raise ApiError(400, "房态不在允许范围内")

    description = str(data.get("description", (existing or {}).get("description") or "") or "").strip()
    if len(description) > 255:
        raise ApiError(400, "描述不能超过255个字符")

    return {
        "room_number": room_number,
        "floor": floor,
        "room_type": room_type,
        "bed_count": bed_count,
        "price": money(data.get("price"), "房价", 1),
        "status": status,
        "description": description,
    }


def make_no(prefix: str) -> str:
    return f"{prefix}{datetime.now():%Y%m%d%H%M%S}{secrets.token_hex(2).upper()}"


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000)
    return f"pbkdf2_sha256${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt, digest = stored.split("$", 2)
    except ValueError:
        return False
    if algo != "pbkdf2_sha256":
        return False
    candidate = hash_password(password, salt).split("$", 2)[2]
    return hmac.compare_digest(candidate, digest)


def seed_data(conn: Any) -> None:
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
        return

    users = [
        ("admin", "admin123", "系统管理员", "admin"),
        ("front", "front123", "前台接待", "frontdesk"),
        ("house", "house123", "客房主管", "housekeeping"),
        ("finance", "finance123", "财务主管", "finance"),
    ]
    for username, password, display_name, role in users:
        conn.execute(
            "INSERT INTO users(username, password_hash, display_name, role) VALUES (?, ?, ?, ?)",
            (username, hash_password(password), display_name, role),
        )

    rooms = [
        ("101", 1, "舒适大床房", 1, 268, "free", "靠近大堂，适合商务单人入住"),
        ("102", 1, "舒适双床房", 2, 288, "free", "采光好，安静楼层"),
        ("103", 1, "家庭亲子房", 3, 398, "free", "儿童主题布置，含沙发床"),
        ("201", 2, "雅致大床房", 1, 328, "free", "城市景观，带书桌"),
        ("202", 2, "雅致双床房", 2, 348, "free", "双人差旅优选"),
        ("203", 2, "豪华景观房", 1, 458, "free", "高楼层景观窗"),
        ("301", 3, "行政套房", 2, 688, "free", "独立客厅，适合长住"),
        ("302", 3, "行政套房", 2, 688, "free", "独立客厅，含会客区"),
        ("303", 3, "豪华景观房", 1, 468, "free", "浴缸与景观窗"),
        ("501", 5, "星空套房", 2, 998, "free", "顶层露台，纪念日推荐"),
        ("502", 5, "星空套房", 2, 998, "free", "顶层景观，独立吧台"),
        ("305", 3, "雅致大床房", 1, 328, "maintenance", "空调检修中"),
    ]
    for room in rooms:
        conn.execute(
            """
            INSERT INTO rooms(room_number, floor, room_type, bed_count, price, status, description)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            room,
        )

    customers = [
        ("120101199201012228", "林知夏", "13800001111", "member", "银卡会员，偏好安静房间"),
        ("330102198811220017", "周明远", "13900002222", "company", "协议客户：天启科技"),
        ("440106199512123335", "许嘉宁", "13700003333", "ota", "携程渠道客户"),
        ("510104199003154446", "沈亦航", "13600004444", "walk_in", "散客"),
    ]
    for customer in customers:
        conn.execute(
            "INSERT INTO customers(id_card, name, phone, source, notes) VALUES (?, ?, ?, ?, ?)",
            customer,
        )

    admin_id = conn.execute("SELECT id FROM users WHERE username = 'admin'").fetchone()[0]
    current = date.today()
    room_101 = conn.execute("SELECT id FROM rooms WHERE room_number = '101'").fetchone()[0]
    room_102 = conn.execute("SELECT id FROM rooms WHERE room_number = '102'").fetchone()[0]
    room_203 = conn.execute("SELECT id FROM rooms WHERE room_number = '203'").fetchone()[0]
    customer_1 = conn.execute("SELECT id FROM customers WHERE name = '林知夏'").fetchone()[0]
    customer_2 = conn.execute("SELECT id FROM customers WHERE name = '周明远'").fetchone()[0]
    customer_3 = conn.execute("SELECT id FROM customers WHERE name = '许嘉宁'").fetchone()[0]

    conn.execute(
        """
        INSERT INTO stays(stay_no, customer_id, room_id, checkin_date, planned_checkout_date, room_rate, deposit, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            make_no("I"),
            customer_1,
            room_101,
            (current - timedelta(days=1)).isoformat(),
            (current + timedelta(days=1)).isoformat(),
            268,
            300,
            admin_id,
        ),
    )
    stay_id = conn.execute("SELECT id FROM stays WHERE room_id = ? AND status = 'active'", (room_101,)).fetchone()[0]
    conn.execute(
        "INSERT INTO extra_charges(stay_id, category, item_name, amount, created_by) VALUES (?, ?, ?, ?, ?)",
        (stay_id, "food", "早餐与咖啡", 68, admin_id),
    )
    conn.execute(
        "INSERT INTO extra_charges(stay_id, category, item_name, amount, created_by) VALUES (?, ?, ?, ?, ?)",
        (stay_id, "laundry", "衬衫洗衣", 36, admin_id),
    )

    stay_no = make_no("I")
    conn.execute(
        """
        INSERT INTO stays(stay_no, customer_id, room_id, checkin_date, planned_checkout_date, actual_checkout_date,
                          room_rate, deposit, status, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'checked_out', ?)
        """,
        (
            stay_no,
            customer_2,
            room_102,
            (current - timedelta(days=5)).isoformat(),
            (current - timedelta(days=3)).isoformat(),
            (current - timedelta(days=3)).isoformat(),
            288,
            200,
            admin_id,
        ),
    )
    old_stay_id = conn.execute("SELECT id FROM stays WHERE stay_no = ?", (stay_no,)).fetchone()[0]
    conn.execute(
        """
        INSERT INTO settlements(bill_no, stay_id, checkout_date, nights, overdue_days, room_total, extra_total,
                                discount, payable_total, payment_method, paid_at, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'), ?)
        """,
        (make_no("B"), old_stay_id, (current - timedelta(days=3)).isoformat(), 2, 0, 576, 0, 0, 576, "card", admin_id),
    )

    conn.execute(
        """
        INSERT INTO reservations(reservation_no, customer_id, room_id, checkin_date, checkout_date,
                                 status, deposit, channel, notes, created_by)
        VALUES (?, ?, ?, ?, ?, 'confirmed', ?, ?, ?, ?)
        """,
        (
            make_no("R"),
            customer_3,
            room_203,
            (current + timedelta(days=1)).isoformat(),
            (current + timedelta(days=3)).isoformat(),
            200,
            "OTA",
            "高楼层优先",
            admin_id,
        ),
    )

    update_room_status(conn, room_101)
    update_room_status(conn, room_102)
    update_room_status(conn, room_203)


def init_db() -> None:
    if DB_ENGINE == "mysql":
        with connect() as conn:
            conn.execute("SELECT 1")
        return
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        seed_data(conn)


def log_action(conn: Any, action: str, entity: str, entity_id: int | None, detail: str, user_id: int | None) -> None:
    conn.execute(
        "INSERT INTO audit_logs(action, entity, entity_id, detail, actor_id) VALUES (?, ?, ?, ?, ?)",
        (action, entity, entity_id, detail, user_id),
    )


def update_room_status(conn: Any, room_id: int) -> None:
    room = fetch_one(conn, "SELECT status FROM rooms WHERE id = ?", (room_id,))
    if not room:
        return
    if room["status"] == "maintenance":
        return
    if fetch_one(conn, "SELECT id FROM stays WHERE room_id = ? AND status = 'active' LIMIT 1", (room_id,)):
        status = "occupied"
    elif fetch_one(
        conn,
        """
        SELECT id FROM reservations
        WHERE room_id = ?
          AND status IN ('pending', 'confirmed')
          AND checkout_date >= ?
        LIMIT 1
        """,
        (room_id, today_iso()),
    ):
        status = "reserved"
    else:
        status = "free"
    conn.execute("UPDATE rooms SET status = ?, updated_at = datetime('now', 'localtime') WHERE id = ?", (status, room_id))


def api_error_from_database(exc: Exception) -> ApiError:
    text = str(exc)
    mapping = {
        "ROOM_IN_MAINTENANCE": "该房间正在维修，不能预订或入住。",
        "ROOM_RESERVATION_CONFLICT": "该房间在所选日期已有预订，不能重复预订。",
        "ROOM_STAY_CONFLICT": "该房间在所选日期已有入住记录，不能重复安排。",
        "UNIQUE constraint failed: customers.id_card": "身份证号已存在，系统已阻止重复客户档案。",
        "UNIQUE constraint failed: rooms.room_number": "房号已存在，不能重复录入。",
        "UNIQUE constraint failed: users.username": "用户名已存在。",
        "Duplicate entry": "数据已存在，系统已阻止重复录入。",
    }
    for key, message in mapping.items():
        if key in text:
            return ApiError(409, message)
    if "CHECK constraint failed" in text:
        return ApiError(400, "数据不满足数据库完整性约束，请检查日期、金额或状态。")
    if "FOREIGN KEY constraint failed" in text:
        return ApiError(400, "关联数据不存在或正在被使用，操作已回滚。")
    return ApiError(500, "数据库操作失败：" + text)


def create_or_update_customer(conn: Any, data: dict, user_id: int | None) -> int:
    customer = validate_customer_data(data)
    existing = fetch_one(conn, "SELECT id FROM customers WHERE id_card = ?", (customer["id_card"],))
    if existing:
        conn.execute(
            """
            UPDATE customers
            SET name = ?, phone = ?, source = ?, notes = ?, updated_at = datetime('now', 'localtime')
            WHERE id = ?
            """,
            (customer["name"], customer["phone"], customer["source"], customer["notes"], existing["id"]),
        )
        customer_id = existing["id"]
        log_action(conn, "update", "customer", customer_id, "预订/入住流程同步客户资料", user_id)
    else:
        cursor = conn.execute(
            "INSERT INTO customers(id_card, name, phone, source, notes) VALUES (?, ?, ?, ?, ?)",
            (customer["id_card"], customer["name"], customer["phone"], customer["source"], customer["notes"]),
        )
        customer_id = cursor.lastrowid
        log_action(conn, "create", "customer", customer_id, "新增客户档案", user_id)
    return int(customer_id)


class HotelHandler(BaseHTTPRequestHandler):
    server_version = "HotelRoomSystem/1.0"

    def log_message(self, format: str, *args) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        safe_print(f"[{timestamp}] {self.address_string()} {format % args}")

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.end_headers()

    def do_GET(self) -> None:
        self.dispatch()

    def do_POST(self) -> None:
        self.dispatch()

    def do_PUT(self) -> None:
        self.dispatch()

    def do_DELETE(self) -> None:
        self.dispatch()

    def dispatch(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path.startswith("/api/"):
            self.handle_api(path, parse_qs(parsed.query))
        elif self.command == "GET":
            self.serve_static(path)
        else:
            self.send_json(405, {"error": "方法不允许"})

    def handle_api(self, path: str, query: dict[str, list[str]]) -> None:
        try:
            parts = [part for part in path.strip("/").split("/") if part]
            if path == "/api/health":
                self.send_json(200, {"ok": True, "database": str(DB_PATH), "today": today_iso()})
                return
            if path == "/api/login" and self.command == "POST":
                self.login()
                return

            user = self.current_user()
            resource = parts[1] if len(parts) > 1 else ""

            if self.command == "GET" and resource == "dashboard":
                self.dashboard()
            elif resource == "rooms":
                self.rooms(parts, query, user)
            elif resource == "customers":
                self.customers(parts, query, user)
            elif resource == "reservations":
                self.reservations(parts, query, user)
            elif resource == "checkins" and self.command == "POST":
                self.create_checkin(user)
            elif resource == "stays":
                self.stays(parts, query, user)
            elif resource == "extras":
                self.extras(parts, query, user)
            elif resource == "checkouts" and self.command == "POST":
                self.checkout(user)
            elif resource == "settlements":
                self.settlements(parts, query, user)
            elif resource == "reports" and self.command == "GET":
                self.reports()
            elif resource == "audit-logs" and self.command == "GET":
                self.require_role(user, {"admin"})
                self.audit_logs()
            else:
                raise ApiError(404, "接口不存在")
        except ApiError as exc:
            self.send_json(exc.status, {"error": exc.message})
        except (sqlite3.Error, pymysql.MySQLError) as exc:
            api_error = api_error_from_database(exc)
            self.send_json(api_error.status, {"error": api_error.message})
        except json.JSONDecodeError:
            self.send_json(400, {"error": "请求体必须是合法 JSON"})
        except Exception as exc:
            self.send_json(500, {"error": "服务器内部错误：" + str(exc)})

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length == 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw)

    def send_json(self, status: int, payload: dict | list) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_static(self, path: str) -> None:
        if path in ("", "/"):
            file_path = FRONTEND_DIR / "index.html"
        else:
            relative = Path(path.lstrip("/"))
            file_path = (FRONTEND_DIR / relative).resolve()
            if not str(file_path).startswith(str(FRONTEND_DIR.resolve())):
                self.send_error(403)
                return
        if not file_path.exists() or not file_path.is_file():
            self.send_error(404)
            return
        content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        data = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type + ("; charset=utf-8" if content_type.startswith("text/") else ""))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def current_user(self) -> dict:
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            raise ApiError(401, "请先登录系统")
        token = header.split(" ", 1)[1].strip()
        user = TOKENS.get(token)
        if not user:
            raise ApiError(401, "登录已失效，请重新登录")
        return user

    def require_role(self, user: dict, roles: set[str]) -> None:
        if user["role"] != "admin" and user["role"] not in roles:
            raise ApiError(403, "当前账号没有执行该操作的权限")

    def login(self) -> None:
        data = self.read_json()
        required(data, "username", "password")
        with connect() as conn:
            user = fetch_one(conn, "SELECT * FROM users WHERE username = ?", (data["username"].strip(),))
        if not user or not verify_password(data["password"], user["password_hash"]):
            raise ApiError(401, "用户名或密码不正确")
        token = secrets.token_urlsafe(32)
        public_user = {
            "id": user["id"],
            "username": user["username"],
            "display_name": user["display_name"],
            "role": user["role"],
        }
        TOKENS[token] = public_user
        self.send_json(200, {"token": token, "user": public_user})

    def dashboard(self) -> None:
        with connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM rooms").fetchone()[0]
            by_status = {row["status"]: row["count"] for row in conn.execute("SELECT status, COUNT(*) AS count FROM rooms GROUP BY status")}
            occupied = by_status.get("occupied", 0)
            available_total = max(total - by_status.get("maintenance", 0), 1)
            today_income = conn.execute("SELECT COALESCE(SUM(payable_total), 0) FROM settlements WHERE date(paid_at) = ?", (today_iso(),)).fetchone()[0]
            month_income = conn.execute(
                "SELECT COALESCE(SUM(payable_total), 0) FROM settlements WHERE strftime('%Y-%m', paid_at) = strftime('%Y-%m', 'now', 'localtime')"
            ).fetchone()[0]
            active_count = conn.execute("SELECT COUNT(*) FROM stays WHERE status = 'active'").fetchone()[0]
            arrival_count = conn.execute(
                "SELECT COUNT(*) FROM reservations WHERE status IN ('pending', 'confirmed') AND checkin_date = ?",
                (today_iso(),),
            ).fetchone()[0]
            departure_count = conn.execute(
                "SELECT COUNT(*) FROM stays WHERE status = 'active' AND planned_checkout_date <= ?",
                (today_iso(),),
            ).fetchone()[0]
            active_stays = fetch_all(
                conn,
                """
                SELECT s.id, s.stay_no, s.checkin_date, s.planned_checkout_date, s.room_rate, s.deposit,
                       c.name AS customer_name, c.phone, r.room_number, r.room_type,
                       COALESCE(SUM(e.amount), 0) AS extra_total
                FROM stays s
                JOIN customers c ON c.id = s.customer_id
                JOIN rooms r ON r.id = s.room_id
                LEFT JOIN extra_charges e ON e.stay_id = s.id
                WHERE s.status = 'active'
                GROUP BY s.id
                ORDER BY s.planned_checkout_date ASC
                LIMIT 8
                """,
            )
            recent_bills = fetch_all(
                conn,
                """
                SELECT se.bill_no, se.payable_total, se.paid_at, c.name AS customer_name, r.room_number
                FROM settlements se
                JOIN stays s ON s.id = se.stay_id
                JOIN customers c ON c.id = s.customer_id
                JOIN rooms r ON r.id = s.room_id
                ORDER BY se.paid_at DESC
                LIMIT 6
                """,
            )
        self.send_json(
            200,
            {
                "rooms": {
                    "total": total,
                    "free": by_status.get("free", 0),
                    "occupied": occupied,
                    "reserved": by_status.get("reserved", 0),
                    "maintenance": by_status.get("maintenance", 0),
                    "occupancy_rate": round(occupied / available_total * 100, 1),
                },
                "business": {
                    "today_income": round(today_income or 0, 2),
                    "month_income": round(month_income or 0, 2),
                    "active_stays": active_count,
                    "today_arrivals": arrival_count,
                    "due_departures": departure_count,
                },
                "active_stays": active_stays,
                "recent_bills": recent_bills,
            },
        )

    def rooms(self, parts: list[str], query: dict[str, list[str]], user: dict) -> None:
        if self.command == "GET" and len(parts) == 2:
            status = (query.get("status") or [""])[0]
            keyword = f"%{(query.get('keyword') or [''])[0].strip()}%"
            params: list = []
            where = ["1=1"]
            if status:
                where.append("r.status = ?")
                params.append(status)
            if keyword != "%%":
                where.append("(r.room_number LIKE ? OR r.room_type LIKE ?)")
                params.extend([keyword, keyword])
            sql = f"""
                SELECT r.*,
                       c.name AS current_guest,
                       s.id AS active_stay_id,
                       (
                           SELECT COUNT(*) FROM reservations rr
                           WHERE rr.room_id = r.id AND rr.status IN ('pending', 'confirmed') AND rr.checkout_date >= date('now', 'localtime')
                       ) AS future_reservations
                FROM rooms r
                LEFT JOIN stays s ON s.room_id = r.id AND s.status = 'active'
                LEFT JOIN customers c ON c.id = s.customer_id
                WHERE {' AND '.join(where)}
                ORDER BY r.floor, r.room_number
            """
            with connect() as conn:
                self.send_json(200, fetch_all(conn, sql, tuple(params)))
            return

        if self.command == "POST" and len(parts) == 2:
            self.require_role(user, {"frontdesk", "housekeeping"})
            data = self.read_json()
            room_data = validate_room_data(data)
            with connect() as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO rooms(room_number, floor, room_type, bed_count, price, status, description)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        room_data["room_number"],
                        room_data["floor"],
                        room_data["room_type"],
                        room_data["bed_count"],
                        room_data["price"],
                        room_data["status"],
                        room_data["description"],
                    ),
                )
                log_action(conn, "create", "room", cursor.lastrowid, f"新增房间 {room_data['room_number']}", user["id"])
                self.send_json(201, {"id": cursor.lastrowid})
            return

        if len(parts) == 3 and parts[2].isdigit():
            room_id = int(parts[2])
            if self.command == "PUT":
                self.require_role(user, {"frontdesk", "housekeeping"})
                data = self.read_json()
                with connect() as conn:
                    room = fetch_one(conn, "SELECT * FROM rooms WHERE id = ?", (room_id,))
                    if not room:
                        raise ApiError(404, "房间不存在")
                    room_data = validate_room_data({**room, **data}, room)
                    new_status = room_data["status"]
                    if new_status == "maintenance":
                        if fetch_one(conn, "SELECT id FROM stays WHERE room_id = ? AND status = 'active'", (room_id,)):
                            raise ApiError(409, "当前房间仍有住客，不能设为维修。")
                        if fetch_one(
                            conn,
                            "SELECT id FROM reservations WHERE room_id = ? AND status IN ('pending', 'confirmed') AND checkout_date >= ?",
                            (room_id, today_iso()),
                        ):
                            raise ApiError(409, "当前房间仍有未完成预订，不能设为维修。")
                    conn.execute(
                        """
                        UPDATE rooms
                        SET room_number = ?, floor = ?, room_type = ?, bed_count = ?, price = ?,
                            status = ?, description = ?, updated_at = datetime('now', 'localtime')
                        WHERE id = ?
                        """,
                        (
                            room_data["room_number"],
                            room_data["floor"],
                            room_data["room_type"],
                            room_data["bed_count"],
                            room_data["price"],
                            new_status,
                            room_data["description"],
                            room_id,
                        ),
                    )
                    if new_status != "maintenance":
                        update_room_status(conn, room_id)
                    log_action(conn, "update", "room", room_id, "更新客房资料/状态", user["id"])
                self.send_json(200, {"ok": True})
                return
            if self.command == "DELETE":
                self.require_role(user, {"admin"})
                with connect() as conn:
                    conn.execute("DELETE FROM rooms WHERE id = ?", (room_id,))
                    log_action(conn, "delete", "room", room_id, "删除客房", user["id"])
                self.send_json(200, {"ok": True})
                return

        raise ApiError(404, "客房接口不存在")

    def customers(self, parts: list[str], query: dict[str, list[str]], user: dict) -> None:
        if self.command == "GET" and len(parts) == 2:
            keyword = f"%{(query.get('keyword') or [''])[0].strip()}%"
            with connect() as conn:
                rows = fetch_all(
                    conn,
                    """
                    SELECT c.*, h.stay_count, h.last_checkout_date, h.total_spent
                    FROM customers c
                    LEFT JOIN v_customer_history h ON h.customer_id = c.id
                    WHERE ? = '%%' OR c.name LIKE ? OR c.phone LIKE ? OR c.id_card LIKE ?
                    ORDER BY c.updated_at DESC, c.id DESC
                    """,
                    (keyword, keyword, keyword, keyword),
                )
            self.send_json(200, rows)
            return

        if self.command == "POST" and len(parts) == 2:
            self.require_role(user, {"frontdesk"})
            data = self.read_json()
            with connect() as conn:
                customer_id = create_or_update_customer(conn, data, user["id"])
            self.send_json(201, {"id": customer_id})
            return

        if self.command == "PUT" and len(parts) == 3 and parts[2].isdigit():
            self.require_role(user, {"frontdesk"})
            data = self.read_json()
            customer_id = int(parts[2])
            customer = validate_customer_data(data)
            with connect() as conn:
                if not fetch_one(conn, "SELECT id FROM customers WHERE id = ?", (customer_id,)):
                    raise ApiError(404, "客户不存在")
                conn.execute(
                    """
                    UPDATE customers
                    SET id_card = ?, name = ?, phone = ?, source = ?, notes = ?, updated_at = datetime('now', 'localtime')
                    WHERE id = ?
                    """,
                    (
                        customer["id_card"],
                        customer["name"],
                        customer["phone"],
                        customer["source"],
                        customer["notes"],
                        customer_id,
                    ),
                )
                log_action(conn, "update", "customer", customer_id, "更新客户档案", user["id"])
            self.send_json(200, {"ok": True})
            return

        raise ApiError(404, "客户接口不存在")

    def reservations(self, parts: list[str], query: dict[str, list[str]], user: dict) -> None:
        if self.command == "GET" and len(parts) == 2:
            status = (query.get("status") or [""])[0]
            where = ["1=1"]
            params: list = []
            if status:
                where.append("rv.status = ?")
                params.append(status)
            with connect() as conn:
                rows = fetch_all(
                    conn,
                    f"""
                    SELECT rv.*, c.name AS customer_name, c.phone, c.id_card, r.room_number, r.room_type, r.price
                    FROM reservations rv
                    JOIN customers c ON c.id = rv.customer_id
                    JOIN rooms r ON r.id = rv.room_id
                    WHERE {' AND '.join(where)}
                    ORDER BY rv.checkin_date ASC, rv.id DESC
                    """,
                    tuple(params),
                )
            self.send_json(200, rows)
            return

        if self.command == "POST" and len(parts) == 2:
            self.require_role(user, {"frontdesk"})
            data = self.read_json()
            required(data, "room_id", "checkin_date", "checkout_date")
            customer_data = data.get("customer") or data
            checkin = parse_date(data["checkin_date"], "入住日期")
            checkout = parse_date(data["checkout_date"], "离店日期")
            if checkout <= checkin:
                raise ApiError(400, "离店日期必须晚于入住日期")
            with connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                customer_id = create_or_update_customer(conn, customer_data, user["id"])
                cursor = conn.execute(
                    """
                    INSERT INTO reservations(reservation_no, customer_id, room_id, checkin_date, checkout_date,
                                             status, deposit, channel, notes, created_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        make_no("R"),
                        customer_id,
                        int(data["room_id"]),
                        checkin.isoformat(),
                        checkout.isoformat(),
                        data.get("status") or "confirmed",
                        money(data.get("deposit", 0), "订金"),
                        data.get("channel") or "frontdesk",
                        data.get("notes") or "",
                        user["id"],
                    ),
                )
                update_room_status(conn, int(data["room_id"]))
                log_action(conn, "create", "reservation", cursor.lastrowid, "创建客房预订", user["id"])
                conn.commit()
            self.send_json(201, {"id": cursor.lastrowid})
            return

        if self.command == "PUT" and len(parts) == 4 and parts[2].isdigit() and parts[3] == "cancel":
            self.require_role(user, {"frontdesk"})
            reservation_id = int(parts[2])
            with connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                reservation = fetch_one(conn, "SELECT * FROM reservations WHERE id = ?", (reservation_id,))
                if not reservation:
                    raise ApiError(404, "预订不存在")
                if reservation["status"] not in ("pending", "confirmed"):
                    raise ApiError(409, "只有未入住的有效预订可以取消")
                conn.execute("UPDATE reservations SET status = 'cancelled' WHERE id = ?", (reservation_id,))
                update_room_status(conn, reservation["room_id"])
                log_action(conn, "cancel", "reservation", reservation_id, "取消预订", user["id"])
                conn.commit()
            self.send_json(200, {"ok": True})
            return

        raise ApiError(404, "预订接口不存在")

    def create_checkin(self, user: dict) -> None:
        self.require_role(user, {"frontdesk"})
        data = self.read_json()
        with connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            reservation_id = data.get("reservation_id")
            if reservation_id:
                reservation = fetch_one(
                    conn,
                    """
                    SELECT rv.*, r.price, r.room_number
                    FROM reservations rv
                    JOIN rooms r ON r.id = rv.room_id
                    WHERE rv.id = ?
                    """,
                    (int(reservation_id),),
                )
                if not reservation:
                    raise ApiError(404, "预订不存在")
                if reservation["status"] not in ("pending", "confirmed"):
                    raise ApiError(409, "该预订状态不能办理入住")
                customer_id = reservation["customer_id"]
                room_id = reservation["room_id"]
                checkin_date = data.get("checkin_date") or max(today_iso(), reservation["checkin_date"])
                planned_checkout = data.get("planned_checkout_date") or reservation["checkout_date"]
                room_rate = money(data.get("room_rate", reservation["price"]), "房价", 1)
                deposit = money(data.get("deposit", reservation["deposit"]), "押金")
            else:
                required(data, "room_id", "planned_checkout_date")
                customer_id = create_or_update_customer(conn, data.get("customer") or data, user["id"])
                room = fetch_one(conn, "SELECT * FROM rooms WHERE id = ?", (int(data["room_id"]),))
                if not room:
                    raise ApiError(404, "房间不存在")
                room_id = int(data["room_id"])
                checkin_date = data.get("checkin_date") or today_iso()
                planned_checkout = data["planned_checkout_date"]
                room_rate = money(data.get("room_rate", room["price"]), "房价", 1)
                deposit = money(data.get("deposit", 0), "押金")
                if fetch_one(
                    conn,
                    """
                    SELECT id FROM reservations
                    WHERE room_id = ?
                      AND status IN ('pending', 'confirmed')
                      AND NOT (checkout_date <= ? OR checkin_date >= ?)
                    """,
                    (room_id, checkin_date, planned_checkout),
                ):
                    raise ApiError(409, "该房间在入住日期范围内已有预订，请先选择其他房间或取消预订。")

            in_date = parse_date(checkin_date, "入住日期")
            out_date = parse_date(planned_checkout, "预计离店日期")
            if out_date <= in_date:
                raise ApiError(400, "预计离店日期必须晚于入住日期")

            cursor = conn.execute(
                """
                INSERT INTO stays(stay_no, reservation_id, customer_id, room_id, checkin_date, planned_checkout_date,
                                  room_rate, deposit, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    make_no("I"),
                    int(reservation_id) if reservation_id else None,
                    customer_id,
                    room_id,
                    in_date.isoformat(),
                    out_date.isoformat(),
                    room_rate,
                    deposit,
                    user["id"],
                ),
            )
            if reservation_id:
                conn.execute("UPDATE reservations SET status = 'checked_in' WHERE id = ?", (int(reservation_id),))
            update_room_status(conn, room_id)
            log_action(conn, "create", "stay", cursor.lastrowid, "办理入住登记", user["id"])
            conn.commit()
        self.send_json(201, {"id": cursor.lastrowid})

    def stays(self, parts: list[str], query: dict[str, list[str]], user: dict) -> None:
        if self.command == "GET" and len(parts) == 2:
            status = (query.get("status") or [""])[0]
            where = ["1=1"]
            params: list = []
            if status:
                where.append("s.status = ?")
                params.append(status)
            with connect() as conn:
                rows = fetch_all(
                    conn,
                    f"""
                    SELECT s.*, c.name AS customer_name, c.phone, c.id_card, r.room_number, r.room_type,
                           COALESCE(SUM(e.amount), 0) AS extra_total
                    FROM stays s
                    JOIN customers c ON c.id = s.customer_id
                    JOIN rooms r ON r.id = s.room_id
                    LEFT JOIN extra_charges e ON e.stay_id = s.id
                    WHERE {' AND '.join(where)}
                    GROUP BY s.id
                    ORDER BY s.status ASC, s.planned_checkout_date ASC, s.id DESC
                    """,
                    tuple(params),
                )
            self.send_json(200, rows)
            return
        raise ApiError(404, "入住接口不存在")

    def extras(self, parts: list[str], query: dict[str, list[str]], user: dict) -> None:
        if self.command == "GET" and len(parts) == 2:
            stay_id = (query.get("stay_id") or [""])[0]
            params: list = []
            where = ["1=1"]
            if stay_id:
                where.append("e.stay_id = ?")
                params.append(int(stay_id))
            with connect() as conn:
                rows = fetch_all(
                    conn,
                    f"""
                    SELECT e.*, s.stay_no, c.name AS customer_name, r.room_number
                    FROM extra_charges e
                    JOIN stays s ON s.id = e.stay_id
                    JOIN customers c ON c.id = s.customer_id
                    JOIN rooms r ON r.id = s.room_id
                    WHERE {' AND '.join(where)}
                    ORDER BY e.occurred_at DESC, e.id DESC
                    """,
                    tuple(params),
                )
            self.send_json(200, rows)
            return

        if self.command == "POST" and len(parts) == 2:
            self.require_role(user, {"frontdesk", "finance"})
            data = self.read_json()
            required(data, "stay_id", "category", "item_name", "amount")
            with connect() as conn:
                stay = fetch_one(conn, "SELECT * FROM stays WHERE id = ?", (int(data["stay_id"]),))
                if not stay:
                    raise ApiError(404, "入住单不存在")
                if stay["status"] != "active":
                    raise ApiError(409, "已退房的入住单不能继续登记消费")
                cursor = conn.execute(
                    """
                    INSERT INTO extra_charges(stay_id, category, item_name, amount, occurred_at, created_by)
                    VALUES (?, ?, ?, ?, COALESCE(?, datetime('now', 'localtime')), ?)
                    """,
                    (
                        int(data["stay_id"]),
                        data["category"],
                        str(data["item_name"]).strip(),
                        money(data["amount"], "消费金额", 0.01),
                        data.get("occurred_at"),
                        user["id"],
                    ),
                )
                log_action(conn, "create", "extra_charge", cursor.lastrowid, "登记额外消费", user["id"])
            self.send_json(201, {"id": cursor.lastrowid})
            return

        raise ApiError(404, "消费接口不存在")

    def checkout(self, user: dict) -> None:
        self.require_role(user, {"frontdesk", "finance"})
        data = self.read_json()
        required(data, "stay_id", "payment_method")
        checkout_date_value = data.get("checkout_date") or today_iso()
        actual = parse_date(checkout_date_value, "退房日期")
        discount = money(data.get("discount", 0), "优惠金额")
        with connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            stay = fetch_one(
                conn,
                """
                SELECT s.*, c.name AS customer_name, r.room_number
                FROM stays s
                JOIN customers c ON c.id = s.customer_id
                JOIN rooms r ON r.id = s.room_id
                WHERE s.id = ?
                """,
                (int(data["stay_id"]),),
            )
            if not stay:
                raise ApiError(404, "入住单不存在")
            if stay["status"] != "active":
                raise ApiError(409, "该入住单已经结算过")
            checkin = parse_date(stay["checkin_date"], "入住日期")
            planned = parse_date(stay["planned_checkout_date"], "预计离店日期")
            if actual < checkin:
                raise ApiError(400, "退房日期不能早于入住日期")
            nights = max((actual - checkin).days, 1)
            overdue_days = max((actual - planned).days, 0)
            room_total = round(nights * float(stay["room_rate"]), 2)
            extra_total = round(
                conn.execute("SELECT COALESCE(SUM(amount), 0) FROM extra_charges WHERE stay_id = ?", (stay["id"],)).fetchone()[0],
                2,
            )
            subtotal = round(room_total + extra_total, 2)
            if discount > subtotal:
                raise ApiError(400, "优惠金额不能大于应收合计")
            payable = round(subtotal - discount, 2)
            cursor = conn.execute(
                """
                INSERT INTO settlements(bill_no, stay_id, checkout_date, nights, overdue_days, room_total,
                                        extra_total, discount, payable_total, payment_method, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    make_no("B"),
                    stay["id"],
                    actual.isoformat(),
                    nights,
                    overdue_days,
                    room_total,
                    extra_total,
                    discount,
                    payable,
                    data["payment_method"],
                    user["id"],
                ),
            )
            conn.execute(
                "UPDATE stays SET status = 'checked_out', actual_checkout_date = ? WHERE id = ?",
                (actual.isoformat(), stay["id"]),
            )
            update_room_status(conn, stay["room_id"])
            log_action(conn, "checkout", "settlement", cursor.lastrowid, "退房结算", user["id"])
            bill = fetch_one(conn, "SELECT * FROM settlements WHERE id = ?", (cursor.lastrowid,))
            conn.commit()
        self.send_json(
            201,
            {
                "id": cursor.lastrowid,
                "bill": bill,
                "customer_name": stay["customer_name"],
                "room_number": stay["room_number"],
                "early_checkout": actual < planned,
                "overdue_days": overdue_days,
            },
        )

    def settlements(self, parts: list[str], query: dict[str, list[str]], user: dict) -> None:
        if self.command != "GET" or len(parts) != 2:
            raise ApiError(404, "结算接口不存在")
        with connect() as conn:
            rows = fetch_all(
                conn,
                """
                SELECT se.*, c.name AS customer_name, c.phone, r.room_number, r.room_type, s.checkin_date
                FROM settlements se
                JOIN stays s ON s.id = se.stay_id
                JOIN customers c ON c.id = s.customer_id
                JOIN rooms r ON r.id = s.room_id
                ORDER BY se.paid_at DESC, se.id DESC
                LIMIT 100
                """,
            )
        self.send_json(200, rows)

    def reports(self) -> None:
        current = date.today()
        start = current - timedelta(days=13)
        days = [(start + timedelta(days=i)).isoformat() for i in range(14)]
        with connect() as conn:
            revenue_rows = {
                row["revenue_date"]: dict(row)
                for row in conn.execute(
                    """
                    SELECT revenue_date, bill_count, room_revenue, extra_revenue, total_revenue
                    FROM v_daily_revenue
                    WHERE revenue_date >= ?
                    """,
                    (start.isoformat(),),
                )
            }
            trend = [
                {
                    "date": day,
                    "bill_count": revenue_rows.get(day, {}).get("bill_count", 0),
                    "room_revenue": round(revenue_rows.get(day, {}).get("room_revenue", 0) or 0, 2),
                    "extra_revenue": round(revenue_rows.get(day, {}).get("extra_revenue", 0) or 0, 2),
                    "total_revenue": round(revenue_rows.get(day, {}).get("total_revenue", 0) or 0, 2),
                }
                for day in days
            ]
            source_stats = fetch_all(
                conn,
                """
                SELECT source, COUNT(*) AS customer_count
                FROM customers
                GROUP BY source
                ORDER BY customer_count DESC
                """,
            )
            room_type_stats = fetch_all(
                conn,
                """
                SELECT room_type,
                       COUNT(*) AS total,
                       SUM(CASE WHEN status = 'occupied' THEN 1 ELSE 0 END) AS occupied,
                       SUM(CASE WHEN status = 'maintenance' THEN 1 ELSE 0 END) AS maintenance,
                       ROUND(SUM(CASE WHEN status = 'occupied' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS occupancy_rate
                FROM rooms
                GROUP BY room_type
                ORDER BY total DESC, room_type
                """,
            )
            monthly = fetch_all(
                conn,
                """
                SELECT strftime('%Y-%m', paid_at) AS month, COUNT(*) AS bill_count, SUM(payable_total) AS revenue
                FROM settlements
                GROUP BY strftime('%Y-%m', paid_at)
                ORDER BY month DESC
                LIMIT 12
                """,
            )
        self.send_json(200, {"revenue_trend": trend, "source_stats": source_stats, "room_type_stats": room_type_stats, "monthly": monthly})

    def audit_logs(self) -> None:
        with connect() as conn:
            rows = fetch_all(
                conn,
                """
                SELECT a.*, u.display_name AS actor_name, u.role AS actor_role
                FROM audit_logs a
                LEFT JOIN users u ON u.id = a.actor_id
                ORDER BY a.created_at DESC, a.id DESC
                LIMIT 120
                """,
            )
        self.send_json(200, rows)


def main() -> None:
    init_db()
    host = os.environ.get("HOTEL_HOST", "127.0.0.1")
    port = int(os.environ.get("HOTEL_PORT", "8000"))
    server = ThreadingHTTPServer((host, port), HotelHandler)
    safe_print(f"酒店客房管理系统已启动: http://{host}:{port}")
    if DB_ENGINE == "mysql":
        cfg = load_mysql_config()
        safe_print(f"MySQL数据库: {cfg['host']}:{cfg['port']}/{cfg['database']}")
    else:
        safe_print(f"数据库文件: {DB_PATH}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        safe_print("\n服务器已停止")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
