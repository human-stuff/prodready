# Auditor: repo hygiene (HY)

What a new engineer, or the on-call person, needs in order to run and fix this project. Most findings here are `low` or `medium`.

## Checks

| ID | Check | Fails when |
|---|---|---|
| HY-01 | README | No README, or no instructions for installing, configuring and running the project locally |
| HY-02 | Env var documentation | Compare every env var the code reads (`process.env.X`, `os.environ`, `os.getenv`, `ENV[...]`, `System.getenv`, `viper`, config schemas) with `.env.example` or the docs. List the undocumented ones. `medium` if required variables are undocumented |
| HY-03 | LICENSE | No LICENSE file in a public or open-source repo |
| HY-04 | Security policy | No `SECURITY.md` or other way to report a vulnerability, in a public repo |
| HY-05 | Ops docs | No notes on how to deploy, roll back, run migrations or restore a backup |
| HY-06 | Lint and format | No linter or formatter config |
| HY-07 | Type checking | For TypeScript: `strict` off, or many `any`/`@ts-ignore` in critical modules. For Python: no type checker on a large codebase. `low` |
| HY-08 | Leftovers | `console.log`/`print` debugging, commented-out code blocks, `TODO`/`FIXME`/`HACK` in auth, payment and data paths. Give counts and the worst examples |
| HY-09 | Committed build output and junk | `dist/`, `build/`, `.DS_Store`, coverage output, `node_modules`, or large binaries tracked in git |
| HY-10 | Versioning | No tags, releases or CHANGELOG, so nobody can tell what is deployed. `low` |
