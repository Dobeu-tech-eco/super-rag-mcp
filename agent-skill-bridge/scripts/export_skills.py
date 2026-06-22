#!/usr/bin/env python3
"""Export every installed Claude SKILL.md into one portable bundle.

Scans Claude skill roots, classifies each SKILL.md as exportable or skipped,
copies exportable skill folders into an output bundle, and writes an index
SKILL.md + manifest.json (+ optional zip). Standard library only.

Usage:
    python export_skills.py --dry-run
    python export_skills.py --out skills-export --zip
    python export_skills.py --roots "C:/a/.claude/skills,C:/b/skills"
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path

INDEX_NAME = "SKILL.md"
MANIFEST_NAME = "manifest.json"
ZIP_NAME = "agent-skill-bundle.zip"
COPY_SUBDIRS = ("references", "scripts", "assets")
MCP_FLAG_THRESHOLD = 2

TARGET_PATHS = [
    ("Grok Build", "{project}/.grok/skills/<name>/  or  {home}/.grok/skills/<name>/"),
    ("Cursor", "{project}/.cursor/skills/<name>/"),
    ("GitHub Copilot CLI", "{home}/.copilot/skills/<name>/"),
    ("OpenAI Codex CLI", "{project}/.agents/skills/<name>/"),
    ("Ona", "{project}/.ona/skills/<name>/"),
    ("Windsurf", "{project}/.windsurf/skills/<name>/"),
]


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body). Minimal YAML-ish parsing, no deps."""
    fm: dict[str, str] = {}
    body = text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            block = text[3:end].strip("\n")
            body = text[end + 4 :].lstrip("\n")
            for line in block.splitlines():
                m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
                if m and not line.startswith(" "):
                    fm[m.group(1).strip()] = m.group(2).strip().strip("\"'")
    return fm, body


def discover_roots(home: Path, project: Path, extra: list[str]) -> list[Path]:
    candidates = [
        project / ".claude" / "skills",
        home / ".claude" / "skills",
        home / ".claude" / "plugins",
    ]
    candidates += [Path(p).expanduser() for p in extra if p.strip()]
    roots, seen = [], set()
    for c in candidates:
        rc = c.resolve()
        if rc.exists() and rc.is_dir() and rc not in seen:
            seen.add(rc)
            roots.append(rc)
    return roots


def find_skill_files(root: Path) -> list[Path]:
    """All SKILL.md under a root (handles plain skill dirs and plugin trees).

    Uses os.walk instead of Path.rglob so that unreadable entries — broken
    symlinks or unsupported reparse points (e.g. foreign-agent skill links
    that raise WinError 1920 on Windows) — are skipped instead of aborting
    the whole scan. Directories that error are silently skipped; individual
    SKILL.md files that later prove unreadable are caught in classify().
    """
    found: list[Path] = []
    for dirpath, _dirnames, filenames in os.walk(root, onerror=lambda _e: None):
        if "SKILL.md" in filenames:
            found.append(Path(dirpath) / "SKILL.md")
    return sorted(found)


def classify(skill_md: Path):
    """Return (status, name, body, mcp_count, reason)."""
    try:
        text = skill_md.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return "skipped", skill_md.parent.name, "", 0, f"unreadable ({e})"
    fm, body = parse_frontmatter(text)
    name = fm.get("name", skill_md.parent.name)
    # command files live under a commands/ dir, not skills
    if any(part == "commands" for part in skill_md.parts):
        return "skipped", name, body, 0, "command file (not a skill)"
    if fm.get("disable-model-invocation", "").lower() == "true":
        return "skipped", name, body, 0, "disable-model-invocation: true"
    if not body.strip():
        return "skipped", name, body, 0, "empty body"
    mcp_count = len(re.findall(r"mcp__[a-zA-Z0-9_]+", body))
    return "exported", name, body, mcp_count, ""


_ILLEGAL_FS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_dirname(name: str, used: set[str]) -> str:
    """Make a skill name safe to use as a folder on every OS.

    Plugin-namespaced skills are named like 'plugin:skill'; ':' (and
    / \\ < > " | ? *) are illegal in Windows paths and would crash mkdir
    (WinError 267). Replace illegal chars, trim trailing dots/spaces, and
    de-duplicate so two sanitized names can't collide.
    """
    safe = _ILLEGAL_FS.sub("-", name).rstrip(". ").strip()
    if not safe:
        safe = "skill"
    candidate, i = safe, 2
    while candidate.lower() in used:
        candidate = f"{safe}-{i}"
        i += 1
    used.add(candidate.lower())
    return candidate


