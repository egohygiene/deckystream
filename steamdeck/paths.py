"""Shared Desktop paths. Existing installations keep their compatibility location."""
import json
import os
from pathlib import Path
import stat
import re

PRIMARY_NAMESPACE = "deckystream"
# Only the explicit pre-rename store may be reused. Never translate arbitrary
# environment variables or copy credentials into a second controller store.
LEGACY_NAMESPACE = "obsgod"

DEFAULTS = {
    "XDG_CONFIG_HOME": ".config",
    "XDG_DATA_HOME": ".local/share",
    "XDG_STATE_HOME": ".local/state",
    "XDG_CACHE_HOME": ".cache",
}


def xdg_root(name, home, environ=None):
    """Resolve one supported absolute XDG base; empty means the standard default."""
    values = os.environ if environ is None else environ
    value = values.get(name, "")
    if name not in DEFAULTS:
        raise ValueError("Unsupported XDG base directory")
    if not isinstance(value, str) or any(char in value for char in "\x00\r\n"):
        raise ValueError(name + " contains an unsupported path")
    root = Path(value) if value else Path(home) / DEFAULTS[name]
    if not root.is_absolute():
        raise ValueError(name + " must be an absolute directory")
    if ".." in root.parts:
        raise ValueError(name + " must not contain parent-directory traversal")
    return root


def normalize_home_path(path, home, *, allow_home=False):
    """Normalize the player's home alias, never links inside owned roots."""
    boundary = Path(home)
    home = boundary.resolve()
    path = Path(path)
    if (not path.is_absolute() or ".." in path.parts or
            any(ord(char) < 32 or ord(char) == 127 for char in str(path))):
        raise ValueError("Application paths must stay inside your home directory")
    aliases = [boundary]
    environment_home = Path(os.environ.get("HOME", str(home)))
    if environment_home.is_absolute() and environment_home.resolve() == home:
        aliases.append(environment_home)
    for alias in aliases:
        if path.is_relative_to(alias):
            # Legacy callers may still write through their supplied spelling.
            # Validate the alias prefix too, including trusted system aliases
            # such as /home -> /var/home, before discarding that spelling.
            for item in (*reversed(alias.parents), alias):
                info = item.lstat()
                target = item.stat()
                if (not stat.S_ISDIR(target.st_mode) or info.st_uid not in (0, os.getuid())
                        or target.st_uid not in (0, os.getuid())):
                    raise ValueError("A home alias has unexpected type or ownership: " + str(item))
                if target.st_mode & 0o022 and not target.st_mode & stat.S_ISVTX:
                    raise ValueError("Refusing a writable nonsticky home alias directory: " + str(item))
            path = home / path.relative_to(alias)
            break
    if not path.is_relative_to(home) or (path == home and not allow_home):
        raise ValueError("Application paths must stay inside your home directory")
    return path


def validate_directory_ancestry(path, home):
    """Refuse replaceable parents before writes, locks or owned-data removal."""
    path = normalize_home_path(path, home, allow_home=True)
    for item in (*reversed(path.parents), path):
        try:
            info = item.lstat()
        except FileNotFoundError:
            break
        if stat.S_ISLNK(info.st_mode):
            raise ValueError("Refusing a symlinked application directory: " + str(item))
        if not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, os.getuid()):
            raise ValueError("An application directory has unexpected type or ownership: " + str(item))
        if info.st_mode & 0o022 and not info.st_mode & stat.S_ISVTX:
            raise ValueError("Refusing a writable nonsticky application directory: " + str(item))
    return path


def validate_owned_root(path, home):
    """Validate a writable application root before creating any directories."""
    path = normalize_home_path(path, home)
    validate_directory_ancestry(path, home)
    if path.exists() and path.stat().st_uid != os.getuid():
        raise ValueError("An application directory has unexpected type or ownership: " + str(path))


def _namespace_exists(path):
    """Observe an owned directory without following links or creating it."""
    for item in (*reversed(path.parents), path):
        try:
            info = item.lstat()
        except FileNotFoundError:
            return False
        if stat.S_ISLNK(info.st_mode):
            raise ValueError("Refusing a symlinked application namespace")
        if not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, os.getuid()):
            raise ValueError("An application namespace has unexpected type or ownership")
        if info.st_mode & 0o022 and not info.st_mode & stat.S_ISVTX:
            raise ValueError("Refusing a writable nonsticky application namespace")
    if info.st_uid != os.getuid():
        raise ValueError("An application namespace is not owned by the current user")
    return True


def namespace_paths(home, namespace, environ=None):
    if namespace not in (PRIMARY_NAMESPACE, LEGACY_NAMESPACE):
        raise ValueError("Unsupported application namespace")
    original_home = Path(home)
    home = original_home.resolve()
    bases = [xdg_root(name, home, environ) for name in DEFAULTS]
    default_data = home / ".local/share"
    if default_data not in bases:
        bases.append(default_data)
    bases.append(home / ".var/app/com.obsproject.Studio/config")
    return [normalize_home_path(base, original_home, allow_home=True) / namespace
            if base.is_relative_to(original_home) else base / namespace for base in bases]


