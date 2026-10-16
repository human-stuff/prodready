# Auditor: performance (PF)

Only problems that will show up at production data sizes and traffic. Do not micro-optimize. N+1 queries and unbounded queries belong to the database auditor; reference them in `related` if relevant.

## Checks

| ID | Check | Fails when |
|---|---|---|
| PF-01 | Pagination | List endpoints return every row, or let the client ask for any page size |
| PF-02 | Blocking work on the request path | In Node: `fs.*Sync`, `crypto.*Sync`, `bcrypt.hashSync`, or large `JSON.parse` in handlers. In async Python: blocking calls (`requests`, `time.sleep`, sync DB drivers) inside `async def`. CPU-heavy work in the web process |
| PF-03 | Caching | Hot, rarely-changing reads (config, feature flags, public pages, product lists) hit the database on every request. Static assets served without cache headers or content hashing |
| PF-04 | Compression | No gzip or brotli for text responses, when no proxy in the repo handles it |
| PF-05 | Frontend weight | Whole-library imports (`import _ from 'lodash'`, `moment` with all locales), no code splitting on large routes, large unoptimized images, render-blocking third-party scripts |
| PF-06 | Over-fetching | Endpoints returning full objects with large or sensitive fields when a few fields are needed. Loading whole tables into memory to filter in code |
| PF-07 | Unbounded growth | In-memory caches, maps or arrays that grow with traffic and are never evicted. Event listeners or intervals added per request and never removed |
| PF-08 | Expensive work repeated | The same external API call, regex compilation or template parsing redone on every request when it could be done once |
| PF-09 | Static file serving | The app server serves large static files or user uploads in production when a CDN, object storage or a reverse proxy should. `low` |
