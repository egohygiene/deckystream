# Protect main while keeping owner and bot access

Run this from a checkout using your ordinary administrator GitHub CLI login:

```sh
python3 scripts/protect-main.py
python3 scripts/protect-main.py --apply
```

The first command previews the exact ruleset; the second creates and verifies
it. It targets only `egohygiene/deckystream` repository ID `1467389697` and
`refs/heads/main`. Existing unrelated rules are preserved. An identical named
rule is a no-op; a differently configured named rule is preserved and refused.

The active rule prevents deletion, force pushes and direct writes without a
pull request. It requires zero approving reviews and no CI status checks.
Repository admins, the verified ChatGPT Codex Connector app and Dependabot
have an always-bypass exception, including force pushes and deletion. The
assistant acts through its existing user or app credential, not a separate
GitHub user. Bypass does not grant repository write permissions.

Other installed GitHub Apps can be explicitly included:

```sh
python3 scripts/protect-main.py --apply --app exact-installed-app-slug
```

Include additional apps when first creating the rule. If it already exists,
inspect and deliberately edit it in GitHub; the script will not replace it.
There is no generic all-bots or all-future-bots bypass role. Workflow
`GITHUB_TOKEN` permissions are separate from the Codex app's access; the current
artifact-building workflows do not need to push to `main`.

Dependency review needs a separate repository setting. Enable **Dependency
Graph** at <https://github.com/egohygiene/deckystream/settings/security_analysis>,
then rerun the dependency-review jobs. The branch command does not enable it,
modify other security settings or claim any checks passed.
