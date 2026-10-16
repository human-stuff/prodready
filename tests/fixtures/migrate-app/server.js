// Minimal app used by prodready's CI to test cleanroom.py with a database and migrations.
const http = require("http");

const port = Number(process.env.PORT || 3000);
const server = http.createServer((req, res) => {
  if (req.url === "/healthz") {
    res.writeHead(200, { "content-type": "application/json" });
    return res.end('{"status":"ok"}');
  }
  if (req.url === "/") {
    res.writeHead(200, { "content-type": "text/plain" });
    return res.end(`hello from ${process.env.APP_NAME || "unnamed"}\n`);
  }
  res.writeHead(404);
  res.end();
});

server.listen(port, () => console.log(`listening on ${port}`));
process.on("SIGTERM", () => server.close(() => process.exit(0)));
