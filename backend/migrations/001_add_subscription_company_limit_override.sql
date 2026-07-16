-- Lets an admin override one specific user's share/company limit,
-- independent of their plan's default (e.g. bump one Premium user from
-- 25 to 30 without changing the Premium plan itself). NULL means "no
-- override, use the plan's company_limit as-is" — the existing behavior
-- for every subscription until an admin explicitly sets one.
ALTER TABLE subscriptions
    ADD COLUMN IF NOT EXISTS company_limit_override INTEGER;
