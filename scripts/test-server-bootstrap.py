#!/usr/bin/env python3
# Exercise server bootstrap with real chezmoi and fake host/package/network commands.
# Usage: python3 scripts/test-server-bootstrap.py; requires chezmoi, git, Python 3.11+.
# Uses disposable HOME/source directories and generated age fixtures; never provisions the host.
import fcntl
import json
import os
from pathlib import Path
import pty
import shutil
import subprocess
import tempfile
import termios

SOURCE = Path(__file__).resolve().parent.parent
CHEZMOI = shutil.which("chezmoi")

MOCK = r'''#!/usr/bin/python3
import json, os, pathlib, shutil, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ['BOOTSTRAP_CALLS'], 'a') as log:
    log.write(json.dumps([name, *args]) + '\n')
if name == 'sudo':
    if args[:3] == ['tailscale', 'file', 'get']:
        shutil.copyfile(os.environ['BOOTSTRAP_KEY'], pathlib.Path(args[3]) / 'key.txt')
    elif args[0] in ('install', 'rm'):
        os.execv('/usr/bin/' + args[0], args)
    elif args[:2] == ['tailscale', 'up'] and os.environ.get('FAIL_LOGIN'):
        sys.exit(9)
elif name == 'tailscale':
    if args == ['ip', '-4']:
        print('100.64.0.42')
elif name == 'mise':
    if 'api' in args:
        print('123+bootstrap@users.noreply.github.com' if '@users' in args[-1] else 'Bootstrap User')
elif name == 'curl':
    tool = 'herdr' if any('herdr.dev' in arg for arg in args) else 'codex'
    target = pathlib.Path(args[args.index('-o') + 1])
    target.write_text('mkdir -p "$HOME/.local/bin"\nprintf "#!/bin/sh\\necho fixture-version\\n" > "$HOME/.local/bin/' + tool + '"\nchmod +x "$HOME/.local/bin/' + tool + '"\n')
elif name == 'systemctl' and os.environ.get('FAIL_SERVICE'):
    sys.exit(3)
elif name == 'id':
    if args == ['-u'] and os.environ.get('FAKE_ROOT'):
        print('0')
    else:
        os.execv('/usr/bin/id', ['id', *args])
'''


