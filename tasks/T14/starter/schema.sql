CREATE TABLE reservation (id integer PRIMARY KEY, branch_id integer NOT NULL,
    patron text NOT NULL, status text NOT NULL, requested_at timestamp NOT NULL);
INSERT INTO reservation
SELECT i, CASE WHEN i % 10 <= 5 THEN 1 ELSE 2 + i % 17 END,
    'Patron ' || i, CASE WHEN i % 23 = 0 THEN 'waiting' ELSE 'completed' END,
    timestamp '2025-01-01' + (i % 5000) * interval '1 second'
FROM generate_series(1, 15000) i;
ANALYZE reservation;
