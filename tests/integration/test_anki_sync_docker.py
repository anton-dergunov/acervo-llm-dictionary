from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
import uuid
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "deploy" / "acervo" / "compose.yaml"
NOTE_IDS = (
    "note00000000001",
    "note00000000002",
)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def parse_json(output: str) -> dict:
    start = output.find("{")
    if start < 0:
        raise AssertionError(f"no JSON object in command output:\n{output}")
    return json.loads(output[start:])


def write_manifest(input_dir: Path, *, updated: bool = False) -> None:
    media = input_dir / "media"
    media.mkdir(exist_ok=True)
    (media / "balsa.webp").write_bytes(
        b"RIFFupdated-WEBP" if updated else b"RIFFinitial-WEBP"
    )
    (media / "balsa.mp3").write_bytes(b"ID3-acervo-audio")
    payload = {
        "schema_version": 2,
        "notes": [
            {
                "kind": "meaning",
                "note_id": NOTE_IDS[0],
                "lexeme_id": "lexeme000000001",
                "sense_id": "sense0000000001",
                "deck": "Spanish::Vocabulary",
                "fields": {
                    "Recognise": "y",
                    "Headword": "balsa",
                    "Sentence": "La balsa actualizada" if updated else "La balsa",
                    "Translation": "The raft",
                    "Note": "Updated." if updated else "A vessel.",
                },
                "tags": [
                    "acervo::topic::nature" if updated else "acervo::topic::travel"
                ],
                "media": {"Picture": "media/balsa.webp", "HeadwordAudio": "media/balsa.mp3"},
            },
            {
                "kind": "meaning",
                "note_id": NOTE_IDS[1],
                "lexeme_id": "lexeme000000002",
                "sense_id": "sense0000000002",
                "deck": "Spanish::Vocabulary",
                "fields": {"Recognise": "y", "Headword": "arroyo", "Sentence": "El arroyo",
                           "Translation": "The stream"},
                "tags": ["acervo::topic::nature"],
            },
        ],
    }
    (input_dir / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.integration
def test_official_server_and_headless_clients_round_trip(tmp_path: Path) -> None:
    if os.environ.get("RUN_DOCKER_INTEGRATION_TESTS", "").lower() != "true":
        pytest.skip("set RUN_DOCKER_INTEGRATION_TESTS=true to run Docker validation")
    if shutil.which("docker") is None:
        pytest.skip("Docker CLI is unavailable")

    project = f"acervo-test-{uuid.uuid4().hex[:10]}"
    server = tmp_path / "server"
    robot = tmp_path / "robot"
    mobile = tmp_path / "mobile"
    input_dir = tmp_path / "input"
    for directory in (server, robot, mobile, input_dir):
        directory.mkdir()
    write_manifest(input_dir)

    credentials = tmp_path / "secrets.env"
    credentials.write_text(
        "ACERVO_ANKI_SYNC_USERNAME=acervo-test\n"
        "ACERVO_ANKI_SYNC_PASSWORD=correct-horse-battery\n",
        encoding="utf-8",
    )
    credentials.chmod(0o600)
    deployment = tmp_path / "deployment.env"
    deployment.write_text(
        f"ACERVO_UID={os.getuid()}\n"
        f"ACERVO_GID={os.getgid()}\n"
        "ACERVO_BIND_ADDRESS=127.0.0.1\n"
        f"ACERVO_ANKI_PORT={free_port()}\n"
        f"ACERVO_ANKI_SERVER_DATA={server}\n"
        f"ACERVO_WORKER_DATA={robot}\n"
        f"ACERVO_INPUT_PATH={input_dir}\n",
        encoding="utf-8",
    )

    base = [
        "docker",
        "compose",
        "-p",
        project,
        "--env-file",
        str(deployment),
        "--env-file",
        str(credentials),
        "-f",
        str(COMPOSE_FILE),
    ]
    evidence_dir_value = os.environ.get("ACERVO_EVIDENCE_DIR")
    evidence_dir = Path(evidence_dir_value) if evidence_dir_value else tmp_path / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [*base, *args],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        with (evidence_dir / "commands.log").open("a", encoding="utf-8") as log:
            log.write(f"$ {' '.join(args)}\n{result.stdout}{result.stderr}\n")
        if check and result.returncode:
            raise AssertionError(
                f"Docker command failed ({result.returncode}): {' '.join(args)}\n"
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        return result

    def robot_command(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return run("--profile", "tools", "run", "--rm", "-T", "acervo-worker", "anki", *args, check=check)

    def mobile_command(command: str) -> dict:
        result = run(
            "--profile",
            "tools",
            "run",
            "--rm",
            "-T",
            "--entrypoint",
            "python",
            "-v",
            f"{mobile}:/mobile",
            "acervo-worker",
            "/app/scripts/integration/anki_sync_client.py",
            command,
            "--endpoint",
            "http://anki-sync-server:8080/",
            "--collection",
            "/mobile/collection.anki2",
        )
        return parse_json(result.stdout)

    try:
        run("build")
        run("up", "-d", "anki-sync-server")
        for _ in range(30):
            health = run("ps", "--format", "json").stdout
            if "healthy" in health:
                break
            time.sleep(1)
        else:
            pytest.fail("sync server did not become healthy")

        bootstrap = parse_json(
            robot_command("bootstrap-upload", "/input/manifest.json").stdout
        )
        assert bootstrap["created"] == 2
        assert bootstrap["media_added"] == 2

        first_mobile = mobile_command("download")
        assert len(first_mobile["notes"]) == 2
        first_ids = {
            note["note_id"]: (note["anki_note_id"], note["card_ids"])
            for note in first_mobile["notes"]
        }
        balsa = next(note for note in first_mobile["notes"] if note["note_id"] == NOTE_IDS[0])
        assert len(balsa["media"]) == 2

        mobile_command("review-state")
        write_manifest(input_dir, updated=True)
        update = parse_json(robot_command("push", "/input/manifest.json").stdout)
        assert update["created"] == 0
        assert update["updated"] == 1
        assert update["unchanged"] == 1
        assert update["media_added"] == 1

        updated_mobile = mobile_command("sync")
        updated_ids = {
            note["note_id"]: (note["anki_note_id"], note["card_ids"])
            for note in updated_mobile["notes"]
        }
        assert updated_ids == first_ids
        balsa = next(note for note in updated_mobile["notes"] if note["note_id"] == NOTE_IDS[0])
        assert balsa["sentence"] == "La balsa actualizada"
        assert balsa["reps"] == [9]
        assert balsa["lapses"] == [3]
        assert balsa["flags"] == [2]
        assert len(balsa["media"]) == 2

        noop = parse_json(robot_command("push", "/input/manifest.json").stdout)
        assert noop["created"] == 0
        assert noop["updated"] == 0
        assert noop["unchanged"] == 2
        assert noop["media_added"] == 0

        state = parse_json(robot_command("export-state").stdout)
        exported = next(note for note in state["notes"] if note["note_id"] == NOTE_IDS[0])
        assert exported["cards"][0]["reps"] == 9
        assert exported["cards"][0]["lapses"] == 3
        assert exported["cards"][0]["flag"] == 2

        run("restart", "anki-sync-server")
        time.sleep(2)
        assert len(mobile_command("sync")["notes"]) == 2

        mobile_command("schema-drift")
        refused = robot_command("push", "/input/manifest.json", check=False)
        assert refused.returncode != 0
        assert "full-sync" in refused.stderr.lower() or "full_sync" in refused.stderr.lower()

        (evidence_dir / "health.json").write_text(
            run("ps", "--format", "json").stdout, encoding="utf-8"
        )
        (evidence_dir / "server.log").write_text(
            run("logs", "--no-color", "anki-sync-server").stdout,
            encoding="utf-8",
        )
    finally:
        run("down", "--volumes", "--remove-orphans", check=False)


@pytest.mark.integration
def test_local_deploy_wrapper_preserves_temporary_dot_acervo(tmp_path: Path) -> None:
    if os.environ.get("RUN_DOCKER_INTEGRATION_TESTS", "").lower() != "true":
        pytest.skip("set RUN_DOCKER_INTEGRATION_TESTS=true to run Docker validation")
    if shutil.which("docker") is None:
        pytest.skip("Docker CLI is unavailable")

    home = tmp_path / "home"
    acervo_root = home / ".acervo"
    robot_data = acervo_root / "data" / "acervo-worker"
    robot_data.mkdir(parents=True)
    sentinel = robot_data / "preserve-me"
    sentinel.write_text("persistent", encoding="utf-8")
    database = robot_data / "collection.anki2"
    database.write_bytes(b"deployment-backup-probe")
    secrets = acervo_root / "secrets.env"

    project = f"acervo-deploy-test-{uuid.uuid4().hex[:10]}"
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home),
            "ACERVO_COMPOSE_PROJECT": project,
            "ACERVO_ANKI_PORT": str(free_port()),
        }
    )
    def deploy(*arguments: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(REPO_ROOT / "deploy.sh"), "--local", *arguments],
            cwd=REPO_ROOT,
            env=env,
            input=stdin,
            text=True,
            capture_output=True,
            check=False,
        )

    try:
        first = deploy(
            "--configure-credentials",
            stdin="deploy-test\ndeploy-password\ndeploy-test@account.example.com\ndeploy-password\n\n",
        )
        assert first.returncode == 0, first.stderr
        second = deploy()
        assert second.returncode == 0, second.stderr
        assert sentinel.read_text(encoding="utf-8") == "persistent"
        assert database.read_bytes() == b"deployment-backup-probe"
        assert any(
            path.read_bytes() == b"deployment-backup-probe"
            for path in (acervo_root / "backups").rglob("collection.anki2")
        )
        assert secrets.stat().st_mode & 0o777 == 0o600
    finally:
        deployment = acervo_root / "deployment.env"
        if deployment.exists():
            subprocess.run(
                [
                    "docker",
                    "compose",
                    "-p",
                    project,
                    "--env-file",
                    str(deployment),
                    "--env-file",
                    str(secrets),
                    "-f",
                    str(COMPOSE_FILE),
                    "down",
                    "--volumes",
                    "--remove-orphans",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
