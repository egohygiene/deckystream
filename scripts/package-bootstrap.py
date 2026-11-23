#!/usr/bin/env python3
"""Build the complete, version-bound Desktop bootstrap without publishing it."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_NOTICES = b"""deckystream Desktop bootstrap
The bundled project helpers are distributed under the accompanying MIT LICENSE.
Only Python's installed standard library is used; no Python interpreter or
third-party Python package is redistributed in this bootstrap. Runtime/plugin
dependency notices and preferred source are supplied in their separate packages.
Checksums provide integrity under the selected publisher, not code signing.
"""
ENTRYPOINT = b'''"""Unpack only this complete bootstrap's verified helper inventory."""
import hashlib, json, os, pathlib, stat, sys, tempfile, zipfile

def prepare():
    names = {"__main__.py", "bootstrap.py", "releases.py", "update.py", "paths.py",
             "product.py", "bootstrap-metadata.json", "LICENSE", "THIRD_PARTY_NOTICES.md"}
    os.umask(0o077)
    with zipfile.ZipFile(sys.argv[0]) as archive:
        entries = archive.infolist()
        if (len(entries) != len(names) or {x.filename for x in entries} != names or
                any(x.file_size > 1024 * 1024 or not stat.S_ISREG(x.external_attr >> 16) for x in entries)):
            raise ValueError("Incomplete or unsafe bootstrap; download the complete matching build again.")
        files = {name: archive.read(name) for name in names}
    metadata = json.loads(files["bootstrap-metadata.json"])
    expected = metadata.get("files")
    if (not isinstance(expected, dict) or set(expected) != names - {"bootstrap-metadata.json"} or
            any(hashlib.sha256(files[name]).hexdigest() != digest for name, digest in expected.items())):
        raise ValueError("Bootstrap helper checksum mismatch; no installer was started.")
    # This short-lived code directory contains only public, verified helpers.
    # Downloaded candidates and filtered progress receipts use validated XDG roots.
    temp_parent = pathlib.Path(tempfile.gettempdir())
    for parent in (*reversed(temp_parent.parents), temp_parent):
        info = parent.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, os.getuid()) or
                info.st_mode & 0o022 and not info.st_mode & stat.S_ISVTX):
            raise ValueError("Unsafe temporary directory; use a protected TMPDIR.")
    temporary = tempfile.TemporaryDirectory(prefix="deckystream-bootstrap-code-", dir=temp_parent)
    try:
        root = pathlib.Path(temporary.name)
        for name, data in files.items():
            target = root / name
            with target.open("xb") as stream:
                stream.write(data)
            target.chmod(0o600)
        sys.path.insert(0, temporary.name)
        import bootstrap
        return temporary, bootstrap
    except BaseException:
        temporary.cleanup()
        raise

try:
    temporary, bootstrap = prepare()
except (OSError, ValueError, zipfile.BadZipFile, KeyError):
    raise SystemExit("Bootstrap could not verify its complete helper bundle. Download the matching build again; no installer was started.") from None
try:
    raise SystemExit(bootstrap.main(bundle_path=pathlib.Path(sys.argv[0]).resolve()))
finally:
    temporary.cleanup()
'''


def source_files(version, revision, epoch):
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Use a complete source revision")
    # Use the existing SemVer implementation, not a second precedence rule.
    import importlib.util
    spec = importlib.util.spec_from_file_location("bootstrap_package_releases", ROOT / "steamdeck/releases.py")
    releases = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(releases)
    releases.version_key(version)
    files = {"__main__.py": ENTRYPOINT, "LICENSE": (ROOT / "LICENSE").read_bytes(),
             "THIRD_PARTY_NOTICES.md": BOOTSTRAP_NOTICES}
    for name in ("bootstrap.py", "releases.py", "update.py", "paths.py", "product.py"):
        path = ROOT / "steamdeck" / name
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 1024 * 1024:
            raise ValueError("Unsafe bootstrap source")
        files[name] = path.read_bytes()
    metadata = {"schema_version": 1, "repository": "egohygiene/deckystream", "version": version,
                "revision": revision, "platform": "linux/amd64", "dirty": False,
                "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}}
    files["bootstrap-metadata.json"] = (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode()
    return files


def output_directory(path):
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("Output must be a new absolute directory")
    for parent in (*reversed(path.parents), path):
        if parent == path:
            if parent.exists() or parent.is_symlink():
                raise FileExistsError("Output already exists; preserved")
            break
        info = parent.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, os.getuid()) or
                info.st_mode & 0o022 and not info.st_mode & stat.S_ISVTX):
            raise ValueError("Unsafe output ancestry")
    if path.parent.stat().st_uid != os.getuid():
        raise ValueError("Output parent must belong to the build user")
    path.mkdir(mode=0o700)


def build(version, output):
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip():
        raise ValueError("Commit source before building the bootstrap")
    epoch = int(subprocess.check_output(["git", "show", "-s", "--format=%ct", revision], cwd=ROOT, text=True))
    files = source_files(version, revision, epoch)
    output_directory(output)
    timestamp = datetime.fromtimestamp(max(epoch, 315532800), timezone.utc).timetuple()[:6]
    target = output / "deckystream-install.pyz"
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, timestamp)
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip():
        raise ValueError("Source changed during bootstrap build; output is unqualified")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    (output / "BOOTSTRAP-SHA256SUMS").write_text(digest + "  " + target.name + "\n")
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(build(args.version, args.output))
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error)) from None


if __name__ == "__main__":
    main()
