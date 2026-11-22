"""Primary naming, retained legacy stores and one-controller upgrade boundaries."""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


P = load("naming_paths", ROOT / "paths.py")
S = load("naming_storage", ROOT / "decky/storage.py")
B = load("naming_backend", ROOT / "decky/main.py")
I = load("naming_install", ROOT / "install.py")
D = load("naming_decky", ROOT / "decky.py")
R = load("naming_releases", ROOT / "releases.py")
U = load("naming_uninstall", ROOT / "uninstall.py")


class NamespaceSelection(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name) / "player"
        self.home.mkdir(mode=0o700)
        self.env = {"HOME": str(self.home), **{
            name: str(self.home / name.lower()) for name in P.DEFAULTS}}

    def test_fresh_namespace_does_not_create_data(self):
        before = list(self.home.iterdir())
        self.assertEqual(P.app_namespace(self.home, self.env), "deckystream")
        self.assertEqual(list(self.home.iterdir()), before)

    def test_each_owned_legacy_family_selects_one_unchanged_namespace(self):
        bases = [Path(self.env[name]) for name in P.DEFAULTS]
        bases += [self.home / ".var/app/com.obsproject.Studio/config", self.home / ".local/share"]
        for base in bases:
            with self.subTest(base=base):
                leaf = base / "obsgod"
                leaf.mkdir(parents=True, mode=0o700)
                self.assertEqual(P.app_namespace(self.home, self.env), "obsgod")
                self.assertEqual(P.app_directories(self.home, self.env)[0].name, "obsgod")
                leaf.rmdir()

    def test_mixed_namespaces_are_refused_without_moving_either(self):
        old = Path(self.env["XDG_CONFIG_HOME"]) / "obsgod"
        new = Path(self.env["XDG_STATE_HOME"]) / "deckystream"
        for path in (old, new):
            path.mkdir(parents=True, mode=0o700)
        identities = [(p.stat().st_dev, p.stat().st_ino) for p in (old, new)]
        with self.assertRaisesRegex(ValueError, "Both current and legacy"):
            P.app_namespace(self.home, self.env)
        self.assertEqual([(p.stat().st_dev, p.stat().st_ino) for p in (old, new)], identities)

    def test_verified_old_plugin_anchors_empty_legacy_namespace(self):
        plugin = self.home / "homebrew/plugins/obsgod"
        plugin.mkdir(parents=True, mode=0o700)
        (plugin / "plugin.json").write_text('{"name":"OBSGod"}')
        (plugin / "package.json").write_text('{"name":"obsgod","version":"0.1.0-deck.9"}')
        self.assertEqual(P.app_namespace(self.home, self.env), "obsgod")
        with patch.dict(os.environ, self.env, clear=True), patch.object(I, "_releases") as releases:
            releases.installed_plugin_version.return_value = "0.1.0-deck.9"
            I.adopt_legacy_store_for_upgrade(self.home)
        for path in plugin.iterdir():
            path.unlink()
        plugin.rmdir()
        self.assertEqual(P.app_namespace(self.home, self.env), "obsgod")
        self.assertTrue((Path(self.env["XDG_STATE_HOME"]) / "obsgod").is_dir())
        self.assertFalse((Path(self.env["XDG_DATA_HOME"]) / "deckystream").exists())

    def test_only_a_present_safe_legacy_plugin_can_anchor_the_namespace(self):
        loader = self.home / "homebrew"
        loader.mkdir(mode=0o700)
        loader.chmod(0o777)
        self.assertEqual(P.app_namespace(self.home, self.env), "deckystream")
        plugin = loader / "plugins/obsgod"
        plugin.mkdir(parents=True, mode=0o700)
        with self.assertRaisesRegex(ValueError, "writable nonsticky"):
            P.app_namespace(self.home, self.env)
        loader.chmod(0o700)
        identity = plugin / "plugin.json"
        identity.write_text('{"name":"OBSGod"}')
        metadata = self.home / "unrelated.json"
        metadata.write_text('{"name":"obsgod","version":"0.1.0-deck.9"}')
        (plugin / "package.json").symlink_to(metadata)
        with self.assertRaisesRegex(ValueError, "identity could not be verified"):
            P.app_namespace(self.home, self.env)
        self.assertEqual(metadata.read_text(), '{"name":"obsgod","version":"0.1.0-deck.9"}')

    def test_linked_or_foreign_legacy_namespace_is_not_adopted(self):
        parent = Path(self.env["XDG_CONFIG_HOME"])
        parent.mkdir(mode=0o700)
        target = self.home / "unrelated"
        target.mkdir(mode=0o700)
        alias = parent / "obsgod"
        alias.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "symlinked"):
            P.app_namespace(self.home, self.env)
        alias.unlink()
        alias.mkdir(mode=0o700)
        with patch.object(P.os, "getuid", return_value=os.getuid() + 1):
            with self.assertRaisesRegex(ValueError, "ownership"):
                P.app_namespace(self.home, self.env)

    @unittest.skipIf(os.getuid() == 0, "Decky metadata requires the ordinary player")
    def test_new_loader_reuses_legacy_credentials_and_control_inode(self):
        config = Path(self.env["XDG_CONFIG_HOME"]) / "obsgod"
        state = Path(self.env["XDG_STATE_HOME"]) / "obsgod"
        for path in (config, state):
            path.mkdir(parents=True, mode=0o700)
        secret = config / "secrets.json"
        secret.write_bytes(b'{"stream_key":"private-retained"}')
        secret.chmod(0o600)
        control = state / "control.lock"
        control.touch(mode=0o600)
        original = (control.stat().st_dev, control.stat().st_ino, secret.read_bytes())
        plugin = self.home / "homebrew/plugins/deckystream"
        plugin.mkdir(parents=True, mode=0o700)
        provided = {}
        for name, folder in (("DECKY_PLUGIN_SETTINGS_DIR", "settings"),
                             ("DECKY_PLUGIN_RUNTIME_DIR", "data"), ("DECKY_PLUGIN_LOG_DIR", "logs")):
            value = self.home / "homebrew" / folder / "deckystream"
            value.mkdir(parents=True, mode=0o700)
            provided[name] = str(value)
        poisoned = dict(self.env, OBSGOD_DECKY_STORAGE_MAP="/untrusted/old-map",
                        OBSGOD_DECKY_RUNTIME_DIR="/untrusted/old-runtime", OBSGOD_DECKY_LOG_DIR="/untrusted/old-logs",
                        DECKYSTREAM_DECKY_STORAGE_MAP="/untrusted/new-map")
        with control.open("r+") as locked:
            fcntl.flock(locked, fcntl.LOCK_EX | fcntl.LOCK_NB)
            child = S.child_environment(plugin, provided, poisoned)
            record = json.loads(Path(child[S.MAP_ENV]).read_text())
            self.assertEqual(record["shared"]["secrets"], str(secret))
            self.assertEqual(record["shared"]["state"], str(state))
            self.assertEqual(record["compatibility"], {"cli": "deckystream", "plugin": "deckystream", "storage_namespace": "obsgod"})
            self.assertFalse(any(key.startswith("OBSGOD_DECKY_") for key in child))
            with control.open("r+") as second:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(second, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.assertEqual((control.stat().st_dev, control.stat().st_ino, secret.read_bytes()), original)
        self.assertFalse((config.parent / "deckystream").exists())

    def test_new_backend_refuses_to_start_alongside_legacy_plugin(self):
        root = self.home / "homebrew/plugins/deckystream"
        previous = root.parent / "obsgod"
        root.mkdir(parents=True)
        previous.mkdir()
        (previous / "plugin.json").write_text('{"name":"OBSGod"}')
        plugin = B.Plugin()
        with patch.object(plugin, "_provided", side_effect=lambda name: str(root) if name == "DECKY_PLUGIN_DIR" else None), patch.object(B.storage, "child_environment") as child:
            with self.assertRaisesRegex(OSError, "previous OBSGod plugin"):
                plugin._child_environment()
            child.assert_not_called()
            with self.assertRaisesRegex(OSError, "previous OBSGod plugin"):
                plugin._dependency_controller()
        self.assertIsNone(plugin._dependency_job)


class LegacyActivation(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.base = self.home / ".local/share/obsgod"
        self.releases = self.base / "releases"
        self.old = self.releases / "old"
        self.old.mkdir(parents=True, mode=0o700)
        (self.old / "obsgod").write_bytes(b"original binary retained")
        self.current = self.base / "current"
        self.current.symlink_to(self.old)
        self.bin = self.home / ".local/bin"
        self.apps = self.home / ".local/share/applications"
        for path in (self.bin, self.apps):
            path.mkdir(parents=True, mode=0o700)
        self.alias = self.bin / "obsgod"
        self.alias.symlink_to(self.current / "obsgod")
        self.shortcut = self.apps / "obsgod-setup.desktop"
        self.shortcut.write_text("[Desktop Entry]\nName=OBSGod Setup\nX-OBSGod-Managed=true\n")
        self.package = self.home / "new-package"
        self.package.mkdir(mode=0o700)
        files = {"deckystream": b"new verified binary", "setup.py": b"# no launch\n"}
        self.manifest = {"version": "1.0.0", "files": {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
        for name, data in files.items():
            (self.package / name).write_bytes(data)
        (self.package / "manifest.json").write_text(json.dumps(self.manifest))

    def test_owned_old_alias_and_menu_are_retired_without_mixing_release_files(self):
        with patch.object(I, "ROOT", self.package):
            I.activate_release(self.base, self.releases, self.bin, self.apps, self.home, self.manifest)
        self.assertEqual(self.alias.readlink(), self.current / "deckystream")
        self.assertEqual((self.bin / "deckystream").readlink(), self.current / "deckystream")
        self.assertFalse(self.shortcut.exists())
        self.assertTrue(list((self.base / "backups").glob("*/obsgod-setup.desktop")))
        self.assertEqual((self.old / "obsgod").read_bytes(), b"original binary retained")
        self.assertFalse((self.current / "obsgod").exists())
        self.assertEqual(set(p.name for p in self.current.iterdir()), {"deckystream", "setup.py", "manifest.json"})

    def test_activation_failure_restores_old_alias_and_menu(self):
        original = Path.replace

        def fail_current(path, destination):
            if path.name == "current" and path.parent.name.startswith(".activate-"):
                raise OSError("fixture activation failure")
            return original(path, destination)

        with patch.object(I, "ROOT", self.package), patch.object(Path, "replace", fail_current):
            with self.assertRaisesRegex(OSError, "fixture activation failure"):
                I.activate_release(self.base, self.releases, self.bin, self.apps, self.home, self.manifest)
        self.assertEqual(self.current.resolve(), self.old)
        self.assertEqual(self.alias.readlink(), self.current / "obsgod")
        self.assertIn("Name=OBSGod Setup", self.shortcut.read_text())
        self.assertFalse((self.bin / "deckystream").exists())

    def legacy_recovery_package(self):
        names = {"obsgod", "setup.py", "bridge.py", "setup.html", "setup.js", "setup.css", "uninstall.py", "obsgod-decky.zip", "LICENSE", "THIRD_PARTY_NOTICES.md", "STEAM-DECK.md",
                 "decky-install", "decky.py", "install.py", "Install OBSGod.desktop", "update.py", "releases.py", "Update OBSGod.desktop", "Update OBSGod.sh"}
        version = "0.1.0-deck.9"
        for name in names:
            (self.old / name).write_bytes(("retained old " + name).encode())
            (self.old / name).chmod(0o700 if name in {"decky-install", "obsgod"} else 0o600)
        with zipfile.ZipFile(self.old / "obsgod-decky.zip", "w") as archive:
            archive.writestr("obsgod/package.json", json.dumps({"name": "obsgod", "version": version, "type": "module"}))
            archive.writestr("obsgod/plugin.json", '{"name":"OBSGod","flags":[],"api_version":1}')
        manifest = {"version": version, "revision": "a" * 40, "dirty": False, "platform": "linux/amd64",
                    "files": {name: hashlib.sha256((self.old / name).read_bytes()).hexdigest() for name in names}}
        (self.old / "manifest.json").write_text(json.dumps(manifest))
        for name in ("paths.py",):
            (self.package / name).write_bytes((ROOT / name).read_bytes())
        (self.package / "decky-install").write_bytes(b"current helper")
        (self.package / "decky-install").chmod(0o700)
        return manifest

    def plugin_metadata(self, name, version):
        directory = self.home / "homebrew/plugins" / ("obsgod" if name == "OBSGod" else name)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "plugin.json").write_text(json.dumps({"name": name}))
        (directory / "package.json").write_text(json.dumps({"name": "obsgod" if name == "OBSGod" else name, "version": version}))
        return directory

    def test_verified_previous_helper_restores_legacy_pair_after_primary_retirement(self):
        manifest = self.legacy_recovery_package()
        candidate_version = "0.1.0-deck.10"
        current_plugin = self.plugin_metadata("deckystream", candidate_version)
        bridge = Mock()
        bridge.run_cli.return_value = {"ok": True, "state": "stopped", "configured": True, "output_known": True,
                                       "stream": {"active": False}, "recording": False, "process": "absent",
                                       "media": {"known": True, "replay_active": False, "recording": {"active": False, "paused": False}}}
        calls = []

        def manager(command, **kwargs):
            request = json.loads(kwargs["input"])
            calls.append((Path(command[0]), request["operation"]))
            lock = self.home / ".local/state/obsgod/control.lock"
            with lock.open("r+") as check:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(check, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if request["operation"] == "uninstall":
                self.assertNotIn("legacy_plugin", request)
                for path in current_plugin.iterdir():
                    path.unlink()
                current_plugin.rmdir()
                return SimpleNamespace(returncode=0, stdout=json.dumps({"ok": True, "removed": True}))
            self.assertEqual(command[0], str(self.old / "decky-install"))
            self.assertNotIn("legacy_plugin", request, "old helpers do not recognize the new request field")
            self.plugin_metadata("OBSGod", manifest["version"])
            return SimpleNamespace(returncode=0, stdout=json.dumps({"ok": True, "version": manifest["version"]}))

        with patch.dict(os.environ, {"HOME": str(self.home)}, clear=True), patch.object(D, "ROOT", self.package), patch.object(D.subprocess, "run", side_effect=manager), patch.object(I, "_releases", R):
            with I.control_lock(self.home):
                self.assertTrue(I.recover_previous_plugin(D, self.old, manifest["version"], candidate_version, self.home, bridge))
        self.assertEqual(calls, [(self.package / "decky-install", "uninstall"), (self.old / "decky-install", "install")])
        self.assertEqual(self.current.resolve(), self.old)

    def test_tampered_previous_helper_never_removes_primary_plugin(self):
        manifest = self.legacy_recovery_package()
        candidate_version = "0.1.0-deck.10"
        current_plugin = self.plugin_metadata("deckystream", candidate_version)
        (self.old / "decky-install").write_bytes(b"changed helper")
        with patch.dict(os.environ, {"HOME": str(self.home)}, clear=True), patch.object(D, "ROOT", self.package), patch.object(D.subprocess, "run") as execute, patch.object(I, "_releases", R):
            self.assertFalse(I.recover_previous_plugin(D, self.old, manifest["version"], candidate_version, self.home, Mock()))
            execute.assert_not_called()
        self.assertTrue(current_plugin.is_dir())

    def test_legacy_retirement_binds_version_and_requires_closed_output(self):
        version = "0.1.0-deck.9"
        old_plugin = self.plugin_metadata("OBSGod", version)
        bridge, decky = Mock(), Mock()
        idle = {"ok": True, "state": "stopped", "output_known": True,
                "stream": {"active": False}, "recording": False, "process": "running",
                "media": {"known": True, "replay_active": False, "recording": {"active": False, "paused": False}}}
        bridge.run_cli.return_value = idle
        with patch.dict(os.environ, {"HOME": str(self.home)}, clear=True), patch.object(I, "_releases", R):
            with self.assertRaisesRegex(RuntimeError, "Close the previous"):
                I.retire_legacy_plugin(decky, bridge, self.home, version)
            decky.helper_request.assert_not_called()
            with self.assertRaisesRegex(RuntimeError, "changed after inspection"):
                I.retire_legacy_plugin(decky, bridge, self.home, "0.1.0-deck.8")
            decky.helper_request.assert_not_called()
            bridge.run_cli.return_value = {**idle, "process": "absent"}

            def retire(*args, **kwargs):
                self.assertEqual(args, ("uninstall",))
                self.assertEqual(kwargs, {"uninstall_existing": True, "legacy_plugin": True, "expected_version": version})
                for path in old_plugin.iterdir():
                    path.unlink()
                old_plugin.rmdir()

            decky.helper_request.side_effect = retire
            self.assertEqual(I.retire_legacy_plugin(decky, bridge, self.home, version), version)

    def test_legacy_uninstall_plans_old_identity_and_removes_only_owned_aliases(self):
        version = "0.1.0-deck.9"
        previous = self.plugin_metadata("OBSGod", version)
        unrelated = self.bin / "another-tool"
        unrelated.write_bytes(b"keep")
        decky = Mock()

        def remove(*args, **kwargs):
            self.assertEqual(args, ("uninstall",))
            self.assertEqual(kwargs, {"uninstall_existing": True, "legacy_plugin": True, "expected_version": version})
            for path in previous.iterdir():
                path.unlink()
            previous.rmdir()
            return {"removed": True}

        decky.helper_request.side_effect = remove
        with patch.dict(os.environ, {"HOME": str(self.home)}, clear=True):
            plan = U.build_plan(self.home)
            self.assertEqual(plan["plugin_directory"], str(previous))
            self.assertEqual(plan["legacy_plugin_version"], version)
            self.assertIn(str(self.alias), [entry["path"] for entry in plan["entries"]])
            with patch.object(U, "_sibling", return_value=decky):
                U.remove_plugin(self.home, plan["plugin_directory"], version)
        self.assertTrue(unrelated.is_file())


class LegacyBackendStatus(unittest.IsolatedAsyncioTestCase):
    async def test_status_explains_legacy_conflict_without_starting_a_child(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "homebrew/plugins/deckystream"
            (root / "bin").mkdir(parents=True)
            (root / "bin/deckystream").write_bytes(b"not executed")
            (root / "bin/deckystream").chmod(0o700)
            (root.parent / "obsgod").mkdir()
            plugin = B.Plugin()
            with patch.object(plugin, "_provided", side_effect=lambda name: str(root) if name == "DECKY_PLUGIN_DIR" else None), patch.object(B.asyncio, "create_subprocess_exec") as spawn:
                status = await plugin.status()
                setup = await plugin.dependency_status()
            self.assertFalse(status["output_known"])
            self.assertIn("previous OBSGod plugin", status["message"])
            self.assertEqual(setup["reason"]["code"], "legacy-plugin")
            self.assertFalse(setup["can_install"])
            spawn.assert_not_called()


if __name__ == "__main__":
    unittest.main()
