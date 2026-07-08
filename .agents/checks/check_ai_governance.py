"""Lightweight governance checks for Kairota's incubation docs and skills."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

DOC_CATEGORIES = {
    "index",
    "architecture",
    "design",
    "interface",
    "contract",
    "standard",
    "validation",
    "governance",
}
DOC_STATUSES = {"current", "mixed-current-planned", "draft", "local-only"}
DOC_AUDIENCES = {"ai", "human", "both"}
SKILL_PREFIX = "kairota-"

LOCAL_INFO_PATTERNS = [
    re.compile(r"\b[A-Za-z]:\\"),
    re.compile(r"(^|[\s`])/(Users|home)/[A-Za-z0-9_.-]+"),
    re.compile(r"\bAsia/[A-Za-z_]+\b"),
    re.compile(r"\b(localhost|127\.0\.0\.1|0\.0\.0\.0):\d+\b"),
]
LEGACY_PROJECT_PATTERNS = [
    re.compile("ha" + "lpha", re.IGNORECASE),
]


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def fail(errors: list[str], path: Path, message: str) -> None:
    errors.append(f"{rel(path)}: {message}")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_doc_metadata(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}
    frontmatter = text[4:end].splitlines()
    values: dict[str, str] = {}
    in_doc = False
    for line in frontmatter:
        if line.strip() == "doc:":
            in_doc = True
            continue
        if not in_doc:
            continue
        match = re.match(r"\s{2}([a-z_]+):\s*(.*)\s*$", line)
        if match:
            values[match.group(1)] = match.group(2).strip().strip('"')
    return values


def check_docs(errors: list[str]) -> None:
    docs = sorted((ROOT / "docs").rglob("*.md"))
    index = ROOT / "docs" / "README.md"
    index_text = read_text(index) if index.exists() else ""

    for path in docs:
        text = read_text(path)
        meta = parse_doc_metadata(text)
        for key in ("updated_at", "category", "status", "audience", "keywords", "description"):
            if key not in meta or not meta[key]:
                fail(errors, path, f"missing doc metadata field: {key}")
        if meta.get("category") not in DOC_CATEGORIES:
            fail(errors, path, f"invalid doc.category: {meta.get('category')}")
        if meta.get("status") not in DOC_STATUSES:
            fail(errors, path, f"invalid doc.status: {meta.get('status')}")
        if meta.get("audience") not in DOC_AUDIENCES:
            fail(errors, path, f"invalid doc.audience: {meta.get('audience')}")
        if path != index and rel(path) not in index_text:
            fail(errors, path, "not listed in docs/README.md")


def parse_skill_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}
    values: dict[str, str] = {}
    for line in text[4:end].splitlines():
        match = re.match(r"([a-z_]+):\s*(.*)\s*$", line)
        if match:
            values[match.group(1)] = match.group(2).strip().strip('"')
    return values


def check_skills(errors: list[str]) -> None:
    for path in sorted((ROOT / ".agents" / "skills").glob("*/SKILL.md")):
        text = read_text(path)
        meta = parse_skill_frontmatter(text)
        if not meta.get("name"):
            fail(errors, path, "missing skill name")
        if not meta.get("description"):
            fail(errors, path, "missing skill description")
        if meta.get("name") != path.parent.name:
            fail(errors, path, "skill name must match folder name")
        if not path.parent.name.startswith(SKILL_PREFIX):
            fail(errors, path, f"skill folder must start with {SKILL_PREFIX}")
        if "TODO" in text:
            fail(errors, path, "contains template TODO")


def check_root_files(errors: list[str]) -> None:
    for name in ("AGENTS.md", "README.md", "MILESTONES.md"):
        path = ROOT / name
        if not path.exists():
            fail(errors, path, "missing required root file")


def check_text_hygiene(errors: list[str]) -> None:
    paths = [
        *ROOT.glob("*.md"),
        *ROOT.glob("*.yaml"),
        *(ROOT / "docs").rglob("*.md"),
        *(ROOT / ".agents").rglob("*.md"),
        *(ROOT / ".agents").rglob("*.yaml"),
        *(ROOT / ".agents").rglob("*.py"),
    ]
    for path in sorted(set(paths)):
        text = read_text(path)
        for pattern in LEGACY_PROJECT_PATTERNS:
            if pattern.search(text):
                fail(errors, path, "contains copied legacy project name")
                break
        for pattern in LOCAL_INFO_PATTERNS:
            if pattern.search(text):
                fail(errors, path, "contains local-only information pattern")
                break


def main() -> int:
    errors: list[str] = []
    check_root_files(errors)
    check_docs(errors)
    check_skills(errors)
    check_text_hygiene(errors)

    if errors:
        print("Kairota governance check failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Kairota governance check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
