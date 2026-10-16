CREATE TABLE orders (
  id bigserial PRIMARY KEY,
  user_id bigint NOT NULL REFERENCES users (id),
  total_cents integer NOT NULL DEFAULT 0
);
CREATE INDEX orders_user_id ON orders (user_id);
