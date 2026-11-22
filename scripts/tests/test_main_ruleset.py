"""Owner-run ruleset safeguards; GitHub reads/writes are fixtures, never live."""
import contextlib
import copy
import importlib.util
import io
from pathlib import Path
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("protect_main", ROOT / "scripts/protect-main.py")
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class GitHub:
    def __init__(self):
        self.calls = []
        self.repository = {"id": M.REPOSITORY_ID, "full_name": M.REPOSITORY,
                           "default_branch": "main", "archived": False,
                           "permissions": {"admin": True}}
        self.apps = {"chatgpt-codex-connector": 1144995, "dependabot": 29110,
                     "another-installed-app": 123, "github-actions": 15368}
        self.installations = [{"id": 1, "app_id": 1144995,
                               "account": {"login": "egohygiene"}, "repository_selection": "all"}]
        self.rulesets = [{"id": 42, "name": "unrelated stronger rule", "source_type": "Repository",
                          "source": M.REPOSITORY}]
        self.detail = None
        self.selected_repositories = []
        self.saved = None

    def request(self, method, path, body=None):
        self.calls.append((method, path, copy.deepcopy(body)))
        if path == "/repos/" + M.REPOSITORY:
            return copy.deepcopy(self.repository)
        if path.startswith("/user/installations?"):
            return {"installations": copy.deepcopy(self.installations)}
        if path.startswith("/user/installations/1/repositories?"):
            return {"repositories": copy.deepcopy(self.selected_repositories)}
        if path.startswith("/apps/"):
            slug = path.rsplit("/", 1)[-1]
            return {"slug": slug, "id": self.apps[slug]}
        if path.startswith("/repos/" + M.REPOSITORY + "/rulesets?"):
            return copy.deepcopy(self.rulesets)
        if path.endswith("/rulesets/7"):
            return copy.deepcopy(self.detail or {**self.saved, "id": 7})
        if method == "POST" and path.endswith("/rulesets"):
            self.saved = copy.deepcopy(body)
            return {**body, "id": 7}
        raise AssertionError((method, path))

    def own_rule(self, changed=False):
        self.rulesets.append({"id": 7, "name": M.NAME, "source_type": "Repository", "source": M.REPOSITORY})
        self.detail = {**M.desired([
            {"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"},
            {"actor_id": 1144995, "actor_type": "Integration", "bypass_mode": "always"},
            {"actor_id": 29110, "actor_type": "Integration", "bypass_mode": "always"}]), "id": 7}
        if changed:
            self.detail["rules"].append({"type": "required_signatures"})


class MainRuleset(unittest.TestCase):
    def run_script(self, api, arguments):
        output = io.StringIO()
        with patch.object(M, "api", side_effect=api.request), contextlib.redirect_stdout(output):
            M.main(arguments)
        return output.getvalue()

    def assert_read_only(self, api):
        self.assertTrue(api.calls)
        self.assertTrue(all(method == "GET" for method, _, _ in api.calls))

    def test_default_preview_is_read_only_and_targets_main_with_explicit_bypass(self):
        api = GitHub()
        output = self.run_script(api, [])
        self.assert_read_only(api)
        self.assertIn('"include": [\n        "refs/heads/main"', output)
        self.assertIn('"required_approving_review_count": 0', output)
        self.assertIn("Read-only preview", output)
        self.assertIsNone(api.saved)

    def test_apply_creates_exactly_one_own_rule_then_reads_it_back(self):
        api = GitHub()
        unrelated = copy.deepcopy(api.rulesets)
        output = self.run_script(api, ["--apply"])
        mutations = [c for c in api.calls if c[0] != "GET"]
        self.assertEqual(len(mutations), 1)
        self.assertEqual(mutations[0][:2], ("POST", "/repos/" + M.REPOSITORY + "/rulesets"))
        self.assertEqual(api.calls[-1][:2], ("GET", "/repos/" + M.REPOSITORY + "/rulesets/7"))
        self.assertEqual(api.rulesets, unrelated)
        self.assertEqual({r["type"] for r in api.saved["rules"]}, {"deletion", "non_fast_forward", "pull_request"})
        self.assertEqual({a["actor_id"] for a in api.saved["bypass_actors"]}, {5, 1144995, 29110})
        self.assertIn("Verified main protection", output)

    def test_identical_existing_rule_is_noop_even_with_apply(self):
        api = GitHub()
        api.own_rule()
        output = self.run_script(api, ["--apply"])
        self.assert_read_only(api)
        self.assertIn("already exists; nothing changed", output)

    def test_existing_stronger_rule_is_preserved_and_refused(self):
        api = GitHub()
        api.own_rule(changed=True)
        original = copy.deepcopy(api.detail)
        with self.assertRaisesRegex(SystemExit, "will not weaken or replace"):
            self.run_script(api, ["--apply"])
        self.assert_read_only(api)
        self.assertEqual(api.detail, original)

    def test_inherited_matching_rule_is_never_replaced(self):
        api = GitHub()
        api.own_rule()
        api.rulesets[-1]["source_type"] = "Organization"
        with self.assertRaisesRegex(SystemExit, "inherited"):
            self.run_script(api, ["--apply"])
        self.assert_read_only(api)

    def test_wrong_repository_or_nonadmin_cannot_write(self):
        for changed in ({"id": 1}, {"default_branch": "master"}, {"permissions": {"admin": False}}):
            with self.subTest(changed=changed):
                api = GitHub()
                api.repository.update(changed)
                with self.assertRaisesRegex(SystemExit, "repository/main/admin check failed"):
                    self.run_script(api, ["--apply"])
                self.assert_read_only(api)

    def test_additional_installed_app_is_explicit_and_repeated_slug_deduplicated(self):
        api = GitHub()
        api.installations.append({"id": 2, "app_id": 123, "account": {"login": "egohygiene"},
                                  "repository_selection": "all"})
        self.run_script(api, ["--apply", "--app", "another-installed-app", "--app", "another-installed-app"])
        self.assertEqual([a["actor_id"] for a in api.saved["bypass_actors"]].count(123), 1)
        self.assertNotIn(15368, {a["actor_id"] for a in api.saved["bypass_actors"]})

    def test_known_public_app_without_repository_installation_cannot_gain_bypass(self):
        api = GitHub()
        with self.assertRaisesRegex(SystemExit, "not visible as installed for this repository"):
            self.run_script(api, ["--apply", "--app", "github-actions"])
        self.assert_read_only(api)

    def test_selected_installation_requires_this_exact_repository(self):
        api = GitHub()
        api.installations[0]["repository_selection"] = "selected"
        api.selected_repositories = [{"id": 17}]
        with self.assertRaisesRegex(SystemExit, "not visible as installed for this repository"):
            self.run_script(api, ["--apply"])
        self.assert_read_only(api)


if __name__ == "__main__":
    unittest.main()
