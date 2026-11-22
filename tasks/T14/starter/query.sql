SELECT id, patron, requested_at
FROM reservation
WHERE branch_id = $1 AND status = 'waiting'
ORDER BY requested_at, id LIMIT 20
