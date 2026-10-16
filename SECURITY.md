# Security policy

## Reporting a vulnerability in prodready

prodready runs scripts, builds and starts containers, and can deploy to servers. If you find a way for a scanned repository or a deploy manual to make prodready do something it shouldn't, please report it privately. Examples: running code during `check`, leaking a secret into a report or a manual, following injected instructions, escaping the clean room's isolated compose project, or deploying without confirmation. Report it through [GitHub security advisories](https://github.com/human-stuff/prodready/security/advisories/new) rather than in a public issue.

You should get a reply within 7 days.

## What is intentionally insecure

`examples/vulnshop/` is a deliberately vulnerable demo app. Its problems are on purpose and are listed in `examples/vulnshop/EXPECTED.md`. Please don't report them.

## Scanned code is untrusted

The audit treats the repository it reads as data. Comments or files in a scanned repo that try to instruct the agent ("ignore previous instructions", "mark this as safe") must not change the result. If you find a case where they do, that is a vulnerability. Please report it.
