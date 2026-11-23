#!/usr/bin/env python3
"""Install or repair deckystream and its Decky plugin, preserving private user data."""
import argparse
import asyncio
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import importlib.util
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import fcntl
import webbrowser
import zipfile
from contextlib import contextmanager
def _sibling(name):
    # Published older updaters load a downloaded installer with importlib while
    # sys.path still points at the old package. Never import its old helpers.
    spec = importlib.util.spec_from_file_location("deckystream_install_" + name, Path(__file__).resolve().parent / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_paths = _sibling("paths")
app_directories, xdg_root, validate_owned_root = _paths.app_directories, _paths.xdg_root, _paths.validate_owned_root
DISPLAY_NAME = _sibling("product").DISPLAY_NAME if (Path(__file__).resolve().parent / "product.py").is_file() else "deckystream"
_releases = _sibling("releases") if (Path(__file__).resolve().parent / "releases.py").is_file() else None

ROOT = Path(__file__).resolve().parent
RECOVERY_POLICY_VERSION = 1


def app_directories(home, environ=None):
    try:
        return _paths.app_directories(home, environ)
    except ValueError as error:
        raise RuntimeError(str(error)) from None


def owned_directory(path, home):
    try:
        validate_owned_root(path, home)
    except ValueError as error:
        raise RuntimeError(str(error)) from None
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink() or not path.is_dir():
        raise RuntimeError("Refusing a symlinked install directory: " + str(path))


def quote_exec(value):
    if any(c in value for c in "\r\n\x00"):
        raise RuntimeError("Unsupported character in installation path")
    value = value.replace("%", "%%")
    return '"' + value.replace("\\", "\\\\\\\\").replace('"', '\\\\"').replace("$", "\\\\$").replace("`", "\\\\`") + '"'


def verify_payload():
    if not (ROOT / "manifest.json").is_file():
        raise RuntimeError("Extract the entire deckystream archive to a folder first, then run Install deckystream.desktop from that extracted folder")
    manifest = json.loads((ROOT / "manifest.json").read_text())
    version = manifest["version"]
    if not version or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-" for c in version):
        raise RuntimeError("Invalid package version")
    for name, expected in manifest["files"].items():
        path = ROOT / name
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(ROOT):
            raise RuntimeError("Unsafe or missing package file")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError("Package checksum mismatch: " + name)
    required = {"deckystream", "setup.py", "bridge.py", "setup.html", "setup.js", "setup.css", "uninstall.py", "deckystream-decky.zip", "LICENSE", "THIRD_PARTY_NOTICES.md", "STEAM-DECK.md"}
    unified = {"decky-install", "decky.py", "install.py", "Install deckystream.desktop", "update.py", "releases.py", "Update deckystream.desktop", "Update deckystream.sh"}
    capture = {"libgstdeckystreamcapture.so", "CAPTURE-SOURCE.tar.gz"}
    product = {"paths.py", "product.py", "Uninstall deckystream.desktop"}
    # Historical archives remain repairable. New native-capture archives must
    # contain the complete unified payload and both binary and preferred source;
    # accepting a single arbitrary extra file would weaken the exact schema.
    if set(manifest["files"]) not in (required, required | unified, required | unified | capture, required | unified | capture | product):
        raise RuntimeError("Unexpected package manifest")
    return manifest


@contextmanager
def _installation_lease(path, home, busy_message):
    owned_directory(path.parent, home)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as lock:
        info = os.fstat(lock.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_nlink != 1 or info.st_mode & 0o077):
            raise RuntimeError("The deckystream installation/control lease is unsafe. Existing data was preserved.")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(busy_message) from None
        current = path.lstat()
        if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
            raise RuntimeError("The deckystream installation/control lease changed. Existing data was preserved.")
        yield


@contextmanager
def installation_lock(base):
    with _installation_lease(base / "install.lock", Path.home(), "Another deckystream installer is running. Let it finish, then retry"):
        yield


def matching_release(release, manifest):
    saved = release / "manifest.json"
    return not saved.is_symlink() and saved.is_file() and saved.read_bytes() == (ROOT / "manifest.json").read_bytes() and all(
        not (release / name).is_symlink() and (release / name).is_file()
        and hashlib.sha256((release / name).read_bytes()).hexdigest() == digest
        for name, digest in manifest["files"].items()
    )


def require_space(base, manifest):
    # Reserve room for staging and repair; Flatpak checks its own runtime space.
    needed = sum((ROOT / name).stat().st_size for name in manifest["files"]) * 2 + 16 * 1024 * 1024
    existing = base
    while not existing.exists():
        existing = existing.parent
    if shutil.disk_usage(existing).free < needed:
        raise RuntimeError("Not enough free space for a verified installation and repair copy. Free space in your home directory and retry; no application was replaced.")


def prepare_release(releases, manifest):
    current = releases.parent / "current"
    if current.is_symlink() and current.resolve().parent == releases:
        if matching_release(current.resolve(), manifest):
            for name in manifest["files"]:
                (current / name).chmod(0o700 if name in {"deckystream", "decky-install", "Install deckystream.desktop", "Update deckystream.desktop", "Update deckystream.sh", "Uninstall deckystream.desktop"} else 0o600)
            return current.resolve()
    release = releases / manifest["version"]
    if release.exists() or release.is_symlink():
        if release.is_symlink() or not release.is_dir():
            raise RuntimeError("Unsafe existing release path")
        if matching_release(release, manifest):
            # ZIP/filesystem tools can drop mode bits. Repair a verified copy.
            for name in manifest["files"]:
                (release / name).chmod(0o700 if name in {"deckystream", "decky-install", "Install deckystream.desktop", "Update deckystream.desktop", "Update deckystream.sh", "Uninstall deckystream.desktop"} else 0o600)
            return release
        # Preserve an older/damaged copy, including files mapped by a running
        # process. A fresh directory allows repair and same-version replacement.
        release = releases / (manifest["version"] + "-" + str(time.time_ns()))
    staging = Path(tempfile.mkdtemp(prefix=".install-", dir=releases))
    try:
        for name in manifest["files"]:
            shutil.copyfile(ROOT / name, staging / name)
            (staging / name).chmod(0o700 if name in {"deckystream", "decky-install", "Install deckystream.desktop", "Update deckystream.desktop", "Update deckystream.sh", "Uninstall deckystream.desktop"} else 0o600)
        shutil.copyfile(ROOT / "manifest.json", staging / "manifest.json")
        staging.rename(release)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return release


def validate_activation_paths(base, releases, bin_dir, apps, manifest):
    current = base / "current"
    if current.exists() or current.is_symlink():
        if not current.is_symlink() or not current.resolve().is_relative_to(releases):
            raise RuntimeError("deckystream current path is not an owned release link")
    executable = bin_dir / "deckystream"
    desktop = apps / "deckystream-setup.desktop"
    updater_desktop = apps / "deckystream-update.desktop" if "update.py" in manifest["files"] else None
    uninstaller_desktop = apps / "deckystream-uninstall.desktop" if "Uninstall deckystream.desktop" in manifest["files"] else None
    for path in [executable, desktop] + [item for item in [updater_desktop, uninstaller_desktop] if item]:
        if path.exists() and not (path.is_file() or path.is_symlink()):
            raise RuntimeError("Refusing to replace a non-file application entry")


def activate_release(base, releases, bin_dir, apps, home, manifest):
    validate_activation_paths(base, releases, bin_dir, apps, manifest)
    current = base / "current"
    executable = bin_dir / "deckystream"
    desktop = apps / "deckystream-setup.desktop"
    updater_desktop = apps / "deckystream-update.desktop" if "update.py" in manifest["files"] else None
    uninstaller_desktop = apps / "deckystream-uninstall.desktop" if "Uninstall deckystream.desktop" in manifest["files"] else None
    release = prepare_release(releases, manifest)
    launch_code = "import subprocess,sys; result=subprocess.run([sys.executable,sys.argv[1]]); input('Press Enter to close this window.'); sys.exit(result.returncode)"
    content = "[Desktop Entry]\nType=Application\nName=" + DISPLAY_NAME + " Setup\nComment=Configure Steam Deck streaming locally\nExec=python3 -c " + quote_exec(launch_code) + " " + quote_exec(str(current / "setup.py")) + "\nIcon=video-display\nTerminal=true\nCategories=AudioVideo;\nX-deckystream-Managed=true\n"
    backup = base / "backups" / str(time.time_ns())
    changes = []
    # Each entry is replaced atomically. Switch current last: any failure before
    # activation restores the old entry points and leaves the old release live.
    with tempfile.TemporaryDirectory(prefix=".activate-", dir=base) as temporary:
        staging = Path(temporary)
        (staging / "executable").symlink_to(current / "deckystream")
        (staging / "desktop").write_text(content)
        (staging / "desktop").chmod(0o600)
        (staging / "current").symlink_to(release)
        entries = [(staging / "executable", executable), (staging / "desktop", desktop)]
        # Retain an already-managed old command for existing shell automation,
        # pointing it at the new binary. Never replace an unrelated command.
        previous_alias = bin_dir / "obsgod"
        if (previous_alias.is_symlink() and previous_alias.lstat().st_uid == os.getuid()
                and previous_alias.readlink() in {current / "obsgod", current / "deckystream"}):
            (staging / "legacy-executable").symlink_to(current / "deckystream")
            entries.append((staging / "legacy-executable", previous_alias))
        if updater_desktop:
            updater_content = "[Desktop Entry]\nType=Application\nName=Update " + DISPLAY_NAME + "\nComment=Check and apply verified updates\nExec=python3 -c " + quote_exec(launch_code) + " " + quote_exec(str(current / "update.py")) + "\nIcon=system-software-update\nTerminal=true\nCategories=AudioVideo;\nX-deckystream-Managed=true\n"
            (staging / "updater-desktop").write_text(updater_content)
            (staging / "updater-desktop").chmod(0o600)
            entries.append((staging / "updater-desktop", updater_desktop))
        if uninstaller_desktop:
            uninstall_content = "[Desktop Entry]\nType=Application\nName=Uninstall " + DISPLAY_NAME + "\nComment=Review removal, reset and owned-data wipe\nExec=python3 -c " + quote_exec(launch_code) + " " + quote_exec(str(current / "uninstall.py")) + "\nIcon=edit-delete\nTerminal=true\nCategories=AudioVideo;\nX-deckystream-Managed=true\n"
            (staging / "uninstaller-desktop").write_text(uninstall_content)
            (staging / "uninstaller-desktop").chmod(0o600)
            entries.append((staging / "uninstaller-desktop", uninstaller_desktop))
        # Old menu entries are retired as part of the same recoverable
        # activation. Saved copies remain in the private backup directory.
        for name in ("obsgod-setup.desktop", "obsgod-update.desktop", "obsgod-uninstall.desktop"):
            previous = apps / name
            if previous.exists() and not previous.is_symlink():
                info = previous.lstat()
                if (stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1
                        and info.st_size <= 65536 and "X-OBSGod-Managed=true" in previous.read_text()):
                    entries.append((None, previous))
        try:
            for source, destination in entries:
                if destination == executable and destination.is_symlink() and destination.readlink() == current / "deckystream":
                    continue
                if destination == desktop and not destination.is_symlink() and destination.is_file() and destination.read_text() == content:
                    continue
                saved = None
                if destination.exists() or destination.is_symlink():
                    owned_directory(backup, home)
                    saved = backup / destination.name
                    # Copy links themselves, including dangling links; never
                    # write through somebody else's application/menu symlink.
                    shutil.copy2(destination, saved, follow_symlinks=False)
                if source is None:
                    destination.unlink()
                else:
                    source.replace(destination)
                changes.append((destination, saved))
            (staging / "current").replace(current)
        except (OSError, RuntimeError):
            for destination, saved in reversed(changes):
                if saved is not None:
                    saved.replace(destination)
                else:
                    destination.unlink(missing_ok=True)
            raise
    return current


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require_idle(bridge, close=False):
    state = bridge.run_cli("status", timeout=6)
    if not isinstance(state, dict):
        raise RuntimeError("OBS output state could not be read. Inspect OBS before changing the installation.")
    recording = state.get("recording")
    recording_active = recording.get("active") if isinstance(recording, dict) else recording
    stream = state.get("stream")
    media = state.get("media")
    # Pre-M3 executables have no replay observation. They may be upgraded only
    # after OBS is absent; missing replay state from a running instance is not
    # proof of idle output. New runtimes always report a media snapshot.
    media_idle = (isinstance(media, dict) and media.get("known") is True
                  and media.get("replay_active") is False
                  and isinstance(media.get("recording"), dict)
                  and media["recording"].get("active") is False
                  and media["recording"].get("paused") is False)
    legacy_absent = media is None and state.get("process") == "absent"
    if (state.get("ok") is not True or state.get("state") not in ("stopped", "setup")
            or not isinstance(stream, dict) or stream.get("active") is not False
            or stream.get("reconnecting", False) is not False
            or not isinstance(recording_active, bool) or recording_active
            or not (media_idle or legacy_absent)
            or state.get("output_known") is not True
            or state.get("process") not in ("absent", "running")
            or state.get("operation") not in (None, "", "idle")):
        raise RuntimeError("OBS output is active, busy or unconfirmed. Stop streaming, recording and replay in deckystream first, then retry. For an older app, close managed OBS before upgrading. The installer will not stop a broadcast or local output for you.")
    if close and state.get("configured"):
        result = bridge.run_cli("restart", timeout=20)
        if not isinstance(result, dict) or not result.get("ok"):
            raise RuntimeError("Idle managed OBS could not be closed safely. Inspect OBS in Desktop Mode and retry; nothing was force-killed.")


def retire_legacy_plugin(decky, bridge, home, expected_version=None):
    """Only the authenticated manager may remove the positively closed preimage."""
    version = _releases.installed_plugin_version(home, legacy=True)
    if version is None:
        return None
    if version != expected_version:
        raise RuntimeError("The previous plugin changed after inspection. No plugin was replaced; review the installed versions and retry.")
    require_idle(bridge)
    current = bridge.run_cli("status", timeout=6)
    if not isinstance(current, dict) or current.get("process") != "absent" or current.get("output_known") is not True:
        raise RuntimeError("Close the previous managed OBS instance before retiring its old plugin. Saved settings and media were preserved.")
    decky.helper_request("uninstall", uninstall_existing=True, legacy_plugin=True, expected_version=version)
    if _releases.installed_plugin_version(home, legacy=True) is not None:
        raise RuntimeError("Decky did not confirm previous-plugin retirement. No new plugin was installed; inspect Decky and retry.")
    return version


def adopt_legacy_store_for_upgrade(home):
    """Anchor an empty pre-rename install to its old control namespace.

    A legacy backend can create its first lock at any time. Seed that same
    state root before this installer creates app data or schedules any worker;
    every later participant will then select the retained old namespace.
    """
    version = _releases.installed_plugin_version(home, legacy=True)
    if version is None:
        return version
    selected = _paths.app_namespace(home)
    if selected != "obsgod" and any(path.exists() or path.is_symlink() for path in _paths.namespace_paths(home, "deckystream")):
        raise RuntimeError("The previous OBSGod plugin and a current application store coexist. Stop its outputs, uninstall only that old plugin through Decky, then rerun this installer. Existing stores were preserved.")
    owned_directory(xdg_root("XDG_STATE_HOME", home) / "obsgod", home)
    if _paths.app_namespace(home) != "obsgod":
        raise RuntimeError("The naming migration changed during inspection. No plugin was replaced.")
    return version


@contextmanager
def control_lock(home):
    state = xdg_root("XDG_STATE_HOME", home) / _paths.app_namespace(home)
    with _installation_lease(state / "control.lock", home, "Another deckystream control operation is busy. Let it finish before installing."):
        yield


def installed_obs_version():
    # `info --show-version` is not a Flatpak option. Resolve the same user
    # application/ref that `flatpak run --user` uses, then query machine-readable
    # installed AppStream metadata. Do not infer it from another branch or the
    # system installation that Discover may also display.
    reference = subprocess.run(["flatpak", "info", "--user", "--show-ref", "com.obsproject.Studio"], capture_output=True, text=True, timeout=15)
    obs_ref = reference.stdout.strip()
    if reference.returncode or not re.fullmatch(r"app/com\.obsproject\.Studio/[A-Za-z0-9_-]+/[A-Za-z0-9._-]+", obs_ref):
        raise RuntimeError("Could not identify the user-installed OBS Studio ref. Check OBS Studio's user installation in Discover, then retry.")
    result = subprocess.run(["flatpak", "list", "--user", "--app", "--columns=ref,version"], capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise RuntimeError("Flatpak could not report the installed OBS version. Check Flatpak/SteamOS updates and retry.")
    versions = []
    for line in result.stdout.splitlines():
        ref, separator, version = line.partition("\t")
        # `info --show-ref` includes app/; `list`'s ref column omits that
        # kind prefix. Preserve the exact application, architecture and branch.
        if ref.strip().removeprefix("app/") == obs_ref.removeprefix("app/"):
            versions.append(version.strip() if separator else "")
    if len(versions) != 1 or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)*(?:[-+][A-Za-z0-9.-]+)?", versions[0]):
        raise RuntimeError("OBS Studio is installed, but Flatpak did not report one usable version for its active user ref. Check the OBS Studio entry in Discover and retry.")
    return versions[0]


@contextmanager
def dependency_policy(manifest):
    """Use the exact native setup worker shipped in this verified plugin ZIP.

    Historical archives without native setup remain usable for app-only repair.
    They cannot fall back to the old unguarded dependency transaction.
    """
    path = ROOT / "deckystream-decky.zip"
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
            raise ValueError()
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != manifest["files"][path.name]:
            raise ValueError()
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = [item for item in archive.infolist() if item.filename == "deckystream/dependency_setup.py"]
            if len(names) != 1 or names[0].file_size > 128 * 1024:
                raise ValueError()
            source = archive.read(names[0])
    except (OSError, ValueError, KeyError, zipfile.BadZipFile):
        raise RuntimeError("This recovery package cannot use verified native dependency setup. Use the current Decky plugin's Setup controls, or install app files only; no Flatpak dependencies were changed.") from None
    with tempfile.TemporaryDirectory(prefix="deckystream-dependency-policy-") as temporary:
        module_path = Path(temporary) / "dependency_setup.py"
        module_path.write_bytes(source)
        module_path.chmod(0o600)
        yield load_module("deckystream_install_dependencies", module_path)


def approve_dependency_setup(consent=None):
    """Accept an explicit UI decision or ask the attached terminal, never a pipe.

    A caller may supply True only for a separate, explicit dependency-install
    action. Invoking the installer itself does not grant Flatpak consent.
    """
    if consent is not None:
        if type(consent) is not bool:
            raise RuntimeError("Dependency setup needs an explicit yes or no decision.")
        return consent
    if not sys.stdin.isatty():
        return False
    question = ("Install missing OBS Studio and its compatible GStreamer extension "
                "as user Flatpaks from Flathub? A verified Flathub user remote will "
                "be added only if missing. Existing settings and recordings are "
                "preserved; this does not start a broadcast. [y/N] ")
    try:
        return input(question).strip().lower() in {"y", "yes"}
    except EOFError:
        return False


async def run_dependency_setup(policy, bridge, home, *, dependency_consent=None):
    """Join the native leased transaction while the caller holds install.lock."""
    jobs = _paths.decky_locations(home)["data"] / "jobs"
    state = xdg_root("XDG_STATE_HOME", home) / _paths.app_namespace(home)

    async def preflight():
        # Native setup owns the canonical control lease before this fresh read.
        # Keep status off the event loop so its bounded subprocess can drain.
        await asyncio.to_thread(require_idle, bridge)
        return True

    job = policy.DependencySetup(jobs, os.environ, control_lock=state / "control.lock", preflight=preflight)
    try:
        # This observation does not mutate Flatpaks. Already compatible refs
        # need no permission to reinstall, and blocked/unsupported contexts do
        # not ask for consent to an operation they cannot perform.
        observed = await job.status()
        if observed["state"] in {"running", "cancelling"}:
            raise RuntimeError("Native dependency setup is already running. Wait or cancel it in Decky before retrying recovery; no second transaction was started.")
        if observed["ready"]:
            return observed
        if not observed["can_install"]:
            raise RuntimeError(observed["message"])
        if not approve_dependency_setup(dependency_consent):
            raise RuntimeError("Dependency installation was not approved. No Flatpak dependencies were changed. Rerun this installer from a Desktop Mode terminal to approve setup, or use the Decky panel's Setup controls; your existing installation and settings are preserved.")
        # Consent does not authorize stale state: the native worker reacquires
        # its setup/control leases and repeats output/ref checks before writes.
        observed = await job.start(consent=True)
        if not observed["can_cancel"]:
            if observed["state"] in {"running", "cancelling"}:
                raise RuntimeError("Native dependency setup is already running. Wait or cancel it in Decky before retrying recovery; no second transaction was started.")
            raise RuntimeError(observed["message"])
        operation_id = observed["operation"]["id"]

        def same_operation(snapshot):
            if ((snapshot.get("operation") or {}).get("id") != operation_id or
                    snapshot["state"] in {"running", "cancelling"} and not snapshot["can_cancel"]):
                raise RuntimeError("Native dependency setup changed while recovery was observing it. Recheck setup in Decky before retrying; no second transaction was started.")

        while job.running:
            await asyncio.sleep(0.1)
            observed = await job.status()
            same_operation(observed)
        observed = await job.status()
        same_operation(observed)
        operation = observed.get("operation") or {}
        if not observed["ready"] or operation.get("state") != "ready":
            raise RuntimeError(policy.MESSAGES.get(operation.get("error_code"), observed["message"]))
        return observed
    finally:
        # Explicit interruption terminates only this transaction's owned group;
        # native worker leases survive abrupt parent death until its budget ends.
        await job.close()


def ensure_dependencies(bridge=None, manifest=None, home=None, *, dependency_consent=None):
    if bridge is None and manifest is None and home is None:
        # The retained Desktop browser calls this helper directly. It receives
        # the same package verification and installer/control leases, rather
        # than keeping a second dependency-installation implementation.
        home = Path.home()
        manifest = verify_payload()
        bridge = load_module("deckystream_install_bridge", ROOT / "bridge.py")
        base, _ = app_directories(home)
        owned_directory(base, home)
        with installation_lock(base):
            return ensure_dependencies(bridge, manifest, home, dependency_consent=dependency_consent)
    with dependency_policy(manifest) as policy:
        result = asyncio.run(run_dependency_setup(policy, bridge, home, dependency_consent=dependency_consent))
    print(result["message"], flush=True)


def recover_previous_plugin(decky, previous, original_plugin_version, candidate_version, home, bridge=None):
    if previous is None or original_plugin_version is None:
        return False
    try:
        manifest_path = previous / "manifest.json"
        if manifest_path.is_symlink() or not manifest_path.is_file():
            return False
        manifest = json.loads(manifest_path.read_text())
        # A retained Desktop app can be older than the normal Decky plugin.
        # Automatic rollback may restore only the exact plugin preimage, never
        # turn an app-activation failure into an unrelated plugin downgrade.
        if (not isinstance(manifest, dict) or not isinstance(manifest.get("files"), dict) or
                manifest.get("version") != original_plugin_version or
                _releases.installed_plugin_version(home) != candidate_version):
            return False
        legacy = "obsgod-decky.zip" in manifest["files"]
        archive_path = previous / ("obsgod-decky.zip" if legacy else "deckystream-decky.zip")
        if archive_path.is_symlink() or not archive_path.is_file() or archive_path.stat().st_size > 32 * 1024 * 1024:
            return False
        payload = archive_path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != manifest.get("files", {}).get(archive_path.name):
            return False
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            packages = [item for item in archive.infolist() if item.filename == ("obsgod/package.json" if legacy else "deckystream/package.json")]
            if len(packages) != 1 or packages[0].file_size > 16384:
                return False
            package = json.loads(archive.read(packages[0]))
            if not isinstance(package, dict) or package.get("version") != original_plugin_version:
                return False
        if legacy:
            # Execute only the hash-verified old helper from this retained
            # package. It keeps its own strict old ZIP identity validator.
            decky.verify_legacy_recovery(previous, manifest)
            if bridge is None:
                return False
            require_idle(bridge)
            observed = bridge.run_cli("status", timeout=6)
            if not isinstance(observed, dict) or observed.get("process") != "absent" or observed.get("output_known") is not True:
                return False
            decky.helper_request("uninstall", uninstall_existing=True)
            decky.helper_request("install", previous, manifest, legacy_package=True)
            if (_releases.installed_plugin_version(home) is not None
                    or _releases.installed_plugin_version(home, legacy=True) != original_plugin_version):
                return False
        else:
            decky.helper_request("install", previous, manifest)
        return True
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, zipfile.BadZipFile):
        return False


