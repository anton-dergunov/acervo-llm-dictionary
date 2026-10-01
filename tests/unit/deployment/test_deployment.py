from __future__ import annotations

import json
import os
import re
import subprocess
import tarfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
# What the fake `docker` reports as every container's healthcheck. One argument holds spaces, because
# the real ones do, and the installer has to hand it over as one word.
PROBE = ("CMD", "python", "-c", "import sys; sys.exit(0)")


def runnable_remote_helper(tmp_path: Path) -> Path:
    source = (REPO_ROOT / "deploy/acervo/remote-helper.sh").read_text(encoding="utf-8")
    source = source.replace('[ "$(id -u)" -eq 0 ] || {', "true || {", 1)
    helper = tmp_path / "deploy-acervo"
    helper.write_text(source, encoding="utf-8")
    helper.chmod(0o755)
    return helper


def fake_tailscale_path(tmp_path: Path, initial_status: str) -> tuple[Path, Path, Path]:
    bin_dir = tmp_path / "tailscale-bin"
    bin_dir.mkdir()
    state = tmp_path / "tailscale-status"
    state.write_text(initial_status, encoding="utf-8")
    log = tmp_path / "tailscale-log"
    tailscale = bin_dir / "tailscale"
    tailscale.write_text(
        "#!/bin/sh\n"
        "if [ \"$1 $2\" = 'serve status' ]; then cat \"$ACERVO_TEST_TS_STATE\"; exit 0; fi\n"
        "printf '%s\\n' \"$*\" >>\"$ACERVO_TEST_TS_LOG\"\n"
        "case \"$4\" in\n"
        "  --https=443) address=https://server.example.com ;;\n"
        "  --https=*) address=https://server.example.com:${4#--https=} ;;\n"
        "  *) exit 2 ;;\n"
        "esac\n"
        "printf '\\n%s (tailnet only)\\n|-- / proxy %s\\n' \"$address\" \"$5\" "
        ">>\"$ACERVO_TEST_TS_STATE\"\n",
        encoding="utf-8",
    )
    tailscale.chmod(0o755)
    return bin_dir, state, log


def fake_tailscale_service_path(
    tmp_path: Path, initial_status: str, version: str = "1.86.0"
) -> tuple[Path, Path, Path]:
    """A Tailscale that speaks the service form of `serve`, which reports through `status --json`."""
    bin_dir = tmp_path / "tailscale-service-bin"
    bin_dir.mkdir()
    state = tmp_path / "tailscale-service-status"
    state.write_text(initial_status, encoding="utf-8")
    log = tmp_path / "tailscale-service-log"
    tailscale = bin_dir / "tailscale"
    tailscale.write_text(
        "#!/bin/sh\n"
        f"if [ \"$1\" = version ]; then printf '{version}\\n  commit: abc\\n'; exit 0; fi\n"
        "if [ \"$1 $2\" = 'serve status' ]; then cat \"$ACERVO_TEST_TS_STATE\"; exit 0; fi\n"
        "printf '%s\\n' \"$*\" >>\"$ACERVO_TEST_TS_LOG\"\n"
        "case \"$2\" in\n"
        "  --service=svc:*) service=${2#--service=} ;;\n"
        "  *) exit 2 ;;\n"
        "esac\n"
        # The proxy target is the final argument, wherever the flags before it land.
        "for target; do :; done\n"
        "printf '{\"%s\":{\"proxy\":\"%s\"}}\\n' \"$service\" \"$target\" >>\"$ACERVO_TEST_TS_STATE\"\n",
        encoding="utf-8",
    )
    tailscale.chmod(0o755)
    return bin_dir, state, log


def fake_docker_path(
    tmp_path: Path,
    *,
    existing: tuple[str, ...] = (),
    published: bool = True,
) -> Path:
    """A `docker` that answers the questions the installer asks it.

    `existing` names containers `inspect` should find, and finds them stopped — which is the state a
    create that could not bind its port leaves behind. `published` is whether `port` reports a host
    binding; without one a container can be healthy and still unreachable, which is the failure the
    installer now refuses to report as success. Every container's healthcheck is `PROBE`, and it
    passes unless `ACERVO_TEST_DOCKER_FAIL_PROBE` names the container. `sleep` is a no-op, so a wait
    that never ends gives up at once rather than a minute later.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    sleep = bin_dir / "sleep"
    sleep.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    sleep.chmod(0o755)
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        'known_containers="' + " ".join(existing) + '"\n'
        '[ -z "${ACERVO_TEST_DOCKER_LOG:-}" ] || echo "$*" >>"$ACERVO_TEST_DOCKER_LOG"\n'
        'case " $* " in\n'
        "  *Healthcheck.Test*) printf '%s\\n' " + " ".join(f"'{arg}'" for arg in PROBE) + "; exit 0 ;;\n"
        # `exec`, the container, then the probe less its "CMD": any other count is a word split wrong.
        f'  *" exec "*) [ "$#" -eq {len(PROBE) + 1} ] || exit 3\n'
        '    [ "$2" != "${ACERVO_TEST_DOCKER_FAIL_PROBE:-}" ] || exit 1; exit 0 ;;\n'
        # A one-shot `compose run` that fails, which is how a converter that refuses looks from here.
        '  *" run "*) [ -z "${ACERVO_TEST_DOCKER_FAIL_RUN:-}" ] || exit 7 ;;\n'
        '  *" port "*) ' + ('echo 127.0.0.1:27702' if published else ':') + '; exit 0 ;;\n'
        "esac\n"
        'if [ "$1" = inspect ]; then\n'
        "  for known in $known_containers; do\n"
        '    for word in "$@"; do\n'
        '      [ "$word" = "$known" ] || continue\n'
        '      case " $* " in *State.Running*) echo false ;; esac\n'
        "      exit 0\n"
        "    done\n"
        "  done\n"
        "  exit 1\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    return bin_dir


def deployment_env(tmp_path: Path) -> tuple[dict[str, str], Path]:
    home = tmp_path / "home"
    root = home / ".acervo"
    root.mkdir(parents=True)
    secrets = root / "secrets.env"
    secrets.write_text(
        "ACERVO_ANKI_SYNC_USERNAME=test\nACERVO_ANKI_SYNC_PASSWORD=password\n"
        "ACERVO_JWT_SECRET='a-durable-signing-secret'\n"
        # An already-deployed root, so the minted-once secrets are present. Both are appended on a
        # first deployment and kept thereafter; a fixture without them would make every later run
        # look like it had rewritten credentials it merely completed.
        "ACERVO_SPEECH_OPERATOR_TOKEN='a-durable-corpus-token'\n",
        encoding="utf-8",
    )
    secrets.chmod(0o600)
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["PATH"] = f"{fake_docker_path(tmp_path)}:{env['PATH']}"
    env["ACERVO_SKIP_MACOS_RELEASE"] = "true"
    env["ACERVO_SKIP_APP_BUILD"] = "true"
    return env, root


def run_local(env: dict[str, str], *, stdin: str = "", reset: bool = False):
    command = [str(REPO_ROOT / "deploy.sh"), "--local"]
    if reset:
        command.append("--reset-anki")
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=env,
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
    )


def test_local_deployment_preserves_data_backs_up_and_rotates(tmp_path: Path) -> None:
    env, root = deployment_env(tmp_path)
    server = root / "data" / "anki-server"
    server.mkdir(parents=True)
    database = server / "collection.anki2"
    database.write_bytes(b"collection-v1")
    robot = root / "data" / "acervo-worker"
    robot.mkdir(parents=True)
    (robot / "collection.anki2").write_bytes(b"robot-v1")
    (server / "media.db").write_bytes(b"media-index-v1")
    sentinel = server / "media-sentinel"
    sentinel.write_text("keep", encoding="utf-8")
    vocabulary = root / "data" / "server"
    vocabulary.mkdir(parents=True)
    vocabulary_sentinel = vocabulary / "acervo.db"
    vocabulary_sentinel.write_bytes(b"vocabulary-v1")
    backups = root / "backups"
    backups.mkdir()
    for index in range(11):
        (backups / f"20000101T0000{index:02d}Z").mkdir()

    result = run_local(env)

    assert result.returncode == 0, result.stderr
    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert vocabulary_sentinel.read_bytes() == b"vocabulary-v1"
    assert len([path for path in backups.iterdir() if path.is_dir()]) == 10
    assert any(
        path.name == "collection.anki2" and path.read_bytes() == b"collection-v1"
        for path in backups.rglob("collection.anki2")
    )
    assert any(path.read_bytes() == b"robot-v1" for path in backups.rglob("collection.anki2"))
    assert any(path.read_bytes() == b"media-index-v1" for path in backups.rglob("media.db"))
    assert (root / "secrets.env").stat().st_mode & 0o777 == 0o600


def test_compiled_dictionaries_travel_with_the_release_and_are_merged(tmp_path: Path) -> None:
    """Dictionaries are built where the compiler runs and are not in the repository, so the release
    carries them the way it carries the macOS application.

    Merged rather than replaced: building only the Spanish ones and deploying must not withdraw the
    Chinese ones deployed last week.
    """
    env, root = deployment_env(tmp_path)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    for name in ("cc-cedict", "kaikki-es-es"):
        (artifacts / f"{name}.json").write_text(f'{{"id": "{name}"}}', encoding="utf-8")
        (artifacts / f"{name}.dict").write_bytes(b"payloads")
        (artifacts / f"{name}.idx").write_bytes(b"index")
    # A metadata file with no payload beside it must not be published: the server would list it and
    # then fail at the moment someone tried to store it.
    (artifacts / "half-built.json").write_text('{"id": "half-built"}', encoding="utf-8")

    served = root / "data" / "dictionaries"
    served.mkdir(parents=True)
    for suffix, content in ((".json", b'{"id": "moedict-zh"}'), (".dict", b"old"), (".idx", b"old")):
        (served / f"moedict-zh{suffix}").write_bytes(content)

    # This is the one test that is about dictionaries travelling, so it says so: `conftest.py`
    # leaves them out everywhere else, where they are 800-odd MB of the owner's own data and
    # nothing to do with what is being checked.
    env["ACERVO_INCLUDE_DICTIONARIES"] = "true"
    env["ACERVO_DICTIONARY_ARTIFACTS"] = str(artifacts)
    result = run_local(env)

    assert result.returncode == 0, result.stderr
    published = {path.stem for path in served.glob("*.json")}
    assert {"cc-cedict", "kaikki-es-es"} <= published, "the release did not publish its dictionaries"
    assert "moedict-zh" in published, "deploying replaced the dictionaries already on the server"
    assert "half-built" not in published
    assert (served / "cc-cedict.dict").read_bytes() == b"payloads"


def test_a_release_without_dictionaries_leaves_the_published_ones_alone(tmp_path: Path) -> None:
    env, root = deployment_env(tmp_path)
    served = root / "data" / "dictionaries"
    served.mkdir(parents=True)
    (served / "cc-cedict.json").write_text('{"id": "cc-cedict"}', encoding="utf-8")

    env["ACERVO_INCLUDE_DICTIONARIES"] = "false"
    result = run_local(env)

    assert result.returncode == 0, result.stderr
    assert (served / "cc-cedict.json").is_file(), "a build with no dictionaries withdrew the old ones"


def test_reset_requires_exact_confirmation_and_backs_up_first(tmp_path: Path) -> None:
    env, root = deployment_env(tmp_path)
    server = root / "data" / "anki-server"
    server.mkdir(parents=True)
    database = server / "collection.anki2"
    database.write_bytes(b"important")

    refused = run_local(env, stdin="no\n", reset=True)
    assert refused.returncode == 2
    assert database.exists()

    accepted = run_local(env, stdin="RESET ACERVO ANKI\n", reset=True)
    assert accepted.returncode == 0, accepted.stderr
    assert not database.exists()
    assert any(path.read_bytes() == b"important" for path in root.rglob("collection.anki2"))


def packaged(tmp_path: Path) -> str:
    """Build a release archive and return where it landed.

    Where that is comes from `conftest.py`'s autouse fixture, which redirects it away from `build/`
    for every test here — see the note there.
    """
    result = subprocess.run(
        [str(REPO_ROOT / "scripts" / "package_acervo_server.sh")],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return result.stdout.strip()


def test_release_archive_excludes_deployment_secrets(tmp_path: Path) -> None:
    archive = Path(packaged(tmp_path))
    with tarfile.open(archive) as package:
        members = package.getnames()
    assert not any(name.endswith("secrets.env") for name in members)
    assert "deploy/acervo/llm.env" not in members
    assert "deploy/acervo/secrets.env.example" in members
    assert "deploy/acervo/llm.env.example" in members
    assert "deploy/acervo/server/web/manifest.webmanifest" in members
    assert "deploy/acervo/server/Dockerfile" in members
    # The image installs the package out of the bundle, so its build files travel with it.
    assert "src/acervo/api/app.py" in members
    assert "pyproject.toml" in members
    assert "version.json" in members


def test_remote_deployment_streams_over_ssh_without_scp(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ssh_log = tmp_path / "ssh.log"
    release_upload = tmp_path / "release.tar.gz"
    credential_upload = tmp_path / "credentials"
    ssh = bin_dir / "ssh"
    ssh.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >>\"$ACERVO_TEST_SSH_LOG\"\n"
        "case \"$*\" in\n"
        "  *'deploy-acervo check'*) printf 'helper\\n' ;;\n"
        "  *'deploy-acervo deploy'*) cat >\"$ACERVO_TEST_RELEASE\" ;;\n"
        "  *'cat > /tmp/acervo-credentials-'*) cat >\"$ACERVO_TEST_CREDENTIALS\" ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    ssh.chmod(0o755)
    scp = bin_dir / "scp"
    scp.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
    scp.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "ACERVO_TEST_SSH_LOG": str(ssh_log),
            "ACERVO_TEST_RELEASE": str(release_upload),
            "ACERVO_TEST_CREDENTIALS": str(credential_upload),
            "ACERVO_SKIP_MACOS_RELEASE": "true",
            "ACERVO_SKIP_APP_BUILD": "true",
        }
    )

    result = subprocess.run(
        [
            str(REPO_ROOT / "deploy.sh"),
            "--target",
            "deployer@server.example.test",
            "--root",
            "/volume1/docker/acervo",
            "--configure-credentials",
        ],
        cwd=REPO_ROOT,
        env=env,
        input="sync-user\ntest-password\n",
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    with tarfile.open(release_upload) as package:
        assert "deploy/acervo/compose.yaml" in package.getnames()
    assert credential_upload.read_text(encoding="utf-8") == (
        "sync-user\ntest-password\n"
    )
    commands = ssh_log.read_text(encoding="utf-8")
    assert "cat > /tmp/acervo-credentials-" in commands
    assert "--credentials-file /tmp/acervo-credentials-" in commands
    assert "sudo -n /usr/local/sbin/deploy-acervo deploy" in commands
    assert "sudo sh" not in commands
    assert " -t " not in commands
    assert "test-password" not in commands


def _jobs_ssh(tmp_path: Path, report: str) -> tuple[dict[str, str], Path]:
    """An ssh that answers the launcher's `jobs open` with `report` and logs everything else."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ssh_log = tmp_path / "ssh.log"
    ssh = bin_dir / "ssh"
    ssh.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >>\"$ACERVO_TEST_SSH_LOG\"\n"
        "case \"$*\" in\n"
        "  *'deploy-acervo check'*) printf 'helper\\n' ;;\n"
        "  *'deploy-acervo jobs open'*) printf '%s\\n' \"$ACERVO_TEST_JOBS\" ;;\n"
        "  *'deploy-acervo deploy'*) cat >/dev/null ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    ssh.chmod(0o755)
    env = os.environ.copy()
    env.update({
        "PATH": f"{bin_dir}:{env['PATH']}",
        "ACERVO_TEST_SSH_LOG": str(ssh_log),
        "ACERVO_TEST_JOBS": report,
        "ACERVO_SKIP_MACOS_RELEASE": "true",
        "ACERVO_SKIP_APP_BUILD": "true",
    })
    return env, ssh_log


