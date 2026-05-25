CREATE DATABASE IF NOT EXISTS hotel_room_system DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE hotel_room_system;

SET FOREIGN_KEY_CHECKS = 0;
DROP VIEW IF EXISTS v_daily_revenue;
DROP VIEW IF EXISTS v_customer_history;
DROP TRIGGER IF EXISTS trg_reservation_room_conflict_insert;
DROP TRIGGER IF EXISTS trg_reservation_room_conflict_update;
DROP TRIGGER IF EXISTS trg_stay_room_conflict_insert;
DROP TABLE IF EXISTS audit_logs;
DROP TABLE IF EXISTS settlements;
DROP TABLE IF EXISTS extra_charges;
DROP TABLE IF EXISTS stays;
DROP TABLE IF EXISTS reservations;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS rooms;
DROP TABLE IF EXISTS users;
SET FOREIGN_KEY_CHECKS = 1;

CREATE TABLE users (
    id INT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(60) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    display_name VARCHAR(80) NOT NULL,
    role ENUM('admin', 'frontdesk', 'housekeeping', 'finance') NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE rooms (
    id INT PRIMARY KEY AUTO_INCREMENT,
    room_number VARCHAR(20) NOT NULL UNIQUE,
    floor INT NOT NULL,
    room_type VARCHAR(80) NOT NULL,
    bed_count INT NOT NULL DEFAULT 1,
    price DECIMAL(10,2) NOT NULL,
    status ENUM('free', 'occupied', 'maintenance', 'reserved') NOT NULL DEFAULT 'free',
    description VARCHAR(255) DEFAULT '',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CHECK (floor BETWEEN 1 AND 99),
    CHECK (bed_count BETWEEN 1 AND 6),
    CHECK (price > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE customers (
    id INT PRIMARY KEY AUTO_INCREMENT,
    id_card VARCHAR(30) NOT NULL UNIQUE,
    name VARCHAR(80) NOT NULL,
    phone VARCHAR(30) NOT NULL,
    source ENUM('walk_in', 'member', 'ota', 'company', 'travel_agency', 'other') NOT NULL DEFAULT 'walk_in',
    notes VARCHAR(255) DEFAULT '',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE reservations (
    id INT PRIMARY KEY AUTO_INCREMENT,
    reservation_no VARCHAR(40) NOT NULL UNIQUE,
    customer_id INT NOT NULL,
    room_id INT NOT NULL,
    reserved_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    checkin_date DATE NOT NULL,
    checkout_date DATE NOT NULL,
    status ENUM('pending', 'confirmed', 'cancelled', 'checked_in', 'no_show') NOT NULL DEFAULT 'confirmed',
    deposit DECIMAL(10,2) NOT NULL DEFAULT 0,
    channel VARCHAR(60) NOT NULL DEFAULT 'frontdesk',
    notes VARCHAR(255) DEFAULT '',
    created_by INT NULL,
    CHECK (checkout_date > checkin_date),
    CHECK (deposit >= 0),
    CONSTRAINT fk_reservation_customer FOREIGN KEY (customer_id) REFERENCES customers(id) ON UPDATE CASCADE,
    CONSTRAINT fk_reservation_room FOREIGN KEY (room_id) REFERENCES rooms(id) ON UPDATE CASCADE,
    CONSTRAINT fk_reservation_user FOREIGN KEY (created_by) REFERENCES users(id) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE stays (
    id INT PRIMARY KEY AUTO_INCREMENT,
    stay_no VARCHAR(40) NOT NULL UNIQUE,
    reservation_id INT UNIQUE NULL,
    customer_id INT NOT NULL,
    room_id INT NOT NULL,
    checkin_date DATE NOT NULL,
    planned_checkout_date DATE NOT NULL,
    actual_checkout_date DATE NULL,
    room_rate DECIMAL(10,2) NOT NULL,
    deposit DECIMAL(10,2) NOT NULL DEFAULT 0,
    status ENUM('active', 'checked_out') NOT NULL DEFAULT 'active',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by INT NULL,
    CHECK (planned_checkout_date > checkin_date),
    CHECK (actual_checkout_date IS NULL OR actual_checkout_date >= checkin_date),
    CHECK (room_rate > 0),
    CHECK (deposit >= 0),
    CONSTRAINT fk_stay_reservation FOREIGN KEY (reservation_id) REFERENCES reservations(id) ON UPDATE CASCADE,
    CONSTRAINT fk_stay_customer FOREIGN KEY (customer_id) REFERENCES customers(id) ON UPDATE CASCADE,
    CONSTRAINT fk_stay_room FOREIGN KEY (room_id) REFERENCES rooms(id) ON UPDATE CASCADE,
    CONSTRAINT fk_stay_user FOREIGN KEY (created_by) REFERENCES users(id) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE extra_charges (
    id INT PRIMARY KEY AUTO_INCREMENT,
    stay_id INT NOT NULL,
    category ENUM('food', 'laundry', 'minibar', 'parking', 'damage', 'other') NOT NULL,
    item_name VARCHAR(120) NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    occurred_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by INT NULL,
    CHECK (amount > 0),
    CONSTRAINT fk_extra_stay FOREIGN KEY (stay_id) REFERENCES stays(id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_extra_user FOREIGN KEY (created_by) REFERENCES users(id) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE settlements (
    id INT PRIMARY KEY AUTO_INCREMENT,
    bill_no VARCHAR(40) NOT NULL UNIQUE,
    stay_id INT NOT NULL UNIQUE,
    checkout_date DATE NOT NULL,
    nights INT NOT NULL,
    overdue_days INT NOT NULL DEFAULT 0,
    room_total DECIMAL(10,2) NOT NULL,
    extra_total DECIMAL(10,2) NOT NULL,
    discount DECIMAL(10,2) NOT NULL DEFAULT 0,
    payable_total DECIMAL(10,2) NOT NULL,
    payment_method ENUM('cash', 'wechat', 'alipay', 'card', 'bank', 'member') NOT NULL,
    paid_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by INT NULL,
    CHECK (nights >= 1),
    CHECK (overdue_days >= 0),
    CHECK (room_total >= 0),
    CHECK (extra_total >= 0),
    CHECK (discount >= 0),
    CHECK (payable_total >= 0),
    CONSTRAINT fk_settlement_stay FOREIGN KEY (stay_id) REFERENCES stays(id) ON UPDATE CASCADE,
    CONSTRAINT fk_settlement_user FOREIGN KEY (created_by) REFERENCES users(id) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE audit_logs (
    id INT PRIMARY KEY AUTO_INCREMENT,
    action VARCHAR(60) NOT NULL,
    entity VARCHAR(60) NOT NULL,
    entity_id INT NULL,
    detail VARCHAR(255) DEFAULT '',
    actor_id INT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_audit_user FOREIGN KEY (actor_id) REFERENCES users(id) ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE INDEX idx_rooms_status ON rooms(status);
CREATE INDEX idx_customers_name_phone ON customers(name, phone);
CREATE INDEX idx_reservations_room_dates ON reservations(room_id, checkin_date, checkout_date, status);
CREATE INDEX idx_stays_room_status_dates ON stays(room_id, status, checkin_date, planned_checkout_date);
CREATE INDEX idx_settlements_paid_at ON settlements(paid_at);

SET FOREIGN_KEY_CHECKS = 0;

INSERT INTO users (id, username, password_hash, display_name, role, created_at) VALUES
    (1, 'admin', 'pbkdf2_sha256$f3108f6b1df3494c70f6a3e3b2a16e4e$959d12a7f4490c1c039a4daada8f81bf92c1b31b2a22683452148c53e58b2f22', '系统管理员', 'admin', '2026-05-16 09:36:20'),
    (2, 'front', 'pbkdf2_sha256$e5c404793cf0fffa0792f529f911da51$f6d746d65482e70e1e2926e4579584204c74f8f037e2871ec70d75ad782ef3f0', '前台接待', 'frontdesk', '2026-05-16 09:36:20'),
    (3, 'house', 'pbkdf2_sha256$d39e7f6a84519d8727ce3a6fce3f94e2$406d5924155d8f434376e2831ef8f80be72db72a669233640afddeb8c6e6358e', '客房主管', 'housekeeping', '2026-05-16 09:36:20'),
    (4, 'finance', 'pbkdf2_sha256$f01777fef07f3c13e76f55904c5c04c5$c8389365d30ad802ecb23fa9cade863c2859fc471a9f9c2c76473dea10f4bd7d', '财务主管', 'finance', '2026-05-16 09:36:20');

INSERT INTO rooms (id, room_number, floor, room_type, bed_count, price, status, description, created_at, updated_at) VALUES
    (1, '101', 1, '舒适大床房', 1, 268.0, 'occupied', '靠近大堂，适合商务单人入住', '2026-05-16 09:36:20', '2026-05-16 09:36:20'),
    (2, '102', 1, '舒适双床房', 2, 288.0, 'free', '采光好，安静楼层', '2026-05-16 09:36:20', '2026-05-16 09:36:20'),
    (3, '103', 1, '家庭亲子房', 3, 398.0, 'free', '儿童主题布置，含沙发床', '2026-05-16 09:36:20', '2026-05-16 09:36:20'),
    (4, '201', 2, '雅致大床房', 1, 328.0, 'free', '城市景观，带书桌', '2026-05-16 09:36:20', '2026-05-16 09:36:20'),
    (5, '202', 2, '雅致双床房', 2, 348.0, 'free', '双人差旅优选', '2026-05-16 09:36:20', '2026-05-16 09:36:20'),
    (6, '203', 2, '豪华景观房', 1, 458.0, 'reserved', '高楼层景观窗', '2026-05-16 09:36:20', '2026-05-16 09:36:20'),
    (7, '301', 3, '行政套房', 2, 688.0, 'free', '独立客厅，适合长住', '2026-05-16 09:36:20', '2026-05-16 09:36:20'),
    (8, '302', 3, '行政套房', 2, 688.0, 'free', '独立客厅，含会客区', '2026-05-16 09:36:20', '2026-05-16 09:36:20'),
    (9, '303', 3, '豪华景观房', 1, 468.0, 'free', '浴缸与景观窗', '2026-05-16 09:36:20', '2026-05-16 09:36:20'),
    (10, '501', 5, '星空套房', 2, 998.0, 'free', '顶层露台，纪念日推荐', '2026-05-16 09:36:20', '2026-05-16 09:36:20'),
    (11, '502', 5, '星空套房', 2, 998.0, 'free', '顶层景观，独立吧台', '2026-05-16 09:36:20', '2026-05-16 09:36:20'),
    (12, '305', 3, '雅致大床房', 1, 328.0, 'maintenance', '空调检修中', '2026-05-16 09:36:20', '2026-05-16 09:36:20');

INSERT INTO customers (id, id_card, name, phone, source, notes, created_at, updated_at) VALUES
    (1, '120101199201012228', '林知夏', '13800001111', 'member', '银卡会员，偏好安静房间', '2026-05-16 09:36:20', '2026-05-16 09:36:20'),
    (2, '330102198811220017', '周明远', '13900002222', 'company', '协议客户：天启科技', '2026-05-16 09:36:20', '2026-05-16 09:36:20'),
    (3, '440106199512123335', '许嘉宁', '13700003333', 'ota', '携程渠道客户', '2026-05-16 09:36:20', '2026-05-16 09:36:20'),
    (4, '510104199003154446', '沈亦航', '13600004444', 'walk_in', '散客', '2026-05-16 09:36:20', '2026-05-16 09:36:20');

INSERT INTO reservations (id, reservation_no, customer_id, room_id, reserved_at, checkin_date, checkout_date, status, deposit, channel, notes, created_by) VALUES
    (1, 'R20260516093620179F', 3, 6, '2026-05-16 09:36:20', '2026-05-17', '2026-05-19', 'confirmed', 200.0, 'OTA', '高楼层优先', 1);

INSERT INTO stays (id, stay_no, reservation_id, customer_id, room_id, checkin_date, planned_checkout_date, actual_checkout_date, room_rate, deposit, status, created_at, created_by) VALUES
    (1, 'I20260516093620D54D', NULL, 1, 1, '2026-05-15', '2026-05-17', NULL, 268.0, 300.0, 'active', '2026-05-16 09:36:20', 1),
    (2, 'I20260516093620E2E5', NULL, 2, 2, '2026-05-11', '2026-05-13', '2026-05-13', 288.0, 200.0, 'checked_out', '2026-05-16 09:36:20', 1);

INSERT INTO extra_charges (id, stay_id, category, item_name, amount, occurred_at, created_by) VALUES
    (1, 1, 'food', '早餐与咖啡', 68.0, '2026-05-16 09:36:20', 1),
    (2, 1, 'laundry', '衬衫洗衣', 36.0, '2026-05-16 09:36:20', 1);

INSERT INTO settlements (id, bill_no, stay_id, checkout_date, nights, overdue_days, room_total, extra_total, discount, payable_total, payment_method, paid_at, created_by) VALUES
    (1, 'B2026051609362096C9', 2, '2026-05-13', 2, 0, 576.0, 0.0, 0.0, 576.0, 'card', '2026-05-16 09:36:20', 1);

SET FOREIGN_KEY_CHECKS = 1;


DELIMITER $$

CREATE TRIGGER trg_reservation_room_conflict_insert
BEFORE INSERT ON reservations
FOR EACH ROW
BEGIN
    IF NEW.status IN ('pending', 'confirmed') THEN
        IF EXISTS (SELECT 1 FROM rooms WHERE id = NEW.room_id AND status = 'maintenance') THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'ROOM_IN_MAINTENANCE';
        END IF;
        IF EXISTS (
            SELECT 1 FROM reservations
            WHERE room_id = NEW.room_id
              AND status IN ('pending', 'confirmed')
              AND NOT (checkout_date <= NEW.checkin_date OR checkin_date >= NEW.checkout_date)
        ) THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'ROOM_RESERVATION_CONFLICT';
        END IF;
        IF EXISTS (
            SELECT 1 FROM stays
            WHERE room_id = NEW.room_id
              AND status = 'active'
              AND NOT (planned_checkout_date <= NEW.checkin_date OR checkin_date >= NEW.checkout_date)
        ) THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'ROOM_STAY_CONFLICT';
        END IF;
    END IF;
END$$

CREATE TRIGGER trg_reservation_room_conflict_update
BEFORE UPDATE ON reservations
FOR EACH ROW
BEGIN
    IF NEW.status IN ('pending', 'confirmed') THEN
        IF EXISTS (SELECT 1 FROM rooms WHERE id = NEW.room_id AND status = 'maintenance') THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'ROOM_IN_MAINTENANCE';
        END IF;
        IF EXISTS (
            SELECT 1 FROM reservations
            WHERE room_id = NEW.room_id
              AND id <> NEW.id
              AND status IN ('pending', 'confirmed')
              AND NOT (checkout_date <= NEW.checkin_date OR checkin_date >= NEW.checkout_date)
        ) THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'ROOM_RESERVATION_CONFLICT';
        END IF;
        IF EXISTS (
            SELECT 1 FROM stays
            WHERE room_id = NEW.room_id
              AND status = 'active'
              AND NOT (planned_checkout_date <= NEW.checkin_date OR checkin_date >= NEW.checkout_date)
        ) THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'ROOM_STAY_CONFLICT';
        END IF;
    END IF;
END$$

CREATE TRIGGER trg_stay_room_conflict_insert
BEFORE INSERT ON stays
FOR EACH ROW
BEGIN
    IF NEW.status = 'active' THEN
        IF EXISTS (SELECT 1 FROM rooms WHERE id = NEW.room_id AND status = 'maintenance') THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'ROOM_IN_MAINTENANCE';
        END IF;
        IF EXISTS (
            SELECT 1 FROM stays
            WHERE room_id = NEW.room_id
              AND status = 'active'
              AND NOT (planned_checkout_date <= NEW.checkin_date OR checkin_date >= NEW.planned_checkout_date)
        ) THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'ROOM_STAY_CONFLICT';
        END IF;
    END IF;
END$$

DELIMITER ;


CREATE VIEW v_customer_history AS
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
GROUP BY c.id, c.name, c.id_card, c.phone;

CREATE VIEW v_daily_revenue AS
SELECT
    DATE(paid_at) AS revenue_date,
    COUNT(*) AS bill_count,
    SUM(room_total) AS room_revenue,
    SUM(extra_total) AS extra_revenue,
    SUM(payable_total) AS total_revenue
FROM settlements
GROUP BY DATE(paid_at);
