"""Adversarial consistency and filesystem checks for unpublished delivery prep."""
import gzip
import importlib.util
import io
import json
import os
from contextlib import redirect_stdout
from pathlib import Path
import platform
import stat
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import urllib.parse
import urllib.request
import zipfile

SPEC = importlib.util.spec_from_file_location("installer_delivery", Path(__file__).parents[1] / "prepare-installer-release.py")
DELIVERY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DELIVERY)


def archive(files, root=None, kind="zip", duplicate=None):
    buffer = io.BytesIO()
    if kind == "tar":
        with gzip.GzipFile(filename="", fileobj=buffer, mode="wb", mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as bundle:
                for name, data in files.items():
                    entry = tarfile.TarInfo(root + "/" + name)
                    entry.size, entry.mode = len(data), 0o644
                    bundle.addfile(entry, io.BytesIO(data))
    else:
        with zipfile.ZipFile(buffer, "w") as bundle:
            for name, data in files.items():
                entry = zipfile.ZipInfo((root + "/" if root else "") + name)
                entry.external_attr = (stat.S_IFREG | 0o644) << 16
                bundle.writestr(entry, data)
            if duplicate is not None:
                entry = zipfile.ZipInfo(duplicate)
                entry.external_attr = (stat.S_IFREG | 0o644) << 16
                bundle.writestr(entry, b"duplicate")
    return buffer.getvalue()


class InstallerDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="installer-delivery-test-")
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name)
        self.runtime_dir, self.primary = self.work / "runtime", self.work / "primary"
        self.runtime_dir.mkdir(mode=0o700)
        self.primary.mkdir(mode=0o700)
        self.version, self.revision = "0.1.0-test.1", "a" * 40
        self.expected = {"version": self.version, "revision": self.revision,
                         "platform": "linux/amd64", "dirty": False}
        self.plugin = {name: ("fixture:" + name).encode() for name in DELIVERY.AUDIT.STANDARD_PLUGIN_FILES
                       if name != "manifest.json"}
        self.plugin["package.json"] = DELIVERY.canonical({"name": "deckystream", "version": self.version})
        self.plugin["plugin.json"] = DELIVERY.canonical({"name": "deckystream"})
        self.plugin["manifest.json"] = DELIVERY.canonical({**self.expected, "format": "decky-plugin",
            "files": {name: DELIVERY.sha(data) for name, data in self.plugin.items()}})
        self.zip = archive(self.plugin, "deckystream")
        self.payload = {name: ("fixture:" + name).encode() for name in DELIVERY.AUDIT.RUNTIME_FILES}
        self.payload["deckystream-decky.zip"] = self.zip
        self.source = {"steamdeck/" + name: data for name, data in self.payload.items()
                       if name.endswith((".py", ".desktop", ".sh", ".html", ".js", ".css"))}
        self.source["LICENSE"] = self.payload["LICENSE"]
        self.source["docs/steam-deck.md"] = self.payload["STEAM-DECK.md"]
        self.runtime = self.runtime_dir / ("deckystream-deck_" + self.version + "_linux_amd64.tar.gz")
        self.write_runtime()
        self.receipt = {**self.expected, "archive": "deckystream-decky.zip", "sha256": DELIVERY.sha(self.zip),
            "source_tools": {"go": "go1.27.4", "node": "24.19.0", "npm": "11.9.0"},
            "source_files_sha256": {"fixture-source.py": DELIVERY.sha(b"source")}}
        self.write_primary()
        self.bootstrap_files = {name: ("bootstrap fixture:" + name).encode()
                                for name in DELIVERY.BOOTSTRAP_FILES if name != "bootstrap-metadata.json"}
        self.bootstrap = self.work / "deckystream-install.pyz"
        self.write_bootstrap()
        self.expected_bootstrap = dict(self.bootstrap_files)
        self.output = self.work / "delivery"
        self.addCleanup(patch.stopall)
        self.current_source = patch.object(DELIVERY, "current_source", return_value=1700000000).start()
        patch.object(DELIVERY, "source", side_effect=lambda revision, name: self.source[name]).start()
        patch.object(DELIVERY, "source_inventory", return_value={"fixture-source.py": DELIVERY.sha(b"source")}).start()
        patch.object(DELIVERY, "source_archive", return_value=gzip.compress(b"synthetic source fixture", mtime=0)).start()
        patch.object(DELIVERY, "bootstrap_source", side_effect=lambda *args: dict(self.expected_bootstrap)).start()

    def write_runtime(self):
        manifest = {**self.expected, "go": "go1.27.4", "node": "24.19.0", "npm": "11.9.0",
                    "files": {name: DELIVERY.sha(data) for name, data in self.payload.items()
                              if name != "manifest.json"}}
        self.payload["manifest.json"] = DELIVERY.canonical(manifest)
        self.runtime.write_bytes(archive(self.payload, "deckystream-" + self.version, "tar"))
        selected = {self.runtime.name: self.runtime.read_bytes(), "manifest.json": self.payload["manifest.json"],
                    "deckystream-decky.zip": self.payload["deckystream-decky.zip"]}
        for name, data in selected.items():
            (self.runtime_dir / name).write_bytes(data)
        (self.runtime_dir / "SHA256SUMS").write_text("".join(DELIVERY.sha(data) + "  " + name + "\n"
                                                         for name, data in selected.items()))

    def write_primary(self):
        (self.primary / "deckystream-decky.zip").write_bytes(self.zip)
        (self.primary / "build-receipt.json").write_bytes(DELIVERY.canonical(self.receipt))
        (self.primary / "SHA256SUMS").write_text(DELIVERY.sha(self.zip) + "  deckystream-decky.zip\n")

    def write_bootstrap(self, *, duplicate=None):
        metadata = {**self.expected, "schema_version": 1, "repository": DELIVERY.REPOSITORY,
                    "files": {name: DELIVERY.sha(data) for name, data in self.bootstrap_files.items()
                              if name != "bootstrap-metadata.json"}}
        self.bootstrap_files["bootstrap-metadata.json"] = DELIVERY.canonical(metadata)
        self.bootstrap.write_bytes(archive(self.bootstrap_files, duplicate=duplicate))

    def prepare(self, *, output=None, audit=None):
        return DELIVERY.prepare(self.runtime, self.primary, self.bootstrap, self.revision,
                                output or self.output, audit)

    def refuses(self, pattern):
        with self.assertRaisesRegex(ValueError, pattern):
            self.prepare()
        self.assertFalse(self.output.exists(), "A refused candidate must not reserve a misleading delivery")

    def test_consistent_delivery_has_exact_integrity_envelope_and_no_publication_claim(self):
        original = self.runtime.read_bytes()
        manifest = self.prepare()
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o700)
        actual = {path.name: path.read_bytes() for path in self.output.iterdir()}
        self.assertEqual(set(actual), set(manifest["artifacts"]) | {"installer-manifest.json", "INSTALLER-SHA256SUMS"})
        self.assertEqual(manifest["repository"], DELIVERY.REPOSITORY)
        self.assertTrue(manifest["unsigned"])
        for name, descriptor in manifest["artifacts"].items():
            self.assertEqual(descriptor, {"size": len(actual[name]), "sha256": DELIVERY.sha(actual[name])})
            self.assertEqual((self.output / name).stat().st_mode & 0o777, 0o600)
        DELIVERY.AUDIT.verify_checksum_list(actual["INSTALLER-SHA256SUMS"],
            {name: data for name, data in actual.items() if name != "INSTALLER-SHA256SUMS"})
        packet = json.loads(actual["installer-owner-packet.json"])
        self.assertEqual(packet["state"], "prepared-unpublished")
        self.assertEqual(packet["qualification"], "unrun-by-this-preparation")
        self.assertEqual(packet["release_audit"], "unrun-by-this-preparation")
        self.assertEqual(packet["public_download_verification"], "unrun-until-approved-publication")
        self.assertEqual(original, self.runtime.read_bytes())

    def test_repeated_preparation_is_byte_identical_and_unifies_shared_checksum_name(self):
        self.prepare()
        other = self.work / "second"
        self.prepare(output=other)
        first = {path.name: path.read_bytes() for path in self.output.iterdir()}
        self.assertEqual(first, {path.name: path.read_bytes() for path in other.iterdir()})
        sums = first["SHA256SUMS"].decode()
        self.assertEqual(sums.count("  deckystream-decky.zip\n"), 1)
        self.assertEqual(first["manifest.json"], self.payload["manifest.json"])

    def test_runtime_hash_tampering_is_rejected_before_output(self):
        self.runtime.write_bytes(self.runtime.read_bytes() + b"tampered")
        self.refuses("checksum mismatch")

    def test_dirty_runtime_is_rejected_even_with_correct_outer_checksums(self):
        self.expected["dirty"] = True
        self.write_runtime()
        self.refuses("clean-source identity")

    def test_incorrect_source_and_platform_are_not_relabelled(self):
        for key, value in (("revision", "b" * 40), ("platform", "linux/arm64")):
            with self.subTest(key=key):
                before = self.expected[key]
                self.expected[key] = value
                self.write_runtime()
                self.refuses("identity mismatch")
                self.expected[key] = before

    def test_rehashed_installer_source_replacement_still_fails_source_binding(self):
        self.payload["install.py"] = b"changed source despite internally valid hash"
        self.write_runtime()
        self.refuses("source differs")

    def test_different_primary_zip_and_mismatched_receipt_fail(self):
        saved = (self.primary / "deckystream-decky.zip").read_bytes()
        (self.primary / "deckystream-decky.zip").write_bytes(b"other plugin")
        self.refuses("Primary ZIP differs")
        (self.primary / "deckystream-decky.zip").write_bytes(saved)
        self.receipt["sha256"] = "0" * 64
        self.write_primary()
        self.refuses("build receipt")

    def test_missing_runtime_sidecar_and_unexpected_payload_refuse(self):
        saved = (self.runtime_dir / "manifest.json").read_bytes()
        (self.runtime_dir / "manifest.json").write_bytes(b"{}")
        self.refuses("sidecar manifest")
        (self.runtime_dir / "manifest.json").write_bytes(saved)
        self.payload["extra.py"] = b"unexpected"
        self.write_runtime()
        self.refuses("inventory")

    def test_source_hash_inventory_must_match_every_primary_build_input(self):
        self.receipt["source_files_sha256"]["fixture-source.py"] = "0" * 64
        self.write_primary()
        self.refuses("complete selected source inventory")

    def test_bootstrap_rehashing_does_not_hide_source_substitution(self):
        self.bootstrap_files["bootstrap.py"] = b"different source, rehashed metadata"
        self.write_bootstrap()
        self.refuses("selected clean source")

    def test_bootstrap_bad_file_hash_and_publisher_refuse(self):
        metadata = json.loads(self.bootstrap_files["bootstrap-metadata.json"])
        metadata["files"]["bootstrap.py"] = "0" * 64
        self.bootstrap_files["bootstrap-metadata.json"] = DELIVERY.canonical(metadata)
        self.bootstrap.write_bytes(archive(self.bootstrap_files))
        self.refuses("checksum mismatch")
        metadata["repository"] = "other/publisher"
        self.bootstrap_files["bootstrap-metadata.json"] = DELIVERY.canonical(metadata)
        self.bootstrap.write_bytes(archive(self.bootstrap_files))
        self.refuses("publisher schema")

    def test_bootstrap_extra_traversal_and_duplicate_files_refuse(self):
        self.bootstrap_files["../outside"] = b"never extracted"
        self.write_bootstrap()
        self.refuses("Unsafe")
        del self.bootstrap_files["../outside"]
        # Construct a duplicate filename without the zipfile warning obscuring
        # the actual assertion about rejecting it.
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            self.write_bootstrap(duplicate="bootstrap.py")
        self.refuses("duplicate")

    def test_duplicate_json_keys_refuse(self):
        with self.assertRaisesRegex(ValueError, "Duplicate JSON"):
            DELIVERY.document(b'{"version":"1.0.0","version":"2.0.0"}')

    def test_symlinked_and_hardlinked_inputs_refuse(self):
        saved = self.bootstrap.read_bytes()
        original = self.work / "original.pyz"
        self.bootstrap.rename(original)
        self.bootstrap.symlink_to(original)
        self.refuses("linked")
        self.bootstrap.unlink()
        self.bootstrap.write_bytes(saved)
        os.link(self.bootstrap, self.work / "hardlink.pyz")
        self.refuses("shared")

    def test_symlinked_ancestor_and_writable_ancestry_refuse(self):
        link = self.work / "linked-primary"
        link.symlink_to(self.primary, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "linked"):
            DELIVERY.inspect_primary(link, self.version, self.revision, self.zip)
        self.primary.chmod(0o777)
        try:
            self.refuses("unprotected")
        finally:
            self.primary.chmod(0o700)

    def test_existing_output_is_preserved(self):
        self.output.mkdir()
        sentinel = self.output / "sentinel"
        sentinel.write_text("keep prior candidate")
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.prepare()
        self.assertEqual(sentinel.read_text(), "keep prior candidate")
        self.assertEqual(list(self.output.iterdir()), [sentinel])

    def test_source_changes_during_preparation_fail_before_output(self):
        self.current_source.side_effect = [1700000000, 1700000001]
        self.refuses("Source changed")

    def launcher(self, *, data=None, declared=None):
        command = DELIVERY.install_command(self.version, self.revision,
            DELIVERY.sha(self.bootstrap.read_bytes()), self.bootstrap.stat().st_size).decode()
        script = command.split("python3 -I - <<'PY'\n", 1)[1].removesuffix("PY\n")
        payload = self.bootstrap.read_bytes() if data is None else data
        response = io.BytesIO(payload)
        response.headers = {} if declared is None else {"Content-Length": str(declared)}
        namespace = {}
        work = self.work / "launch"
        work.mkdir(mode=0o700)
        class Executed(Exception):
            pass
        with patch.object(os, "getuid", return_value=1000), \
                patch.object(os, "umask"), \
                patch.object(platform, "system", return_value="Linux"), \
                patch.object(platform, "machine", return_value="x86_64"), \
                patch.object(os, "open", return_value=55), \
                patch.object(os, "dup2") as duplicate, \
                patch.object(os, "close"), \
                patch.object(tempfile, "mkdtemp", return_value=str(work)), \
                patch.object(urllib.request.OpenerDirector, "open", return_value=response), \
                patch.object(os, "execv", side_effect=Executed) as execute, \
                redirect_stdout(io.StringIO()):
            try:
                exec(compile(script, "INSTALL-COMMAND.txt", "exec"), namespace)
            except Executed:
                return command, namespace, execute.call_args, duplicate.call_args
        raise AssertionError("Launcher did not execute or refuse")

    def test_actual_launcher_verifies_complete_asset_restores_tty_and_executes_isolated(self):
        command, namespace, execute, terminal = self.launcher(declared=self.bootstrap.stat().st_size)
        self.assertEqual(namespace["url"], "https://github.com/egohygiene/deckystream/releases/download/v" + self.version + "/deckystream-install.pyz")
        self.assertEqual(namespace["expected"], DELIVERY.sha(self.bootstrap.read_bytes()))
        self.assertIn("# Source revision: " + self.revision, command)
        self.assertEqual(terminal.args, (55, 0))
        self.assertEqual(execute.args[0], sys.executable)
        self.assertEqual(execute.args[1], [sys.executable, "-I", str(self.work / "launch/deckystream-install.pyz"),
            "--version", self.version, "--channel", "preview", "--no-launch"])
        self.assertEqual((self.work / "launch/deckystream-install.pyz").read_bytes(), self.bootstrap.read_bytes())

    def test_actual_launcher_rejects_truncation_tampering_and_inconsistent_length(self):
        for key, kwargs in (("truncated", {"data": b"short"}),
                            ("tampered", {"data": b"x" * self.bootstrap.stat().st_size}),
                            ("length", {"declared": self.bootstrap.stat().st_size + 1})):
            with self.subTest(case=key), self.assertRaisesRegex(SystemExit, "mismatch"):
                self.launcher(**kwargs)
            self.assertFalse((self.work / "launch/deckystream-install.pyz").exists())
            (self.work / "launch").rmdir()

    def test_actual_launcher_allows_only_one_official_asset_redirect(self):
        _, namespace, _, _ = self.launcher()
        handler = namespace["AssetRedirect"]()
        url = namespace["url"]
        target = "https://release-assets.githubusercontent.com/github-production-release-asset/123/abc-def?token=opaque"
        request = urllib.request.Request(url)
        redirected = handler.redirect_request(request, None, 302, "Found", {}, target)
        self.assertEqual(redirected.full_url, target)
        for source, destination in ((url, "https://github.com/other/repo/releases/download/v1/asset.pyz"),
                (url, "http://release-assets.githubusercontent.com/github-production-release-asset/123/abc"),
                (url, "https://release-assets.githubusercontent.com.evil.test/github-production-release-asset/123/abc"),
                (url, "https://release-assets.githubusercontent.com/not-the-asset-path"),
                (target, target)):
            with self.subTest(destination=destination), self.assertRaisesRegex(ValueError, "redirect"):
                handler.redirect_request(urllib.request.Request(source), None, 302, "Found", {}, destination)

    def test_launcher_stable_channel_and_size_guard(self):
        command = DELIVERY.install_command("1.0.0", self.revision, "a" * 64, 12).decode()
        self.assertIn("channel = 'stable'", command)
        self.assertNotIn("import subprocess", command)
        self.assertNotIn("eval(", command)
        for size in (0, DELIVERY.MAX_METADATA + 1):
            with self.subTest(size=size), self.assertRaisesRegex(ValueError, "4 MiB"):
                DELIVERY.install_command("1.0.0", self.revision, "a" * 64, size)

    def audit_fixture(self):
        directory = self.work / "audit"
        directory.mkdir()
        selected = {self.runtime.name: self.runtime.read_bytes(), "manifest.json": self.payload["manifest.json"],
                    "deckystream-decky.zip": self.zip}
        report = {"revision": self.revision, "version": self.version, "repository": DELIVERY.REPOSITORY,
            "integrity": "passed", "source_inventory": "passed", "preferred_source": "passed",
            "subjects": [{"name": name, "digest": {"sha256": DELIVERY.sha(data)}} for name, data in selected.items()]}
        files = {"release-audit.json": DELIVERY.canonical(report), "sbom.spdx.json": b"{}\n",
                 "provenance.unsigned.json": b"{}\n"}
        for name, data in files.items():
            (directory / name).write_bytes(data)
        (directory / "AUDIT-SHA256SUMS").write_text("".join(DELIVERY.sha(data) + "  " + name + "\n"
                                                          for name, data in files.items()))
        return directory, report

    def test_matching_audit_is_bound_to_actual_selected_artifacts(self):
        audit, _ = self.audit_fixture()
        manifest = self.prepare(audit=audit)
        self.assertIn("sbom.spdx.json", manifest["artifacts"])
        packet = json.loads((self.output / "installer-owner-packet.json").read_bytes())
        self.assertEqual(packet["release_audit"], "included-passed-integrity-only")
        self.assertEqual(packet["qualification"], "unrun-by-this-preparation")

    def test_passed_audit_for_other_artifact_is_rejected(self):
        audit, report = self.audit_fixture()
        report["subjects"][0]["digest"]["sha256"] = "f" * 64
        (audit / "release-audit.json").write_bytes(DELIVERY.canonical(report))
        with self.assertRaisesRegex(ValueError, "selected artifact"):
            self.prepare(audit=audit)
        self.assertFalse(self.output.exists())

    def test_version_rejects_non_semver_and_ambiguous_numeric_preview(self):
        for version in ("../outside", "1.2", "01.2.3", "1.2.3-01", "1.2.3+build"):
            with self.subTest(version=version), self.assertRaises(ValueError):
                DELIVERY.version_of({"version": version})


if __name__ == "__main__":
    unittest.main()
