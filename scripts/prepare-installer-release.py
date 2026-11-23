#!/usr/bin/env python3
"""Stage an exact, verified installer delivery without publishing anything.

This preparation joins already-built runtime, primary Decky and bootstrap
artifacts. It does not build their binaries, run downloaded code, install,
contact GitHub, sign, publish or deploy. A consistent package is not product
qualification or release approval.
"""
import argparse
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "egohygiene/deckystream"
MAX_ASSET = 64 * 1024 * 1024
MAX_METADATA = 4 * 1024 * 1024
BOOTSTRAP_FILES = frozenset({"__main__.py", "bootstrap.py", "releases.py", "update.py",
    "paths.py", "product.py", "bootstrap-metadata.json", "LICENSE", "THIRD_PARTY_NOTICES.md"})
AUDIT_FILES = ("release-audit.json", "sbom.spdx.json", "provenance.unsigned.json", "AUDIT-SHA256SUMS")


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


AUDIT = module("installer_delivery_audit", "release-audit.py")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, "Duplicate JSON object key")
        value[key] = item
    return value


def document(data):
    result = json.loads(data, object_pairs_hook=unique_object)
    require(isinstance(result, dict), "Expected a JSON object")
    return result


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def source(revision, name):
    return git("show", revision + ":" + name)


def current_source(revision):
    require(re.fullmatch(r"[0-9a-f]{40}", revision) is not None,
            "Use the full lowercase source commit SHA")
    require(git("rev-parse", "HEAD").decode().strip() == revision,
            "Only the current clean source revision can label a delivery")
    require(not git("status", "--porcelain").strip(),
            "Commit source changes before preparing an installer delivery")
    require(document(source(revision, "product.json")).get("repository") == REPOSITORY,
            "The source publisher does not match the fixed installer repository")
    return int(git("show", "-s", "--format=%ct", revision))


def protected_path(path, *, directory=False):
    require(path.is_absolute() and ".." not in path.parts,
            "Use an absolute path without traversal")
    for parent in ((path,) if directory else ()) + tuple(path.parents):
        info = parent.lstat()
        require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode),
                "Refusing a linked or non-directory input/output ancestor")
        require(info.st_uid in (0, os.getuid()) and
                (not info.st_mode & 0o022 or info.st_mode & stat.S_ISVTX),
                "Refusing foreign or unprotected input/output ancestry")


