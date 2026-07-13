INSERT INTO plans (
    name,
    price,
    company_limit,
    duration_days
)
VALUES

(
    'FREE',
    0,
    10,
    3650
),

(
    'PREMIUM',
    299,
    25,
    30
)
ON CONFLICT (name) DO UPDATE SET
    price         = EXCLUDED.price,
    company_limit = EXCLUDED.company_limit,
    duration_days = EXCLUDED.duration_days;
