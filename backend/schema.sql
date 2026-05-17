PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'frontdesk', 'housekeeping', 'finance')),
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS rooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_number TEXT NOT NULL UNIQUE,
    floor INTEGER NOT NULL CHECK (floor BETWEEN 1 AND 99),
    room_type TEXT NOT NULL,
    bed_count INTEGER NOT NULL DEFAULT 1 CHECK (bed_count BETWEEN 1 AND 6),
    price REAL NOT NULL CHECK (price > 0),
    status TEXT NOT NULL DEFAULT 'free' CHECK (status IN ('free', 'occupied', 'maintenance', 'reserved')),
    description TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    id_card TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'walk_in' CHECK (source IN ('walk_in', 'member', 'ota', 'company', 'travel_agency', 'other')),
    notes TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS reservations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reservation_no TEXT NOT NULL UNIQUE,
    customer_id INTEGER NOT NULL REFERENCES customers(id) ON UPDATE CASCADE,
    room_id INTEGER NOT NULL REFERENCES rooms(id) ON UPDATE CASCADE,
    reserved_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    checkin_date TEXT NOT NULL,
    checkout_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'confirmed' CHECK (status IN ('pending', 'confirmed', 'cancelled', 'checked_in', 'no_show')),
    deposit REAL NOT NULL DEFAULT 0 CHECK (deposit >= 0),
    channel TEXT NOT NULL DEFAULT 'frontdesk',
    notes TEXT DEFAULT '',
    created_by INTEGER REFERENCES users(id) ON UPDATE CASCADE,
    CHECK (julianday(checkout_date) > julianday(checkin_date))
);

CREATE TABLE IF NOT EXISTS stays (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stay_no TEXT NOT NULL UNIQUE,
    reservation_id INTEGER UNIQUE REFERENCES reservations(id) ON UPDATE CASCADE,
    customer_id INTEGER NOT NULL REFERENCES customers(id) ON UPDATE CASCADE,
    room_id INTEGER NOT NULL REFERENCES rooms(id) ON UPDATE CASCADE,
    checkin_date TEXT NOT NULL,
    planned_checkout_date TEXT NOT NULL,
    actual_checkout_date TEXT,
    room_rate REAL NOT NULL CHECK (room_rate > 0),
    deposit REAL NOT NULL DEFAULT 0 CHECK (deposit >= 0),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'checked_out')),
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    created_by INTEGER REFERENCES users(id) ON UPDATE CASCADE,
    CHECK (julianday(planned_checkout_date) > julianday(checkin_date)),
    CHECK (actual_checkout_date IS NULL OR julianday(actual_checkout_date) >= julianday(checkin_date))
);

CREATE TABLE IF NOT EXISTS extra_charges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stay_id INTEGER NOT NULL REFERENCES stays(id) ON DELETE CASCADE ON UPDATE CASCADE,
    category TEXT NOT NULL CHECK (category IN ('food', 'laundry', 'minibar', 'parking', 'damage', 'other')),
    item_name TEXT NOT NULL,
    amount REAL NOT NULL CHECK (amount > 0),
    occurred_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    created_by INTEGER REFERENCES users(id) ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS settlements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_no TEXT NOT NULL UNIQUE,
    stay_id INTEGER NOT NULL UNIQUE REFERENCES stays(id) ON UPDATE CASCADE,
    checkout_date TEXT NOT NULL,
    nights INTEGER NOT NULL CHECK (nights >= 1),
    overdue_days INTEGER NOT NULL DEFAULT 0 CHECK (overdue_days >= 0),
    room_total REAL NOT NULL CHECK (room_total >= 0),
    extra_total REAL NOT NULL CHECK (extra_total >= 0),
    discount REAL NOT NULL DEFAULT 0 CHECK (discount >= 0),
    payable_total REAL NOT NULL CHECK (payable_total >= 0),
    payment_method TEXT NOT NULL CHECK (payment_method IN ('cash', 'wechat', 'alipay', 'card', 'bank', 'member')),
    paid_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    created_by INTEGER REFERENCES users(id) ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    entity TEXT NOT NULL,
    entity_id INTEGER,
    detail TEXT DEFAULT '',
    actor_id INTEGER REFERENCES users(id) ON UPDATE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_rooms_status ON rooms(status);
