from __future__ import annotations

import re
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
HOME_PATH = re.compile(r"/(Users|home)/([A-Za-z][A-Za-z0-9._-]*)/")
EMAIL_OR_SSH_TARGET = re.compile(
    r"\b([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b"
)
PRIVATE_ADDRESS = re.compile(
    r"\b(?:192\.168\.\d{1,3}\.\d{1,3}|"
    r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
    r"100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3})\b"
)
SECRET_SHAPE = re.compile(
    r"\b(?:AIza[A-Za-z0-9_-]{30,}|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,})\b"
)

# Placeholder local parts, allowed on any domain.
#
# The reserved `.example.com` domains cover almost everything, but not documentation that has to
# name a *provider* account: `docs/providers.md` tells the owner to bind an IAM role
# to their Google login, and `learner@account.example.com` there would be worse than useless — it
# implies a domain that cannot be a Google account, so a reader would copy something that cannot
# work. The address has to look like what they will actually type.
#
# **The local part is the identifying half**, which is why the exception is written here and not as
# an allowed domain. `address@gmail.com` names nobody; the leak this test exists to catch is a real
# local part, and that is caught on gmail.com exactly as before.
PLACEHOLDER_LOCALS = {"address", "you", "your-account", "name"}


def candidate_text_files():
    listing = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    ).stdout.decode().split("\0")
    for relative in filter(None, listing):
        # Generated registry metadata can contain package maintainers' public contact addresses;
        # it cannot contain local deployment configuration and is not repository-authored prose.
        if relative.endswith("package-lock.json"):
            continue
        path = REPO_ROOT / relative
        if not path.is_file():
            continue
        try:
            yield relative, path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue


def test_candidate_repository_files_contain_no_personal_details_or_secrets():
    violations = []
    for relative, contents in candidate_text_files():
        for match in HOME_PATH.finditer(contents):
            if match.group(2) not in {"user", "example"}:
                violations.append(f"{relative}: personal home path {match.group(0)!r}")
        for match in EMAIL_OR_SSH_TARGET.finditer(contents):
            if match.group(0).endswith("@2x.png"):
                continue  # Standard Apple Retina asset filename, not an address.
            domain = match.group(2).lower()
            if match.group(1).lower() in PLACEHOLDER_LOCALS:
                continue  # Names nobody, whatever the domain. See PLACEHOLDER_LOCALS.
            if not (domain.endswith(".example.com") or domain.endswith(".example.test")):
                violations.append(f"{relative}: non-reserved address {match.group(0)!r}")
        for match in PRIVATE_ADDRESS.finditer(contents):
            violations.append(f"{relative}: private address {match.group(0)!r}")
        for match in SECRET_SHAPE.finditer(contents):
            violations.append(f"{relative}: credential-shaped value {match.group(0)!r}")
    assert violations == []


def test_editor_swap_files_are_ignored():
    ignored = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "*.swp" in ignored
    assert "*.swo" in ignored


def test_local_operational_notes_stay_ignored():
    """These carry an account, a hostname and home paths, and the scan above only sees what git
    would publish — so the ignore rule is the whole defence."""
    ignored = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    for path in ("/ingest.sh", "/TODO.txt", "/vertex-remote-config.txt"):
        assert path in ignored
