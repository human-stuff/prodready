ALTER TABLE users DROP COLUMN legacy_name;
ALTER TABLE orders ADD COLUMN status text NOT NULL;