def offer_decky_guide(url):
    """Offer official instructions, never download or execute a privileged installer."""
    question = "Decky is not ready. Open its official installation and troubleshooting instructions? Finish that setup, then rerun this installer."
    accepted = False
    if shutil.which("kdialog"):
        accepted = subprocess.run(["kdialog", "--title", DISPLAY_NAME, "--yesno", question], check=False).returncode == 0
    elif shutil.which("zenity"):
        accepted = subprocess.run(["zenity", "--question", "--title=" + DISPLAY_NAME, "--text=" + question], check=False).returncode == 0
    elif sys.stdin.isatty():
        accepted = input(question + " [y/N] ").strip().lower() in {"y", "yes"}
    if accepted:
        return webbrowser.open(url)
    return False


def install(launch=True, with_decky=True, recovery_plugin_version=None, expected_plugin_version=None, *, dependency_consent=None):
    if platform.system() != "Linux" or platform.machine() not in {"x86_64", "amd64"}:
        raise RuntimeError("This preview package requires Linux x86_64 (Steam Deck)")
    if os.getuid() == 0:
        raise RuntimeError("Run this installer as your normal Deck user, without sudo")
    os.umask(0o077)
    manifest = verify_payload()
    decky = bridge = None
    if with_decky:
        if not {"decky.py", "decky-install"} <= set(manifest["files"]):
            raise RuntimeError("This older package cannot install Decky automatically. Use its documented manual ZIP path or download the current unified package.")
        decky = load_module("deckystream_install_decky", ROOT / "decky.py")
        print("Checking Decky's authenticated service and existing Steam connection…", flush=True)
        report = decky.status()
        if not report["ok"]:
            if launch:
                offer_decky_guide("https://decky.xyz/")
            raise RuntimeError(report["message"] + " No app or plugin was replaced. Install/start Decky using its official instructions, keep normal Steam open in Desktop Mode, and rerun this installer.")
        print("Decky " + report["version"] + " is ready.", flush=True)
        bridge = load_module("deckystream_install_bridge", ROOT / "bridge.py")
    home = Path.home()
    if with_decky:
        if _releases is None or not hasattr(_releases, "require_plugin_replacement"):
            raise RuntimeError("This installer cannot verify the current Decky plugin version. Use the current recovery package or install app files only.")
        legacy_version = adopt_legacy_store_for_upgrade(home)
        _releases.require_plugin_replacement(manifest["version"], home, recovery_plugin_version, expected_plugin_version)
        if legacy_version is not None:
            _releases.require_plugin_replacement(manifest["version"], home, recovery_plugin_version, expected_plugin_version, legacy=True)
    base, apps = app_directories(home)
    releases = base / "releases"
    bin_dir = home / ".local/bin"
    for path in [base, releases, bin_dir, apps]:
        owned_directory(path, home)
    require_space(base, manifest)
    with installation_lock(base):
        if with_decky:
            ensure_dependencies(bridge, manifest, home, dependency_consent=dependency_consent)
            require_idle(bridge, close=True)
            with control_lock(home):
                # Close/recheck while holding the same lock as Start/configure.
                # A concurrent start cannot race plugin replacement or activation.
                require_idle(bridge)
                original_plugin_version = _releases.require_plugin_replacement(manifest["version"], home, recovery_plugin_version, expected_plugin_version)
                current_path = base / "current"
                previous = current_path.resolve() if current_path.is_symlink() and current_path.resolve().parent == releases else None
                validate_activation_paths(base, releases, bin_dir, apps, manifest)
                candidate = prepare_release(releases, manifest)
                legacy_plugin_version = retire_legacy_plugin(decky, bridge, home, legacy_version)
                if original_plugin_version is None:
                    original_plugin_version = legacy_plugin_version
                plugin_verified = False
                try:
                    print("Installing the verified deckystream plugin through Decky…", flush=True)
                    decky.helper_request("install", candidate, manifest)
                    plugin_verified = True
                    current = activate_release(base, releases, bin_dir, apps, home, manifest)
                except (OSError, RuntimeError):
                    # An interrupted/timeout request can still be running in
                    # Decky. Never race it with a second rollback request. Only
                    # restore after confirmed plugin completion + app failure.
                    recovered = recover_previous_plugin(decky, previous, original_plugin_version, manifest["version"], home, bridge) if plugin_verified else False
                    record = {"version": manifest["version"], "previous_version": previous.name if previous else None, "app_activation_changed": current_path.is_symlink() and current_path.resolve() == candidate, "plugin_rollback_confirmed": recovered}
                    recovery_path = base / "installation-recovery.json"
                    if not recovery_path.is_symlink():
                        recovery_path.write_text(json.dumps(record, indent=2) + "\n")
                        recovery_path.chmod(0o600)
                    raise RuntimeError("Installation did not complete. The previous app activation was preserved. " + ("The previous plugin was restored and verified." if recovered else "The plugin version/rollback is unconfirmed; check Decky and rerun this same installer to repair both copies.") + " Your key, settings and recordings were not reset.") from None
                recovery_path = base / "installation-recovery.json"
                if recovery_path.is_file() and not recovery_path.is_symlink():
                    recovery_path.unlink()
        else:
            current = activate_release(base, releases, bin_dir, apps, home, manifest)
    print("Installed " + DISPLAY_NAME + " " + manifest["version"] + (" in the app and Decky." if with_decky else " app files only; Decky was not installed or verified."))
    print("Reopen setup from Applications → Multimedia → " + DISPLAY_NAME + " Setup.")
    if "update.py" in manifest["files"]:
        print("Check and apply updates from Applications → Multimedia → Update " + DISPLAY_NAME + ".")
    print("Settings, keys, recordings, diagnostic history and unrelated plugins are preserved.")
    if not with_decky:
        print("Manual Decky ZIP: " + str(current / "deckystream-decky.zip"))
    if launch:
        print("Keep this terminal open while configuring deckystream. Finish setup in the browser when done.", flush=True)
        result = subprocess.run([sys.executable, str(current / "setup.py")])
        if result.returncode:
            raise RuntimeError("Files were installed, but the setup page failed to start. The error is shown above; rerun deckystream Setup after correcting it")
    return current


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-launch", action="store_true")
    parser.add_argument("--app-only", action="store_true", help="Install only app files for manual repair/testing; does not install or verify Decky")
    parser.add_argument("--recover-plugin-version", metavar="VERSION", help="Explicitly permit replacing a newer Decky plugin with this exact package version")
    parser.add_argument("--expect-plugin-version", metavar="VERSION", help="Require this exact installed plugin version for an explicit recovery replacement")
    args = parser.parse_args()
    try:
        install(launch=not args.no_launch, with_decky=not args.app_only, recovery_plugin_version=args.recover_plugin_version,
                expected_plugin_version=args.expect_plugin_version)
    except subprocess.TimeoutExpired:
        raise SystemExit("Install timed out while checking or installing a dependency. Inspect Decky/Discover and rerun the same installer to verify or repair the app/plugin pair; settings and recordings are preserved.") from None
    except KeyboardInterrupt:
        raise SystemExit("Installation was interrupted. Rerun this same installer to verify or repair both copies; do not delete your settings or stream key.") from None
    except (OSError, RuntimeError, ValueError, KeyError) as error:
        raise SystemExit("Install failed: " + str(error))
