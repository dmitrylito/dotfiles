#!/usr/bin/env python3
# Isolated Chezmoi validation; invoke scripts/test-templates.sh from any directory.
# Requires Python 3.11+, chezmoi, uv, bash, zsh and luac. No personal keys or config needed.

import argparse
import ast
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib


SOURCE = Path(__file__).resolve().parent.parent
FIXTURES = SOURCE / "scripts/fixtures"
ENCRYPTED_FIXTURES = {
    "docker-appdata/homepage/encrypted_private_services.yaml.age": "[]\n",
    "dot_config/opencode/encrypted_opencode.json": "{}\n",
    "dot_config/private_secrets/encrypted_private_shared.env.age": "VALIDATION_ONLY=1\n",
    "dot_config/containers/systemd/private_secrets/encrypted_private_gluetun.env.age": "VALIDATION_ONLY=1\n",
    "scripts/moshi-pairing-token.age": "validation-only-token\n",
    "scripts/codex-config-baseline.toml.age": (FIXTURES / "codex-config.toml").read_text(),
}
COMMAND_TIMEOUT = 120


def run(command, env, cwd, input=None):
    result = subprocess.run(
        command, input=input, text=True, capture_output=True,
        env=env, cwd=cwd, timeout=COMMAND_TIMEOUT,
    )
    if result.returncode:
        raise RuntimeError(f"{command[0]} failed ({result.returncode}):\n{result.stderr[-8000:]}")
    return result.stdout


def check_syntax(name, contents, env, cwd):
    first = contents.splitlines()[0] if contents else ""
    if name.endswith(".py") or (first.startswith("#!") and "python" in first):
        ast.parse(contents, filename=name)
    elif name.endswith(".lua"):
        run(["luac", "-p", "-"], env, cwd, contents)
    elif name in (".aliases", ".zshrc", ".zshenv") or name.endswith(".zsh") or "zsh" in first:
        run(["zsh", "-f", "-n"], env, cwd, contents)
    elif name.endswith(".sh") or (first.startswith("#!") and "sh" in first):
        run(["bash", "-n"], env, cwd, contents)
    elif name.endswith(".toml"):
        tomllib.loads(contents)


def validate_case(profile, work, hostname, staged, scratch, base_env, age):
    label = f"{profile}-{str(work).lower()}-{hostname}"
    home = scratch / label
    config_dir = home / ".config/chezmoi"
    config_dir.mkdir(parents=True)
    env = base_env | {
        "HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_DATA_HOME": str(home / ".local/share"),
        "XDG_STATE_HOME": str(home / ".local/state"),
        "XDG_CACHE_HOME": str(home / ".cache"),
    }
    config = {
        "sourceDir": str(staged), "destDir": str(home),
        "encryption": "age", "useBuiltinAge": True, "age": age,
        "data": {"profile": profile, "work": work},
        "git": {"autoCommit": False, "autoPush": False},
    }
    (config_dir / "chezmoi.json").write_text(json.dumps(config))
    override = json.dumps({"chezmoi": {"hostname": hostname, "os": "darwin" if profile == "mac" else "linux"}})
    command = ["chezmoi", "--no-tty", "--override-data", override]
    print(f"validating {label}", flush=True)
    rendered_config = run(
        command + ["execute-template", "--init"], env, home,
        (staged / ".chezmoi.toml.tmpl").read_text(),
    )
    tomllib.loads(rendered_config)
    state = json.loads(run(command + ["dump", "--format=json"], env, home))
    for name, entry in state.items():
        if "contents" in entry:
            check_syntax(name, entry["contents"], env, home)
    for path in staged.rglob("modify_*"):
        if path.is_file():
            contents = path.read_text()
            if path.suffix == ".tmpl":
                contents = run(command + ["execute-template"], env, home, contents)
            check_syntax(path.name.removesuffix(".tmpl"), contents, env, home)
    plugins = state[".zshrc"]["contents"].split("plugins=(", 1)[1].split(")", 1)[0].split()
    assert ("archlinux" in plugins) == (profile != "mac"), label
    tools = tomllib.loads(state[".config/mise/config.toml"]["contents"])["tools"]
    assert tools["agy"] == "latest" and ("codex" in tools) == (profile != "server"), label
    assert (".config/hypr/hyprland.lua" in state) == (profile == "omarchy"), label
    assert (".config/systemd/user/cer-production-watch.service" in state) == (profile == "server" and hostname == "dlco-prod"), f"{label}: production service routing"
    assert ("ROCR_VISIBLE_DEVICES=0" in state[".zshenv"]["contents"]) == (profile == "omarchy" and hostname == "fcoffice"), label
    settings = json.loads(state[".claude/settings.json"]["contents"])
    assert any(f"under {home} with" in rule for rule in settings["autoMode"]["allow"]), label


