# Scoring

The score is there so you can see what to fix first and whether a release improved anything. It is not a certification. The same findings always give the same score.

## Area score

Each area starts at 100. Subtract a penalty for every finding, multiplied by a confidence factor:

| Severity | Penalty | | Confidence | Factor |
|---|---|---|---|---|
| critical | 30 | | confirmed | 1.0 |
| high | 12 | | likely | 0.75 |
| medium | 5 | | needs-review | 0.5 |
| low | 1 | | | |

`area score = max(0, round(100 - sum(penalty × factor)))`

When one check has many findings with the same fix (the same missing timeout in 40 places), count it once at its highest severity, plus 1 point for each extra location, up to 10 extra points.

An area with `applicable: false` gets no score and is left out of the overall score.

## Overall score

The weighted average of the applicable areas, with the weights rescaled to add up to 100:

| Area | Weight | | Area | Weight |
|---|---|---|---|---|
| access | 15 | | reliability | 7 |
| input | 15 | | testing | 6 |
| secrets | 12 | | container | 5 |
| dependencies | 10 | | observability | 5 |
| database | 8 | | privacy | 4 |
| cicd | 8 | | performance | 3 |
| | | | hygiene | 2 |

For a partial audit (`audit <areas>` or `--quick`), compute the overall score over the areas that ran, and label it **partial** everywhere it appears.

## Caps

An average can hide one fatal problem, so caps limit the overall score. Apply every cap that matches, keep the lowest, and list each one in the report.

| Condition | Maximum score |
|---|---|
| A live-looking secret is committed or in git history (critical in SC-01, SC-02, SC-03) | 40 |
| Passwords stored in plaintext or with a fast hash (critical in SC-05) | 40 |
| A confirmed critical finding in `access` or `input` | 50 |
| Any other critical finding | 60 |
| No tests at all (TS-01 failed) | 70 |
| No CI pipeline (CI-01 failed) | 75 |
| The runtime is already past end of life (DP-06 high) | 80 |

## Accepted risks

Findings accepted in `prodready.yml` (and not past their `until` date) still lower their area score, because the risk is still there. They don't trigger caps, and they don't block `ship` or `deploy`. The report marks them **accepted**, with the reason.

## Verdict

| Score | Verdict | Meaning |
|---|---|---|
| 85–100 with no critical or high | **Ready** | Ship it, and work through the mediums |
| 70–100 with no critical | **Ready after fixes** | Fix the high findings first, then ship |
| 50–69, or any critical | **Not ready** | Real risks. Fix the criticals and re-run |
| 0–49 | **Blocked** | Do not deploy this to the internet yet |

The verdict is the worse of what the score and the findings say. A score of 88 with one high finding is **Ready after fixes**.
