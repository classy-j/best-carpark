-- Run ONCE on a database created before this column existed:
--   mysql -u root -h 127.0.0.1 carpark < db/migrations/001_add_short_term_parking.sql
-- Then reload carpark info to fill it:  python -m collector.load_carparks
ALTER TABLE carparks
    ADD COLUMN short_term_parking VARCHAR(32) NULL AFTER night_parking;