def run_case(name, overrides=None, preview=False, wrong_key=False, installed_tools=False):
    with tempfile.TemporaryDirectory(prefix="chezmoi-bootstrap-test-") as temp:
        root = Path(temp)
        home, source, bins = (root / part for part in ("home", "source", "bin"))
        for path in (home, source / "scripts", source / "dot_config/mise", bins):
            path.mkdir(parents=True)
        env = os.environ | {
            "HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_DATA_HOME": str(home / ".local/share"),
            "XDG_STATE_HOME": str(home / ".local/state"),
            "XDG_CACHE_HOME": str(home / ".cache"),
            "PATH": str(bins) + ":/usr/bin:/bin",
            "BOOTSTRAP_CALLS": str(root / "calls"),
            "BOOTSTRAP_KEY": str(root / "key.txt"),
        } | (overrides or {})
        for key in tuple(env):
            if key.startswith("CHEZMOI_"):
                del env[key]
        subprocess.run(["git", "init", "-q", str(source)], check=True, capture_output=True)
        for path in (".chezmoi.toml.tmpl", "scripts/bootstrap-server.sh", "run_after_executable_finish-server-bootstrap.sh.tmpl"):
            shutil.copyfile(SOURCE / path, source / path)
        (source / ".chezmoiignore").write_text("scripts/\n")
        (source / "dot_config/mise/config.toml.tmpl").write_text("[tools]\n")
        existing_tools = [home / ".local/bin/herdr", home / ".local/bin/codex", home / ".local/share/bob/nvim-bin/nvim"]
        if installed_tools:
            for tool in existing_tools:
                tool.parent.mkdir(parents=True, exist_ok=True)
                tool.write_text("#!/bin/sh\necho existing-version\n")
                tool.chmod(0o700)
        reconcile = source / "scripts/reconcile-packages.sh"
        reconcile.write_text('#!/bin/sh\nprintf \'["reconcile", "%s"]\\n\' "$1" >> "$BOOTSTRAP_CALLS"\n')
        reconcile.chmod(0o700)
        for command in ("sudo", "pacman", "tailscale", "systemctl", "mise", "curl", "id", "bob"):
            path = bins / command
            path.write_text(MOCK)
            path.chmod(0o700)
        subprocess.run([CHEZMOI, "age-keygen", "-o", env["BOOTSTRAP_KEY"]], check=True, capture_output=True, env=env)
        identity = Path(env["BOOTSTRAP_KEY"]).read_text()
        recipient = next(line.split(": ", 1)[1] for line in identity.splitlines() if line.startswith("# public key:"))
        encrypt_config = root / "encrypt.json"
        encrypt_config.write_text(json.dumps({"encryption": "age", "useBuiltinAge": True, "age": {"recipient": recipient}}))
        encrypted = subprocess.run([CHEZMOI, "--config", str(encrypt_config), "encrypt"], input=b"bootstrap fixture\n", capture_output=True, env=env)
        assert encrypted.returncode == 0, encrypted.stderr.decode()
        encrypted = encrypted.stdout
        (source / "scripts/codex-config-baseline.toml.age").write_bytes(encrypted)
        (source / "encrypted_dot_bootstrap-secret.age").write_bytes(encrypted)
        if wrong_key:
            Path(env["BOOTSTRAP_KEY"]).write_text("invalid identity\n")
        config = home / ".config/chezmoi/chezmoi.toml"
        config.parent.mkdir(parents=True)
        config.write_text('[data]\nprofile="server"\nwork=false\n')
        command = [CHEZMOI, "--source", str(source), "--destination", str(home), "--config", str(config), "init", "--apply"]
        if preview:
            command.append("--dry-run")
        master, slave = pty.openpty()

        def controlling_tty():
            os.setsid()
            fcntl.ioctl(0, termios.TIOCSCTTY, 0)

        try:
            with tempfile.TemporaryFile() as output:
                proc = subprocess.Popen(command, env=env, stdin=slave, stdout=output, stderr=output, preexec_fn=controlling_tty)
                os.close(slave)
                os.write(master, b"\n")
                try:
                    code = proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                    raise
                output.seek(0)
                transcript = output.read().decode(errors="replace")
        finally:
            os.close(master)
        calls_path = root / "calls"
        calls = [json.loads(line) for line in calls_path.read_text().splitlines()] if calls_path.exists() else []
        state = home / ".local/state/chezmoi/server-bootstrap"
        if preview:
            assert not calls, calls
            assert not state.exists()
        elif overrides or wrong_key:
            assert code != 0, transcript
            assert not (state / "complete").exists()
            if not (overrides or {}).get("FAIL_SERVICE"):
                assert not (home / ".bootstrap-secret").exists()
        else:
            assert code == 0, transcript
            assert (home / ".bootstrap-secret").read_text() == "bootstrap fixture\n"
            assert (state / "complete").exists()
            assert (home / ".config/chezmoi/key.txt").stat().st_mode & 0o777 == 0o600
            assert ["sudo", "systemctl", "enable", "--now", "sshd.service", "tailscaled.service"] in calls
            assert next(i for i, call in enumerate(calls) if call[0] == "reconcile") < next(i for i, call in enumerate(calls) if call[:4] == ["sudo", "tailscale", "file", "get"])
            if installed_tools:
                assert not any(call[0] in ("curl", "bob") for call in calls), calls
                assert all(tool.read_text() == "#!/bin/sh\necho existing-version\n" for tool in existing_tools)
            assert all("--needed" in call for call in calls if call[:2] == ["sudo", "pacman"])
            assert not any("--force" in call or "-f" in call for call in calls if call[0] == "mise" and "install" in call)
            calls_path.write_text("")
            rerun = subprocess.run(command, env=env, capture_output=True, text=True, timeout=15)
            assert rerun.returncode == 0, rerun.stderr
            assert not calls_path.read_text(), calls_path.read_text()
        print("PASS:", name)


run_case("fresh keyless init installs tools, receives key, applies secrets, finishes, and reruns without provisioning")
run_case("dry-run has no provisioning side effects", preview=True)
run_case("root is rejected", {"FAKE_ROOT": "1"})
run_case("Tailscale login failure stops setup", {"FAIL_LOGIN": "1"})
run_case("wrong age key stops before apply", wrong_key=True)
run_case("failed final service check never marks complete", {"FAIL_SERVICE": "1"})

run_case("existing native tools are preserved without running installers", installed_tools=True)
