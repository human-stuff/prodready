const express = require("express");
const axios = require("axios");
const { pool } = require("./db");
const { hashPassword, requireUser, sign } = require("./auth");

const app = express();
app.use(express.json());

app.use((req, res, next) => {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Credentials", "true");
  next();
});

app.post("/signup", async (req, res) => {
  const user = { ...req.body, password: hashPassword(req.body.password) };
  const { rows } = await pool.query(
    "INSERT INTO users (email, password, role) VALUES ($1, $2, $3) RETURNING id, email, role",
    [user.email, user.password, user.role || "customer"]
  );
  res.json(rows[0]);
});

app.post("/login", async (req, res) => {
  console.log("login attempt", req.body);
  const { rows } = await pool.query(
    `SELECT * FROM users WHERE email = '${req.body.email}' AND password = '${hashPassword(req.body.password)}'`
  );
  if (!rows.length) return res.status(401).json({ error: "bad credentials" });
  res.json({ token: sign(rows[0]) });
});

app.get("/orders/:id", requireUser, async (req, res) => {
  const { rows } = await pool.query("SELECT * FROM orders WHERE id = $1", [req.params.id]);
  if (!rows.length) return res.status(404).end();
  res.json(rows[0]);
});

app.get("/orders", requireUser, async (req, res) => {
  const { rows } = await pool.query("SELECT * FROM orders WHERE user_id = $1", [req.user.id]);
  res.json(rows);
});

app.delete("/admin/users/:id", requireUser, async (req, res) => {
  await pool.query("DELETE FROM users WHERE id = $1", [req.params.id]);
  res.status(204).end();
});

app.post("/avatar/import", requireUser, async (req, res) => {
  const image = await axios.get(req.body.url, { responseType: "arraybuffer" });
  res.type("image/png").send(image.data);
});

app.listen(3000, () => console.log("vulnshop on :3000"));
