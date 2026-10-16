#!/usr/bin/env python3
"""Validate the prodready repository: manifests, versions, skill frontmatter,
auditor briefs, check IDs and relative links. Exit code 1 on any error."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "prodready"
errors: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


def load_json(rel: str):
    try:
        return json.loads((ROOT / rel).read_text(encoding="utf-8"))
    except FileNotFoundError:
        err(f"{rel}: missing")
    except json.JSONDecodeError as e:
        err(f"{rel}: invalid JSON ({e})")
    return {}


# 1. Manifests and version consistency
manifests = {
    ".claude-plugin/plugin.json": lambda d: d.get("version"),
    ".claude-plugin/marketplace.json": lambda d: (d.get("plugins") or [{}])[0].get("version"),
    ".codex-plugin/plugin.json": lambda d: d.get("version"),
    ".cursor-plugin/plugin.json": lambda d: d.get("version"),
}
versions = {rel: get(load_json(rel)) for rel, get in manifests.items()}
skill_md = (SKILL / "SKILL.md").read_text(encoding="utf-8")
check_md = (SKILL / "references" / "check.md").read_text(encoding="utf-8")
m = re.search(r"`prodready_version` \(`([\d.]+)`\)", check_md)
versions["references/check.md"] = m.group(1) if m else None
m = re.search(r"prodready ([\d.]+)", (SKILL / "templates" / "report.md").read_text(encoding="utf-8"))
versions["templates/report.md"] = m.group(1) if m else None
m = re.search(r"^## ([\d.]+)", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), re.M)
versions["CHANGELOG.md"] = m.group(1) if m else None
if len(set(versions.values())) != 1:
    err("version mismatch: " + ", ".join(f"{k}={v}" for k, v in versions.items()))

for rel in (".claude-plugin/plugin.json",):
    for path in load_json(rel).get("skills") or []:
        if not (ROOT / path).is_dir():
            err(f"{rel}: skills path {path} does not exist")

# 2. SKILL.md frontmatter (Agent Skills spec: name <= 64 chars, description <= 1024)
fm = re.match(r"^---\n(.*?)\n---\n", skill_md, re.S)
if not fm:
    err("SKILL.md: no YAML frontmatter")
else:
    fields = dict(re.findall(r"^([a-z-]+):\s*(.*)$", fm.group(1), re.M))
    if fields.get("name") != "prodready":
        err("SKILL.md: name must be 'prodready'")
    desc = fields.get("description", "")
    if not desc:
        err("SKILL.md: description missing")
    elif len(desc) > 1024:
        err(f"SKILL.md: description is {len(desc)} chars, limit is 1024")
if len(skill_md.splitlines()) > 500:
    err("SKILL.md: over 500 lines; move detail into references/")

# 3. Auditor briefs: every area in the SKILL.md table has a brief, and vice versa
areas = re.findall(r"^\| `([a-z]+)` \| ([A-Z]{2}) \|", skill_md, re.M)
area_names = {a for a, _ in areas}
briefs = {p.stem for p in (SKILL / "auditors").glob("*.md") if not p.stem.startswith("_")}
for missing in sorted(area_names - briefs):
    err(f"area '{missing}' is listed in SKILL.md but auditors/{missing}.md is missing")
for extra in sorted(briefs - area_names):
    err(f"auditors/{extra}.md has no row in the SKILL.md area table")
if len(area_names) != 13:
    err(f"expected 13 areas in SKILL.md, found {len(area_names)}")

# 4. Check IDs: right prefix, unique, numbered without gaps
total = 0
for area, prefix in areas:
    p = SKILL / "auditors" / f"{area}.md"
    if not p.is_file():
        continue
    ids = re.findall(r"^\| ([A-Z]{2})-(\d{2}) \|", p.read_text(encoding="utf-8"), re.M)
    if not ids:
        err(f"auditors/{area}.md: no check rows found")
    nums = []
    for pre, num in ids:
        if pre != prefix:
            err(f"auditors/{area}.md: {pre}-{num} has the wrong prefix (expected {prefix})")
        nums.append(int(num))
    if len(nums) != len(set(nums)):
        err(f"auditors/{area}.md: duplicate check IDs")
    if nums and sorted(nums) != list(range(1, max(nums) + 1)):
        err(f"auditors/{area}.md: check IDs are not numbered 01..{max(nums):02d} without gaps")
    total += len(nums)

for doc in ("CHANGELOG.md", "README.md"):
    for n in re.findall(r"(\d+) checks", (ROOT / doc).read_text(encoding="utf-8")):
        if int(n) != total:
            err(f"{doc} says {n} checks, the briefs define {total}")

# 5. Files referenced from SKILL.md exist
for ref in sorted(set(re.findall(r"`((?:auditors|references|templates|scripts)/[\w./-]+\.(?:md|sh|py))`", skill_md))):
    if "<" in ref:
        continue
    if not (SKILL / ref).is_file():
        err(f"SKILL.md references {ref}, which does not exist")

# 5b. Every stage in the SKILL.md command table names a playbook that exists, and every playbook is used
stages = re.findall(r"^\| `([a-z]+)[^`]*` \| [^|]+\| `references/([a-z]+)\.md` \|", skill_md, re.M)
for stage, ref in stages:
    if not (SKILL / "references" / f"{ref}.md").is_file():
        err(f"stage '{stage}' points at references/{ref}.md, which does not exist")
used = {ref for _, ref in stages} | {"scoring", "config"}
for p in (SKILL / "references").glob("*.md"):
    if p.stem not in used:
        err(f"references/{p.name} is not reachable from the SKILL.md command table")
if len(stages) < 9:
    err(f"expected at least 9 stages with playbooks in SKILL.md, found {len(stages)}")

# 5c. Every bundled script mentioned in the docs exists
for doc in [skill_md] + [p.read_text(encoding="utf-8") for p in (SKILL / "references").glob("*.md")]:
    for script in set(re.findall(r"scripts/([\w-]+\.(?:py|sh))", doc)):
        if not (SKILL / "scripts" / script).is_file():
            err(f"a playbook references scripts/{script}, which does not exist")

# 6. Relative links in markdown files resolve
link_re = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)|<img src=\"([^\"]+)\"|href=\"([^\"#]+)\"")
for md in ROOT.rglob("*.md"):
    if any(part in {".git", "node_modules", ".prodready"} for part in md.parts) or md.name == "prompt.md":
        continue
    text = re.sub(r"```.*?```", "", md.read_text(encoding="utf-8"), flags=re.S)
    for groups in link_re.findall(text):
        target = next((g for g in groups if g), "")
        if not target or re.match(r"^(https?:|mailto:|#|<)", target) or "<" in target:
            continue
        if not (md.parent / target).resolve().exists():
            err(f"{md.relative_to(ROOT)}: broken link {target}")

# 7. vulnshop expected-findings count matches the README
exp = (ROOT / "examples" / "vulnshop" / "EXPECTED.md").read_text(encoding="utf-8")
rows = len(re.findall(r"^\| [A-Z]{2}-\d{2} \|", exp, re.M))
m = re.search(r"with (\d+) planted problems", (ROOT / "README.md").read_text(encoding="utf-8"))
if m and int(m.group(1)) != rows:
    err(f"README says {m.group(1)} planted problems, EXPECTED.md lists {rows}")

if errors:
    print("validation failed:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
print(f"ok: {len(area_names)} areas, {total} checks, {len(stages)} stages, version {versions['references/check.md']}, {rows} planted vulnshop problems")