def legacy_plugin_present(home, environ=None):
    """A verified old loader installation anchors even its first control lock."""
    values = os.environ if environ is None else environ
    home = Path(home).resolve()
    root = Path(values.get("DECKY_HOME") or home / "homebrew")
    if not root.is_absolute() or ".." in root.parts or not root.resolve().is_relative_to(home):
        raise ValueError("DECKY_HOME must identify a safe directory inside your home")
    plugin = root / "plugins/obsgod"
    validate_directory_ancestry(plugin, home)
    if not plugin.exists() and not plugin.is_symlink():
        return False
    records = []
    for name in ("plugin.json", "package.json"):
        path = plugin / name
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid not in (0, os.getuid())
                or info.st_nlink != 1 or info.st_mode & 0o022 or info.st_size > 65536):
            raise ValueError("The previous plugin identity could not be verified")
        records.append(json.loads(path.read_text()))
    identity, package = records
    if (not isinstance(identity, dict) or identity.get("name") != "OBSGod"
            or not isinstance(package, dict) or package.get("name") not in {"obsgod", "obsgod-decky"}
            or not isinstance(package.get("version"), str)
            or not re.fullmatch(r"[0-9][A-Za-z0-9.-]{0,79}", package["version"])):
        raise ValueError("The previous plugin identity could not be verified")
    return True


def app_namespace(home, environ=None):
    """Choose one coherent new/legacy store, retaining existing lock inodes.

    This is the same contract as Go UserPaths: any validated legacy store and
    no primary store retains the old namespace across every XDG/OBS root.
    Ambiguous coexistence requires deliberate recovery, never an implicit move.
    """
    present = {}
    for namespace in (PRIMARY_NAMESPACE, LEGACY_NAMESPACE):
        present[namespace] = any([_namespace_exists(path) for path in namespace_paths(home, namespace, environ)])
    present[LEGACY_NAMESPACE] = legacy_plugin_present(home, environ) or present[LEGACY_NAMESPACE]
    if all(present.values()):
        raise ValueError("Both current and legacy application stores exist. Resolve the naming migration before changing either store.")
    return LEGACY_NAMESPACE if present[LEGACY_NAMESPACE] else PRIMARY_NAMESPACE


def app_directories(home, environ=None):
    """Return (app data, Desktop entries), preserving a pre-XDG install.

    No implicit data migration occurs when a user changes XDG_DATA_HOME. Two
    existing locations require a deliberate repair instead of guessing which
    installation owns the current OBS connection and updater state.
    """
    home = Path(home)
    data = xdg_root("XDG_DATA_HOME", home, environ)
    namespace = app_namespace(home, environ)
    legacy = home / ".local/share" / namespace
    wanted = data / namespace
    if wanted != legacy and (legacy.exists() or legacy.is_symlink()):
        if wanted.exists() or wanted.is_symlink():
            raise ValueError("Two deckystream installation locations exist. Resolve the XDG data migration before changing either installation.")
        return legacy, home / ".local/share/applications"
    return wanted, data / "applications"


def decky_locations(home, environ=None):
    """Resolve only the stable deckystream plugin's Decky roots, never shared parents."""
    values = os.environ if environ is None else environ
    root_value = values.get("DECKY_HOME", "")
    root = Path(root_value) if root_value else Path(home) / "homebrew"
    if not root.is_absolute() or ".." in root.parts or any(c in str(root) for c in "\x00\r\n") or not root.resolve().is_relative_to(Path(home).resolve()):
        raise ValueError("DECKY_HOME must identify a safe absolute directory inside your home")
    expected = {"plugin": root / "plugins/deckystream", "settings": root / "settings/deckystream",
                "data": root / "data/deckystream", "logs": root / "logs/deckystream"}
    variables = {"plugin": "DECKY_PLUGIN_DIR", "settings": "DECKY_PLUGIN_SETTINGS_DIR",
                 "data": "DECKY_PLUGIN_RUNTIME_DIR", "logs": "DECKY_PLUGIN_LOG_DIR"}
    for key, name in variables.items():
        value = values.get(name, "")
        if value and Path(value) != expected[key]:
            raise ValueError(name + " disagrees with the stable deckystream directory under DECKY_HOME")
    for path in expected.values():
        for parent in [path, *path.parents]:
            if parent in (Path(home), Path(home).resolve()) or not parent.resolve().is_relative_to(Path(home).resolve()):
                continue
            if parent.is_symlink():
                raise ValueError("Refusing a symlinked Decky directory")
    return expected
