#!/usr/bin/env python3
"""Preview/create main protection with explicit owner and installed-app bypass.

Default is read-only. --apply creates one named rule only; an identical rule is
a no-op and differing existing rules are never weakened. --app adds one exact
installed GitHub App slug. Future bots are not automatically trusted. Bypass
does not grant repository permissions, and ordinary workflow GITHUB_TOKENs do
not inherit another app's bypass. Current workflows need no direct-push bypass.
"""
import argparse
import json
import subprocess

REPOSITORY = "egohygiene/deckystream"
REPOSITORY_ID = 1467389697
NAME = "deckystream-main-owner-and-bots"
DEFAULT_APPS = ("chatgpt-codex-connector", "dependabot")


def api(method, path, body=None):
    command = ["gh", "api", "--hostname", "github.com", "--method", method, path]
    if body is not None:
        command += ["--input", "-"]
    result = subprocess.run(command, input=json.dumps(body).encode() if body is not None else None,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    if result.returncode:
        raise SystemExit("GitHub refused a request. Run with your normal administrator gh login; no token is needed in this script. Existing rules are preserved.")
    return json.loads(result.stdout)


def desired(actors):
    return {"name": NAME, "target": "branch", "enforcement": "active",
            "conditions": {"ref_name": {"include": ["refs/heads/main"], "exclude": []}},
            "bypass_actors": actors,
            "rules": [{"type": "deletion"}, {"type": "non_fast_forward"},
                      {"type": "pull_request", "parameters": {
                          "required_approving_review_count": 0,
                          "dismiss_stale_reviews_on_push": False,
                          "require_code_owner_review": False,
                          "require_last_push_approval": False,
                          "required_review_thread_resolution": False}}]}


def pages(path, key=None):
    result = []
    for page in range(1, 101):
        value = api("GET", path + "?per_page=100&page=" + str(page))
        rows = value[key] if key else value
        if not isinstance(rows, list):
            raise SystemExit("Unsupported GitHub list response; no rule writes attempted.")
        result.extend(rows)
        if len(rows) < 100:
            return result
    raise SystemExit("Repository list exceeded the bounded scan; inspect in GitHub.")


def equivalent(actual, expected):
    """Ignore response metadata/defaulted fields, never ignore extra rules/actors."""
    def contains(a, e):
        if isinstance(e, dict):
            return isinstance(a, dict) and all(k in a and contains(a[k], v) for k, v in e.items())
        if isinstance(e, list):
            return (isinstance(a, list) and len(a) == len(e)
                    and all(any(contains(x, y) for x in a) for y in e))
        return a == e
    return contains(actual, expected)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="create the displayed rule; default is read-only preview")
    parser.add_argument("--app", action="append", default=[], help="additional installed GitHub App slug to allow; repeatable")
    args = parser.parse_args(argv)
    repository = api("GET", "/repos/" + REPOSITORY)
    if (repository.get("id") != REPOSITORY_ID or repository.get("full_name") != REPOSITORY
            or repository.get("default_branch") != "main" or repository.get("archived") is not False
            or repository.get("permissions", {}).get("admin") is not True):
        raise SystemExit("Exact repository/main/admin check failed; no rules changed.")
    # This is the built-in repository administrator role. The connector's
    # existing credential acts as this user OR as its named installed app.
    actors = [{"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}]
    apps = list(dict.fromkeys((*DEFAULT_APPS, *args.app)))
    installations = pages("/user/installations", "installations")
    for slug in apps:
        if not slug or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in slug):
            raise SystemExit("Use an exact lowercase GitHub App slug; no rules changed.")
        app = api("GET", "/apps/" + slug)
        if app.get("slug") != slug or type(app.get("id")) is not int:
            raise SystemExit("App identity could not be verified; no rules changed.")
        # Dependabot is built in, so it need not appear as a user installation.
        if slug != "dependabot":
            available = False
            for installation in installations:
                if (installation.get("app_id") != app["id"]
                        or installation.get("account", {}).get("login") != "egohygiene"):
                    continue
                if installation.get("repository_selection") == "all":
                    available = True
                    break
                repos = pages("/user/installations/" + str(installation["id"]) + "/repositories", "repositories")
                if any(r.get("id") == REPOSITORY_ID for r in repos):
                    available = True
                    break
            if not available:
                raise SystemExit("Requested app is not visible as installed for this repository; no rules changed.")
        actors.append({"actor_id": app["id"], "actor_type": "Integration", "bypass_mode": "always"})
    payload = desired(actors)
    current = pages("/repos/" + REPOSITORY + "/rulesets")
    matching = [r for r in current if r.get("name") == NAME]
    if len(matching) > 1:
        raise SystemExit("Multiple matching rules exist; inspect them in GitHub. No rules changed.")
    if matching:
        rule = matching[0]
        if rule.get("source_type") != "Repository" or rule.get("source") != REPOSITORY:
            raise SystemExit("A matching inherited rule exists; no rules changed.")
        detail = api("GET", "/repos/" + REPOSITORY + "/rulesets/" + str(rule["id"]))
        if equivalent(detail, payload):
            print("The exact main protection rule already exists; nothing changed.")
            return
        raise SystemExit("The named rule already has different settings. Inspect it in GitHub; this script will not weaken or replace it.")
    print(json.dumps(payload, indent=2))
    if not args.apply:
        print("Read-only preview. Add --apply to create this rule.")
        return
    result = api("POST", "/repos/" + REPOSITORY + "/rulesets", payload)
    if not equivalent(result, payload) or type(result.get("id")) is not int:
        raise SystemExit("Creation response needs inspection in GitHub; do not blindly retry.")
    actual = api("GET", "/repos/" + REPOSITORY + "/rulesets/" + str(result["id"]))
    if not equivalent(actual, payload):
        raise SystemExit("Saved rule needs inspection in GitHub; no automatic replacement or deletion.")
    print("Verified main protection: https://github.com/" + REPOSITORY + "/settings/rules/" + str(result["id"]))


if __name__ == "__main__":
    main()
