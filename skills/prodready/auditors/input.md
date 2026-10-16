# Auditor: input handling and injection (IN)

Untrusted input reaching something that interprets it. For every finding, trace the value from where it enters to where it is used.

**Sources:** `req.body`, `req.query`, `req.params`, headers, cookies, `request.GET/POST/json`, form data, uploaded file names and contents, webhook payloads, message queue payloads, URL fragments read by client code, and data stored earlier from any of these (second-order).

## Checks

| ID | Check | Look for |
|---|---|---|
| IN-01 | SQL injection | Strings built into queries: template literals or `+` in `query(`, f-strings or `%` in `execute(`, `raw(`, `$queryRawUnsafe`, `knex.raw` with interpolation, `sequelize.query` without `replacements`, `.extra(`, `RawSQL`, `fmt.Sprintf` into `db.Query`, `ORDER BY` built from input |
| IN-02 | NoSQL injection | A request object passed as a Mongo filter (`find(req.body)`, `{ user: req.body.user }` where `user` can be `{"$ne": null}`), `$where`, `mapReduce` with input |
| IN-03 | OS command injection | `exec(`, `execSync(`, `spawn(..., {shell: true})`, `subprocess.*(shell=True)`, `os.system`, `os.popen`, backticks, `Runtime.exec` with concatenated input |
| IN-04 | XSS | `dangerouslySetInnerHTML`, `v-html`, `innerHTML =`, `insertAdjacentHTML`, `document.write`, `{{ x \| safe }}`, `mark_safe`, `html_safe`, `raw`, `<%- %>` in EJS, `{!! !!}` in Blade, autoescape turned off, `href={userUrl}` without a scheme check (`javascript:`) |
| IN-05 | SSRF | `fetch`, `axios`, `requests`, `http.Get`, `urllib` or webhook senders called with a user-supplied URL or host, with no allowlist and no block on private, link-local and metadata addresses (`169.254.169.254`) |
| IN-06 | Path traversal | `fs.readFile`, `sendFile`, `open(`, `send_file`, `File(` or `os.path.join` with input and no normalize-and-check against a base directory. Zip extraction without checking entry paths (zip slip) |
| IN-07 | File upload | No type check (or extension only), no size limit, stored under the web root or served with the user's `Content-Type`, original file name used on disk, SVG or HTML uploads served from the main origin |
| IN-08 | Unsafe deserialization and eval | `pickle.loads`, `yaml.load` without `SafeLoader`, `marshal`, Java `ObjectInputStream`, PHP `unserialize`, `node-serialize`, `eval`, `new Function`, `vm.runInContext` on input |
| IN-09 | Template injection | `render_template_string`, `Template(user_input)`, `ejs.render(input)`, Handlebars or Jinja compiling user-provided templates |
| IN-10 | Open redirect | `res.redirect(req.query.next)`, `redirect(request.GET['next'])` and similar with no same-origin or allowlist check |
| IN-11 | Validation at the boundary | Request bodies used without a schema (zod, joi, yup, class-validator, pydantic, marshmallow, Bean Validation, strong params). Missing on a few minor routes is `low`; missing everywhere on a public API is `medium` |
| IN-12 | Security headers | No CSP, HSTS, `X-Content-Type-Options` or `frame-ancestors`/`X-Frame-Options` on HTML responses (helmet, `SecurityMiddleware`, `secure_headers`, or the proxy config if it is in the repo) |
| IN-13 | XXE | XML parsers with external entities or DTDs enabled (`libxml` `noent`, `DocumentBuilderFactory` defaults, `lxml` with `resolve_entities`) |
| IN-14 | ReDoS | `new RegExp(input)`, or nested-quantifier patterns such as `(a+)+` applied to request input |
| IN-15 | Prototype pollution | Deep merge or `set(obj, path, value)` of user objects (`lodash.merge`, `_.set`, hand-written recursive merges) in JS/TS |
| IN-16 | Error and debug leakage | Stack traces or SQL errors returned to clients, `DEBUG = True`, `app.run(debug=True)`, the Express default error handler in production, `display_errors=On` |
| IN-17 | Webhook signature verification | Incoming webhooks (Stripe, GitHub, Slack, Twilio, payment providers) processed without checking the signature, or compared with `==` instead of a constant-time comparison |

## Severity guide

- Reachable from an unauthenticated route: `critical` for IN-01/02/03/05/08/09, `high` for IN-04/06/07.
- Reachable only by authenticated users: one level lower, unless any user can sign up.
- Reachable only by admins: `medium`, and say so.
- Not reachable from any route (dead code, scripts): `low`.

## Common false positives

- ORM query builders with bound parameters (`where: { id }`, `filter(id=x)`, `?` placeholders) are safe. Do not report them.
- A `raw()` call whose only interpolated values are constants or allowlisted column names is safe, if you can see the allowlist.
- React escapes `{value}` by default. Only report the explicit escape hatches.
