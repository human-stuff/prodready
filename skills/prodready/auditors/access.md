# Auditor: access control (AC)

Who can do what. This is where most real breaches in web apps come from, so this brief is the most thorough.

## Start with the route matrix

Before running any check, list every route or handler. Find them by framework:

| Framework | Where to look |
|---|---|
| Express, Koa, Fastify, Hono | `app.get(` `router.post(` `fastify.route(` and `app.use(` for middleware order |
| NestJS | `@Controller` `@Get` `@Post`, and `@UseGuards` at class and method level |
| Next.js | `app/**/route.{ts,js}`, `pages/api/**`, server actions (`"use server"`), `middleware.ts` matchers |
| FastAPI | `@app.get` `@router.post`, `Depends(` for auth dependencies |
| Flask | `@app.route` `@bp.route`, `@login_required` |
| Django / DRF | `urls.py`, views, `permission_classes`, `get_queryset` |
| Rails | `config/routes.rb`, `before_action`, Pundit/CanCan policies |
| Spring | `@RequestMapping` `@GetMapping`, `SecurityFilterChain`, `@PreAuthorize` |
| Go (net/http, gin, echo, chi, fiber) | `HandleFunc` `r.GET(` `e.POST(` and middleware groups |
| Laravel | `routes/*.php`, `->middleware('auth')`, policies |
| GraphQL | resolvers. Auth must be checked per resolver or field, not only at the HTTP endpoint |

For each route, record: method, path, authenticated (yes/no/how), authorization (role, ownership, or none), whether it takes an object ID, and the handler's `path:line`. Put this table in `appendix`. If there are more than 60 routes, include every mutating route and every route that takes an ID, and give a count of the rest.

## Checks

| ID | Check | Fails when |
|---|---|---|
| AC-01 | Object-level authorization (IDOR / BOLA) | A handler loads, updates or deletes a record by a client-supplied ID without checking that it belongs to the caller or the caller's tenant |
| AC-02 | Authentication coverage | A route that reads private data or changes state has no auth, or the auth middleware is mounted after the route |
| AC-03 | Function-level authorization | An admin or staff route checks only that the user is logged in, or reads the role from the request body, a header or a client-editable claim |
| AC-04 | Mass assignment | The request body is passed whole into create or update (`...req.body`, `Model.create(req.body)`, `**data`, `params.permit!`) on a model that has `role`, `isAdmin`, `ownerId`, `balance`, `verified` or similar |
| AC-05 | Tenant isolation | In a multi-tenant app, queries are not scoped by tenant/org, or the tenant ID comes from the client instead of the session |
| AC-06 | JWT handling | `decode` used where `verify` is needed, `algorithms` not pinned, `none` accepted, no `exp`, a weak or hardcoded signing secret, or tokens stored in `localStorage` for a high-value app (medium) |
| AC-07 | Session cookies | Session cookies missing `HttpOnly`, `Secure` or `SameSite`; the session ID is not regenerated on login; logout does not invalidate the server-side session |
| AC-08 | CSRF | Cookie-authenticated, state-changing requests with no CSRF token or `SameSite=Lax/Strict`. N/A for bearer-token-only APIs |
| AC-09 | CORS | `Access-Control-Allow-Origin: *` with credentials, the request's origin reflected without an allowlist, or a regex allowlist that can be bypassed (`/example\.com/` matches `evilexample.com`) |
| AC-10 | Brute force | Login, OTP, password reset and signup have no rate limit or lockout |
| AC-11 | Password reset and email verification | Tokens are guessable, never expire or can be reused. The response reveals whether an account exists. The reset link is built from the `Host` header |
| AC-12 | OAuth / OIDC / SSO | No `state` parameter, `redirect_uri` not validated exactly, no PKCE for public clients, ID token not verified |
| AC-13 | Client-side-only checks | Permissions enforced only in the UI (hidden buttons, route guards) with no matching server check. GraphQL introspection or playground enabled in production |
| AC-14 | Exposed admin and debug surfaces | Debug routes, `/actuator/*`, Django admin at `/admin` with no extra protection, Swagger UI or GraphiQL served in production, test login endpoints |
| AC-15 | API keys and tokens in URLs | Credentials passed in query strings, where they end up in logs and browser history |

## How to check AC-01 properly

For every route that takes an ID (`:id`, `{id}`, `<int:pk>`, `?id=`, or a body field like `orderId`):

1. Find the data access: `findById`, `findUnique`, `get_object_or_404`, `Model.find`, `SELECT ... WHERE id =`.
2. Look for an ownership condition: `userId`/`ownerId`/`tenantId` in the same query, a policy or permission call before it, or a `get_queryset` filtered by `request.user`.
3. If there is none, also check the middleware and decorators in front of the route, and any repository wrapper that scopes queries automatically (Postgres RLS, a scoped default manager, Prisma middleware).
4. Report it only after steps 2 and 3 come up empty. If the record is meant to be public (a blog post, a product), it is not a finding.

## Common false positives

- A route behind a gateway or service mesh that does auth: mark it `needs-review` and name the assumption.
- `SameSite=Lax` cookies with only `GET` reads: not a CSRF finding.
- An internal admin tool behind a VPN: lower the severity by one level, and say why.
