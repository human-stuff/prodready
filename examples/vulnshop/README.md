# vulnshop

A tiny Express + Postgres shop with **deliberate** security and production problems. It exists so you can see what prodready finds, and so changes to prodready can be checked against a known answer.

**Do not deploy it. Do not reuse its code.**

```text
cd examples/vulnshop
/prodready check     # the readiness review
/prodready env       # finds the JWT secret and database URL that fall back to values in code
/prodready migrate   # flags the destructive migration in migrations/002_cleanup.sql
```

[`EXPECTED.md`](EXPECTED.md) lists every planted problem. A good run finds all of the critical and high ones.

For the pack, verify and deploy stages, [`tests/fixtures/cleanroom-app`](../../tests/fixtures/cleanroom-app) is a small working app that prodready's CI verifies end to end.
