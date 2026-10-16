const { Pool } = require("pg");

// Connects as the superuser with the password in the code.
const pool = new Pool({
  connectionString: process.env.DATABASE_URL || "postgres://postgres:postgres@localhost:5432/shop",
});

module.exports = { pool };
