"""Version-bound Desktop entry point; installation remains owned by install.py."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parent
MAX_METADATA = 2 * 1024 * 1024


class BootstrapError(RuntimeError):
    pass


def sibling(name):
    spec = importlib.util.spec_from_file_location("deckystream_bootstrap_" + name, ROOT / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_file(path, limit):
    """Read a regular, non-linked complete local asset without following links."""
    path = Path(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_mode & 0o022 or
                info.st_size > limit or info.st_uid not in (0, os.getuid())):
            raise BootstrapError("The local candidate contains an unsafe or oversized file.")
        data = stream.read(limit + 1)
        after = path.lstat()
        if (len(data) != info.st_size or len(data) > limit or
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) !=
                (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)):
            raise BootstrapError("A candidate file changed while being read. Retry with the complete build.")
        return data


def metadata(releases):
    data = json.loads(read_file(ROOT / "bootstrap-metadata.json", MAX_METADATA))
    if (not isinstance(data, dict) or data.get("schema_version") != 1 or
            data.get("repository") != releases.REPOSITORY or data.get("dirty") is not False or
            data.get("platform") != "linux/amd64" or
            not isinstance(data.get("revision"), str) or not re.fullmatch(r"[0-9a-f]{40}", data["revision"])):
        raise BootstrapError("The bootstrap source metadata is unsupported. Download a complete current build.")
    releases.version_key(data.get("version"))
    return data


def validate_delivery(value, meta):
    if (not isinstance(value, dict) or value.get("schema_version") != 1 or
            any(value.get(key) != meta[key] for key in ("repository", "version", "revision", "platform")) or
            value.get("dirty") is not False or value.get("unsigned") is not True):
        raise BootstrapError("The delivery does not match this bootstrap's clean version, source and platform.")
    assets = value.get("artifacts")
    required = {"deckystream-install.pyz", "manifest.json",
                "deckystream-deck_" + meta["version"] + "_linux_amd64.tar.gz"}
    if not isinstance(assets, dict) or not required <= set(assets) or len(assets) > 256:
        raise BootstrapError("The delivery inventory is incomplete.")
    for name, item in assets.items():
        if (not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,180}", name) or
                not isinstance(item, dict) or type(item.get("size")) is not int or
                not 0 < item["size"] <= 128 * 1024 * 1024 or
                not isinstance(item.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"])):
            raise BootstrapError("The delivery inventory contains an unsafe asset.")
    return assets


def verify_bytes(data, item):
    if len(data) != item["size"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
        raise BootstrapError("A delivery asset has the wrong size or checksum. Nothing was installed.")


def local_directory(path):
    if not path.is_absolute() or ".." in path.parts:
        raise BootstrapError("Use an absolute path to the complete prepared delivery directory.")
    for parent in (*reversed(path.parents), path):
        info = parent.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, os.getuid()) or
                info.st_mode & 0o022 and not info.st_mode & stat.S_ISVTX):
            raise BootstrapError("The local delivery directory has unsafe ancestry.")


def descriptor(meta, channel, delivery, bundle_path, releases):
    archive = "deckystream-deck_" + meta["version"] + "_linux_amd64.tar.gz"
    if delivery:
        local_directory(delivery)
        read = lambda name: read_file(delivery / name, MAX_METADATA)
        candidate = None
    else:
        candidate = releases._latest(channel, target_version=meta["version"])
        if candidate is None:
            raise BootstrapError("No matching release is published. Use the supplied review candidate; no installation was changed.")
        if candidate["revision"] != meta["revision"]:
            raise BootstrapError("The release tag no longer matches this bootstrap source. Nothing was installed.")
        base = candidate["archive_url"].rsplit("/", 1)[0] + "/"
        if not base.startswith("https://github.com/" + releases.REPOSITORY + "/releases/download/"):
            raise BootstrapError("This historical delivery predates the verified bootstrap contract.")
        read = lambda name: releases._read_url(base + name)
    sums = releases._checksums(read("INSTALLER-SHA256SUMS"))
    raw = read("installer-manifest.json")
    if hashlib.sha256(raw).hexdigest() != sums.get("installer-manifest.json"):
        raise BootstrapError("The installer delivery manifest checksum does not match.")
    assets = validate_delivery(json.loads(raw), meta)
    for name in (archive, "manifest.json", "deckystream-install.pyz"):
        if sums.get(name) != assets[name]["sha256"]:
            raise BootstrapError("The installer checksum envelope and inventory disagree.")
    verify_bytes(read_file(bundle_path, 4 * 1024 * 1024), assets["deckystream-install.pyz"])
    manifest_data = read("manifest.json")
    verify_bytes(manifest_data, assets["manifest.json"])
    manifest = releases.validate_manifest(json.loads(manifest_data), meta["version"], meta["revision"])
    if not releases.UNIFIED_FILES <= set(manifest["files"]):
        raise BootstrapError("This runtime does not support the guarded Desktop installer.")
    if candidate is not None and (candidate["archive_sha256"] != assets[archive]["sha256"] or
            candidate["manifest_sha256"] != assets["manifest.json"]["sha256"]):
        raise BootstrapError("The runtime and installer delivery contracts disagree.")
    return candidate, assets, manifest_data


def player_preflight():
    if platform.system() != "Linux" or platform.machine() not in {"x86_64", "amd64"}:
        raise BootstrapError("Installation supports SteamOS/Linux x86_64 on Steam Deck. Use --inspect or --verify-only for off-device review.")
    uid = os.getuid()
    if uid == 0 or os.geteuid() == 0 or uid != os.geteuid():
        raise BootstrapError("Run this command as your normal Deck user, without sudo.")
    import pwd
    home = Path.home()
    if home.resolve() != Path(pwd.getpwuid(uid).pw_dir).resolve() or home.stat().st_uid != uid:
        raise BootstrapError("The current HOME does not belong to the signed-in player. Use that player's Desktop terminal.")
    desktop = " ".join(os.environ.get(key, "") for key in
                       ("XDG_CURRENT_DESKTOP", "XDG_SESSION_DESKTOP", "DESKTOP_SESSION")).lower()
    if ("gamescope" in desktop or not any(value in desktop for value in ("kde", "plasma")) or
            not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))):
        raise BootstrapError("Switch to Steam Deck Desktop Mode, keep normal Steam open, and run this command in its terminal.")
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR", ""))
    if (not runtime.is_absolute() or runtime.is_symlink() or not runtime.is_dir() or
            runtime.stat().st_uid != uid or runtime.stat().st_mode & 0o077):
        raise BootstrapError("The player session directory is unavailable or unsafe. Sign into Desktop Mode and retry.")
    if not shutil.which("flatpak"):
        raise BootstrapError("Flatpak is unavailable. Restore the SteamOS Desktop Flatpak support, then retry; do not unlock the system partition.")
    if sys.version_info < (3, 9):
        raise BootstrapError("Use SteamOS system Python 3.9 or newer.")
    if not sys.stdin.isatty():
        raise BootstrapError("Run the downloaded complete bootstrap in a terminal so dependency prompts remain available.")


def private_attempt(paths, home):
    # A cache inside either runtime namespace would create a second store
    # before the installer resolves the legacy/current identity. This sibling
    # is download scratch only and cannot alter the canonical control lock.
    parent = paths.xdg_root("XDG_CACHE_HOME", home) / "deckystream-bootstrap"
    paths.validate_owned_root(parent, home)
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    paths.validate_owned_root(parent, home)
    if parent.stat().st_mode & 0o077:
        raise BootstrapError("The bootstrap cache directory is not private. Fix its permissions and retry.")
    if shutil.disk_usage(parent).free < 208 * 1024 * 1024:
        raise BootstrapError("Free at least 208 MiB in your home directory before downloading the candidate. Flatpak may need additional space.")
    return Path(tempfile.mkdtemp(prefix="attempt-", dir=parent))


def verify_payload(archive, work, meta, raw_manifest, updater, releases):
    unpacked = work / "unpacked"
    unpacked.mkdir(mode=0o700)
    package = updater.unpack_payload(archive, unpacked, meta["version"])
    embedded = read_file(package / "manifest.json", MAX_METADATA)
    if embedded != raw_manifest:
        raise BootstrapError("The embedded runtime manifest differs from the verified release manifest.")
    manifest = releases.validate_manifest(json.loads(embedded), meta["version"], meta["revision"])
    actual = {p.name for p in package.iterdir()}
    if actual != set(manifest["files"]) | {"manifest.json"}:
        raise BootstrapError("The runtime contains unexpected or missing files.")
    for name, digest in manifest["files"].items():
        if hashlib.sha256(read_file(package / name, releases.MAX_ARCHIVE)).hexdigest() != digest:
            raise BootstrapError("An extracted runtime file failed checksum verification.")
    updater.require_recovery_policy(package / "install.py")
    return package


def main(argv=None, *, bundle_path=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspect", action="store_true", help="Show bundled version/source without networking or installation")
    parser.add_argument("--channel", choices=("stable", "preview"), default="stable")
    parser.add_argument("--version", help="Assert this exact bundled version; download that version's bootstrap first")
    parser.add_argument("--delivery", type=Path, help="Use a complete locally prepared delivery instead of contacting GitHub")
    parser.add_argument("--verify-only", action="store_true", help="Verify the complete package without loading it or contacting Decky")
    parser.add_argument("--check", action="store_true", help="Also probe supported Decky in Desktop Mode without installing")
    parser.add_argument("--no-launch", action="store_true", help="Finish after installation; configure in the Decky panel")
    args = parser.parse_args(argv)
    work = None
    installation_attempted = False
    stage = "bootstrap-metadata"
    os.umask(0o077)
    try:
        releases = sibling("releases")
        meta = metadata(releases)
        if args.version is not None and args.version != meta["version"]:
            raise BootstrapError("The requested version does not match this bootstrap. Download the bootstrap from that exact release.")
        if args.inspect:
            print(json.dumps({key: meta[key] for key in ("version", "revision", "repository", "platform", "dirty")}, sort_keys=True))
            return 0
        if args.channel == "stable" and releases.version_key(meta["version"])[3] == 0:
            raise BootstrapError("This is a preview build. Add --channel preview to deliberately select it; stable does not select prereleases.")
        if args.check and args.verify_only:
            raise BootstrapError("Choose --check or --verify-only.")
        if not args.verify_only:
            player_preflight()
        paths = sibling("paths")
        updater = sibling("update")
        work = private_attempt(paths, Path.home())
        print("Private candidate and progress receipt: " + str(work), flush=True)
        stage = "delivery-verification"
        candidate, assets, raw_manifest = descriptor(meta, args.channel, args.delivery, bundle_path, releases)
        name = "deckystream-deck_" + meta["version"] + "_linux_amd64.tar.gz"
        archive = work / name
        stage = "runtime-download"
        if args.delivery:
            data = read_file(args.delivery / name, releases.MAX_ARCHIVE)
            verify_bytes(data, assets[name])
            archive.write_bytes(data)
        else:
            releases.download_archive(candidate, archive)
            if archive.stat().st_size != assets[name]["size"]:
                raise BootstrapError("The downloaded archive length does not match the delivery inventory.")
        stage = "runtime-verification"
        package = verify_payload(archive, work, meta, raw_manifest, updater, releases)
        if args.verify_only:
            stage = "verified-only"
            print("Verified deckystream " + meta["version"] + " at " + meta["revision"] + ". No package code or Decky operation was executed.")
        elif args.check:
            stage = "decky-probe"
            decky = updater.load_module("deckystream_bootstrap_probe", package / "decky.py")
            report = decky.status()
            if not report.get("ok"):
                raise BootstrapError("Decky is unavailable or unsupported. Install/update Decky from https://decky.xyz/, keep normal Steam open in Desktop Mode, and retry.")
            stage = "ready-to-install"
            print("Verified package and supported Decky connection. Nothing was installed.")
        else:
            stage = "installer-running"
            print("Verified download. The existing installer will now check Decky, output state and dependencies. It never starts a broadcast.", flush=True)
            command = [sys.executable, str(package / "install.py")]
            if args.no_launch:
                command.append("--no-launch")
            installation_attempted = True
            result = subprocess.run(command, stdin=sys.stdin)
            if result.returncode:
                raise BootstrapError("The installer stopped. Read the terminal message above; rerun this same build to verify or repair. Do not delete settings or recordings.")
            stage = "installed"
            print("Installed version: " + meta["version"] + ". Open Gaming Mode → ••• → Decky → deckystream.")
            print("Desktop Applications → Multimedia provides setup, update and uninstall. OBS and other plugins remain separate.")
        (work / "progress.json").write_text(json.dumps({"schema_version": 1, "stage": stage,
            "version": meta["version"], "revision": meta["revision"], "installation_attempted": installation_attempted,
            "device_acceptance": "unrun", "publication": "not-performed"}, indent=2) + "\n")
        print("Filtered progress receipt: " + str(work / "progress.json") + ". It contains no stream key or raw installer output.")
        return 0
    except KeyboardInterrupt:
        print("Bootstrap interrupted. Rerun the same complete build to verify or repair; do not remove your settings or media.", file=sys.stderr)
        outcome = "interrupted"
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, tarfile.TarError, subprocess.SubprocessError):
        # Only controlled bootstrap/release errors are suitable for public output.
        error = sys.exc_info()[1]
        safe_errors = (BootstrapError,)
        if "releases" in locals():
            safe_errors += (releases.ReleaseError,)
        if "updater" in locals():
            safe_errors += (updater.UpdateError,)
        if isinstance(error, safe_errors):
            print(str(error), file=sys.stderr)
        else:
            print("Bootstrap could not verify this candidate. Retry with the complete matching build and check your connection/free space.", file=sys.stderr)
        outcome = "failed"
    if work is not None:
        try:
            (work / "progress.json").write_text(json.dumps({"schema_version": 1, "stage": stage,
                "outcome": outcome, "installation_attempted": installation_attempted,
                "publication": "not-performed"}, indent=2) + "\n")
        except OSError:
            print("Could not save the progress receipt. Inspect the terminal outcome and retained candidate before retrying.", file=sys.stderr)
        print("Retained private recovery candidate and filtered receipt: " + str(work), file=sys.stderr)
    return 1
