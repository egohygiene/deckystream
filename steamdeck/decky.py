"""Verified local Decky helper boundary; no tokens, settings or stderr are exposed."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
OFFICIAL_DECKY = "https://decky.xyz/"


def verify_legacy_recovery(package, manifest):
    """Validate only a retained, exact pre-rename package before any removal."""
    package = Path(package)
    policy_path = ROOT / "paths.py"
    spec = importlib.util.spec_from_file_location("deckystream_cached_recovery_paths", policy_path)
    policy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(policy)
    home = Path.home()
    policy.validate_owned_root(package, home)
    base, _ = policy.app_directories(home)
    if package.is_symlink() or package.parent != base / "releases":
        raise RuntimeError("The previous helper is not in the retained application release store")
    required = {"obsgod", "setup.py", "bridge.py", "setup.html", "setup.js", "setup.css", "uninstall.py", "obsgod-decky.zip", "LICENSE", "THIRD_PARTY_NOTICES.md", "STEAM-DECK.md"}
    unified = {"decky-install", "decky.py", "install.py", "Install OBSGod.desktop", "update.py", "releases.py", "Update OBSGod.desktop", "Update OBSGod.sh"}
    capture = {"libgstobsgodcapture.so", "CAPTURE-SOURCE.tar.gz"}
    product = {"paths.py", "product.py", "Uninstall OBSGod.desktop"}
    files = manifest.get("files") if isinstance(manifest, dict) else None
    if (not isinstance(files, dict) or set(files) not in (required | unified, required | unified | capture, required | unified | capture | product)
            or manifest.get("platform") != "linux/amd64" or manifest.get("dirty") is not False
            or not re.fullmatch(r"[0-9a-f]{40}", manifest.get("revision", ""))
            or not re.fullmatch(r"[0-9][A-Za-z0-9.-]{0,79}", manifest.get("version", ""))):
        raise RuntimeError("The previous package has no supported verified recovery helper")
    for name, digest in files.items():
        path = package / name
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1
                or info.st_mode & 0o077 or info.st_size > 64 * 1024 * 1024
                or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
                or hashlib.sha256(path.read_bytes()).hexdigest() != digest):
            raise RuntimeError("The previous package could not be verified for recovery")
    return package / "decky-install"


def helper_request(operation, package=ROOT, manifest=None, uninstall_existing=False, legacy_plugin=False, legacy_package=False, expected_version=None):
    if operation not in {"probe", "install", "uninstall"}:
        raise RuntimeError("Unknown Decky operation")
    if legacy_package and (operation != "install" or legacy_plugin):
        raise RuntimeError("A retained previous helper is only valid for verified rollback installation")
    helper = verify_legacy_recovery(package, manifest) if legacy_package else ROOT / "decky-install"
    if helper.is_symlink() or not helper.is_file():
        raise RuntimeError("The verified Decky installer is missing. Extract the complete deckystream release and retry.")
    # chmod changes ctime even when mode bits already match. Installed cleanup
    # previews must not be invalidated by merely executing the verified helper.
    if stat.S_IMODE(helper.stat().st_mode) != 0o700:
        helper.chmod(0o700)
    request = {"operation": operation}
    if legacy_plugin:
        if operation != "uninstall" or not uninstall_existing or not isinstance(expected_version, str) or not re.fullmatch(r"[0-9][A-Za-z0-9.-]{0,79}", expected_version):
            raise RuntimeError("Legacy identity is only valid for explicit previous-plugin retirement")
        request["legacy_plugin"] = True
        request["version"] = expected_version
    elif expected_version is not None:
        raise RuntimeError("An expected legacy version is only valid for previous-plugin retirement")
    if uninstall_existing:
        if operation != "uninstall":
            raise RuntimeError("Existing plugin removal is only valid for uninstall")
        request["uninstall_existing"] = True
    temporary = None
    if operation == "install":
        if not manifest or not re.fullmatch(r"[0-9][A-Za-z0-9.-]{0,79}", manifest.get("version", "")):
            raise RuntimeError("The plugin package version is invalid")
        archive_name = "obsgod-decky.zip" if legacy_package else "deckystream-decky.zip"
        source = package / archive_name
        expected = manifest.get("files", {}).get(archive_name)
        if source.is_symlink() or not source.is_file() or not re.fullmatch(r"[a-f0-9]{64}", expected or ""):
            raise RuntimeError("The verified Decky ZIP is missing")
        data = source.read_bytes()
        if len(data) > 32 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != expected:
            raise RuntimeError("The Decky ZIP checksum does not match the release")
        # The Go boundary requires private regular ZIPs. Never chmod or mutate a
        # previous installed release while a running process may still use it.
        temporary = tempfile.TemporaryDirectory(prefix="deckystream-decky-")
        private_zip = Path(temporary.name) / "deckystream-decky.zip"
        private_zip.write_bytes(data)
        private_zip.chmod(0o600)
        request.update(zip_path=str(private_zip), sha256=expected, version=manifest["version"])
    try:
        process = subprocess.run([str(helper)], input=json.dumps(request), capture_output=True, text=True, timeout=100 if operation in {"install", "uninstall"} else 25)
        result = json.loads(process.stdout)
        if not isinstance(result, dict) or not isinstance(result.get("ok"), bool) or (result.get("ok") and process.returncode != 0):
            raise ValueError()
        if not result["ok"]:
            message = result.get("message")
            if not isinstance(message, str) or len(message) > 600 or any(c in message for c in "\r\x00"):
                raise ValueError()
            raise RuntimeError(message)
        if operation == "install" and result.get("version") != manifest["version"]:
            raise RuntimeError("Decky did not confirm the requested deckystream version. Rerun this installer to repair both copies.")
        if operation == "uninstall" and result.get("removed") is not True:
            raise RuntimeError("Decky did not confirm plugin removal. Inspect Decky before deleting application files.")
        return result
    except (OSError, subprocess.SubprocessError, ValueError):
        raise RuntimeError("Decky's installer could not be verified. Keep Steam and Decky running in Desktop Mode, check the visible installer log and retry. Your saved settings were preserved.") from None
    finally:
        if temporary is not None:
            temporary.cleanup()


def status():
    try:
        result = helper_request("probe")
        return {"ok": True, "running": True, "frontend_connected": result.get("frontend_connected") is True, "version": result.get("decky_version", "unknown"), "message": "Decky service and Steam connection are ready."}
    except RuntimeError as error:
        return {"ok": False, "running": False, "frontend_connected": False, "version": "unknown", "message": str(error) + " Official Decky installation: " + OFFICIAL_DECKY}
