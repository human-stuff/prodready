# Auditor: testing (TS)

Not "is coverage at 80%" but "would the tests catch a break in the parts that matter". Do not run the tests. Read them.

## Checks

| ID | Check | Fails when |
|---|---|---|
| TS-01 | Tests exist and are wired up | No test files, no test runner configured, or no test script. No tests at all: `high` |
| TS-02 | Tests run in CI | Tests exist but no CI job runs them |
| TS-03 | Critical paths covered | No tests touch auth (login, signup, reset), permission checks, payments or billing, or the main write paths. List which critical modules have no tests |
| TS-04 | Authorization tests | Nothing tests that user A cannot read or change user B's data, or that a normal user cannot call admin routes. If the access auditor is likely to find IDOR, this is how it would have been caught |
| TS-05 | Integration or end-to-end tests | Only unit tests with everything mocked. The main user flows are never exercised against a real (test) database or HTTP server |
| TS-06 | Disabled tests | `.skip`, `xit`, `xdescribe`, `@pytest.mark.skip`, `@Disabled`, `t.Skip()` without a linked reason. Report the count and the most important ones |
| TS-07 | Flaky patterns | Fixed `sleep`s, real network calls to third parties, tests that depend on order or shared state, current-time dependence with no clock control |
| TS-08 | Test isolation | Tests that point at a shared or production database, use real credentials, or send real email or payments |
| TS-09 | Coverage visibility | No coverage configuration at all. If a coverage report is committed or configured, read the numbers and report the critical files below 50%. `low` on its own |

## Appendix

A table of critical modules (from the context map and the route matrix) and whether tests cover them: module, `path`, tests (`yes`/`partial`/`no`), the test file.
