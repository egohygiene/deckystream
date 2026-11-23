"""Exercise verification and refusal before any candidate code can execute."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B = load("desktop_bootstrap", ROOT / "steamdeck/bootstrap.py")
P = load("bootstrap_packager", ROOT / "scripts/package-bootstrap.py")
R = load("desktop_bootstrap_releases", ROOT / "steamdeck/releases.py")
U = load("desktop_bootstrap_update", ROOT / "steamdeck/update.py")


class DesktopBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="desktop-bootstrap-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.meta = {"schema_version": 1, "repository": R.REPOSITORY, "version": "0.1.0-test.1",
                     "revision": "a" * 40, "platform": "linux/amd64", "dirty": False}
        self.delivery = self.root / "delivery"
        self.delivery.mkdir(mode=0o700)
        self.pyz = self.root / "deckystream-install.pyz"
        self.pyz.write_bytes(b"fixture trusted bootstrap")
        self.name = "deckystream-deck_" + self.meta["version"] + "_linux_amd64.tar.gz"
        # This code is a trap: verification must never execute it.
        self.files = {"install.py": b"RECOVERY_POLICY_VERSION = 1\nraise RuntimeError('CANDIDATE_EXECUTED')\n",
                      "deckystream": b"fixture binary", "deckystream-decky.zip": b"fixture zip",
                      "setup.py": b"fixture setup", "bridge.py": b"fixture bridge",
                      "decky.py": b"fixture handoff", "decky-install": b"fixture helper",
                      "update.py": b"fixture updater", "releases.py": b"fixture releases"}
        self.manifest = dict(self.meta, files={name: hashlib.sha256(data).hexdigest()
                                             for name, data in self.files.items()})
        self.raw_manifest = json.dumps(self.manifest, sort_keys=True).encode()
        self.files["manifest.json"] = self.raw_manifest
        self.write_archive()
        self.write_delivery()

    def write_archive(self, extra=None):
        with tarfile.open(self.delivery / self.name, "w:gz") as archive:
            for name, data in self.files.items():
                entry = tarfile.TarInfo("deckystream-" + self.meta["version"] + "/" + name)
                entry.size = len(data)
                archive.addfile(entry, io.BytesIO(data))
            if extra:
                archive.addfile(extra)

    def write_delivery(self):
        (self.delivery / "manifest.json").write_bytes(self.raw_manifest)
        data = {"deckystream-install.pyz": self.pyz.read_bytes(), self.name: (self.delivery / self.name).read_bytes(),
                "manifest.json": self.raw_manifest}
        assets = {name: {"size": len(value), "sha256": hashlib.sha256(value).hexdigest()} for name, value in data.items()}
        value = dict(self.meta, unsigned=True, artifacts=assets)
        raw = json.dumps(value).encode()
        (self.delivery / "installer-manifest.json").write_bytes(raw)
        sums = {name: item["sha256"] for name, item in assets.items()}
        sums["installer-manifest.json"] = hashlib.sha256(raw).hexdigest()
        (self.delivery / "INSTALLER-SHA256SUMS").write_text("".join(digest + "  " + name + "\n" for name, digest in sorted(sums.items())))
        return value

    def test_valid_local_candidate_uses_no_network_and_executes_no_payload(self):
        with mock.patch.object(R, "_open_url", side_effect=AssertionError("network")):
            candidate, _, raw = B.descriptor(self.meta, "preview", self.delivery, self.pyz, R)
        self.assertIsNone(candidate)
        work = self.root / "work"
        work.mkdir()
        package = B.verify_payload(self.delivery / self.name, work, self.meta, raw, U, R)
        self.assertEqual((package / "install.py").read_bytes(), self.files["install.py"])
        self.assertEqual((package / "deckystream").stat().st_mode & 0o777, 0o700)

    def test_runtime_extra_traversal_and_link_are_refused_without_code_execution(self):
        for kind in ("traversal", "link", "extra"):
            with self.subTest(kind=kind):
                name = "../escape" if kind == "traversal" else "deckystream-" + self.meta["version"] + "/unexpected"
                entry = tarfile.TarInfo(name)
                if kind == "link":
                    entry.type = tarfile.SYMTYPE
                    entry.linkname = "/etc/passwd"
                self.write_archive(entry)
                work = self.root / kind
                work.mkdir()
                with self.assertRaises((B.BootstrapError, U.UpdateError)):
                    B.verify_payload(self.delivery / self.name, work, self.meta, self.raw_manifest, U, R)
        self.assertFalse((self.root / "escape").exists())

    def test_every_runtime_file_and_embedded_manifest_is_checked(self):
        for name in ("install.py", "manifest.json", "deckystream-decky.zip"):
            with self.subTest(name=name):
                original = self.files[name]
                self.files[name] = original + b"tampered"
                self.write_archive()
                work = self.root / ("changed-" + name.replace(".", "-"))
                work.mkdir()
                with self.assertRaises(B.BootstrapError):
                    B.verify_payload(self.delivery / self.name, work, self.meta, self.raw_manifest, U, R)
                self.files[name] = original

    def test_delivery_version_revision_platform_cleanliness_and_publisher_are_bound(self):
        value = self.write_delivery()
        for key, wrong in (("version", "0.2.0"), ("revision", "b" * 40), ("platform", "linux/arm64"),
                           ("repository", "other/project"), ("dirty", True), ("unsigned", False)):
            with self.subTest(key=key), self.assertRaises(B.BootstrapError):
                B.validate_delivery(dict(value, **{key: wrong}), self.meta)

    def test_inventory_rejects_unsafe_names_size_digest_and_boolean_length(self):
        value = self.write_delivery()
        for name, entry in (("../escape", {"size": 1, "sha256": "a" * 64}),
                            ("unsafe", {"size": True, "sha256": "a" * 64}),
                            ("unsafe", {"size": 129 * 1024 * 1024, "sha256": "a" * 64}),
                            ("unsafe", {"size": 1, "sha256": "not a digest"})):
            with self.subTest(name=name, entry=entry), self.assertRaises(B.BootstrapError):
                B.validate_delivery(dict(value, artifacts=dict(value["artifacts"], **{name: entry})), self.meta)

    def test_bundle_hash_manifest_hash_and_envelope_disagreement_refuse(self):
        for name in ("installer-manifest.json", "manifest.json", "bundle", "INSTALLER-SHA256SUMS"):
            with self.subTest(name=name):
                self.write_delivery()
                path = self.pyz if name == "bundle" else self.delivery / name
                original = path.read_bytes()
                path.write_bytes(original + b"changed")
                with self.assertRaises((B.BootstrapError, R.ReleaseError, ValueError)):
                    B.descriptor(self.meta, "preview", self.delivery, self.pyz, R)
                path.write_bytes(original)

    def test_no_release_and_moved_tag_refuse(self):
        with mock.patch.object(R, "_latest", return_value=None), self.assertRaisesRegex(B.BootstrapError, "No matching release"):
            B.descriptor(self.meta, "preview", None, self.pyz, R)
        with mock.patch.object(R, "_latest", return_value={"revision": "b" * 40}), self.assertRaisesRegex(B.BootstrapError, "tag"):
            B.descriptor(self.meta, "preview", None, self.pyz, R)

    def test_local_links_and_partial_files_refuse(self):
        path = self.delivery / "manifest.json"
        path.unlink()
        path.symlink_to(self.pyz)
        with self.assertRaises(OSError):
            B.read_file(path, 100)
        path.unlink()
        path.write_bytes(b"partial")
        with self.assertRaises(B.BootstrapError):
            B.descriptor(self.meta, "preview", self.delivery, self.pyz, R)
        hardlink = self.delivery / "hardlink"
        os.link(path, hardlink)
        with self.assertRaises(B.BootstrapError):
            B.read_file(path, 100)

    def test_preview_default_and_version_assertion_refuse_before_download(self):
        with mock.patch.object(B, "metadata", return_value=self.meta), mock.patch.object(B, "descriptor", side_effect=AssertionError("download")):
            self.assertEqual(B.main(["--verify-only"], bundle_path=self.pyz), 1)
            self.assertEqual(B.main(["--version", "9.0.0", "--verify-only"], bundle_path=self.pyz), 1)

    def test_root_missing_desktop_and_pipe_refuse_before_install(self):
        with mock.patch.object(B.os, "getuid", return_value=0), self.assertRaisesRegex(B.BootstrapError, "without sudo"):
            B.player_preflight()
        uid = os.getuid() or 1000
        user = mock.Mock(pw_dir=str(self.root))
        with mock.patch.object(B.os, "getuid", return_value=uid), mock.patch.object(B.os, "geteuid", return_value=uid), mock.patch.object(pwd, "getpwuid", return_value=user), mock.patch.object(B.Path, "home", return_value=self.root), mock.patch.object(B.Path, "stat", return_value=mock.Mock(st_uid=uid)), mock.patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "gamescope"}, clear=True):
            with self.assertRaisesRegex(B.BootstrapError, "Desktop Mode"):
                B.player_preflight()

    def test_progress_failure_is_filtered_and_existing_work_is_preserved(self):
        work = self.root / "attempt"
        work.mkdir()
        sentinel = work / "keep"
        sentinel.write_text("preserved")
        with mock.patch.object(B, "metadata", return_value=self.meta), mock.patch.object(B, "private_attempt", return_value=work), mock.patch.object(B, "descriptor", side_effect=KeyboardInterrupt):
            self.assertEqual(B.main(["--channel", "preview", "--verify-only"], bundle_path=self.pyz), 1)
        receipt = json.loads((work / "progress.json").read_text())
        self.assertEqual(receipt["outcome"], "interrupted")
        self.assertFalse(receipt["installation_attempted"])
        self.assertEqual(sentinel.read_text(), "preserved")
        self.assertNotIn("secret", receipt)

    def test_complete_zipapp_runs_inspection_without_repo_imports_or_network(self):
        files = P.source_files(self.meta["version"], self.meta["revision"], 1700000000)
        with zipfile.ZipFile(self.pyz, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in files.items():
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, data)
        result = subprocess.run([sys.executable, "-I", str(self.pyz), "--inspect"], cwd=self.root,
                                text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(result.stdout)["revision"], self.meta["revision"])
        with zipfile.ZipFile(self.pyz, "a") as archive:
            archive.writestr("unexpected.py", b"raise RuntimeError('MUST_NOT_RUN')")
        result = subprocess.run([sys.executable, "-I", str(self.pyz), "--inspect"], cwd=self.root, text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)

    def test_writable_local_candidate_and_unsafe_code_temp_parent_refuse(self):
        path = self.delivery / "manifest.json"
        path.chmod(0o666)
        with self.assertRaises(B.BootstrapError):
            B.read_file(path, 10000)
        path.chmod(0o600)
        files = P.source_files(self.meta["version"], self.meta["revision"], 1700000000)
        with zipfile.ZipFile(self.pyz, "w") as archive:
            for name, data in files.items():
                info = zipfile.ZipInfo(name)
                info.external_attr = 0o100644 << 16
                archive.writestr(info, data)
        shared = self.root / "unsafe-temp"
        shared.mkdir()
        shared.chmod(0o777)
        env = dict(os.environ, TMPDIR=str(shared))
        result = subprocess.run([sys.executable, "-I", str(self.pyz), "--inspect"], cwd=self.root, env=env,
                                text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(list(shared.iterdir()), [])

    def test_bootstrap_scratch_does_not_create_a_second_legacy_store(self):
        paths = load("bootstrap_legacy_paths", ROOT / "steamdeck/paths.py")
        home = self.root / "player"
        home.mkdir()
        state = home / ".local/state/obsgod"
        state.mkdir(parents=True)
        lock = state / "control.lock"
        lock.write_text("")
        lock.chmod(0o600)
        inode = lock.stat().st_ino
        env = {"HOME": str(home)}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(B.shutil, "disk_usage", return_value=mock.Mock(free=500 * 1024 * 1024)):
            self.assertEqual(paths.app_namespace(home), "obsgod")
            attempt = B.private_attempt(paths, home)
            self.assertEqual(attempt.parent, home / ".cache/deckystream-bootstrap")
            self.assertEqual(paths.app_namespace(home), "obsgod")
            self.assertFalse((home / ".cache/deckystream").exists())
            self.assertEqual(lock.stat().st_ino, inode)

    def test_existing_and_unsafe_output_is_preserved(self):
        with self.assertRaises(FileExistsError):
            P.output_directory(self.delivery)
        self.assertTrue((self.delivery / self.name).is_file())
        shared = self.root / "shared"
        shared.mkdir(mode=0o777)
        shared.chmod(0o777)
        with self.assertRaises(ValueError):
            P.output_directory(shared / "output")


if __name__ == "__main__":
    unittest.main()
