const crypto = require("crypto");
const jwt = require("jsonwebtoken");

const JWT_SECRET = process.env.JWT_SECRET || "secret";

function hashPassword(password) {
  return crypto.createHash("md5").update(password).digest("hex");
}

function requireUser(req, res, next) {
  const token = (req.headers.authorization || "").replace("Bearer ", "");
  try {
    req.user = jwt.decode(token);
    if (!req.user) return res.status(401).json({ error: "unauthorized" });
    next();
  } catch (err) {
    res.status(401).json({ error: "unauthorized" });
  }
}

function sign(user) {
  return jwt.sign({ id: user.id, email: user.email, role: user.role }, JWT_SECRET);
}

module.exports = { hashPassword, requireUser, sign };