def _deploy_remotely(env: dict[str, str], *extra: str, stdin: str = ""):
    return subprocess.run(
        [str(REPO_ROOT / "deploy.sh"), "--target", "deployer@server.example.test", *extra],
        cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=False, input=stdin,
    )


def test_a_deploy_refuses_while_the_server_has_jobs_open(tmp_path: Path) -> None:
    """A deploy never carries a job across a version, so it will not start one under it either —
    and it says so before building anything."""
    env, ssh_log = _jobs_ssh(
        tmp_path, '{"open": 3, "byKind": {"corpus.update": 1, "enrich": 2}}'
    )
    result = _deploy_remotely(env)
    assert result.returncode == 1
    assert "Refusing to deploy: 3 jobs are open (1 corpus.update, 2 enrich)." in result.stderr
    assert "./deploy.sh --cancel-jobs" in result.stderr
    assert "deploy-acervo deploy" not in ssh_log.read_text(encoding="utf-8")


@pytest.mark.parametrize("report", ['{"open": 0, "byKind": {}}', ""])
def test_a_deploy_goes_ahead_when_nothing_is_open_or_nothing_answers(
    tmp_path: Path, report: str
) -> None:
    """No answer is a first deployment, a stopped server, or a server from before jobs existed."""
    env, ssh_log = _jobs_ssh(tmp_path, report)
    result = _deploy_remotely(env)
    assert result.returncode == 0, result.stderr
    assert "sudo -n /usr/local/sbin/deploy-acervo deploy" in ssh_log.read_text(encoding="utf-8")


def test_cancel_jobs_cancels_then_deploys(tmp_path: Path) -> None:
    env, ssh_log = _jobs_ssh(tmp_path, '{"open": 2, "byKind": {"enrich": 2}}')
    result = _deploy_remotely(env, "--cancel-jobs")
    assert result.returncode == 0, result.stderr
    commands = ssh_log.read_text(encoding="utf-8").splitlines()
    cancel = next(i for i, c in enumerate(commands) if "deploy-acervo jobs cancel" in c)
    deploy = next(i for i, c in enumerate(commands) if "deploy-acervo deploy" in c)
    assert cancel < deploy
    assert not any("jobs open" in c for c in commands)


