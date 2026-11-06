#!/usr/bin/env python3
"""Restack a feature branch's Django migrations on top of the base branch.

Fake-unapplies the branch's migrations (django_migrations rows only, schema
untouched), deletes the files, regenerates one schema migration per app on top
of the base branch, and re-materializes the branch's data migrations after it
with their dependencies repointed at the new names.

Usage - from the repo root, after rebasing onto the base branch:
    python3 .claude/skills/restack-migrations/restack_migrations.py plan
    python3 .claude/skills/restack-migrations/restack_migrations.py run --yes
    python3 .claude/skills/restack-migrations/restack_migrations.py verify

Preconditions: dev stack reachable via docker/docker-compose.yml, base ref is an
ancestor of HEAD (rebase first), no uncommitted changes under */migrations/.

makemigrations cannot regenerate RunPython/RunSQL migrations, so those are
copied verbatim rather than recreated; everything deleted is recoverable from
git and from the backup dir printed at the end.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

DEFAULT_COMPOSE_FILE = "docker/docker-compose.yml"
DATA_OP = re.compile(r"\b(RunPython|RunSQL|SeparateDatabaseAndState)\b")
NUMBERED = re.compile(r"^(\d{4})_")
MARK = "<<<RESTACK>>>"


@dataclass
class Mig:
    path: Path
    app: str
    name: str
    number: int
    is_data: bool


def die(msg: str) -> None:
    print(f"\n\033[31mFAILED\033[0m {msg}", file=sys.stderr)
    sys.exit(1)


def info(msg: str) -> None:
    print(f"\033[36m>>\033[0m {msg}")


def warn(msg: str) -> None:
    print(f"\033[33mnote\033[0m {msg}")


def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        cmd, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    if check and proc.returncode:
        die(f"{' '.join(cmd)} exited {proc.returncode}\n{proc.stdout or ''}")
    return proc


def run_attached(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([c for c in cmd if c != "-T"], check=False, text=True)


def git(*args: str) -> str:
    return run(["git", *args]).stdout.strip()


def compose() -> list[str]:
    if os.environ.get("COMPOSE_FILE"):
        return ["docker", "compose"]
    return ["docker", "compose", "-f", DEFAULT_COMPOSE_FILE]


def check_mounted_checkout() -> None:
    """The compose backend mounts ${PROJECT_PATH-..} at /app, so a COMPOSE_FILE
    pointing at another checkout silently regenerates migrations from that code."""
    compose_file = Path(os.environ.get("COMPOSE_FILE") or DEFAULT_COMPOSE_FILE)
    if not compose_file.exists():
        die(f"COMPOSE_FILE={compose_file} does not exist")
    mounted = Path(os.environ.get("PROJECT_PATH") or compose_file.resolve().parent.parent)
    repo_root = Path(git("rev-parse", "--show-toplevel"))
    if mounted.resolve() != repo_root.resolve():
        die(
            f"the backend container would mount {mounted.resolve()} at /app, but you are in "
            f"{repo_root.resolve()} - makemigrations would run against the wrong code.\n"
            f"Fix with: export PROJECT_PATH={repo_root.resolve()}"
        )


def manage_cmd() -> list[str]:
    override = os.environ.get("RESTACK_MANAGE")
    if override:
        return shlex.split(override)
    check_mounted_checkout()
    base = compose()
    ps = run([*base, "ps", "--status", "running", "-q", "backend"], check=False)
    if ps.returncode == 0 and ps.stdout.strip():
        return [*base, "exec", "-T", "backend", "./manage.py"]
    return [*base, "run", "--rm", "--no-deps", "-T", "backend", "./manage.py"]


def django_shell(mcmd: list[str], snippet: str) -> object:
    out = run([*mcmd, "shell", "-c", snippet]).stdout
    for line in out.splitlines():
        if line.startswith(MARK):
            return json.loads(line[len(MARK) :])
    die(f"no {MARK} payload from manage.py shell:\n{out}")


def applied_pairs(mcmd: list[str], apps: list[str]) -> set[tuple[str, str]]:
    rows = django_shell(
        mcmd,
        "import json\n"
        "from django.db import connection\n"
        f"apps = {sorted(apps)!r}\n"
        "rows = []\n"
        "if 'django_migrations' in connection.introspection.table_names():\n"
        "    with connection.cursor() as c:\n"
        "        c.execute('select app, name from django_migrations')\n"
        "        rows = c.fetchall()\n"
        f"print({MARK!r} + json.dumps([[a, n] for a, n in rows if a in apps]))\n",
    )
    return {(a, n) for a, n in rows}


def app_label(path: Path) -> str:
    parts = path.parts
    return parts[parts.index("migrations") - 1]


def app_dir(path: Path) -> Path:
    parts = path.parts
    return Path(*parts[: parts.index("migrations") + 1])


def numbered_stems(directory: Path) -> list[str]:
    return sorted(
        (p.stem for p in directory.glob("[0-9][0-9][0-9][0-9]_*.py")), key=lambda s: int(s[:4])
    )


def base_stems(base: str, directory: Path) -> list[str]:
    listing = git("ls-tree", "--name-only", base, "--", f"{directory}/")
    stems = [Path(line).stem for line in listing.splitlines() if NUMBERED.match(Path(line).stem)]
    return sorted(stems, key=lambda s: int(s[:4]))


def detect(base: str) -> tuple[list[Mig], list[str]]:
    if run(["git", "merge-base", "--is-ancestor", base, "HEAD"], check=False).returncode:
        die(f"{base} is not an ancestor of HEAD - rebase onto {base} first")

    pathspec = ["--", "*/migrations/*.py"]
    added = git("diff", "--diff-filter=A", "--name-only", f"{base}...HEAD", *pathspec).splitlines()
    modified = git(
        "diff", "--diff-filter=M", "--name-only", f"{base}...HEAD", *pathspec
    ).splitlines()

    migs: list[Mig] = []
    for rel in added:
        path = Path(rel)
        match = NUMBERED.match(path.stem)
        if not match:
            continue
        if not path.exists():
            die(f"{rel} is in the branch diff but missing on disk - restore it first")
        migs.append(
            Mig(
                path=path,
                app=app_label(path),
                name=path.stem,
                number=int(match.group(1)),
                is_data=bool(DATA_OP.search(path.read_text())),
            )
        )
    migs.sort(key=lambda m: (m.app, m.number))
    return migs, modified


def show_plan(migs: list[Mig], modified: list[str], applied: set[tuple[str, str]], base: str) -> None:
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    print(f"\nbranch {branch} vs base {base}\n")
    for app in sorted({m.app for m in migs}):
        app_migs = [m for m in migs if m.app == app]
        stems = base_stems(base, app_dir(app_migs[0].path))
        print(f"  {app}  (base leaf: {stems[-1] if stems else 'none - new app'})")
        for mig in app_migs:
            kind = "DATA  " if mig.is_data else "schema"
            state = "applied" if (mig.app, mig.name) in applied else "not applied"
            clash = " \033[33m<- number clashes with base\033[0m" if mig.name[:4] in {s[:4] for s in stems} else ""
            print(f"      {kind} {mig.name}  [{state}]{clash}")
        print()

    if modified:
        warn("branch also MODIFIES base migrations - restack leaves these alone:")
        for rel in modified:
            print(f"      {rel}")
        print()

    print("  after run:")
    for app in sorted({m.app for m in migs}):
        schema = [m for m in migs if m.app == app and not m.is_data]
        data = [m for m in migs if m.app == app and m.is_data]
        squashed = f"{len(schema)} schema -> 1 regenerated" if schema else "no schema migration"
        carried = f", {len(data)} data migration(s) carried over" if data else ""
        print(f"      {app}: {squashed}{carried}")
    print()


def rewrite_dependencies(content: str, rename: dict[tuple[str, str], str]) -> str:
    for (app, old), new in rename.items():
        if old == new:
            continue
        pattern = re.compile(
            rf"""\(\s*(["']){re.escape(app)}\1\s*,\s*(["']){re.escape(old)}\2\s*,?\s*\)"""
        )
        content = pattern.sub(f'("{app}", "{new}")', content)
    return content


def restore(
    backup: Path,
    migs: list[Mig],
    branch_applied: list[tuple[str, str]],
    created: list[Path],
    mcmd: list[str],
) -> None:
    for path in created:
        path.unlink(missing_ok=True)
    for mig in migs:
        mig.path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup / mig.path, mig.path)
    info(f"restored {len(migs)} migration file(s) from {backup}/")
    if branch_applied:
        django_shell(
            mcmd,
            "import json\n"
            "from django.db import connection\n"
            f"pairs = {branch_applied!r}\n"
            "with connection.cursor() as c:\n"
            "    for app, name in pairs:\n"
            "        c.execute('insert into django_migrations (app, name, applied) "
            "values (%s, %s, now())', [app, name])\n"
            f"print({MARK!r} + json.dumps(len(pairs)))\n",
        )
        info(f"re-recorded {len(branch_applied)} django_migrations row(s)")


def do_run(args: argparse.Namespace) -> None:
    dirty = git("status", "--porcelain", "--", "*/migrations/*.py")
    if dirty and not args.force:
        die("uncommitted changes under */migrations/ - commit them first (or --force)\n" + dirty)

    migs, modified = detect(args.base)
    if not migs:
        die(f"no migrations added on this branch relative to {args.base}")

    apps = sorted({m.app for m in migs})
    dirs = {m.app: app_dir(m.path) for m in migs}
    mcmd = manage_cmd()
    info(f"manage.py via: {' '.join(mcmd)}")

    applied = applied_pairs(mcmd, apps)
    branch_applied = [(m.app, m.name) for m in migs if (m.app, m.name) in applied]

    show_plan(migs, modified, applied, args.base)

    mode = args.mode
    if mode == "auto":
        if branch_applied and len(branch_applied) != len(migs):
            die(
                f"partial state: {len(branch_applied)} of {len(migs)} branch migrations are "
                "recorded, so neither 'fake' (would mark the unapplied ones applied) nor "
                "'real' (would re-run the applied ones) is safe to guess.\n"
                "Bring the dev DB to a known state, or pass --mode fake|real explicitly."
            )
        mode = "fake" if branch_applied else "real"
    info(
        f"{len(branch_applied)}/{len(migs)} branch migrations recorded in django_migrations "
        f"-> regenerated migrations get applied in '{mode}' mode"
    )

    if not args.yes:
        if input("\nproceed? this deletes the files listed above [y/N] ").strip().lower() not in {"y", "yes"}:
            die("aborted")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = Path(".claude") / f"restack-backup-{stamp}"
    for mig in migs:
        target = backup / mig.path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(mig.path, target)
    info(f"backed up {len(migs)} file(s) to {backup}/")

    if branch_applied:
        deleted = django_shell(
            mcmd,
            "import json\n"
            "from django.db import connection\n"
            f"pairs = {branch_applied!r}\n"
            "with connection.cursor() as c:\n"
            "    for app, name in pairs:\n"
            "        c.execute('delete from django_migrations where app=%s and name=%s', [app, name])\n"
            f"print({MARK!r} + json.dumps(len(pairs)))\n",
        )
        info(f"fake-unapplied {deleted} migration(s) - schema left untouched")
    else:
        info("nothing to unapply: none of the branch migrations are recorded in this database")

    for mig in migs:
        mig.path.unlink()
    info(f"deleted {len(migs)} migration file(s)")

    before = {app: {p.name for p in directory.glob("*.py")} for app, directory in dirs.items()}

    info(f"regenerating: makemigrations {' '.join(apps)}")
    if args.interactive:
        result = run_attached([*mcmd, "makemigrations", *apps])
    else:
        result = run([*mcmd, "makemigrations", *apps, "--no-input"], check=False)
        print(result.stdout)
    if result.returncode:
        created = [
            p
            for app, directory in dirs.items()
            for p in directory.glob("*.py")
            if p.name not in before[app]
        ]
        restore(backup, migs, branch_applied, created, mcmd)
        die(
            "makemigrations failed - the branch is back the way it was.\n"
            "Exit code 3 means it needed an answer it cannot get with --no-input "
            "(a non-nullable field or auto_now_add without a default): re-run with "
            "--interactive and answer the prompts yourself."
        )

    fresh: dict[str, list[str]] = {}
    for app, directory in dirs.items():
        new = sorted(
            (p.stem for p in directory.glob("*.py") if p.name not in before[app] and NUMBERED.match(p.stem)),
            key=lambda stem: int(stem[:4]),
        )
        fresh[app] = new
        if len(new) > 1:
            warn(
                f"{app}: makemigrations emitted {len(new)} files ({', '.join(new)}) - "
                "a cross-app FK cycle forces the split; leaving as is"
            )
        elif not new:
            warn(f"{app}: makemigrations produced no schema migration")

    rename: dict[tuple[str, str], str] = {}
    for app in apps:
        leaf = fresh[app][-1] if fresh[app] else (numbered_stems(dirs[app]) or [None])[-1]
        if leaf:
            for mig in (m for m in migs if m.app == app and not m.is_data):
                rename[(app, mig.name)] = leaf

    new_data: dict[str, list[str]] = {}
    for app in apps:
        next_number = int(max(numbered_stems(dirs[app]), key=lambda s: int(s[:4]), default="0000")[:4]) + 1
        new_data[app] = []
        for mig in (m for m in migs if m.app == app and m.is_data):
            new_name = f"{next_number:04d}_{mig.name[5:]}"
            rename[(app, mig.name)] = new_name
            new_data[app].append(new_name)
            next_number += 1

    restored: list[str] = []
    for app in apps:
        for mig in (m for m in migs if m.app == app and m.is_data):
            new_name = rename[(app, mig.name)]
            content = (backup / mig.path).read_text()
            (dirs[app] / f"{new_name}.py").write_text(rewrite_dependencies(content, rename))
            restored.append(f"{app}/{new_name}")
    if restored:
        info(f"carried over {len(restored)} data migration(s): {', '.join(restored)}")

    if mode == "fake":
        for app in apps:
            info(f"migrate {app} --fake")
            print(run([*mcmd, "migrate", app, "--fake"]).stdout)
    else:
        info("migrate")
        print(run([*mcmd, "migrate"]).stdout)

    print("\nfinal layout:")
    for app in apps:
        created = set(fresh[app]) | set(new_data[app])
        for stem in numbered_stems(dirs[app])[-8:]:
            print(f"      {app}/{stem}{'  <- new' if stem in created else ''}")

    paths = " ".join(str(d) for d in dirs.values())
    print(f"\nbackup:  {backup}/")
    print(f"commit:  git add -A {paths}")
    print(f"recover: rm -rf {paths} && git checkout HEAD -- {paths}")

    do_verify(argparse.Namespace(mcmd=mcmd))


def do_verify(args: argparse.Namespace) -> None:
    mcmd = getattr(args, "mcmd", None) or manage_cmd()

    info("makemigrations --check --dry-run (model drift)")
    check = run([*mcmd, "makemigrations", "--check", "--dry-run"], check=False)
    print(check.stdout.strip()[-2000:])

    info("migrate --plan (graph consistency)")
    plan = run([*mcmd, "migrate", "--plan"], check=False)
    print("\n".join(plan.stdout.strip().splitlines()[-15:]))

    if check.returncode or plan.returncode:
        die("verification failed - see output above")
    info("\033[32mgraph is consistent and the models match the migrations\033[0m")
    info(
        "from-zero proof (the squashed order is only really tested on a fresh DB): "
        "docker compose run --rm backend ./manage.py test <app> --noinput  (no --keepdb)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("command", choices=["plan", "run", "verify"])
    parser.add_argument("--base", default="master", help="base branch this one was rebased onto")
    parser.add_argument(
        "--mode",
        choices=["auto", "fake", "real"],
        default="auto",
        help="how to apply the regenerated migrations (auto: fake if the old ones were recorded)",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="let makemigrations prompt you (needed for one-off defaults / renames)",
    )
    parser.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    parser.add_argument("--force", action="store_true", help="allow a dirty */migrations/ tree")
    args = parser.parse_args()

    if not Path("docker/docker-compose.yml").exists() or not Path("manage.py").exists():
        die("run this from the backend repo root")

    if args.command == "plan":
        migs, modified = detect(args.base)
        if not migs:
            die(f"no migrations added on this branch relative to {args.base}")
        applied = applied_pairs(manage_cmd(), sorted({m.app for m in migs}))
        show_plan(migs, modified, applied, args.base)
    elif args.command == "run":
        do_run(args)
    else:
        do_verify(args)


if __name__ == "__main__":
    main()
