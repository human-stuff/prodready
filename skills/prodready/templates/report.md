<!-- Template for .prodready/report.md. Replace every <placeholder>. Drop sections that would be empty, except Verdict, Scorecard and Method. -->

# Production readiness: <project name>

`<commit short sha>` · <YYYY-MM-DD> · prodready 1.0.0 · <full audit | partial: areas | quick>

## Verdict

**<score> / 100 · <Ready | Ready after fixes | Not ready | Blocked>**

<critical count> critical, <high count> high, <medium count> medium, <low count> low.
<One line per cap applied, e.g. "Capped at 50: confirmed IDOR in order lookup (AC-01).">

<Two or three sentences, in plain words: the state of the project and the one thing that matters most.>

## Scorecard

| Area | Score | Critical | High | Medium | Low |
|---|---:|---:|---:|---:|---:|
| Access control | <n> | <n> | <n> | <n> | <n> |
| Input and injection | | | | | |
| Secrets and passwords | | | | | |
| Dependencies | | | | | |
| Database | | | | | |
| CI/CD | | | | | |
| Reliability | | | | | |
| Testing | | | | | |
| Containers and config | | | | | |
| Observability | | | | | |
| Privacy | | | | | |
| Performance | | | | | |
| Repo hygiene | | | | | |

<Areas that don't apply: show "n/a" in the Score column with the reason in a footnote.>

## Fix these first

| # | ID | Severity | Location | Problem | Fix | Effort |
|---:|---|---|---|---|---|---|
| 1 | <AC-01> | critical | `<path:line>` | <one line> | <one line> | S |

<Up to 10 rows: every critical, then high findings ordered by area weight. Mark the rows `/prodready fix` can handle with "auto" in the Effort column, for example "S, auto".>

## 12-month outlook

| Component | In use | End of life | Upgrade to |
|---|---|---|---|
| <Node.js> | <20> | <2026-04-30, passed> | <24 LTS> |

<Runtimes, frameworks and core libraries that go out of support before <date + 12 months>, from the dependency auditor. "Nothing goes out of support in the next 12 months" is a valid line.>

## Findings

<One subsection per area that has findings, in scorecard order.>

### Access control · <score>

<area summary>

#### AC-01 · critical · confirmed · <title>

`<path:line>`

```<lang>
<evidence>
```

**Impact:** <impact>

**Fix:** <fix>

**Effort:** <S/M/L> · **Autofix:** <safe/review/manual> <· Related: IDs>

## What is already good

- <Up to 10 items from the auditors' `good` lists, with locations.>

## Appendix

### Route matrix

<From the access auditor.>

### Dependencies to act on

<From the dependency auditor.>

### Personal data inventory

<From the privacy auditor.>

### Tests for critical modules

<From the testing auditor.>

## Method

- Areas: <list>. Auditors ran <in parallel as subagents | sequentially>.
- Scanners: <ran: tool vX, …> · <not installed: …>. Dependency registry lookups: <done | offline>.
- Not checked: <the auditors' not_checked lists, in short>.
- Every critical and high finding was re-read in the source before it went into this report. This is a static review of the repository. It does not replace a penetration test, and it can't see infrastructure that isn't in the repo.
