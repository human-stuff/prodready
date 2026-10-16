CREATE TABLE users (
  id serial PRIMARY KEY,
  email text NOT NULL,
  password text NOT NULL,
  role text NOT NULL DEFAULT 'customer',
  legacy_name text
);

CREATE TABLE orders (
  id serial PRIMARY KEY,
  user_id integer NOT NULL REFERENCES users (id),
  total_cents integer NOT NULL
);