def copy_skill(src_dir: Path, dest_dir: Path) -> None:
    """Copy a skill folder, tolerating unreadable subtrees.

    Individual files/dirs that raise OSError (e.g. broken symlinks or
    unsupported reparse points) are skipped so one bad entry can't abort
    the whole export.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(src_dir / "SKILL.md", dest_dir / "SKILL.md")
    except OSError as e:
        print(f"  warn  {dest_dir.name}: could not copy SKILL.md ({e})")
    for sub in COPY_SUBDIRS:
        s = src_dir / sub
        if s.is_dir():
            try:
                shutil.copytree(s, dest_dir / sub, dirs_exist_ok=True)
            except OSError as e:
                print(f"  warn  {dest_dir.name}/{sub}: partial copy ({e})")


def build_index(exported: list[dict]) -> str:
    lines = [
        "# Exported skills bundle",
        "",
        f"{len(exported)} skill(s) packaged. Each `<name>/` folder installs independently.",
        "",
        "## Install paths by target",
        "",
        "| agent | path |",
        "| --- | --- |",
    ]
    for agent, path in TARGET_PATHS:
        lines.append(f"| {agent} | `{path}` |")
    lines += ["", "## Skills", "", "| name | source | mcp refs |", "| --- | --- | --- |"]
    for e in exported:
        note = str(e["mcp_count"]) + (" (rebind)" if e["mcp_count"] > MCP_FLAG_THRESHOLD else "")
        lines.append(f"| {e['name']} | {e['source_root']} | {note} |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Bundle all installed Claude skills.")
    ap.add_argument("--roots", default="", help="Extra skill dirs, comma-separated.")
    ap.add_argument("--out", default="skills-export", help="Output bundle dir.")
    ap.add_argument("--home", default=str(Path.home()))
    ap.add_argument("--project", default=str(Path.cwd()))
    ap.add_argument("--zip", action="store_true", help="Also write a zip of the bundle.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    home, project = Path(args.home).expanduser(), Path(args.project).expanduser()
    roots = discover_roots(home, project, args.roots.split(","))
    if not roots:
        print("No skill roots found. Pass --roots with the real skills dir(s).", file=sys.stderr)
        return 2

    exported: list[dict] = []
    skipped: list[dict] = []
    seen_names: set[str] = set()

    for root in roots:
        for skill_md in find_skill_files(root):
            status, name, body, mcp_count, reason = classify(skill_md)
            rel = str(skill_md.parent)
            if status == "skipped":
                skipped.append({"name": name, "source": rel, "reason": reason})
                continue
            if name in seen_names:
                skipped.append({"name": name, "source": rel, "reason": "duplicate (first root wins)"})
                continue
            seen_names.add(name)
            exported.append({
                "name": name,
                "src_dir": skill_md.parent,
                "source_root": str(root),
                "mcp_count": mcp_count,
            })

    print(f"Roots scanned: {len(roots)}")
    for r in roots:
        print(f"  - {r}")
    print(f"Exported: {len(exported)} | Skipped: {len(skipped)}")
    for s in skipped:
        print(f"  skip  {s['name']}: {s['reason']}")
    flagged = [e['name'] for e in exported if e['mcp_count'] > MCP_FLAG_THRESHOLD]
    if flagged:
        print(f"MCP rebind needed on target for: {', '.join(flagged)}")

    if args.dry_run:
        print("\n(dry run — nothing written)")
        return 0

    out = Path(args.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    used_dirs: set[str] = set()
    for e in exported:
        e["folder"] = safe_dirname(e["name"], used_dirs)
        copy_skill(e["src_dir"], out / e["folder"])

    (out / INDEX_NAME).write_text(build_index(exported), encoding="utf-8")
    manifest = {
        "exported": [
            {"name": e["name"], "folder": e.get("folder", e["name"]),
             "source_root": e["source_root"], "mcp_references": e["mcp_count"],
             "note": "rebind MCP tools on target" if e["mcp_count"] > MCP_FLAG_THRESHOLD else ""}
            for e in exported
        ],
        "skipped": skipped,
        "roots": [str(r) for r in roots],
    }
    (out / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    if args.zip:
        zip_path = out / ZIP_NAME
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in sorted(out.rglob("*")):
                if p.is_file() and p.name != ZIP_NAME:
                    zf.write(p, p.relative_to(out))
        print(f"Zip written: {zip_path}")

    print(f"\nBundle written to: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
