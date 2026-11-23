#!/usr/bin/env python3
"""Check the actual bootstrap bundle against a prepared, unpublished delivery.

The generated zipapp runs as a subprocess with an isolated fixture HOME. No
SteamOS/Decky/OBS installation is simulated as a pass: verification-only exits
before those boundaries. Public GitHub downloads and real device installation
remain separately unrun. Only this script's private fixture copies are changed.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def private_output(path):
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("Use a new absolute output directory")
    for parent in path.parents:
        info = parent.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, os.getuid()) or
                info.st_mode & 0o022 and not info.st_mode & stat.S_ISVTX):
            raise ValueError("Output ancestry must be protected against replacement")
    if path.parent.stat().st_uid != os.getuid():
        raise ValueError("Output parent must belong to this test user")
    path.mkdir(mode=0o700)


def file_snapshot(root):
    """Include inodes so a replaced coordination lock cannot look preserved."""
    return {str(path.relative_to(root)): {
                "sha256": digest(path.read_bytes()),
                "inode": path.stat().st_ino,
                "mode": stat.S_IMODE(path.stat().st_mode)}
            for path in root.rglob("*") if path.is_file()}


def refresh_delivery(directory):
    """Keep outer integrity coherent to reach the intended binding boundary.

    This is a deliberately modified private negative fixture, never a candidate
    or a publisher attestation. Matching a checksum must not accept wrong source
    identity, an unsafe archive or a crossed bootstrap.
    """
    sums = directory / "SHA256SUMS"
    if sums.is_file():
        rows = []
        for row in sums.read_text().splitlines():
            match = re.fullmatch(r"[0-9a-f]{64} [ *]([A-Za-z0-9._-]+)", row)
            if not match:
                raise ValueError("Unexpected fixture runtime checksum format")
            name = match[1]
            rows.append(digest((directory / name).read_bytes()) + "  " + name + "\n")
        sums.write_text("".join(rows))
    path = directory / "installer-manifest.json"
    manifest = json.loads(path.read_text())
    for name, entry in manifest["artifacts"].items():
        source = directory / name
        if source.is_file() and not source.is_symlink():
            data = source.read_bytes()
            entry.update(size=len(data), sha256=digest(data))
    path.write_bytes(canonical(manifest))
    names = sorted([*manifest["artifacts"], "installer-manifest.json"])
    (directory / "INSTALLER-SHA256SUMS").write_text("".join(
        digest((directory / name).read_bytes()) + "  " + name + "\n"
        for name in names if (directory / name).is_file() and not (directory / name).is_symlink()))


def exercise(bundle, delivery, output, revision):
    with zipfile.ZipFile(bundle) as archive:
        metadata = json.loads(archive.read("bootstrap-metadata.json"))
    manifest = json.loads((delivery / "installer-manifest.json").read_text())
    version = manifest["version"]
    if metadata.get("revision") != revision or manifest.get("revision") != revision:
        raise ValueError("Both inputs must match the exact selected source revision")
    if metadata.get("version") != version or "-" not in version:
        raise ValueError("Use the matching explicit preview candidate for this qualification fixture")
    expected_bundle = manifest.get("artifacts", {}).get("deckystream-install.pyz", {})
    if expected_bundle.get("sha256") != digest(bundle.read_bytes()):
        raise ValueError("Use the exact bootstrap recorded by this delivery")

    home = output / "fixture-home"
    home.mkdir(mode=0o700)
    secrets = ("private-fixture-stream-key-DO-NOT-REPORT", "private-fixture-control-secret-DO-NOT-REPORT")
    retained = {
        ".config/obsgod/secrets.json": canonical({"stream_key": secrets[0], "obs_password": secrets[1]}),
        ".config/obsgod/deck.json": b'{"capture_mode":"game"}\n',
        ".local/state/obsgod/control.lock": b"",
        ".local/share/obsgod/installed-marker": b"prior fixture installation\n",
        "Videos/OBSGod/keep.mp4": b"preserved fixture media\n",
        ".var/app/com.obsproject.Studio/config/obs-studio/ordinary.ini": b"ordinary OBS fixture\n",
    }
    for name, data in retained.items():
        target = home / name
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        target.write_bytes(data)
        target.chmod(0o600)
    before = file_snapshot(home)

    def preserved():
        after = file_snapshot(home)
        return all(after.get(name) == entry for name, entry in before.items())
    commands = output / "forbidden-commands"
    commands.mkdir(mode=0o700)
    invoked = output / "unexpected-command"
    for name in ("flatpak", "steam", "obs", "obs-studio", "sudo", "pkexec", "xdg-open", "kdialog", "zenity"):
        target = commands / name
        target.write_text("#!/bin/sh\nprintf '%s\\n' " + name + " >> '" + str(invoked).replace("'", "'\\''") + "'\nexit 97\n")
        target.chmod(0o700)
    env = dict(os.environ)
    for key in ("PYTHONHOME", "PYTHONPATH", "DECKYSTREAM_DECKY_STORAGE_MAP", "DECKYSTREAM_DECKY_RUNTIME_DIR", "DECKYSTREAM_DECKY_LOG_DIR"):
        env.pop(key, None)
    env.update(HOME=str(home), XDG_CONFIG_HOME=str(home / ".config"),
               XDG_DATA_HOME=str(home / ".local/share"), XDG_STATE_HOME=str(home / ".local/state"),
               XDG_CACHE_HOME=str(home / ".cache"), PATH=str(commands) + os.pathsep + env.get("PATH", ""),
               HTTP_PROXY="http://127.0.0.1:9", HTTPS_PROXY="http://127.0.0.1:9", ALL_PROXY="http://127.0.0.1:9",
               http_proxy="http://127.0.0.1:9", https_proxy="http://127.0.0.1:9", all_proxy="http://127.0.0.1:9",
               NO_PROXY="", no_proxy="")
    checks = []

    def run(name, arguments, success):
        command = [sys.executable, "-I", "-B", str(bundle), *arguments]
        result = subprocess.run(command, capture_output=True, text=True, env=env, timeout=45)
        combined = result.stdout + result.stderr
        if any(secret in combined for secret in secrets):
            raise AssertionError("Bootstrap diagnostics exposed a synthetic private fixture value")
        log = output / (name + ".log")
        log.write_text(combined)
        log.chmod(0o600)
        item = {"name": name, "command": command, "expected": "passed" if success else "refused",
                "exit_code": result.returncode, "log_sha256": digest(log.read_bytes()),
                "existing_files_and_lock_inode_preserved": preserved(),
                "forbidden_commands_unrun": not invoked.exists(),
                "result": "passed" if ((result.returncode == 0) == success and
                    "Traceback (most recent call last)" not in combined and
                    preserved() and not invoked.exists()) else "failed"}
        checks.append(item)
        if item["result"] != "passed":
            raise AssertionError(name + " did not meet its expected boundary; inspect its private log")
        return combined

    def verify_args(directory=delivery):
        return ["--delivery", str(directory), "--verify-only", "--channel", "preview", "--version", version]

    inspected = run("inspect-embedded-metadata", ["--inspect"], True)
    if version not in inspected or revision not in inspected:
        raise AssertionError("Inspect omitted the actual bundle version or source revision")
    run("verify-matching-unpublished-candidate", verify_args(), True)
    run("stable-default-refuses-preview", ["--delivery", str(delivery), "--verify-only"], False)
    run("different-explicit-version-refused", ["--delivery", str(delivery), "--verify-only", "--channel", "preview", "--version", "999.0.0"], False)

    def modified(name, mutation, success=False):
        with tempfile.TemporaryDirectory(prefix="bootstrap-negative-", dir=output) as temporary:
            copied = Path(temporary) / "delivery"
            shutil.copytree(delivery, copied)
            mutation(copied)
            run(name, verify_args(copied), success)

    def negative(name, mutation):
        modified(name, mutation)

    def change_manifest(field, value):
        def change(directory):
            path = directory / "installer-manifest.json"
            value_ = json.loads(path.read_text())
            value_[field] = value
            path.write_bytes(canonical(value_))
            refresh_delivery(directory)
        return change

    for field, value in (("repository", "untrusted-owner/deckystream"),
                         ("revision", "0" * 40), ("version", "999.0.0"),
                         ("platform", "linux/arm64"), ("dirty", True)):
        negative("wrong-" + field + "-refused", change_manifest(field, value))
    runtime_name = "deckystream-deck_" + version + "_linux_amd64.tar.gz"

    # A deliberately altered private fixture tests the no-import boundary. Its
    # checksums are coherent so a successful verification actually reaches the
    # installer policy parser. It is never a clean-source delivery candidate.
    executed = output / "candidate-code-executed"

    def trapped_installer(directory):
        archive = directory / runtime_name
        with tarfile.open(archive, "r:gz") as source:
            members = [(member, source.extractfile(member).read())
                       for member in source if member.isfile()]
        prefix = "deckystream-" + version + "/"
        files = {member.name: data for member, data in members}
        trap = ("RECOVERY_POLICY_VERSION = 1\nfrom pathlib import Path\nPath(" +
                repr(str(executed)) + ").write_text('unexpected candidate execution')\n" +
                "raise RuntimeError('CANDIDATE_CODE_EXECUTED')\n").encode()
        files[prefix + "install.py"] = trap
        embedded = json.loads(files[prefix + "manifest.json"])
        embedded["files"]["install.py"] = digest(trap)
        files[prefix + "manifest.json"] = canonical(embedded)
        replacement = directory / "replacement.tar.gz"
        with tarfile.open(replacement, "w:gz") as target:
            for member, _ in members:
                data = files[member.name]
                member.size = len(data)
                target.addfile(member, io.BytesIO(data))
        replacement.replace(archive)
        (directory / "manifest.json").write_bytes(files[prefix + "manifest.json"])
        refresh_delivery(directory)

    modified("verify-only-never-imports-candidate-installer", trapped_installer, True)
    if executed.exists():
        raise AssertionError("Verification executed candidate installer code")

    def truncate(directory):
        archive = directory / runtime_name
        data = archive.read_bytes()
        archive.write_bytes(data[:len(data) // 2])
    negative("partial-runtime-refused", truncate)

    def corrupt(directory):
        archive = directory / runtime_name
        archive.write_bytes(archive.read_bytes() + b"different bytes\n")
    negative("runtime-checksum-mismatch-refused", corrupt)

    def cross_bootstrap(directory):
        archive = directory / "deckystream-install.pyz"
        archive.write_bytes(archive.read_bytes() + b"different bootstrap\n")
        refresh_delivery(directory)
    negative("crossed-bootstrap-bytes-refused", cross_bootstrap)

    def malformed(directory):
        (directory / "installer-manifest.json").write_text("{not valid JSON")
    negative("malformed-delivery-manifest-refused", malformed)

    def unsafe_archive(directory):
        archive = directory / runtime_name
        replacement = directory / "replacement.tar.gz"
        with tarfile.open(archive, "r:gz") as source, tarfile.open(replacement, "w:gz") as target:
            for member in source:
                target.addfile(member, source.extractfile(member) if member.isfile() else None)
            link = tarfile.TarInfo("deckystream-" + version + "/outside")
            link.type, link.linkname = tarfile.SYMTYPE, str(output / "escaped")
            target.addfile(link)
        replacement.replace(archive)
        refresh_delivery(directory)
    negative("coherent-checksums-do-not-accept-archive-link", unsafe_archive)
    if (output / "escaped").exists():
        raise AssertionError("Unsafe archive escaped its private extraction root")

    receipt = {"schema_version": 1, "result": "passed", "revision": revision, "version": version,
               "platform": sys.platform, "python": sys.version.split()[0],
               "observed_at": datetime.now(timezone.utc).isoformat(),
               "bootstrap_sha256": digest(bundle.read_bytes()),
               "installer_manifest_sha256": digest((delivery / "installer-manifest.json").read_bytes()),
               "checks": checks,
               "limits": {"actual_steam_deck_install": "unrun", "public_download": "unrun",
                          "provider_viewer": "unrun", "dependency_download": "unrun",
                          "scope": "Actual generated zipapp and prepared local packages; verification-only, no installation"}}
    (output / "qualification.json").write_bytes(canonical(receipt))
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bootstrap", type=Path)
    parser.add_argument("--delivery", required=True, type=Path)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.revision):
        parser.error("Use the complete selected source revision")
    private_output(args.output)
    try:
        receipt = exercise(args.bootstrap.resolve(strict=True), args.delivery.resolve(strict=True), args.output, args.revision)
        print(json.dumps({"result": receipt["result"], "checks": len(receipt["checks"]), "revision": args.revision}))
    except (OSError, RuntimeError, ValueError, AssertionError, subprocess.SubprocessError, zipfile.BadZipFile, tarfile.TarError) as error:
        (args.output / "qualification.json").write_bytes(canonical({"schema_version": 1, "result": "failed", "revision": args.revision,
            "message": str(error), "scope": "Verification-only packaged bootstrap fixtures; no device/public-download pass"}))
        raise SystemExit(str(error)) from None


if __name__ == "__main__":
    main()
