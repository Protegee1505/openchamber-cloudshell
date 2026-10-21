#!/usr/bin/env python3
"""Small, dependency-free helpers for the ocs CLI.

Everything here is deliberately stdlib-only: Cloud Shell images change, and
ocs must keep working on a fresh VM before any package is installed.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path


def die(message: str) -> "NoReturn":
    print(f"ocs: {message}", file=sys.stderr)
    raise SystemExit(1)


def rehome(value: str, old_home: str, new_home: str) -> str:
    old_home = old_home.rstrip("/")
    new_home = new_home.rstrip("/")
    if value == old_home:
        return new_home
    if value.startswith(old_home + "/"):
        return new_home + value[len(old_home) :]
    return value


def project_id(path: str) -> str:
    encoded = base64.urlsafe_b64encode(path.encode("utf-8")).decode("ascii").rstrip("=")
    return f"path_{encoded}"


def db_backup(src: str, dst: str) -> None:
    src_path = Path(src)
    if not src_path.exists():
        return
    dst_path = Path(dst)
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    if dst_path.exists():
        dst_path.unlink()
    source = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    target = sqlite3.connect(str(dst_path))
    try:
        source.backup(target)
        target.execute("PRAGMA journal_mode=DELETE")
        target.commit()
    finally:
        target.close()
        source.close()
    os.chmod(dst_path, 0o600)


def db_check(path: str) -> None:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        row = conn.execute("PRAGMA quick_check").fetchone()
        if not row or row[0] != "ok":
            die(f"SQLite integrity check failed: {row!r}")
    finally:
        conn.close()


def text_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    columns = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    result = []
    for _cid, name, ctype, *_rest in columns:
        ctype = (ctype or "").upper()
        if ctype == "" or "TEXT" in ctype or "CHAR" in ctype or "CLOB" in ctype:
            result.append(name)
    return result


def db_migrate(path: str, old_home: str, new_home: str, check: bool = True) -> None:
    if old_home.rstrip("/") == new_home.rstrip("/"):
        if check:
            db_check(path)
        return
    conn = sqlite3.connect(path)
    try:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        for table in tables:
            for column in text_columns(conn, table):
                try:
                    conn.execute(
                        f'UPDATE "{table}" SET "{column}" = replace("{column}", ?, ?) '
                        f'WHERE "{column}" LIKE ?',
                        (old_home.rstrip("/"), new_home.rstrip("/"), f"%{old_home.rstrip('/')}%"),
                    )
                except sqlite3.DatabaseError:
                    # A view/FTS shadow table can be read-only or have unusual
                    # typing. Paths in those tables are not worth risking the
                    # whole restore for.
                    continue
        conn.commit()
        if check:
            row = conn.execute("PRAGMA quick_check").fetchone()
            if not row or row[0] != "ok":
                die(f"SQLite integrity check failed after migration: {row!r}")
    finally:
        conn.close()


def migrate_json_strings(value, old_home: str, new_home: str):
    if isinstance(value, str):
        return rehome(value, old_home, new_home)
    if isinstance(value, list):
        return [migrate_json_strings(item, old_home, new_home) for item in value]
    if isinstance(value, dict):
        return {key: migrate_json_strings(item, old_home, new_home) for key, item in value.items()}
    return value


def settings_migrate(home: Path, old_home: str, new_home: str) -> None:
    openchamber = home / ".config" / "openchamber"
    settings_path = openchamber / "settings.json"
    if not settings_path.exists():
        return
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception as exc:
        die(f"cannot read {settings_path}: {exc}")

    projects_path = openchamber / "projects"
    for project in settings.get("projects", []):
        if not isinstance(project, dict):
            continue
        old_path = project.get("path")
        if not isinstance(old_path, str):
            continue
        new_path = rehome(old_path, old_home, new_home)
        old_id = project.get("id") or project_id(old_path)
        new_id = project_id(new_path)
        if settings.get("activeProjectId") == old_id:
            settings["activeProjectId"] = new_id
        project["path"] = new_path
        project["id"] = new_id
        if new_id != old_id:
            candidates = [
                (projects_path / f"{old_id}.json", projects_path / f"{new_id}.json"),
                (projects_path / old_id, projects_path / new_id),
            ]
            for source, target in candidates:
                if source.exists() and not target.exists():
                    shutil.move(str(source), str(target))
    for key in ("homeDirectory", "lastDirectory"):
        if isinstance(settings.get(key), str):
            settings[key] = rehome(settings[key], old_home, new_home)
    settings = migrate_json_strings(settings, old_home, new_home)
    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")

    for name in ("preferences.json",):
        path = openchamber / name
        if not path.exists():
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            value = migrate_json_strings(value, old_home, new_home)
            path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        except Exception:
            continue

    context_files = projects_path.glob("*/context.json") if projects_path.exists() else []
    for path in context_files:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            value = migrate_json_strings(value, old_home, new_home)
            path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        except Exception:
            continue

    opencode_json = home / ".config" / "opencode" / "opencode.json"
    if opencode_json.exists():
        try:
            value = json.loads(opencode_json.read_text(encoding="utf-8"))
            value = migrate_json_strings(value, old_home, new_home)
            opencode_json.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        except Exception:
            pass


def migrate_tree(tree: Path, old_home: str, new_home: str) -> None:
    home = tree / "home"
    if not home.exists():
        die(f"restore tree is missing home/: {tree}")
    settings_migrate(home, old_home, new_home)
    db = home / ".local" / "share" / "opencode" / "opencode.db"
    if db.exists():
        db_migrate(str(db), old_home, new_home)
    projects_json = home / ".config" / "ocs" / "projects.json"
    if projects_json.exists():
        try:
            value = json.loads(projects_json.read_text(encoding="utf-8"))
            value = migrate_json_strings(value, old_home, new_home)
            projects_json.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        except Exception:
            pass


def projects_export(settings_path: str, output: str) -> None:
    projects = []
    path = Path(settings_path)
    if path.exists():
        try:
            settings = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            settings = {}
        for project in settings.get("projects", []):
            if not isinstance(project, dict) or not isinstance(project.get("path"), str):
                continue
            directory = Path(project["path"]).expanduser()
            git_dir = directory / ".git"
            if not git_dir.exists():
                continue
            try:
                remote = subprocess.check_output(
                    ["git", "-C", str(directory), "remote", "get-url", "origin"],
                    text=True,
                    stderr=subprocess.DEVNULL,
                ).strip()
                branch = subprocess.check_output(
                    ["git", "-C", str(directory), "rev-parse", "--abbrev-ref", "HEAD"],
                    text=True,
                    stderr=subprocess.DEVNULL,
                ).strip()
            except Exception:
                continue
            if remote:
                projects.append(
                    {"path": str(directory), "remote": remote, "branch": branch or "main"}
                )
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(projects, indent=2) + "\n", encoding="utf-8")


def projects_list(path: str) -> None:
    try:
        projects = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return
    for project in projects:
        if not isinstance(project, dict):
            continue
        directory = project.get("path")
        remote = project.get("remote")
        branch = project.get("branch") or "main"
        if directory and remote:
            print(f"{directory}\t{remote}\t{branch}")


def strip_managed_block(lines: list[str], start: str, end: str) -> list[str]:
    output = []
    skipping = False
    for line in lines:
        stripped = line.strip()
        if stripped == start:
            skipping = True
            continue
        if skipping and stripped == end:
            skipping = False
            continue
        if not skipping:
            output.append(line)
    return output


def bashrc_install(path: str) -> None:
    target = Path(path)
    original = target.read_text(encoding="utf-8") if target.exists() else ""
    lines = original.splitlines()
    lines = strip_managed_block(lines, "# >>> ocs >>>", "# <<< ocs <<<")

    # The old writan bootstrap added a PATH line and an auto-start block. Drop
    # exactly those; preserve everything else the user has in .bashrc.
    cleaned = []
    drop_next_path = False
    skip_legacy_opencode = False
    for line in lines:
        stripped = line.strip()
        if "cloudshell-writan:" in stripped:
            drop_next_path = True
            continue
        if drop_next_path:
            drop_next_path = False
            if stripped.startswith("export PATH="):
                continue
        if stripped.startswith("# Keep OpenChamber (and its Private Relay) up"):
            skip_legacy_opencode = True
            continue
        if skip_legacy_opencode:
            if stripped == "fi":
                skip_legacy_opencode = False
            continue
        cleaned.append(line)

    while cleaned and cleaned[-1] == "":
        cleaned.pop()
    cleaned.extend(
        [
            "",
            "# >>> ocs >>>",
            "# Managed by ocs. Do not edit this block; edit ~/.config/ocs/shell.sh instead.",
            'if [ -f "$HOME/.config/ocs/shell.sh" ]; then',
            '  . "$HOME/.config/ocs/shell.sh"',
            "fi",
            "# <<< ocs <<<",
            "",
        ]
    )
    target.write_text("\n".join(cleaned), encoding="utf-8")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        die("helper subcommand required")
    command = argv[1]
    if command == "db-backup":
        db_backup(argv[2], argv[3])
    elif command == "db-check":
        db_check(argv[2])
    elif command == "db-migrate":
        db_migrate(argv[2], argv[3], argv[4])
    elif command == "migrate-tree":
        migrate_tree(Path(argv[2]), argv[3], argv[4])
    elif command == "projects-export":
        projects_export(argv[2], argv[3])
    elif command == "projects-list":
        projects_list(argv[2])
    elif command == "bashrc-install":
        bashrc_install(argv[2])
    else:
        die(f"unknown helper subcommand: {command}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