def read_regular(path, limit=MAX_ASSET):
    protected_path(path)
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and
            info.st_uid in (0, os.getuid()) and not info.st_mode & 0o022,
            "Refusing a linked, shared, foreign or writable package input")
    require(0 <= info.st_size <= limit, "Package input exceeded its size limit")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    require(len(data) == info.st_size and len(data) <= limit and
            (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
            "Package input changed or exceeded its size limit while reading")
    return data


def identity(value, version, revision):
    require(value.get("version") == version and value.get("revision") == revision and
            value.get("platform") == "linux/amd64" and value.get("dirty") is False,
            "Artifact version, revision, platform or clean-source identity mismatch")


def source_inventory(revision):
    """Match the primary receipt's complete SHA256 snapshot to Git objects."""
    paths = git("ls-tree", "-rz", "--name-only", revision).split(b"\0")
    return {os.fsdecode(path): sha(source(revision, os.fsdecode(path)))
            for path in paths if path}


def version_of(manifest):
    version = manifest.get("version")
    require(isinstance(version, str) and len(version) <= 80 and
            re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?", version),
            "The candidate version must be SemVer without build metadata")
    if "-" in version:
        require(all(not part.isdigit() or part == "0" or not part.startswith("0")
                    for part in version.split("-", 1)[1].split(".")),
                "Numeric preview version identifiers cannot have leading zeroes")
    return version


def inspect_runtime(runtime, revision):
    archive = read_regular(runtime)
    root, files = AUDIT.archive_files(archive, "tar")
    require(set(files) == AUDIT.RUNTIME_FILES | {"manifest.json"},
            "Runtime installer inventory is incomplete or unexpected")
    require(sum(len(data) for data in files.values()) <= 96 * 1024 * 1024,
            "Runtime payload expansion exceeded its supported limit")
    manifest = document(files["manifest.json"])
    version = version_of(manifest)
    identity(manifest, version, revision)
    require(root == "deckystream-" + version and
            runtime.name == "deckystream-deck_" + version + "_linux_amd64.tar.gz",
            "Runtime filename/root differs from its version")
    AUDIT.verify_manifest(files, manifest)
    require((manifest.get("go"), manifest.get("node"), manifest.get("npm")) ==
            ("go1.27.4", "24.19.0", "11.9.0"), "Runtime toolchain identity mismatch")
    require(read_regular(runtime.parent / "manifest.json", MAX_METADATA) == files["manifest.json"],
            "Runtime sidecar manifest differs from the packaged manifest")
    artifacts = {runtime.name: archive, "manifest.json": files["manifest.json"],
                 "deckystream-decky.zip": files["deckystream-decky.zip"]}
    require(read_regular(runtime.parent / "deckystream-decky.zip") == artifacts["deckystream-decky.zip"],
            "Runtime sidecar plugin differs from its embedded ZIP")
    AUDIT.verify_checksum_list(read_regular(runtime.parent / "SHA256SUMS", MAX_METADATA), artifacts)
    for name, data in files.items():
        if name.endswith((".py", ".desktop", ".sh", ".html", ".js", ".css")):
            require(data == source(revision, "steamdeck/" + name),
                    "Runtime installer source differs from selected revision: " + name)
    require(files["LICENSE"] == source(revision, "LICENSE"),
            "Runtime license differs from the selected source")
    require(files["STEAM-DECK.md"] == source(revision, "docs/steam-deck.md"),
            "Runtime guide differs from selected source")
    return version, files, artifacts


def inspect_primary(primary, version, revision, expected_zip):
    protected_path(primary, directory=True)
    archive = read_regular(primary / "deckystream-decky.zip")
    require(archive == expected_zip, "Primary ZIP differs from the runtime embedded plugin")
    receipt_bytes = read_regular(primary / "build-receipt.json", MAX_METADATA)
    receipt = document(receipt_bytes)
    identity(receipt, version, revision)
    require(receipt.get("archive") == "deckystream-decky.zip" and
            receipt.get("sha256") == sha(archive) and
            receipt.get("source_tools") == {"go": "go1.27.4", "node": "24.19.0", "npm": "11.9.0"},
            "Primary build receipt differs from its archive or pinned source tools")
    require(receipt.get("source_files_sha256") == source_inventory(revision),
            "Primary build receipt does not match the complete selected source inventory")
    AUDIT.verify_checksum_list(read_regular(primary / "SHA256SUMS", MAX_METADATA),
                               {"deckystream-decky.zip": archive})
    root, files = AUDIT.archive_files(archive, "zip")
    require(root == "deckystream" and set(files) == AUDIT.STANDARD_PLUGIN_FILES,
            "Primary standard-plugin inventory/root mismatch")
    manifest = document(files["manifest.json"])
    identity(manifest, version, revision)
    require(manifest.get("format") == "decky-plugin", "Standard plugin manifest format mismatch")
    AUDIT.verify_manifest(files, manifest)
    require(document(files["plugin.json"]).get("name") == "deckystream" and
            document(files["package.json"]).get("name") == "deckystream" and
            document(files["package.json"]).get("version") == version,
            "Primary plugin identity mismatch")
    return receipt_bytes


def bootstrap_source(version, revision, epoch):
    # Import the maintained source packager, never code from the input archive.
    return module("installer_delivery_bootstrap_packager", "package-bootstrap.py").source_files(version, revision, epoch)


def inspect_bootstrap(path, version, revision, epoch):
    require(path.name == "deckystream-install.pyz", "Use the canonical bootstrap asset filename")
    data = read_regular(path, MAX_METADATA)
    files, total = {}, 0
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for entry in archive.infolist():
            total += entry.file_size
            require(entry.filename in BOOTSTRAP_FILES and entry.filename not in files and
                    stat.S_ISREG(entry.external_attr >> 16) and not entry.flag_bits & 1 and
                    0 <= entry.file_size <= MAX_METADATA and total <= MAX_METADATA,
                    "Unsafe, duplicate, encrypted or oversized bootstrap member")
            files[entry.filename] = archive.read(entry)
    require(set(files) == BOOTSTRAP_FILES, "Bootstrap inventory mismatch")
    metadata = document(files["bootstrap-metadata.json"])
    identity(metadata, version, revision)
    require(metadata.get("schema_version") == 1 and metadata.get("repository") == REPOSITORY,
            "Bootstrap source/publisher schema mismatch")
    require(metadata.get("files") == {name: sha(content) for name, content in files.items()
                                     if name != "bootstrap-metadata.json"},
            "Bootstrap source file checksum mismatch")
    require(files == bootstrap_source(version, revision, epoch),
            "Bootstrap payload differs from the selected clean source")
    return data


def source_archive(revision, version):
    data = git("archive", "--format=tar", "--prefix=deckystream-source-" + version + "/", revision)
    require(len(data) <= 128 * 1024 * 1024, "Source archive exceeded its preparation limit")
    output = io.BytesIO()
    with gzip.GzipFile(filename="", fileobj=output, mode="wb", compresslevel=9, mtime=0) as stream:
        stream.write(data)
    return output.getvalue()


def audit_material(directory, version, revision, selected):
    protected_path(directory, directory=True)
    files = {name: read_regular(directory / name, MAX_METADATA) for name in AUDIT_FILES}
    report = document(files["release-audit.json"])
    require(report.get("revision") == revision and report.get("repository") == REPOSITORY and
            report.get("version") == version and report.get("integrity") == "passed" and
            report.get("source_inventory") == "passed" and report.get("preferred_source") == "passed",
            "Supplied release audit does not pass for this source/version")
    subjects = report.get("subjects")
    require(isinstance(subjects, list), "Supplied release audit subjects are missing")
    inventory = {}
    for subject in subjects:
        require(isinstance(subject, dict) and isinstance(subject.get("name"), str) and
                subject["name"] not in inventory and isinstance(subject.get("digest"), dict),
                "Invalid or duplicate release audit subject")
        inventory[subject["name"]] = subject["digest"].get("sha256")
    for name in selected:
        require(inventory.get(name) == sha(selected[name]),
                "Supplied release audit does not match the selected artifact: " + name)
    AUDIT.verify_checksum_list(files["AUDIT-SHA256SUMS"],
                               {name: files[name] for name in AUDIT_FILES if name != "AUDIT-SHA256SUMS"})
    return files


def new_output(path):
    require(path.is_absolute() and ".." not in path.parts, "Use a new absolute output directory")
    protected_path(path.parent, directory=True)
    require(path.parent.stat().st_uid == os.getuid(), "Output parent must belong to the current user")
    require(not path.exists() and not path.is_symlink(), "Output already exists; previous candidates are preserved")
    require(not path.is_relative_to(ROOT) and not ROOT.is_relative_to(path),
            "Keep delivery output outside the source checkout")
    path.mkdir(mode=0o700)


def release_notes(version, revision):
    return ("# deckystream " + version + " — unpublished candidate\n\n"
        "Source: https://github.com/" + REPOSITORY + "/tree/" + revision + "\n\n"
        "Supported installation target: Steam Deck Desktop Mode, Linux x86_64, with an existing supported Decky Loader and normal Steam session. "
        "The one-command bootstrap downloads a complete verified runtime installer; that installer installs the plugin plus retained Desktop setup, update and recovery files. "
        "OBS and capture dependencies remain separately consented user-scoped Flatpaks. Installation never starts broadcasting or unlocks SteamOS read-only protection.\n\n"
        "The standard deckystream-decky.zip is the direct Decky install unit; GitHub source archives and outer Actions artifacts are not plugin packages. "
        "The bootstrap, runtime, standard ZIP and metadata must come from this same version and revision.\n\n"
        "Checksums and unsigned self-reported metadata establish consistency with the reviewed files, not an authenticated signing identity. "
        "No signed release, stable support lifetime, device/provider acceptance, public URL availability or publication approval is claimed.\n\n"
        "Before publishing: complete exact-candidate qualification and owner-device tests, resolve rights/publisher/contact/signing policy and select the exact destinations. "
        "A preview publication also needs explicit approval. After approved publication, verify the real anonymous download/install command before closing delivery criteria. "
        "Existing credentials/media and shared OBS/dependencies remain outside default cleanup scope; rollback and uninstall must use the documented guarded tools.\n").encode()


def install_command(version, revision, checksum, size):
    """Concrete anonymous launcher; complete bytes are checked before execution."""
    require(0 < size <= MAX_METADATA, "Bootstrap exceeded the public launcher's 4 MiB limit")
    template = '''# Prepared command; unavailable until these exact release assets are approved and published.
# Source revision: @REVISION@
python3 -I - <<'PY'
import hashlib, os, platform, re, stat, sys, tempfile, time
from pathlib import Path
import urllib.error, urllib.parse, urllib.request

url = @URL@
expected = @CHECKSUM@
expected_size = @SIZE@
version = @VERSION@
channel = @CHANNEL@
limit = 4 * 1024 * 1024

def stop(message):
    raise SystemExit("deckystream installer: " + message)

if os.getuid() == 0:
    stop("Run this command as the normal Deck user, without sudo.")
if platform.system() != "Linux" or platform.machine() not in {"x86_64", "amd64"}:
    stop("This installer requires Steam Deck/Linux x86_64.")
os.umask(0o077)
temporary = Path("/tmp")
try:
    for path in (temporary, *temporary.parents):
        info = path.lstat()
        if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
                or info.st_uid not in {0, os.getuid()}
                or info.st_mode & 0o022 and not info.st_mode & stat.S_ISVTX):
            stop("Unsafe temporary directory ancestry; nothing was installed.")
    terminal = os.open("/dev/tty", os.O_RDONLY | os.O_CLOEXEC)
except OSError:
    stop("Open a normal terminal in Desktop Mode and run this command again.")

class AssetRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, target):
        try:
            parsed = urllib.parse.urlsplit(target)
            allowed = (request.full_url == url and parsed.scheme == "https"
                and parsed.netloc == "release-assets.githubusercontent.com"
                and parsed.username is None and parsed.password is None
                and parsed.port is None and not parsed.fragment
                and not any(ord(char) < 32 or ord(char) == 127 for char in target)
                and re.fullmatch(r"/github-production-release-asset/[0-9]+/[A-Za-z0-9-]+", parsed.path))
        except ValueError:
            allowed = False
        if not allowed:
            raise ValueError("Unsupported release redirect")
        return super().redirect_request(request, response, code, message, headers, target)

try:
    request = urllib.request.Request(url, headers={"User-Agent": "deckystream-bootstrap", "Accept": "application/octet-stream"})
    opener = urllib.request.build_opener(AssetRedirect())
    deadline = time.monotonic() + 45
    data = bytearray()
    with opener.open(request, timeout=15) as response:
        declared = response.headers.get("Content-Length")
        if declared is not None and (not declared.isdecimal() or int(declared) != expected_size):
            stop("Download length mismatch; nothing was installed.")
        while True:
            chunk = response.read(64 * 1024)
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > limit or len(data) > expected_size or time.monotonic() > deadline:
                stop("Download exceeded its size/time limit; nothing was installed.")
except (OSError, ValueError, urllib.error.URLError):
    stop("Download unavailable or outside the approved release path. Check your connection and whether this exact release is published; nothing was installed.")
if len(data) != expected_size or hashlib.sha256(data).hexdigest() != expected:
    stop("Download checksum/length mismatch; nothing was installed.")
try:
    work = Path(tempfile.mkdtemp(prefix="deckystream-bootstrap-", dir=str(temporary)))
    package = work / "deckystream-install.pyz"
    with package.open("xb") as stream:
        stream.write(data)
    os.dup2(terminal, 0)
    os.close(terminal)
    print("Verified deckystream " + version + ". Retained installer: " + str(package), flush=True)
    os.execv(sys.executable, [sys.executable, "-I", str(package), "--version", version,
        "--channel", channel, "--no-launch"])
except OSError:
    stop("Could not stage or launch the verified installer. Existing installation is unchanged; check free space and rerun from a Desktop Mode terminal.")
PY
'''
    values = {"@REVISION@": revision,
        "@URL@": repr("https://github.com/" + REPOSITORY + "/releases/download/v" + version + "/deckystream-install.pyz"),
        "@CHECKSUM@": repr(checksum), "@SIZE@": str(size), "@VERSION@": repr(version),
        "@CHANNEL@": repr("preview" if "-" in version else "stable")}
    for marker, value in values.items():
        template = template.replace(marker, value)
    return template.encode()


def prepare(runtime, primary, bootstrap, revision, output, audit=None):
    epoch = current_source(revision)
    version, payload, assets = inspect_runtime(runtime, revision)
    assets["build-receipt.json"] = inspect_primary(primary, version, revision, assets["deckystream-decky.zip"])
    assets["deckystream-install.pyz"] = inspect_bootstrap(bootstrap, version, revision, epoch)
    assets["INSTALL-COMMAND.txt"] = install_command(version, revision,
        sha(assets["deckystream-install.pyz"]), len(assets["deckystream-install.pyz"]))
    selected = {name: assets[name] for name in (runtime.name, "deckystream-decky.zip", "manifest.json")}
    if audit is not None:
        assets.update(audit_material(audit, version, revision, selected))
    assets["LICENSE"] = payload["LICENSE"]
    assets["THIRD_PARTY_NOTICES.md"] = payload["THIRD_PARTY_NOTICES.md"]
    assets["deckystream-source_" + version + ".tar.gz"] = source_archive(revision, version)
    # The two existing readers consume disjoint metadata and the same ZIP.
    # Their shared checksum file is the union, never one candidate overwriting
    # a conflicting primary/runtime checksum under the same asset name.
    assets["SHA256SUMS"] = "".join(sha(assets[name]) + "  " + name + "\n"
        for name in sorted(selected)).encode()
    assets["release-notes.md"] = release_notes(version, revision)
    packet = {"schema_version": 1, "repository": REPOSITORY, "version": version,
        "revision": revision, "platform": "linux/amd64", "dirty": False,
        "state": "prepared-unpublished", "publication": "not performed", "deployment": "not performed",
        "integrity_scope": "Matching runtime/plugin/bootstrap source identities, manifests and actual artifact hashes; no downloaded payload executed",
        "release_audit": "included-passed-integrity-only" if audit is not None else "unrun-by-this-preparation",
        "signing": "unsigned; publisher verification policy requires owner disposition",
        "proposed_destination": "https://github.com/" + REPOSITORY + "/releases/tag/v" + version,
        "public_download_verification": "unrun-until-approved-publication",
        "install_command": "INSTALL-COMMAND.txt; exact pinned public command, unavailable until approved assets exist",
        "qualification": "unrun-by-this-preparation",
        "rollback": "Retain the previously qualified runtime/ZIP and use guarded exact-version recovery; not demonstrated by this preparation",
        "remaining_gates": ["Exact final-source automated matrix and required reviews/CI",
            "Real Steam Deck install/upgrade/recovery/uninstall and provider-viewer evidence",
            "Artwork/source rights, attribution, publisher identity and contact",
            "Explicit signing or intentionally unsigned policy and exact publication approval",
            "Actual anonymous public download and consumer/adoption proof"]}
    assets["installer-owner-packet.json"] = canonical(packet)
    manifest = {"schema_version": 1, "repository": REPOSITORY, "version": version,
        "revision": revision, "platform": "linux/amd64", "dirty": False, "unsigned": True,
        "artifacts": {name: {"size": len(data), "sha256": sha(data)} for name, data in sorted(assets.items())}}
    assets["installer-manifest.json"] = canonical(manifest)
    assets["INSTALLER-SHA256SUMS"] = "".join(sha(data) + "  " + name + "\n"
        for name, data in sorted(assets.items())).encode()
    # Avoid relabelling concurrently edited source, even though its Git objects
    # were used for source comparison and the deterministic source archive.
    require(current_source(revision) == epoch, "Source changed during delivery preparation")
    new_output(output)
    for name, data in sorted(assets.items()):
        with (output / name).open("xb") as stream:
            stream.write(data)
        (output / name).chmod(0o600)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True, help="Matching complete runtime TAR and its original sidecars")
    parser.add_argument("--primary", type=Path, required=True, help="Matching primary build directory with ZIP/receipt/SHA256SUMS")
    parser.add_argument("--bootstrap", type=Path, required=True, help="Matching deckystream-install.pyz")
    parser.add_argument("--revision", required=True, help="Full clean checked-out source commit")
    parser.add_argument("--output", type=Path, required=True, help="New absolute private delivery directory outside the checkout")
    parser.add_argument("--audit", type=Path, help="Optional passed release audit/SPDX/unsigned provenance directory")
    args = parser.parse_args()
    try:
        result = prepare(args.runtime, args.primary, args.bootstrap, args.revision, args.output, args.audit)
        print(json.dumps({"state": "prepared-unpublished", "revision": result["revision"],
            "version": result["version"], "artifacts": len(result["artifacts"]),
            "output": str(args.output), "publication": "not performed"}, sort_keys=True))
    except (ValueError, OSError, KeyError, TypeError, EOFError,
            subprocess.SubprocessError, tarfile.TarError, zipfile.BadZipFile) as error:
        parser.exit(1, "Installer delivery preparation refused: " + str(error) + "\n")


if __name__ == "__main__":
    main()