def main():
    parser = argparse.ArgumentParser(description="Validate disposable Chezmoi renders without personal configuration.")
    parser.add_argument("--installed-omarchy", action="store_true", help="also validate against the installed Omarchy entrypoint")
    args = parser.parse_args()
    tools = {}
    for tool in ("chezmoi", "uv", "bash", "zsh", "luac"):
        if shutil.which(tool) is None:
            parser.error(f"missing prerequisite: {tool}; see docs/validation.md")
        tools[tool] = shutil.which(tool)
    with tempfile.TemporaryDirectory(prefix="chezmoi-validation-") as directory:
        scratch = Path(directory)
        binaries = scratch / "bin"
        binaries.mkdir()
        for name, path in tools.items():
            (binaries / name).symlink_to(path)
        (binaries / "python3").symlink_to(sys.executable)
        staged = scratch / "source"
        shutil.copytree(SOURCE, staged, symlinks=True, ignore=shutil.ignore_patterns(".git", "__pycache__", ".antigravitycli"))
        found = {
            str(path.relative_to(staged)) for path in staged.rglob("*")
            if path.is_file() and (path.name.startswith("encrypted_") or path.suffix == ".age")
        }
        if found != ENCRYPTED_FIXTURES.keys():
            raise RuntimeError(f"Update encrypted fixture inventory: {found ^ ENCRYPTED_FIXTURES.keys()}")
        home = scratch / "bootstrap"
        home.mkdir()
        env = {
            "PATH": f"{binaries}:/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(home), "LANG": "C.UTF-8",
            "XDG_CONFIG_HOME": str(home / ".config"), "XDG_DATA_HOME": str(home / ".local/share"),
            "XDG_CACHE_HOME": str(home / ".cache"), "XDG_STATE_HOME": str(home / ".local/state"),
            "UV_CACHE_DIR": str(scratch / "uv-cache"), "UV_PYTHON": sys.executable,
            "UV_PYTHON_DOWNLOADS": "never", "OMARCHY_PATH": str(scratch / "omarchy"),
        }
        identity = scratch / "identity.txt"
        run(["chezmoi", "age-keygen", "-o", str(identity)], env, home)
        recipient = run(["chezmoi", "age-keygen", "-y", str(identity)], env, home).strip()
        age = {"identity": str(identity), "recipient": recipient}
        config_dir = home / ".config/chezmoi"
        config_dir.mkdir(parents=True)
        (config_dir / "chezmoi.json").write_text(json.dumps({"encryption": "age", "useBuiltinAge": True, "age": age}))
        for name, contents in ENCRYPTED_FIXTURES.items():
            (staged / name).write_text(run(["chezmoi", "encrypt"], env, home, contents))
        upstream = Path(env["OMARCHY_PATH"]) / "config/hypr/hyprland.lua"
        upstream.parent.mkdir(parents=True)
        shutil.copyfile(FIXTURES / "hyprland.lua", upstream)
        for profile, hostname in (("omarchy", "validation-host"), ("server", "validation-host"), ("mac", "validation-host"), ("omarchy", "fcoffice"), ("server", "dlco-prod")):
            for work in (False, True):
                validate_case(profile, work, hostname, staged, scratch, env, age)
        if args.installed_omarchy:
            installed = Path(os.environ.get("OMARCHY_PATH", "/usr/share/omarchy"))
            contents = run([sys.executable, str(staged / "dot_config/hypr/modify_hyprland.lua")], env | {"OMARCHY_PATH": str(installed)}, home, "")
            check_syntax("hyprland.lua", contents, env, home)
            print(f"installed Omarchy entrypoint validated: {installed}")
    print("all 10 fixture-based profile/role/host combinations passed")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, subprocess.TimeoutExpired, AssertionError, SyntaxError, ValueError) as error:
        sys.exit(str(error))