def test_resetting_the_database_does_not_ask_about_jobs(tmp_path: Path) -> None:
    """The table goes with the database, so the question has no answer worth waiting for."""
    env, ssh_log = _jobs_ssh(tmp_path, '{"open": 2, "byKind": {"enrich": 2}}')
    result = _deploy_remotely(env, "--reset-database", stdin="RESET ACERVO VOCABULARY\n")
    assert result.returncode == 0, result.stderr
    assert "deploy-acervo jobs" not in ssh_log.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("operation", "expected"),
    [
        ("open", "exec acervo-server-1 python -m acervo.admin jobs open --json"),
        ("cancel", "exec acervo-server-1 python -m acervo.admin jobs cancel --all"),
    ],
)
def test_the_launcher_asks_the_server_container_about_its_jobs(
    tmp_path: Path, operation: str, expected: str
) -> None:
    helper = runnable_remote_helper(tmp_path)
    docker_log = tmp_path / "docker.log"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$*\" >>\"$ACERVO_TEST_DOCKER_LOG\"\n", encoding="utf-8"
    )
    docker.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["ACERVO_TEST_DOCKER_LOG"] = str(docker_log)
    result = subprocess.run(
        [str(helper), "jobs", operation], env=env, text=True, capture_output=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert expected in docker_log.read_text(encoding="utf-8")


def test_the_launcher_refuses_any_other_jobs_operation(tmp_path: Path) -> None:
    helper = runnable_remote_helper(tmp_path)
    result = subprocess.run(
        [str(helper), "jobs", "enqueue"], text=True, capture_output=True, check=False
    )
    assert result.returncode == 2


def test_remote_llm_configuration_streams_the_key_without_exposing_it(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ssh_log = tmp_path / "ssh.log"
    release_upload = tmp_path / "release.tar.gz"
    llm_upload = tmp_path / "llm-credentials"
    ssh = bin_dir / "ssh"
    ssh.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >>\"$ACERVO_TEST_SSH_LOG\"\n"
        "case \"$*\" in\n"
        "  *'deploy-acervo check'*) printf 'helper\\n' ;;\n"
        "  *'deploy-acervo deploy'*) cat >\"$ACERVO_TEST_RELEASE\" ;;\n"
        "  *'cat > /tmp/acervo-llm-credentials-'*) cat >\"$ACERVO_TEST_LLM\" ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    ssh.chmod(0o755)
    env = os.environ.copy()
    env.update({
        "PATH": f"{bin_dir}:{env['PATH']}",
        "ACERVO_TEST_SSH_LOG": str(ssh_log),
        "ACERVO_TEST_RELEASE": str(release_upload),
        "ACERVO_TEST_LLM": str(llm_upload),
        "ACERVO_SKIP_MACOS_RELEASE": "true",
        "ACERVO_SKIP_APP_BUILD": "true",
    })

    result = subprocess.run(
        [
            str(REPO_ROOT / "deploy.sh"), "--target", "deployer@server.example.test",
            "--root", "/volume1/docker/acervo", "--configure-llm",
            "--llm-chain", "cloudflare,gemini-free",
            "--llm-set", "CLOUDFLARE_ACCOUNT_ID=0123456789abcdef0123456789abcdef",
            "--llm-key", "CLOUDFLARE_API_TOKEN", "--llm-api-key-stdin",
        ],
        cwd=REPO_ROOT, env=env, input="cloudflare-token\n", text=True,
        capture_output=True, check=False,
    )

    assert result.returncode == 0, result.stderr
    assert llm_upload.read_text(encoding="utf-8") == (
        "ACERVO_TEXT_CHAIN=cloudflare,gemini-free\n"
        "CLOUDFLARE_ACCOUNT_ID=0123456789abcdef0123456789abcdef\n"
        "CLOUDFLARE_API_TOKEN=cloudflare-token\n"
    )
    commands = ssh_log.read_text(encoding="utf-8")
    assert "cat > /tmp/acervo-llm-credentials-" in commands
    assert "--llm-credentials-file /tmp/acervo-llm-credentials-" in commands
    # The key travels over stdin into a mode-600 file. A command line is visible in `ps`.
    assert "cloudflare-token" not in commands + result.stdout + result.stderr


def test_installer_accepts_streamed_credential_file_and_network_options(
    tmp_path: Path,
) -> None:
    root = tmp_path / "acervo"
    credential_file = tmp_path / "credentials"
    credential_file.write_text(
        "sync-user\ntest-password\n",
        encoding="utf-8",
    )
    credential_file.chmod(0o600)
    env = os.environ.copy()
    env["PATH"] = f"{fake_docker_path(tmp_path)}:{env['PATH']}"

    result = subprocess.run(
        [
            str(REPO_ROOT / "deploy/acervo/install.sh"),
            "--root",
            str(root),
            "--credentials-file",
            str(credential_file),
            "--bind-address",
            "0.0.0.0",
            "--port",
            "27801",
            "--app-bind-address",
            "127.0.0.1",
            "--app-port",
            "27802",
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    written = (root / "secrets.env").read_text(encoding="utf-8")
    assert written.startswith(
        "ACERVO_ANKI_SYNC_USERNAME='sync-user'\nACERVO_ANKI_SYNC_PASSWORD='test-password'\n"
    )
    # Minted here and kept, because regenerating it signs out every device.
    assert re.search(r"^ACERVO_JWT_SECRET='[A-Za-z0-9]{16,}'$", written, flags=re.MULTILINE)
    # A model credential belongs in llm.env and nowhere else: compose passes llm.env last, so a key
    # defined in both files has a silent loser, which is what took capture down.
    assert "GEMINI_API_KEY" not in (root / "secrets.env").read_text(encoding="utf-8")
    deployment = (root / "deployment.env").read_text(encoding="utf-8")
    assert "ACERVO_BIND_ADDRESS=0.0.0.0\n" in deployment
    assert "ACERVO_ANKI_PORT=27801\n" in deployment
    assert "ACERVO_APP_BIND_ADDRESS=127.0.0.1\n" in deployment
    assert "ACERVO_APP_PORT=27802\n" in deployment
    assert f"ACERVO_SERVER_DATA={root}/data/server\n" in deployment
    assert f"ACERVO_DOWNLOADS={root}/downloads\n" in deployment


def test_installer_moves_a_model_key_out_of_secrets_env(tmp_path: Path) -> None:
    """One variable defined in two files has a silent loser, and llm.env is passed last."""
    env, root = deployment_env(tmp_path)
    secrets = root / "secrets.env"
    secrets.write_text(
        secrets.read_text(encoding="utf-8") + "GEMINI_API_KEY='stranded-key'\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            str(REPO_ROOT / "deploy/acervo/install.sh"),
            "--root", str(root),
            "--bind-address", "127.0.0.1", "--port", "27701",
            "--app-bind-address", "127.0.0.1", "--app-port", "27702",
        ],
        cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "GEMINI_API_KEY" not in secrets.read_text(encoding="utf-8")
    assert "GEMINI_API_KEY=stranded-key\n" in (root / "llm.env").read_text(encoding="utf-8")
    # The move happens once and leaves nothing behind to move again.
    assert (root / "llm.env").read_text(encoding="utf-8").count("GEMINI_API_KEY") == 1


def test_reconfiguring_credentials_does_not_sign_every_device_out(tmp_path: Path) -> None:
    """The credential stream owns two lines. Rewriting the file wholesale would take the token
    signing secret with it and the next block would mint a fresh one — so reconfiguring the Anki
    password would sign out every device, for no reason anyone could have guessed."""
    env, root = deployment_env(tmp_path)
    secrets = root / "secrets.env"
    secrets.write_text(
        "ACERVO_ANKI_SYNC_USERNAME=old\nACERVO_ANKI_SYNC_PASSWORD=old-password\n"
        "ACERVO_JWT_SECRET='the-secret-every-device-holds-a-token-from'\n"
        "ACERVO_SPEECH_OPERATOR_TOKEN=the-token-the-corpus-knows\n",
        encoding="utf-8",
    )
    credentials = tmp_path / "credentials"
    credentials.write_text("sync-user\nnew-password\n", encoding="utf-8")

    result = subprocess.run(
        [
            str(REPO_ROOT / "deploy/acervo/install.sh"),
            "--root", str(root), "--credentials-file", str(credentials),
            "--bind-address", "127.0.0.1", "--port", "27701",
            "--app-bind-address", "127.0.0.1", "--app-port", "27702",
        ],
        cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=False,
    )

    assert result.returncode == 0, result.stderr
    written = secrets.read_text(encoding="utf-8")
    assert "ACERVO_ANKI_SYNC_PASSWORD='new-password'" in written
    assert "ACERVO_JWT_SECRET='the-secret-every-device-holds-a-token-from'" in written
    assert written.count("ACERVO_JWT_SECRET") == 1
    # The corpus's operator token survives too, for the same reason.
    assert "ACERVO_SPEECH_OPERATOR_TOKEN=the-token-the-corpus-knows" in written
    assert written.count("ACERVO_ANKI_SYNC_PASSWORD") == 1


def test_installer_strips_the_retired_superuser_pair_and_mints_a_signing_secret(
    tmp_path: Path,
) -> None:
    """An already-deployed secrets.env carries a superuser that no longer exists, and the installer
    used to hard-fail without one. The strip erases itself; the signing secret is minted once and
    kept, because regenerating it signs out every device."""
    env, root = deployment_env(tmp_path)
    secrets = root / "secrets.env"
    secrets.write_text(
        "ACERVO_ANKI_SYNC_USERNAME=test\nACERVO_ANKI_SYNC_PASSWORD=password\n"
        "ACERVO_PB_SUPERUSER_EMAIL=admin@account.example.com\n"
        "ACERVO_PB_SUPERUSER_PASSWORD=pb-password\n",
        encoding="utf-8",
    )

    def deploy() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                str(REPO_ROOT / "deploy/acervo/install.sh"),
                "--root", str(root),
                "--bind-address", "127.0.0.1", "--port", "27701",
                "--app-bind-address", "127.0.0.1", "--app-port", "27702",
            ],
            cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=False,
        )

    result = deploy()
    assert result.returncode == 0, result.stderr
    written = secrets.read_text(encoding="utf-8")
    assert "ACERVO_PB_SUPERUSER" not in written
    assert "ACERVO_ANKI_SYNC_PASSWORD=password" in written
    minted = re.search(r"^ACERVO_JWT_SECRET='([A-Za-z0-9]{16,})'$", written, flags=re.MULTILINE)
    assert minted, written

    # A second deployment neither re-strips nor re-mints: a new secret would sign out every device.
    assert deploy().returncode == 0
    again = secrets.read_text(encoding="utf-8")
    assert again.count("ACERVO_JWT_SECRET") == 1
    assert minted.group(1) in again


def run_installer(
    root: Path, env: dict[str, str], *extra: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            str(REPO_ROOT / "deploy/acervo/install.sh"),
            "--root", str(root),
            "--bind-address", "127.0.0.1", "--port", "27701",
            "--app-bind-address", "127.0.0.1", "--app-port", "27702",
            *extra,
        ],
        cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=False,
    )


def test_the_installer_writes_the_zone_it_is_given_and_keeps_it_when_given_none(tmp_path: Path) -> None:
    """deployment.env is rewritten whole on every deploy, so a zone that arrived once must not be
    lost by the next deploy that does not name one: every day boundary would move to UTC."""
    env, root = deployment_env(tmp_path)
    assert run_installer(root, env, "--timezone", "Europe/London").returncode == 0
    assert "ACERVO_TIMEZONE=Europe/London\n" in (root / "deployment.env").read_text(encoding="utf-8")

    assert run_installer(root, env).returncode == 0
    assert "ACERVO_TIMEZONE=Europe/London\n" in (root / "deployment.env").read_text(encoding="utf-8")

    assert run_installer(root, env, "--timezone", "America/Argentina/Buenos_Aires").returncode == 0
    assert "ACERVO_TIMEZONE=America/Argentina/Buenos_Aires\n" in (
        root / "deployment.env").read_text(encoding="utf-8")


@pytest.mark.parametrize("zone", ["../etc/passwd", "Europe/London; rm", "/etc/localtime", "Europe/"])
def test_the_installer_refuses_a_zone_that_is_not_a_zone_name(tmp_path: Path, zone: str) -> None:
    env, root = deployment_env(tmp_path)
    assert run_installer(root, env, "--timezone", zone).returncode == 2


def test_a_deploy_names_this_machines_zone(tmp_path: Path) -> None:
    env, root = deployment_env(tmp_path)
    env["TZ"] = "Asia/Tokyo"
    assert run_local(env).returncode == 0
    assert "ACERVO_TIMEZONE=Asia/Tokyo\n" in (root / "deployment.env").read_text(encoding="utf-8")


def test_a_deploy_does_not_pass_on_a_posix_rule_as_a_zone(tmp_path: Path) -> None:
    env, root = deployment_env(tmp_path)
    (root / "deployment.env").write_text("ACERVO_TIMEZONE=Europe/Madrid\n", encoding="utf-8")
    env["TZ"] = "<+03>-3"
    assert run_local(env).returncode == 0
    assert "ACERVO_TIMEZONE=Europe/Madrid\n" in (root / "deployment.env").read_text(encoding="utf-8")


def _commands(log: Path) -> list[str]:
    return log.read_text(encoding="utf-8").splitlines()


def _index(commands: list[str], *needles: str) -> int:
    return next(i for i, command in enumerate(commands) if all(n in command for n in needles))


def test_a_transition_backs_up_the_database_then_converts_it_before_the_new_server_starts(
    tmp_path: Path,
) -> None:
    """The order is the whole safety of it: the server is stopped so the copy and the conversion see
    a database nothing is writing to, the backup exists before anything changes it, and the converter
    has run before the new server is asked to open a schema it would otherwise refuse."""
    env, root = deployment_env(tmp_path)
    log = tmp_path / "docker.log"
    env["ACERVO_TEST_DOCKER_LOG"] = str(log)
    server = root / "data" / "server"
    server.mkdir(parents=True)
    (server / "acervo.db").write_bytes(b"vocabulary-v1")
    (server / "acervo.db-wal").write_bytes(b"wal-v1")
    (server / "takes").mkdir()
    (server / "takes" / "big.flac").write_bytes(b"not a database")

    result = run_installer(root, env, "--transition")

    assert result.returncode == 0, result.stderr
    backups = list((root / "backups").glob("*/server"))
    assert len(backups) == 1, "one dated directory holds it"
    assert (backups[0] / "acervo.db").read_bytes() == b"vocabulary-v1"
    assert (backups[0] / "acervo.db-wal").read_bytes() == b"wal-v1"
    assert not (backups[0] / "takes").exists(), "only the database is copied, not what sits beside it"
    assert (server / "acervo.db").read_bytes() == b"vocabulary-v1", "and the live one is untouched"

    commands = _commands(log)
    build = _index(commands, "build server")
    stop = _index(commands, "stop server")
    convert = _index(commands, " run ", "--no-deps", "transition.py")
    up = _index(commands, " up -d")
    assert build < stop < convert < up
    assert "/scripts:/opt/release-scripts:ro" in commands[convert], "the release carries its converters"
    assert "--rm" in commands[convert]
    # Said where the owner will see it, and said again at the end, past the build output.
    assert result.stdout.count(f"{backups[0]}") >= 2


def test_a_refused_transition_starts_the_old_server_again_and_deploys_nothing(tmp_path: Path) -> None:
    env, root = deployment_env(tmp_path)
    log = tmp_path / "docker.log"
    env["ACERVO_TEST_DOCKER_LOG"] = str(log)
    env["ACERVO_TEST_DOCKER_FAIL_RUN"] = "1"
    server = root / "data" / "server"
    server.mkdir(parents=True)
    (server / "acervo.db").write_bytes(b"vocabulary-v1")

    result = run_installer(root, env, "--transition")

    assert result.returncode == 7, "the converter's own status, not a generic failure"
    assert "not converted" in result.stderr
    commands = _commands(log)
    assert _index(commands, "start server") > _index(commands, "transition.py")
    assert not any(" up -d" in command for command in commands), "the new server was never started"
    assert not (root / "current-release").exists(), "and the deployment did not move"
    assert next((root / "backups").glob("*/server/acervo.db")).read_bytes() == b"vocabulary-v1"


def test_an_ordinary_deploy_neither_copies_the_database_nor_runs_a_converter(tmp_path: Path) -> None:
    env, root = deployment_env(tmp_path)
    log = tmp_path / "docker.log"
    env["ACERVO_TEST_DOCKER_LOG"] = str(log)
    server = root / "data" / "server"
    server.mkdir(parents=True)
    (server / "acervo.db").write_bytes(b"vocabulary-v1")

    result = run_installer(root, env)

    assert result.returncode == 0, result.stderr
    assert not list((root / "backups").glob("*/server"))
    assert "transition.py" not in log.read_text(encoding="utf-8")


def test_a_transition_and_a_reset_are_opposite_answers_and_cannot_be_asked_together(
    tmp_path: Path,
) -> None:
    env, root = deployment_env(tmp_path)

    installer = run_installer(root, env, "--transition", "--reset-database")
    deployer = subprocess.run(
        [str(REPO_ROOT / "deploy.sh"), "--local", "--transition", "--reset-database"],
        cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=False,
    )

    assert installer.returncode == 2
    assert deployer.returncode == 2


def test_the_deployer_forwards_a_transition_through_the_launcher(tmp_path: Path) -> None:
    env, ssh_log = _jobs_ssh(tmp_path, '{"open": 0, "byKind": {}}')
    result = _deploy_remotely(env, "--transition")
    assert result.returncode == 0, result.stderr
    assert "deploy-acervo deploy" in ssh_log.read_text(encoding="utf-8")
    assert " --transition" in ssh_log.read_text(encoding="utf-8")


def test_installing_the_samples_sends_every_pinned_part_and_the_whole_digest(tmp_path: Path) -> None:
    """GitHub refuses a release asset of 2 GiB or more, so the bundle is published in parts. Each
    part must reach the fetch, in order, beside the digest of the archive they join into."""
    pin = json.loads((REPO_ROOT / "deploy/acervo/lexibeat/pin.json").read_text(encoding="utf-8"))
    env, ssh_log = _jobs_ssh(tmp_path, "")
    result = _deploy_remotely(env, "--install-samples")
    assert result.returncode == 0, result.stderr
    sent = ssh_log.read_text(encoding="utf-8")
    # The bundle's own release, which the wheel's tag need not be: it is not re-uploaded every time.
    base = f"{pin['repository']}/releases/download/{pin['bundle']['release']}/"
    expected = " ".join(f"--from {base}{part}" for part in pin["bundle"]["parts"])
    assert f"deploy-acervo install-samples {expected} --sha256 '{pin['bundle']['sha256']}'" in sent


def test_the_launcher_fetches_every_part_and_refuses_anything_that_is_not_one(tmp_path: Path) -> None:
    helper = runnable_remote_helper(tmp_path)
    root = tmp_path / "acervo"
    release = root / "releases" / "one"
    (release / "deploy" / "acervo").mkdir(parents=True)
    (release / "deploy" / "acervo" / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    (root / "current-release").write_text(f"{release}\n", encoding="utf-8")
    log = tmp_path / "docker.log"
    env = os.environ.copy()
    env["PATH"] = f"{fake_docker_path(tmp_path)}:{env['PATH']}"
    env["ACERVO_TEST_DOCKER_LOG"] = str(log)
    part = "https://github.com/owner/lexibeat/releases/download/v1/bundle.tar"
    digest = "a" * 64

    result = subprocess.run(
        [str(helper), "install-samples", "--from", f"{part}.001", "--from", f"{part}.002",
         "--sha256", digest, "--root", str(root)],
        env=env, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (f"lexibeat-bundle fetch --into /var/lib/lexibeat/bundle --from {part}.001 "
            f"--from {part}.002 --sha256 {digest}") in log.read_text(encoding="utf-8")

    for refused in (part, f"{part}.001;reboot", "https://example.com/bundle.tar.001"):
        result = subprocess.run(
            [str(helper), "install-samples", "--from", refused, "--sha256", digest,
             "--root", str(root)],
            env=env, text=True, capture_output=True, check=False,
        )
        assert result.returncode == 2, refused


def test_a_transition_still_refuses_while_jobs_are_open(tmp_path: Path) -> None:
    """Unlike a reset, it keeps the jobs table, so a job would survive into the new schema — and a
    deploy never carries a job across a version."""
    env, ssh_log = _jobs_ssh(tmp_path, '{"open": 2, "byKind": {"enrich": 2}}')
    result = _deploy_remotely(env, "--transition")
    assert result.returncode == 1
    assert "Refusing to deploy" in result.stderr
    assert "deploy-acervo deploy" not in ssh_log.read_text(encoding="utf-8")


def test_installer_retires_the_container_that_was_holding_the_app_port(tmp_path: Path) -> None:
    """Renaming the compose service left the old container running on an already-deployed server, and
    it still held the app port: the new one failed to bind with "port is already allocated". Compose
    calls it an orphan and warns rather than removing it."""
    env, root = deployment_env(tmp_path)
    log = tmp_path / "docker.log"
    env["ACERVO_TEST_DOCKER_LOG"] = str(log)
    fake_docker_path(tmp_path, existing=("acervo-pocketbase-1",))

    result = run_installer(root, env)

    assert result.returncode == 0, result.stderr
    assert "acervo-pocketbase-1" in result.stdout
    assert "rm -f acervo-pocketbase-1" in log.read_text(encoding="utf-8")
    # The words in it are the owner's. An export is the documented way to carry them across, and
    # deleting the last copy on their behalf is not the installer's call.
    assert "rm -rf" not in log.read_text(encoding="utf-8")


def test_installer_discards_a_server_container_that_failed_to_bind(tmp_path: Path) -> None:
    """The nastier half of the same failure. A create that cannot bind leaves the container behind,
    and its host binding is never programmed — not on a later start, and not on a restart. Compose
    then finds a matching container, starts it, and reports success while nothing is published,
    because the healthcheck runs inside the container."""
    env, root = deployment_env(tmp_path)
    log = tmp_path / "docker.log"
    env["ACERVO_TEST_DOCKER_LOG"] = str(log)
    fake_docker_path(tmp_path, existing=("acervo-server-1",))

    result = run_installer(root, env)

    assert result.returncode == 0, result.stderr
    assert "rm -f acervo-server-1" in log.read_text(encoding="utf-8")


def test_installer_refuses_to_call_an_unpublished_server_healthy(tmp_path: Path) -> None:
    """Asking the container whether it is healthy is not asking whether anyone can reach it."""
    env, root = deployment_env(tmp_path)
    fake_docker_path(tmp_path, published=False)

    result = run_installer(root, env)

    assert result.returncode == 1
    assert "port is not published" in result.stderr
    assert "docker rm -f acervo-server-1" in result.stderr
    # The claim it used to make regardless.
    assert "internal HTTP backend is healthy" not in result.stdout


def test_installer_runs_each_containers_own_healthcheck_rather_than_waiting_for_docker(
    tmp_path: Path,
) -> None:
    """Docker's first probe comes a whole interval after start, and the interval is a minute, so
    waiting on its "healthy" would add that minute to every deploy. The installer asks the container
    now, with the command the container was configured with, so compose.yaml is the one place a probe
    is written."""
    env, root = deployment_env(tmp_path)
    log = tmp_path / "docker.log"
    env["ACERVO_TEST_DOCKER_LOG"] = str(log)

    result = run_installer(root, env)

    assert result.returncode == 0, result.stderr
    commands = _commands(log)
    for service in ("anki-sync-server", "speech-retrieval", "lexibeat", "server"):
        assert f"exec acervo-{service}-1 {' '.join(PROBE[1:])}" in commands
    assert not any(" ps " in command for command in commands)


def test_installer_gives_up_on_a_service_that_never_answers_its_probe(tmp_path: Path) -> None:
    env, root = deployment_env(tmp_path)
    log = tmp_path / "docker.log"
    env["ACERVO_TEST_DOCKER_LOG"] = str(log)
    env["ACERVO_TEST_DOCKER_FAIL_PROBE"] = "acervo-lexibeat-1"

    result = run_installer(root, env)

    assert result.returncode == 1
    commands = _commands(log)
    assert sum(command.startswith("exec acervo-lexibeat-1 ") for command in commands) == 30
    assert any(command.endswith(" logs lexibeat") for command in commands), "its logs, for the owner"
    assert not any(command.startswith("exec acervo-server-1 ") for command in commands)
    assert not (root / "current-release").exists()


def test_every_long_running_service_probes_once_a_minute() -> None:
    """Each probe makes Docker rewrite the container's state with an fsync; at 5 s across four
    services that was a constant ~200 small writes a second on the NAS's disks. Nothing restarts on
    "unhealthy", so a minute apart and three misses is soon enough, and nothing slower is needed."""
    import yaml

    compose = yaml.safe_load(
        (REPO_ROOT / "deploy/acervo/compose.yaml").read_text(encoding="utf-8")
    )
    probed = {name: service["healthcheck"] for name, service in compose["services"].items()
              if "healthcheck" in service}
    assert set(probed) == {"server", "speech-retrieval", "lexibeat", "anki-sync-server"}
    for name, healthcheck in probed.items():
        assert (healthcheck["interval"], healthcheck["retries"]) == ("60s", 3), name


def test_creating_an_account_goes_through_the_launcher_and_keeps_the_password_off_the_wire(
    tmp_path: Path,
) -> None:
    """The launcher already runs a streamed installer as root, so running one fixed command in one
    named container is a narrower privilege than it grants today, not a wider one. Refusing it only
    left the flag printing advice."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ssh_log = tmp_path / "ssh.log"
    stdin_log = tmp_path / "stdin.log"
    ssh = bin_dir / "ssh"
    ssh.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >>\"$ACERVO_TEST_SSH_LOG\"\n"
        "case \"$*\" in\n"
        "  *'deploy-acervo check'*) printf 'helper\\n' ;;\n"
        "  *'deploy-acervo create-account'*) cat >>\"$ACERVO_TEST_STDIN_LOG\" ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    ssh.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["ACERVO_TEST_SSH_LOG"] = str(ssh_log)
    env["ACERVO_TEST_STDIN_LOG"] = str(stdin_log)

    result = subprocess.run(
        [str(REPO_ROOT / "deploy.sh"), "--target", "deployer@server.example.test", "--create-account"],
        cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=False,
        input="learner@account.example.com\nan-account-password\n",
    )

    assert result.returncode == 0, result.stderr
    commands = ssh_log.read_text(encoding="utf-8")
    assert "sudo -n /usr/local/sbin/deploy-acervo create-account" in commands
    # Positional on stdin, so neither the address nor the password is ever an argument.
    assert stdin_log.read_text(encoding="utf-8") == (
        "learner@account.example.com\nan-account-password\n"
    )
    assert "an-account-password" not in commands + result.stdout + result.stderr


def test_the_launcher_runs_the_account_command_in_the_container_without_naming_the_password(
    tmp_path: Path,
) -> None:
    helper = runnable_remote_helper(tmp_path)
    docker_log = tmp_path / "docker.log"
    stdin_log = tmp_path / "docker-stdin.log"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >>\"$ACERVO_TEST_DOCKER_LOG\"\n"
        "cat >>\"$ACERVO_TEST_STDIN_LOG\"\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["ACERVO_TEST_DOCKER_LOG"] = str(docker_log)
    env["ACERVO_TEST_STDIN_LOG"] = str(stdin_log)

    result = subprocess.run(
        [str(helper), "create-account"], env=env, text=True, capture_output=True, check=False,
        input="learner@account.example.com\nan-account-password\n",
    )

    assert result.returncode == 0, result.stderr
    asked = docker_log.read_text(encoding="utf-8")
    assert "exec -i acervo-server-1 python -m acervo.admin accounts create" in asked
    assert "--email learner@account.example.com" in asked
    # The password reaches the command on stdin and never as an argument, so it stays out of the
    # host's process list.
    assert "an-account-password" not in asked
    assert stdin_log.read_text(encoding="utf-8") == "an-account-password\n"


@pytest.mark.parametrize(
    "address",
    ["learner@account.example.com; rm -rf /", "learner@account.example.com'", "no-at-sign", ""],
)
def test_the_launcher_refuses_an_address_that_is_not_one(tmp_path: Path, address: str) -> None:
    """It is the one part of this that reaches a remote shell as text."""
    helper = runnable_remote_helper(tmp_path)
    result = subprocess.run(
        [str(helper), "create-account"], text=True, capture_output=True, check=False,
        input=f"{address}\nan-account-password\n",
    )
    assert result.returncode == 2
    assert "implausible shape" in result.stderr or "Missing account" in result.stderr


def test_a_finished_deployment_says_where_to_open_acervo(tmp_path: Path) -> None:
    """A summary that named a loopback port and a service id was not telling the operator the one
    thing they needed. The tailnet suffix is a property of the tailnet, so the deploying machine's
    answer is the server's answer."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ssh = bin_dir / "ssh"
    ssh.write_text(
        "#!/bin/sh\n"
        "case \"$*\" in\n"
        "  *'deploy-acervo check'*) printf 'helper\\n' ;;\n"
        "  *) cat >/dev/null 2>&1 || true ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    ssh.chmod(0o755)
    tailscale = bin_dir / "tailscale"
    tailscale.write_text(
        "#!/bin/sh\n"
        "case \"$*\" in\n"
        '  "status --json") printf \'{\\n  "MagicDNSSuffix": "tailexample.ts.net"\\n}\\n\' ;;\n'
        "esac\n",
        encoding="utf-8",
    )
    tailscale.chmod(0o755)
    env, _ = deployment_env(tmp_path)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"

    result = subprocess.run(
        [
            str(REPO_ROOT / "deploy.sh"),
            "--target", "deployer@server.example.test",
            "--service", "acervo",
        ],
        cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "https://acervo.tailexample.ts.net/" in result.stdout


def test_the_summary_says_the_shape_of_the_address_when_it_cannot_read_the_tailnet(
    tmp_path: Path,
) -> None:
    """Guessing is worse than saying where to look."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ssh = bin_dir / "ssh"
    ssh.write_text(
        "#!/bin/sh\n"
        "case \"$*\" in\n"
        "  *'deploy-acervo check'*) printf 'helper\\n' ;;\n"
        "  *) cat >/dev/null 2>&1 || true ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    ssh.chmod(0o755)
    # A `tailscale` that is present but says nothing useful, which is the same situation as none.
    tailscale = bin_dir / "tailscale"
    tailscale.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    tailscale.chmod(0o755)
    env, _ = deployment_env(tmp_path)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"

    result = subprocess.run(
        [
            str(REPO_ROOT / "deploy.sh"),
            "--target", "deployer@server.example.test",
            "--service", "acervo",
        ],
        cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "https://acervo.<your tailnet>.ts.net/" in result.stdout
    assert "tailscale status" in result.stdout


def run_configure_llm(tmp_path: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PATH"] = f"{fake_docker_path(tmp_path)}:{env['PATH']}"
    # Hermetic: the real .acervo-deploy names a live server.
    env["ACERVO_DEPLOY_PROFILE"] = str(tmp_path / "absent-profile")
    return subprocess.run(
        [str(REPO_ROOT / "deploy.sh"), "--local", "--configure-llm", *arguments],
        cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=False, input="a-key\n",
    )


def test_a_variable_name_that_looks_nothing_like_one_is_refused(tmp_path: Path) -> None:
    """Which names are allowed is the catalogue's business — the installer checks against the row
    list it was shipped. What this script can say on its own is that a name is shaped like one."""
    result = run_configure_llm(tmp_path, "--llm-set", "not a variable=x")
    assert result.returncode == 2
    assert "Unsafe LLM variable name" in result.stderr


def test_a_provider_id_that_is_merely_new_is_not_refused(tmp_path: Path) -> None:
    """No list of provider names lives in this script any more, so a row added to the catalogue
    tomorrow needs no change here. That is what replaced the old `gemini|vertex` whitelist."""
    result = run_configure_llm(tmp_path, "--llm-chain", "some-provider-invented-later")
    assert "some-provider-invented-later" not in result.stderr


def test_a_key_on_standard_input_needs_to_say_which_variable_it_is(tmp_path: Path) -> None:
    result = run_configure_llm(tmp_path, "--llm-api-key-stdin")
    assert result.returncode == 2
    assert "--llm-key" in result.stderr


def test_credentials_and_llm_are_configured_in_separate_commands(tmp_path: Path) -> None:
    result = run_configure_llm(
        tmp_path, "--configure-credentials", "--llm-chain", "gemini-free",
    )
    assert result.returncode == 2
    assert "separate commands" in result.stderr


def test_installer_updates_only_llm_env_and_preserves_both_provider_keys(tmp_path: Path) -> None:
    env, root = deployment_env(tmp_path)
    original_secrets = (root / "secrets.env").read_bytes()

    def configure(contents: str) -> subprocess.CompletedProcess[str]:
        settings = tmp_path / "llm-credentials"
        settings.write_text(contents, encoding="utf-8")
        settings.chmod(0o600)
        return subprocess.run(
            [
                str(REPO_ROOT / "deploy/acervo/install.sh"),
                "--root", str(root),
                "--llm-credentials-file", str(settings),
                "--bind-address", "127.0.0.1", "--port", "27701",
                "--app-bind-address", "127.0.0.1", "--app-port", "27702",
            ],
            cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=False,
        )

    result = configure(
        "ACERVO_TEXT_CHAIN=cloudflare\n"
        "CLOUDFLARE_ACCOUNT_ID=0123456789abcdef0123456789abcdef\n"
        "CLOUDFLARE_API_TOKEN=cloudflare-token\n"
    )
    assert result.returncode == 0, result.stderr
    result = configure("ACERVO_TEXT_CHAIN=gemini-free\nGEMINI_API_KEY=gemini-key\n")
    assert result.returncode == 0, result.stderr

    assert (root / "secrets.env").read_bytes() == original_secrets
    llm = (root / "llm.env").read_text(encoding="utf-8")
    assert "ACERVO_TEXT_CHAIN=gemini-free\n" in llm
    assert "GEMINI_API_KEY=gemini-key\n" in llm
    # The point of the whole file: switching provider keeps the other one's credentials, so
    # switching back does not mean minting a new key.
    assert "CLOUDFLARE_API_TOKEN=cloudflare-token\n" in llm
    assert "CLOUDFLARE_ACCOUNT_ID=0123456789abcdef0123456789abcdef\n" in llm
    assert llm.count("ACERVO_TEXT_CHAIN") == 1
    assert (root / "llm.env").stat().st_mode & 0o777 == 0o600


def test_the_installer_refuses_a_variable_no_provider_reads(tmp_path: Path) -> None:
    """The replacement for the old `gemini|vertex` whitelist: a name has to belong to a row.

    A key written under a name nothing reads is the worst kind of misconfiguration — it deploys
    cleanly and the server is simply unable to build entries, with health blaming the variable that
    *is* missing.
    """
    env, root = deployment_env(tmp_path)
    settings = tmp_path / "llm-credentials"
    settings.write_text("NOT_A_PROVIDER_VARIABLE=x\n", encoding="utf-8")
    settings.chmod(0o600)
    result = subprocess.run(
        [
            str(REPO_ROOT / "deploy/acervo/install.sh"),
            "--root", str(root),
            "--llm-credentials-file", str(settings),
            "--bind-address", "127.0.0.1", "--port", "27701",
            "--app-bind-address", "127.0.0.1", "--app-port", "27702",
        ],
        cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 2
    assert "not a variable any provider in the catalogue reads" in result.stderr


def test_remote_status_does_not_build_or_upload(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ssh_log = tmp_path / "ssh.log"
    ssh = bin_dir / "ssh"
    ssh.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >>\"$ACERVO_TEST_SSH_LOG\"\n"
        "case \"$*\" in\n"
        "  *'deploy-acervo check'*) printf 'helper\\n' ;;\n"
        "  *'deploy-acervo status'*) printf 'state=running,health=healthy\\n0.0.0.0:27701\\n' ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    ssh.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["ACERVO_TEST_SSH_LOG"] = str(ssh_log)

    result = subprocess.run(
        [
            str(REPO_ROOT / "deploy.sh"),
            "--target",
            "deployer@server.example.test",
            "--status",
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "health=healthy" in result.stdout
    commands = ssh_log.read_text(encoding="utf-8")
    assert "sudo -n /usr/local/sbin/deploy-acervo status" in commands
    assert "cat >" not in commands


def test_remote_helper_install_is_an_explicit_one_password_operation(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    uploaded = tmp_path / "remote-helper.sh"
    ssh_log = tmp_path / "ssh.log"
    ssh = bin_dir / "ssh"
    ssh.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >>\"$ACERVO_TEST_SSH_LOG\"\n"
        "case \"$*\" in *'cat > /tmp/deploy-acervo-'*) cat >\"$ACERVO_TEST_HELPER\" ;; esac\n",
        encoding="utf-8",
    )
    ssh.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "ACERVO_TEST_SSH_LOG": str(ssh_log),
            "ACERVO_TEST_HELPER": str(uploaded),
        }
    )

    result = subprocess.run(
        [
            str(REPO_ROOT / "deploy.sh"),
            "--target",
            "deployer@server.example.test",
            "--install-helper",
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert uploaded.read_bytes() == (REPO_ROOT / "deploy/acervo/remote-helper.sh").read_bytes()
    commands = ssh_log.read_text(encoding="utf-8")
    assert "sudo sh /tmp/deploy-acervo-" in commands
    assert "--install" in commands


def test_remote_helper_runs_the_packaged_installer_from_standard_input(tmp_path: Path) -> None:
    helper = runnable_remote_helper(tmp_path)
    root = tmp_path / "acervo"
    root.mkdir()
    secrets = root / "secrets.env"
    secrets.write_text(
        "ACERVO_ANKI_SYNC_USERNAME=test\nACERVO_ANKI_SYNC_PASSWORD=password\n"
        "ACERVO_JWT_SECRET='a-durable-signing-secret'\n",
        encoding="utf-8",
    )
    secrets.chmod(0o600)
    archive = Path(packaged(tmp_path))
    env = os.environ.copy()
    env["PATH"] = f"{fake_docker_path(tmp_path)}:{env['PATH']}"

    # The Google credential rides through the launcher too, and it is the one credential that is a
    # file the whole way. The launcher only accepts it under the path the deployer streams it to,
    # so the test has to use that path rather than tmp_path.
    uploaded = Path(f"/tmp/acervo-google-credentials-{os.getpid()}")
    uploaded.write_text('{"type": "service_account", "client_email": "a@b.example.com"}',
                        encoding="utf-8")

    try:
        result = subprocess.run(
            [
                str(helper),
                "deploy",
                "--root",
                str(root),
                "--google-credentials-file",
                str(uploaded),
                "--bind-address",
                "127.0.0.1",
                "--port",
                "27701",
                "--app-bind-address",
                "127.0.0.1",
                "--app-port",
                "27702",
            ],
            env=env,
            input=archive.read_bytes(),
            capture_output=True,
            check=False,
        )
    finally:
        uploaded.unlink(missing_ok=True)

    assert result.returncode == 0, result.stderr.decode()
    assert (root / "deployment.env").exists()
    assert b"internal HTTP backend" in result.stdout
    installed = root / "credentials" / "google.json"
    assert installed.read_text(encoding="utf-8").startswith('{"type": "service_account"')
    assert installed.stat().st_mode & 0o777 == 0o600
    # The launcher removes what it was handed, so nothing sensitive is left in /tmp on the server.
    assert not uploaded.exists()


def test_the_launcher_refuses_a_credential_path_it_did_not_expect(tmp_path: Path) -> None:
    """The launcher runs as root out of sudoers, so every path it is handed is checked against the
    shape the deployer would have written — the same guard the other two credentials already have."""
    helper = runnable_remote_helper(tmp_path)
    elsewhere = tmp_path / "google.json"
    elsewhere.write_text('{"type": "service_account"}', encoding="utf-8")
    result = subprocess.run(
        [
            str(helper), "deploy", "--root", str(tmp_path / "acervo"),
            "--google-credentials-file", str(elsewhere),
            "--bind-address", "127.0.0.1", "--port", "27701",
            "--app-bind-address", "127.0.0.1", "--app-port", "27702",
        ],
        text=True, capture_output=True, check=False,
    )
    assert result.returncode == 2
    assert "Unexpected Google credentials path" in result.stderr


def test_the_launcher_protocol_matches_the_deployer() -> None:
    """The two numbers are how a server learns its installed launcher is stale. Letting them drift
    means a launcher fix is written, shipped, and never installed — which is exactly how
    `--google-credentials-file` reached a launcher that had never heard of it."""
    helper = (REPO_ROOT / "deploy/acervo/remote-helper.sh").read_text(encoding="utf-8")
    deployer = (REPO_ROOT / "deploy.sh").read_text(encoding="utf-8")
    spoken = re.search(r"^PROTOCOL=(\d+)$", helper, re.MULTILINE)
    expected = re.search(r"^helper_protocol=(\d+)$", deployer, re.MULTILINE)
    assert spoken and expected
    assert spoken.group(1) == expected.group(1)


def test_every_installer_flag_the_deployer_forwards_is_one_the_launcher_accepts() -> None:
    """The launcher is a middle hop with its own allow-list, and a flag added at both ends but not
    in the middle fails only on a real server, at the end of a full release build."""
    deployer = (REPO_ROOT / "deploy.sh").read_text(encoding="utf-8")
    helper = (REPO_ROOT / "deploy/acervo/remote-helper.sh").read_text(encoding="utf-8")
    # Only the remote half. `--local` runs the installer directly and legitimately passes
    # `--credentials-stdin`, which the launcher has no reason to know about.
    remote = deployer[deployer.index("remote_installer="):]
    accepted = set(re.findall(r"^\s+(--[a-z-]+)\)", helper, re.MULTILINE))
    forwarded = set(re.findall(r"installer_arguments\s+(--[a-z-]+)", remote))
    forwarded |= set(re.findall(r"credential_args=[\"']?(--[a-z-]+)", remote))
    forwarded |= set(re.findall(r"credential_args\s+(--[a-z-]+)", remote))
    assert forwarded, "the pattern stopped matching; this test is no longer checking anything"
    assert forwarded <= accepted, f"the launcher rejects {sorted(forwarded - accepted)}"


def test_deploy_profile_supports_legacy_format_defaults_and_cli_precedence(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ssh_log = tmp_path / "ssh.log"
    ssh = bin_dir / "ssh"
    ssh.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >>\"$ACERVO_TEST_SSH_LOG\"\n"
        "case \"$*\" in *'deploy-acervo check'*) printf 'helper\\n' ;; esac\n",
        encoding="utf-8",
    )
    ssh.chmod(0o755)
    profile = tmp_path / ".acervo-deploy"
    profile.write_text("deployer@server.example.test\n", encoding="utf-8")
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "ACERVO_TEST_SSH_LOG": str(ssh_log),
            "ACERVO_DEPLOY_PROFILE": str(profile),
        }
    )

    legacy = subprocess.run(
        [str(REPO_ROOT / "deploy.sh"), "--configure-https"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert legacy.returncode == 0, legacy.stderr
    assert "--https-port 27702 --app-port 27702" in ssh_log.read_text(encoding="utf-8")

    profile.write_text(
        "DEPLOY_TARGET=deployer@server.example.test\n"
        "ACERVO_ROOT=/volume1/docker/acervo\n"
        "ACERVO_BIND_ADDRESS=127.0.0.1\n"
        "ACERVO_ANKI_PORT=27801\n"
        "ACERVO_APP_BIND_ADDRESS=127.0.0.1\n"
        "ACERVO_APP_PORT=27802\n"
        "ACERVO_HTTPS_PORT=27803\n",
        encoding="utf-8",
    )
    ssh_log.write_text("", encoding="utf-8")
    overridden = subprocess.run(
        [
            str(REPO_ROOT / "deploy.sh"),
            "--configure-https",
            "--app-port",
            "27902",
            "--https-port",
            "27903",
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert overridden.returncode == 0, overridden.stderr
    assert "--https-port 27903 --app-port 27902" in ssh_log.read_text(encoding="utf-8")

    saved_profile = tmp_path / "saved-acervo-deploy"
    env["ACERVO_DEPLOY_PROFILE"] = str(saved_profile)
    saved = subprocess.run(
        [
            str(REPO_ROOT / "deploy.sh"),
            "--target",
            "deployer@server.example.test",
            "--root",
            "/volume1/docker/acervo",
            "--https-port",
            "27903",
            "--remember-target",
            "--status",
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert saved.returncode == 0, saved.stderr
    assert saved_profile.stat().st_mode & 0o777 == 0o600
    assert saved_profile.read_text(encoding="utf-8") == (
        "DEPLOY_TARGET=deployer@server.example.test\n"
        "ACERVO_ROOT=/volume1/docker/acervo\n"
        "ACERVO_BIND_ADDRESS=127.0.0.1\n"
        "ACERVO_ANKI_PORT=27701\n"
        "ACERVO_APP_BIND_ADDRESS=127.0.0.1\n"
        "ACERVO_APP_PORT=27702\n"
        "ACERVO_HTTPS_PORT=27903\n"
        "ACERVO_SERVICE=\n"
    )


def test_configure_https_is_additive_idempotent_and_collision_safe(tmp_path: Path) -> None:
    helper = runnable_remote_helper(tmp_path)
    existing = (
        "https://server.example.com (tailnet only)\n"
        "|-- / proxy http://127.0.0.1:8080\n\n"
        "https://server.example.com:8091 (tailnet only)\n"
        "|-- / proxy http://127.0.0.1:8090\n\n"
        "https://server.example.com:8443 (tailnet only)\n"
        "|-- / proxy http://127.0.0.1:8000\n"
    )
    bin_dir, state, log = fake_tailscale_path(tmp_path, existing)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "ACERVO_TEST_TS_STATE": str(state),
            "ACERVO_TEST_TS_LOG": str(log),
        }
    )

    added = subprocess.run(
        [str(helper), "configure-https", "--https-port", "27702", "--app-port", "27702"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert added.returncode == 0, added.stderr
    assert log.read_text(encoding="utf-8") == (
        "serve --bg --yes --https=27702 http://127.0.0.1:27702\n"
    )
    assert state.read_text(encoding="utf-8").startswith(existing)

    log.write_text("", encoding="utf-8")
    repeated = subprocess.run(
        [str(helper), "configure-https", "--https-port", "27702", "--app-port", "27702"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert repeated.returncode == 0, repeated.stderr
    assert "already exists" in repeated.stdout
    assert log.read_text(encoding="utf-8") == ""

    occupied = subprocess.run(
        [str(helper), "configure-https", "--https-port", "8091", "--app-port", "27702"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert occupied.returncode == 1
    assert "Refusing to replace" in occupied.stderr
    assert log.read_text(encoding="utf-8") == ""


def test_configure_https_publishes_a_service_on_its_own_443(tmp_path: Path) -> None:
    """A service's 443 is its own virtual IP's, so it neither claims the host's nor collides with
    another service. This is what lets Android mint a WebAPK and install Acervo alongside another
    self-hosted app rather than replacing it."""
    helper = runnable_remote_helper(tmp_path)
    neighbour = '{"svc:calorie-logger":{"proxy":"http://127.0.0.1:8090"}}\n'
    bin_dir, state, log = fake_tailscale_service_path(tmp_path, neighbour)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "ACERVO_TEST_TS_STATE": str(state),
            "ACERVO_TEST_TS_LOG": str(log),
        }
    )

    added = subprocess.run(
        [str(helper), "configure-https", "--service", "acervo", "--app-port", "27702"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert added.returncode == 0, added.stderr
    assert log.read_text(encoding="utf-8") == (
        "serve --service=svc:acervo --bg --yes --https=443 http://127.0.0.1:27702\n"
    )
    # The neighbouring service is left exactly as it was.
    assert state.read_text(encoding="utf-8").startswith(neighbour)

    log.write_text("", encoding="utf-8")
    repeated = subprocess.run(
        [str(helper), "configure-https", "--service", "acervo", "--app-port", "27702"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert repeated.returncode == 0, repeated.stderr
    assert "already exists" in repeated.stdout
    assert log.read_text(encoding="utf-8") == ""


def test_configure_https_refuses_a_service_name_that_is_not_a_bare_label(tmp_path: Path) -> None:
    """`svc:` is reference syntax for the policy file and the CLI, never part of the name itself."""
    helper = runnable_remote_helper(tmp_path)
    bin_dir, state, log = fake_tailscale_service_path(tmp_path, "{}\n")
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "ACERVO_TEST_TS_STATE": str(state),
            "ACERVO_TEST_TS_LOG": str(log),
        }
    )

    for rejected in ("svc:acervo", "Acervo", "acervo app", ""):
        result = subprocess.run(
            [str(helper), "configure-https", "--service", rejected, "--app-port", "27702"],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 2, rejected
        # Rejected before Tailscale is invoked at all, so the log is never even created.
        assert not log.exists()


def test_configure_https_reports_a_tailscale_too_old_to_host_a_service(tmp_path: Path) -> None:
    """Services arrived in 1.86.0. An older client answers --service with its whole usage screen,
    which reads like a bug here rather than a server that needs updating."""
    helper = runnable_remote_helper(tmp_path)
    bin_dir, state, log = fake_tailscale_service_path(tmp_path, "{}\n", version="1.78.1")
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "ACERVO_TEST_TS_STATE": str(state),
            "ACERVO_TEST_TS_LOG": str(log),
        }
    )

    stale = subprocess.run(
        [str(helper), "configure-https", "--service", "acervo", "--app-port", "27702"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert stale.returncode == 1
    assert "1.86.0 or later is required" in stale.stderr
    assert "--https-port" in stale.stderr
    assert not log.exists()


def test_explicit_port_443_is_allowed_but_cannot_replace_an_existing_service(tmp_path: Path) -> None:
    helper = runnable_remote_helper(tmp_path)
    occupied_status = (
        "https://server.example.com (tailnet only)\n"
        "|-- / proxy http://127.0.0.1:8080\n"
    )
    bin_dir, state, log = fake_tailscale_path(tmp_path, occupied_status)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "ACERVO_TEST_TS_STATE": str(state),
            "ACERVO_TEST_TS_LOG": str(log),
        }
    )

    occupied = subprocess.run(
        [str(helper), "configure-https", "--https-port", "443", "--app-port", "27702"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert occupied.returncode == 1
    assert log.exists() is False

    state.write_text("", encoding="utf-8")
    allowed = subprocess.run(
        [str(helper), "configure-https", "--https-port", "443", "--app-port", "27702"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert allowed.returncode == 0, allowed.stderr
    assert log.read_text(encoding="utf-8") == (
        "serve --bg --yes --https=443 http://127.0.0.1:27702\n"
    )


def test_remote_robot_wrapper_streams_validated_input_without_scp(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ssh_log = tmp_path / "ssh.log"
    helper_upload = tmp_path / "run-worker.sh"
    input_upload = tmp_path / "input.tar.gz"
    ssh = bin_dir / "ssh"
    ssh.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$*\" >>\"$ACERVO_TEST_SSH_LOG\"\n"
        "case \"$*\" in\n"
        "  *'cat > /tmp/acervo-run-worker-'*) cat >\"$ACERVO_TEST_HELPER\" ;;\n"
        "  *'cat > /tmp/acervo-anki-input-'*) cat >\"$ACERVO_TEST_INPUT\" ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    ssh.chmod(0o755)
    scp = bin_dir / "scp"
    scp.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
    scp.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "ACERVO_TEST_SSH_LOG": str(ssh_log),
            "ACERVO_TEST_HELPER": str(helper_upload),
            "ACERVO_TEST_INPUT": str(input_upload),
        }
    )

    result = subprocess.run(
        [
            str(REPO_ROOT / "scripts/acervo_anki_remote.sh"),
            "--target",
            "deployer@server.example.test",
            "--root",
            "/volume1/docker/acervo",
            "anki-bootstrap-upload",
            str(REPO_ROOT / "examples/anki-sync-smoke/manifest.json"),
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert helper_upload.read_bytes() == (REPO_ROOT / "deploy/acervo/run-worker.sh").read_bytes()
    with tarfile.open(input_upload) as package:
        assert package.getnames() == ["manifest.json"]
    commands = ssh_log.read_text(encoding="utf-8")
    assert "--input-archive /tmp/acervo-anki-input-" in commands
    assert "--input-archive /tmp/acervo-anki-input-" in commands.split("anki-bootstrap-upload")[0]


def test_acervo_wide_defaults_are_not_anki_named() -> None:
    deploy = (REPO_ROOT / "deploy.sh").read_text(encoding="utf-8")
    installer = (REPO_ROOT / "deploy" / "acervo" / "install.sh").read_text(
        encoding="utf-8"
    )
    assert "$HOME/.acervo" in deploy
    assert "/volume1/docker/acervo" in installer
    assert "/opt/acervo" in installer
    assert "/etc/acervo-root" in installer
    assert "/volume1/docker/acervo-anki" not in deploy + installer


def test_app_and_anki_ports_are_distinct_and_collisions_are_rejected(tmp_path: Path) -> None:
    compose = (REPO_ROOT / "deploy/acervo/compose.yaml").read_text(encoding="utf-8")
    assert "${ACERVO_ANKI_PORT:-27701}:8080" in compose
    assert "${ACERVO_APP_PORT:-27702}:8000" in compose
    # The installer asks `docker port` about the same container port to check that publishing
    # actually happened, so the two statements of it have to agree. They disagree loudly rather than
    # quietly — an unanswered `docker port` fails the deployment — but agreeing is cheaper.
    installer = (REPO_ROOT / "deploy/acervo/install.sh").read_text(encoding="utf-8")
    assert 'docker port "$compose_project-server-1" 8000' in installer

    env, _ = deployment_env(tmp_path)
    result = subprocess.run(
        [
            str(REPO_ROOT / "deploy.sh"),
            "--local",
            "--port",
            "27800",
            "--app-port",
            "27800",
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2
    assert "must differ" in result.stderr


def test_shared_host_guardrails_are_documented_and_global_serve_mutations_are_absent() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    docs = (REPO_ROOT / "docs/operations/deployment.md").read_text(encoding="utf-8")
    helper = (REPO_ROOT / "deploy/acervo/remote-helper.sh").read_text(encoding="utf-8")
    combined = readme + docs

    assert "shared host" in combined.lower()
    assert "never assume" in combined
    assert "--https-port" in combined
    assert "serve --bg http://127.0.0.1:27702" not in combined
    assert "serve reset" not in helper
    assert "serve off" not in helper


def test_a_google_credential_that_is_not_one_is_refused_before_it_is_deployed(tmp_path: Path) -> None:
    """Vertex does not authenticate from a variable, so this is a file — and a file is the one kind
    of credential that can be plausibly wrong: an API key pasted into a file, the wrong export,
    something else entirely. Discovering that at the first capture costs a deployment cycle."""
    wrong = tmp_path / "not-a-key.json"
    wrong.write_text('{"api_key": "AIzaSyNotAKeyFile"}', encoding="utf-8")
    result = run_configure_llm(tmp_path, "--google-credentials", str(wrong))
    assert result.returncode == 2
    assert "neither a service-account key nor an" in result.stderr


@pytest.mark.parametrize("kind", ["service_account", "authorized_user"])
def test_both_shapes_google_actually_writes_are_accepted(tmp_path: Path, kind: str) -> None:
    """A key, and the file `gcloud auth application-default login` writes. Refusing the second would
    mean the one-command path that already works on a workstation could not reach the server."""
    good = tmp_path / "creds.json"
    good.write_text(f'{{"type": "{kind}", "client_email": "acervo-vertex@personal.example.com"}}',
                    encoding="utf-8")
    result = run_configure_llm(tmp_path, "--google-credentials", str(good))
    assert "neither a service-account key" not in result.stderr


def test_a_google_credential_is_installed_beside_the_env_file_and_named_from_inside(tmp_path: Path) -> None:
    env, root = deployment_env(tmp_path)
    key = tmp_path / "google.json"
    key.write_text('{"type": "service_account", "project_id": "p"}', encoding="utf-8")
    settings = tmp_path / "llm-credentials"
    settings.write_text(
        "GOOGLE_APPLICATION_CREDENTIALS=/run/acervo/credentials/google.json\n", encoding="utf-8"
    )
    settings.chmod(0o600)

    result = subprocess.run(
        [
            str(REPO_ROOT / "deploy/acervo/install.sh"),
            "--root", str(root),
            "--llm-credentials-file", str(settings),
            "--google-credentials-file", str(key),
            "--bind-address", "127.0.0.1", "--port", "27701",
            "--app-bind-address", "127.0.0.1", "--app-port", "27702",
        ],
        cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr

    installed = root / "credentials" / "google.json"
    assert installed.read_text(encoding="utf-8").startswith('{"type": "service_account"')
    assert installed.stat().st_mode & 0o777 == 0o600
    # The variable names the path the container will read, not the one it was uploaded from.
    llm = (root / "llm.env").read_text(encoding="utf-8")
    assert "GOOGLE_APPLICATION_CREDENTIALS=/run/acervo/credentials/google.json\n" in llm


def test_the_credentials_directory_exists_even_when_no_key_is_configured(tmp_path: Path) -> None:
    """A bind mount of a path that does not exist makes a root-owned directory instead, and the
    container then fails in a way that has nothing to do with the missing credential."""
    env, root = deployment_env(tmp_path)
    result = subprocess.run(
        [
            str(REPO_ROOT / "deploy/acervo/install.sh"),
            "--root", str(root),
            "--bind-address", "127.0.0.1", "--port", "27701",
            "--app-bind-address", "127.0.0.1", "--app-port", "27702",
        ],
        cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (root / "credentials").is_dir()
    assert "ACERVO_CREDENTIALS=" in (root / "deployment.env").read_text(encoding="utf-8")


def test_the_corpus_operator_token_is_minted_once_and_kept(tmp_path: Path) -> None:
    """Nobody types this one, so the installer mints it.

    The retrieval service refuses to start when channel mutations are enabled on a non-loopback
    bind with no operator token, and it is bound to `0.0.0.0` inside the compose network. Re-minting
    on every deploy would leave the running service holding a token the proxy no longer sends, so it
    is kept exactly as the signing secret is.
    """
    env, root = deployment_env(tmp_path)
    secrets = root / "secrets.env"
    # A root that predates the corpus service: the token is absent and has to be appended.
    secrets.write_text(
        "ACERVO_ANKI_SYNC_USERNAME=test\nACERVO_ANKI_SYNC_PASSWORD=password\n"
        "ACERVO_JWT_SECRET='a-durable-signing-secret'\n",
        encoding="utf-8",
    )
    secrets.chmod(0o600)

    def deploy() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                str(REPO_ROOT / "deploy/acervo/install.sh"),
                "--root", str(root),
                "--bind-address", "127.0.0.1", "--port", "27701",
                "--app-bind-address", "127.0.0.1", "--app-port", "27702",
            ],
            cwd=REPO_ROOT, env=env, text=True, capture_output=True, check=False,
        )

    assert deploy().returncode == 0
    written = secrets.read_text(encoding="utf-8")
    minted = re.search(
        r"^ACERVO_SPEECH_OPERATOR_TOKEN='([A-Za-z0-9]{16,})'$", written, flags=re.MULTILINE
    )
    assert minted, written
    # It is a credential, so it belongs beside the others rather than in llm.env — whose writer only
    # accepts names a provider row in models/catalogue.json reads, and would reject this one.
    assert "ACERVO_SPEECH_OPERATOR_TOKEN" not in (root / "llm.env").read_text(encoding="utf-8")

    assert deploy().returncode == 0
    again = secrets.read_text(encoding="utf-8")
    assert again.count("ACERVO_SPEECH_OPERATOR_TOKEN") == 1
    assert minted.group(1) in again


def test_neither_reset_can_reach_the_caption_cache(tmp_path: Path) -> None:
    """The one store here that is neither disposable nor rebuildable from anything Acervo holds.

    Downloaded captions cost bandwidth and cannot politely be re-fetched, so the greenfield rule
    that development data is disposable stops at this directory. The index beside it is derived and
    may be thrown away freely. Asserted rather than trusted, because both resets delete by literal
    path and a fourth path added to either list would be silent.
    """
    installer = (REPO_ROOT / "deploy/acervo/install.sh").read_text(encoding="utf-8")
    deletions = re.findall(r"^\s*rm -rf -- (.+)$", installer, flags=re.MULTILINE)
    assert deletions, "expected the installer to delete something on the reset paths"

    for deletion in deletions:
        assert "speech-cache" not in deletion, deletion
        assert "speech-index" not in deletion, deletion
        assert "speech-catalogues" not in deletion, deletion

    # deploy.sh forwards the reset flags and deletes nothing itself; a volume removal there would
    # bypass the check above entirely.
    launcher = (REPO_ROOT / "deploy.sh").read_text(encoding="utf-8")
    assert "docker volume rm" not in launcher
    assert "down -v" not in launcher and "down --volumes" not in launcher


def test_old_release_trees_are_pruned_but_the_current_one_survives(tmp_path: Path) -> None:
    """Releases used to accumulate forever; backups have always rotated.

    Each tree carries the compiled dictionaries and the macOS application, so an unpruned
    `releases/` grows by hundreds of megabytes per deployment — 48 had piled up before this existed.
    Nothing rolls back to an old release, so the ones kept are for looking at rather than running,
    and the current one must survive because `run-worker.sh` reads its compose file.
    """
    env, root = deployment_env(tmp_path)
    releases = root / "releases"
    releases.mkdir(parents=True)
    for day in range(1, 6):
        tree = releases / f"2026090{day}T120000Z"
        tree.mkdir()
        (tree / "marker").write_text("release", encoding="utf-8")

    result = run_local(env)
    assert result.returncode == 0, result.stderr

    survivors = sorted(path.name for path in releases.iterdir())
    current = Path((root / "current-release").read_text(encoding="utf-8").strip())

    # Three kept: the release this deployment just made, plus the two newest of the five.
    assert len(survivors) == 3, survivors
    assert survivors[:2] == ["20260904T120000Z", "20260905T120000Z"], survivors
    assert current.name == survivors[2], (current, survivors)
    assert current.is_dir(), "the current release must survive; run-worker.sh reads its compose file"


def test_pruning_releases_is_idempotent_and_safe_when_there_are_few(tmp_path: Path) -> None:
    env, root = deployment_env(tmp_path)
    releases = root / "releases"
    releases.mkdir(parents=True)
    (releases / "20260901T120000Z").mkdir()

    assert run_local(env).returncode == 0
    # One old tree plus the one this deployment made: under the limit, so nothing is pruned.
    assert sorted(path.name for path in releases.iterdir())[0] == "20260901T120000Z"
    assert len(list(releases.iterdir())) == 2

    # A second deployment prunes nothing new and never removes what it is about to run from.
    assert run_local(env).returncode == 0
    survivors = sorted(path.name for path in releases.iterdir())
    assert len(survivors) == 3, survivors
    assert survivors[0] == "20260901T120000Z"
    assert Path((root / "current-release").read_text(encoding="utf-8").strip()).is_dir()


def test_the_launcher_runs_the_worker_from_the_current_release(tmp_path: Path) -> None:
    """A scheduled job needs root without a password, and on Synology reaching Docker *is* reaching
    root — the socket is root-owned and there is no docker group. So the worker goes through the
    same reviewed launcher as everything else rather than a blanket NOPASSWD on docker."""
    helper = runnable_remote_helper(tmp_path)
    root = tmp_path / "acervo"
    release = root / "releases" / "20260910T120000Z"
    (release / "deploy" / "acervo").mkdir(parents=True)
    recorded = tmp_path / "recorded"
    worker = release / "deploy" / "acervo" / "run-worker.sh"
    worker.write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" >"{recorded}"\n', encoding="utf-8")
    worker.chmod(0o755)
    (root / "current-release").write_text(f"{release}\n", encoding="utf-8")

    result = subprocess.run(
        [str(helper), "worker", "--root", str(root), "anki-pull-state"],
        text=True, capture_output=True, check=False,
    )

    assert result.returncode == 0, result.stderr
    # The root is passed on, so the worker script does not have to resolve it a second time and
    # cannot disagree with the launcher about which deployment this is.
    assert recorded.read_text(encoding="utf-8").strip() == f"--root {root} anki-pull-state"


def test_the_launcher_passes_worker_arguments_through(tmp_path: Path) -> None:
    helper = runnable_remote_helper(tmp_path)
    root = tmp_path / "acervo"
    release = root / "releases" / "20260910T120000Z"
    (release / "deploy" / "acervo").mkdir(parents=True)
    recorded = tmp_path / "recorded"
    worker = release / "deploy" / "acervo" / "run-worker.sh"
    worker.write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" >"{recorded}"\n', encoding="utf-8")
    worker.chmod(0o755)
    (root / "current-release").write_text(f"{release}\n", encoding="utf-8")

    result = subprocess.run(
        [str(helper), "worker", "--root", str(root), "backfill", "--limit", "50"],
        text=True, capture_output=True, check=False,
    )

    assert result.returncode == 0, result.stderr
    assert recorded.read_text(encoding="utf-8").strip().endswith("backfill --limit 50")


def test_the_launcher_refuses_a_worker_operation_that_is_not_a_bare_word(tmp_path: Path) -> None:
    """The operation allow-list belongs to run-worker.sh, which already has one; a second copy here
    would drift from it. What this guards is only that nothing path-like or flag-like arrives where
    a subcommand is expected."""
    helper = runnable_remote_helper(tmp_path)
    root = tmp_path / "acervo"
    release = root / "releases" / "20260910T120000Z"
    (release / "deploy" / "acervo").mkdir(parents=True)
    worker = release / "deploy" / "acervo" / "run-worker.sh"
    worker.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    worker.chmod(0o755)
    (root / "current-release").write_text(f"{release}\n", encoding="utf-8")

    for rejected in ("../../etc/shadow", "/bin/sh", "-rf", "index clips", "index;clips"):
        result = subprocess.run(
            [str(helper), "worker", "--root", str(root), rejected],
            text=True, capture_output=True, check=False,
        )
        assert result.returncode == 2, f"{rejected!r} was accepted: {result.stdout}{result.stderr}"


def test_the_launcher_refuses_a_worker_run_with_no_deployment(tmp_path: Path) -> None:
    helper = runnable_remote_helper(tmp_path)
    root = tmp_path / "acervo"
    root.mkdir()

    result = subprocess.run(
        [str(helper), "worker", "--root", str(root), "anki-pull-state"],
        text=True, capture_output=True, check=False,
    )

    assert result.returncode == 2
    assert "No deployed release" in result.stderr


def test_the_launcher_refuses_an_unexpected_acervo_root(tmp_path: Path) -> None:
    """The same guard `run-worker.sh` and the installer apply: a root that is not `/*/acervo` is a
    mistake, and this one runs as root."""
    helper = runnable_remote_helper(tmp_path)

    result = subprocess.run(
        [str(helper), "worker", "--root", str(tmp_path / "elsewhere"), "anki-pull-state"],
        text=True, capture_output=True, check=False,
    )

    assert result.returncode == 2
    assert "Refusing unexpected Acervo root" in result.stderr


def test_the_loop_service_is_given_no_provider_credential_at_all() -> None:
    """The one companion service that calls no model, and its absence from the tuple above is the
    design rather than an oversight.

    LexiBeat is *handed* a voice: `serve.py` implements its Backend as a call home to
    POST /pronunciations/take, carrying a render-scoped token that arrives with the request and
    lives in the process. So there is one rate limiter, one cooldown, one call log and one place the
    owner chooses — all of them on the server — and nothing in this container to leak, rotate or keep
    in step. Asserted rather than merely commented, because the natural thing for somebody adding a
    variable to the services above is to add it here too (plan §2.2).
    """
    import yaml

    compose = yaml.safe_load(
        (REPO_ROOT / "deploy/acervo/compose.yaml").read_text(encoding="utf-8")
    )
    service = compose["services"]["lexibeat"]
    environment = set(service.get("environment") or {})
    forbidden = {
        "ACERVO_TEXT_CHAIN", "GEMINI_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY",
        "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "ACERVO_OLLAMA_URL",
        "ACERVO_VERTEX_PROJECT", "GOOGLE_APPLICATION_CREDENTIALS", "ACERVO_VERTEX_ACCOUNT",
        "ACERVO_JWT_SECRET",
    }
    assert not (forbidden & environment), f"lexibeat must hold no credential: {sorted(forbidden & environment)}"
    # Vertex's is a *file*, so not mounting the directory is half of the same statement.
    assert not any("/run/acervo/credentials" in mount for mount in service.get("volumes") or [])
    # And nothing outside the compose network may reach it: a render is asked for by the server.
    assert "ports" not in service


def test_the_loop_sample_bundle_is_never_deleted_by_a_reset() -> None:
    """~3.1 GB fetched once, and the dictionaries arrangement for the dictionaries' reason: it is the
    owner's own data moved between the owner's own machines, not something a reset should cost them.

    `--reset-anki` clears the Anki collections and the worker's, and nothing else — so this asserts
    the bundle directory is not named there rather than that some exclusion list contains it.
    """
    installer = (REPO_ROOT / "deploy/acervo/install.sh").read_text(encoding="utf-8")
    reset = installer.split("if [ \"$reset_anki\" = true ]; then", 1)[1].split("fi", 1)[0]
    assert "lexibeat" not in reset
    assert "data/lexibeat-bundle" in installer, "the installer must still create the bundle directory"


def test_every_service_that_calls_a_model_is_given_the_same_credentials() -> None:
    """Three services walk the owner's chain, and they must be able to walk all of it.

    Nothing asserted this, and the speech service was silently missing Cloudflare's two variables
    while the server and the worker had them. The symptom is as bad as it is quiet: a catalogue row
    is checked for environment variables, so the row looks perfectly available *in the container
    that has them* and is simply skipped in the one that does not — and a chain naming only that row
    fails every call there while succeeding everywhere else.
    """
    import yaml

    compose = yaml.safe_load(
        (REPO_ROOT / "deploy/acervo/compose.yaml").read_text(encoding="utf-8")
    )
    callers = ("server", "acervo-worker", "speech-retrieval")
    # Everything a catalogue row names, plus the chain that orders them. Not a wildcard over the
    # services' environments: each carries variables of its own that have no business being shared.
    required = {
        "ACERVO_TEXT_CHAIN", "GEMINI_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY",
        "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "ACERVO_OLLAMA_URL",
        "ACERVO_VERTEX_PROJECT", "GOOGLE_APPLICATION_CREDENTIALS", "ACERVO_VERTEX_ACCOUNT",
    }
    for name in callers:
        environment = set(compose["services"][name]["environment"])
        assert required <= environment, f"{name} is missing {sorted(required - environment)}"
    # Vertex is the one credential that is a file, so the directory has to be mounted as well as
    # named — half of that configuration works exactly as badly as none of it.
    for name in callers:
        mounts = " ".join(compose["services"][name]["volumes"])
        assert "/run/acervo/credentials" in mounts, f"{name} cannot read Vertex credentials"


def test_the_speech_image_can_authenticate_to_vertex() -> None:
    """LiteLLM does not require `google-auth`, and reaches Vertex through a deferred import of it.

    The server image gets it transitively through `google-genai`; this one installs LiteLLM alone
    and got nothing, so a Vertex chain raised on the first real call — with the row having looked
    entirely available, because availability is environment variables and a credentials file and
    never an importable library. The `[requests]` extra is what supplies
    `google.auth.transport.requests`; LiteLLM itself depends on httpx.
    """
    dockerfile = (REPO_ROOT / "deploy/acervo/speech/Dockerfile").read_text(encoding="utf-8")
    assert "google-auth[requests]" in dockerfile


def test_the_speech_image_carries_every_acervo_module_its_launcher_imports() -> None:
    """The image copies Acervo's modules one by one rather than installing the package, so an import
    added to `serve.py` without a `COPY` beside it builds cleanly and dies on start."""
    serve = (REPO_ROOT / "deploy/acervo/speech/serve.py").read_text(encoding="utf-8")
    dockerfile = (REPO_ROOT / "deploy/acervo/speech/Dockerfile").read_text(encoding="utf-8")
    imported = set(re.findall(r"^from acervo\.(\w+)", serve, re.MULTILINE))
    assert imported
    for module in imported:
        assert (f"COPY src/acervo/{module} " in dockerfile
                or f"COPY src/acervo/{module}.py " in dockerfile), f"acervo.{module} is not in the image"
