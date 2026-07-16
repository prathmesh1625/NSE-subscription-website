-- Marks which companies form the "default watchlist" that every NEW user
-- automatically gets added to their own watchlist on signup. Kept in sync
-- with the admin dashboard's "Add/remove shares to every user's watchlist"
-- bulk actions: adding a company to everyone also makes it a default for
-- anyone who signs up later; removing it from everyone also drops it from
-- that default set (see adminRepository.js addCompaniesToAllUsers /
-- removeCompaniesFromAllUsers).
ALTER TABLE companies
    ADD COLUMN IF NOT EXISTS is_default_watchlist BOOLEAN NOT NULL DEFAULT FALSE;