CREATE INDEX IF NOT EXISTS idx_customers_name_phone ON customers(name, phone);
CREATE INDEX IF NOT EXISTS idx_reservations_room_dates ON reservations(room_id, checkin_date, checkout_date, status);
CREATE INDEX IF NOT EXISTS idx_stays_room_status_dates ON stays(room_id, status, checkin_date, planned_checkout_date);
CREATE INDEX IF NOT EXISTS idx_settlements_paid_at ON settlements(paid_at);

CREATE TRIGGER IF NOT EXISTS trg_reservation_room_conflict_insert
BEFORE INSERT ON reservations
WHEN NEW.status IN ('pending', 'confirmed')
BEGIN
    SELECT CASE
        WHEN EXISTS (
            SELECT 1 FROM rooms
            WHERE id = NEW.room_id AND status = 'maintenance'
        ) THEN RAISE(ABORT, 'ROOM_IN_MAINTENANCE')
        WHEN EXISTS (
            SELECT 1 FROM reservations
            WHERE room_id = NEW.room_id
              AND status IN ('pending', 'confirmed')
              AND NOT (checkout_date <= NEW.checkin_date OR checkin_date >= NEW.checkout_date)
        ) THEN RAISE(ABORT, 'ROOM_RESERVATION_CONFLICT')
        WHEN EXISTS (
            SELECT 1 FROM stays
            WHERE room_id = NEW.room_id
              AND status = 'active'
              AND NOT (planned_checkout_date <= NEW.checkin_date OR checkin_date >= NEW.checkout_date)
        ) THEN RAISE(ABORT, 'ROOM_STAY_CONFLICT')
    END;
END;

CREATE TRIGGER IF NOT EXISTS trg_reservation_room_conflict_update
BEFORE UPDATE OF room_id, checkin_date, checkout_date, status ON reservations
WHEN NEW.status IN ('pending', 'confirmed')
BEGIN
    SELECT CASE
        WHEN EXISTS (
            SELECT 1 FROM rooms
            WHERE id = NEW.room_id AND status = 'maintenance'
        ) THEN RAISE(ABORT, 'ROOM_IN_MAINTENANCE')
        WHEN EXISTS (
            SELECT 1 FROM reservations
            WHERE room_id = NEW.room_id
              AND id <> NEW.id
              AND status IN ('pending', 'confirmed')
              AND NOT (checkout_date <= NEW.checkin_date OR checkin_date >= NEW.checkout_date)
        ) THEN RAISE(ABORT, 'ROOM_RESERVATION_CONFLICT')
        WHEN EXISTS (
            SELECT 1 FROM stays
            WHERE room_id = NEW.room_id
              AND status = 'active'
              AND NOT (planned_checkout_date <= NEW.checkin_date OR checkin_date >= NEW.checkout_date)
        ) THEN RAISE(ABORT, 'ROOM_STAY_CONFLICT')
    END;
END;

CREATE TRIGGER IF NOT EXISTS trg_stay_room_conflict_insert
BEFORE INSERT ON stays
WHEN NEW.status = 'active'
BEGIN
    SELECT CASE
        WHEN EXISTS (
            SELECT 1 FROM rooms
            WHERE id = NEW.room_id AND status = 'maintenance'
        ) THEN RAISE(ABORT, 'ROOM_IN_MAINTENANCE')
        WHEN EXISTS (
            SELECT 1 FROM stays
            WHERE room_id = NEW.room_id
              AND status = 'active'
              AND NOT (planned_checkout_date <= NEW.checkin_date OR checkin_date >= NEW.planned_checkout_date)
        ) THEN RAISE(ABORT, 'ROOM_STAY_CONFLICT')
    END;
END;

CREATE VIEW IF NOT EXISTS v_customer_history AS
SELECT
    c.id AS customer_id,
    c.name,
    c.id_card,
    c.phone,
    COUNT(s.id) AS stay_count,
    MAX(s.actual_checkout_date) AS last_checkout_date,
    COALESCE(SUM(se.payable_total), 0) AS total_spent
FROM customers c
LEFT JOIN stays s ON s.customer_id = c.id
LEFT JOIN settlements se ON se.stay_id = s.id
GROUP BY c.id;

CREATE VIEW IF NOT EXISTS v_daily_revenue AS
SELECT
    date(paid_at) AS revenue_date,
    COUNT(*) AS bill_count,
    SUM(room_total) AS room_revenue,
    SUM(extra_total) AS extra_revenue,
    SUM(payable_total) AS total_revenue
FROM settlements
GROUP BY date(paid_at);
