SELECT id, room_number, floor, room_type, price, status
FROM rooms
ORDER BY floor, room_number;

SELECT
    s.stay_no,
    c.name AS customer_name,
    c.phone,
    r.room_number,
    s.checkin_date,
    s.planned_checkout_date,
    s.room_rate,
    s.deposit
FROM stays s
JOIN customers c ON c.id = s.customer_id
JOIN rooms r ON r.id = s.room_id
WHERE s.status = 'active'
ORDER BY s.planned_checkout_date;

SELECT
    rv.reservation_no,
    c.name AS customer_name,
    r.room_number,
    rv.checkin_date,
    rv.checkout_date,
    rv.status,
    rv.deposit
FROM reservations rv
JOIN customers c ON c.id = rv.customer_id
JOIN rooms r ON r.id = rv.room_id
WHERE rv.status IN ('pending', 'confirmed')
ORDER BY rv.checkin_date;

SELECT *
FROM v_customer_history
ORDER BY stay_count DESC, total_spent DESC;

SELECT *
FROM v_daily_revenue
ORDER BY revenue_date DESC;

SELECT
    a.created_at,
    u.display_name AS actor,
    a.action,
    a.entity,
    a.entity_id,
    a.detail
FROM audit_logs a
LEFT JOIN users u ON u.id = a.actor_id
ORDER BY a.created_at DESC
LIMIT 30;
