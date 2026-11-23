# Installer delivery and release preparation

The one-command Desktop Mode entry point is a small, self-contained Python
zipapp, **`deckystream-install.pyz`**. It verifies and downloads a complete
runtime installer, then invokes the existing guarded `install.py`. It does not
implement a second plugin installer, install Decky silently, unlock SteamOS or
start a broadcast. An existing supported Decky Loader and normal Steam session
are required; dependency installation uses the existing consented user-scoped
Flatpak setup.

This route installs the plugin **and the retained Desktop setup, update and
recovery files**. The ordinary `deckystream-decky.zip` remains the direct Decky
installation unit. A GitHub source archive or an outer Actions artifact is not
that plugin ZIP. The complete runtime includes its matching ZIP; a separate
Desktop download is unnecessary when installing the standard ZIP through Decky.

Current work prepares an unpublished candidate. A working public installation
command requires separately approved release assets and a real anonymous
download test. Do not advertise a `latest/download` link before those assets
exist. Actions review artifacts normally require GitHub authentication and do
not prove anonymous delivery.

## One version and source revision

The bootstrap contains its exact clean source revision, SemVer version,
`linux/amd64` platform and fixed `egohygiene/deckystream` repository identity.
Its bundled source inventory covers the entry point, Python modules and license
files. The bootstrap's version and source must match the selected runtime and
delivery manifest. A script from a newer source revision cannot silently install
an older package, even if both belong to the same publisher.

Stable is the default channel and excludes prereleases. Preview selection must
be explicit. A supplied version asserts the zipapp's bundled version; it is not
a repository or arbitrary download override. Resolve the actual release tag's
commit, rather than trusting mutable `target_commitish` metadata. A release with
missing, conflicting or unsupported verification data fails without installing.
No published release, offline access and unsupported session/loader are distinct
failures with a retry or repair action.

The fixed publisher and approved GitHub asset redirect policy are inherited from
the maintained release reader. Environment variables and CLI flags cannot
replace the trusted owner/repository. Checksums obtained from the same publisher
detect changes relative to those published values; they are not an independent
signature or authenticated build attestation.

## Prepare a candidate without publishing

Commit the complete source first and use the pinned
[build tools](steam-deck-building.md). Build the runtime and independently
qualified primary plugin at the **same version and full revision**; see
[standard packaging](decky-package.md) and
[release engineering](release-engineering.md). Keep original build outputs and
receipts intact.

Build the bootstrap into a new absolute directory outside the checkout:

```sh
candidate_parent=$(mktemp -d)
python3 scripts/package-bootstrap.py --version 0.1.0-deck.9 \
  --output "$candidate_parent/bootstrap"
```

The following command is a maintainer template. Replace the primary-build and
audit directory paths with the actual matching outputs, and use the version
selected for that candidate:

```sh
python3 scripts/prepare-installer-release.py \
  --runtime "$PWD/dist/deckystream-deck_0.1.0-deck.9_linux_amd64.tar.gz" \
  --primary /absolute/path/to/qualified-primary/second \
  --bootstrap "$candidate_parent/bootstrap/deckystream-install.pyz" \
  --revision "$(git rev-parse HEAD)" \
  --audit /absolute/path/to/matching-supply-chain-audit \
  --output "$candidate_parent/delivery"
```

`--audit` is optional during preparation. Omitting it records that audit evidence
was not supplied; it does not pass the final audit or relax release requirements.
An audit supplied for different artifact bytes or source is refused. The helper
does not run a full qualification matrix or execute code from an input archive.

The helper checks private/protected filesystem ancestry, exact runtime inventory
and sidecars, every payload checksum, source-bound installer text, the primary
ZIP/build receipt, and equality of the standalone and embedded plugin ZIPs. It
compares the bootstrap's complete payload against the maintained packager at
the selected clean source. Unexpected files, links, duplicate paths, mismatched
versions, source changes during preparation and existing output directories
refuse instead of overwriting a previous candidate.

The output directory is new and private, with these delivery assets:

| Asset | Purpose |
| --- | --- |
| `deckystream-install.pyz` | Complete source-bound bootstrap; Python standard library only |
| `deckystream-deck_VERSION_linux_amd64.tar.gz` | Existing complete guarded runtime installer and matching embedded plugin |
| `deckystream-decky.zip` | Independently built, byte-identical standard plugin |
| `manifest.json` | Unchanged runtime payload inventory |
| `build-receipt.json` | Primary plugin build identity and actual archive hash |
| `SHA256SUMS` | Compatible union for runtime manifest/archive and standard ZIP; duplicate names cannot hide differing bytes |
| `deckystream-source_VERSION.tar.gz` | Deterministic source archive of the selected Git commit |
| `LICENSE`, `THIRD_PARTY_NOTICES.md` | Retained source license and runtime dependency notices |
| `release-notes.md` | Unpublished candidate notes and explicit remaining gates |
| `installer-owner-packet.json` | Candidate identity, preparation scope and owner/device/publication actions |
| `INSTALL-COMMAND.txt` | Concrete one-command launcher pinned to this zipapp's real version, length and SHA256; requires approved assets to exist |
| `installer-manifest.json` | Version/source/platform binding and every staged asset's size/SHA256 |
| `INSTALLER-SHA256SUMS` | Delivery manifest and all staged assets, excluding this checksum list itself |
| Optional audit files | Matching release audit, SPDX inventory and unsigned provenance with their checksum list |

The additive installer manifest uses schema version 1:

```json
{
  "schema_version": 1,
  "repository": "egohygiene/deckystream",
  "version": "0.1.0-deck.9",
  "revision": "FULL_40_CHARACTER_LOWERCASE_GIT_SHA",
  "platform": "linux/amd64",
  "dirty": false,
  "unsigned": true,
  "artifacts": {
    "deckystream-install.pyz": {"size": 12345, "sha256": "FULL_SHA256"}
  }
}
```

The example hashes and size are placeholders, not release metadata. Actual
`artifacts` is the exact preparation inventory; it excludes the manifest itself
and `INSTALLER-SHA256SUMS` to avoid a circular hash. The checksum list covers the
manifest. The existing runtime and plugin metadata contracts are preserved.

Use the actual prepared zipapp with its local delivery directory for offline
verification or controlled installation. Local-package results do not prove the
real public download URL, Steam Deck behavior or provider reception.

## Approval and public verification

[Finalization #1](https://github.com/egohygiene/deckystream/issues/1) owns the
full original acceptance, source/rights facts, responsible publisher/contact,
signing or deliberately unsigned policy, device/provider tests and final release
decision. Preparation and CI upload do not publish a release or deploy a site.
The source archive is not a replacement for the separate complete legacy
Git/tracker/release recovery archive.

Before approval, review exact revision/version/artifacts/hashes, candidate
qualification, rights/notices, proposed destinations and rollback evidence.
Support contacts and lifetime must reflect actual owner commitments. This
preparation does not invent them. A deliberately unsigned preview must disclose
its verification limits and receive the same concrete publication approval.

After approved publication, download anonymously from the actual same-tag
GitHub release, verify the downloaded bytes against the reviewed candidate,
and run the documented installation/upgrade/recovery journey. Publish the exact
versioned zipapp URL and its independently reviewed SHA256 in the one-command
launcher; download the complete bounded zipapp before checking or executing it.
The prepared `INSTALL-COMMAND.txt` implements that launcher: it permits only
the fixed release URL and one official GitHub release-asset CDN redirect,
checks the exact length and hash, stages privately under protected `/tmp`
ancestry, and restores terminal input before executing the zipapp. This preserves
interactive dependency consent when the command itself was supplied by heredoc.
Keep the explicit preview opt-in for prerelease builds. No maintainer GitHub
credentials, Go/npm or Docker should be required on the user's Deck.

The work is split into [bootstrap #17](https://github.com/egohygiene/deckystream/issues/17),
[delivery #18](https://github.com/egohygiene/deckystream/issues/18) and
[qualification #19](https://github.com/egohygiene/deckystream/issues/19).
Publication depends on the applicable **pre-publication** checks in #19, not its
complete closure when that same issue still contains a post-publication smoke.
If publication remains deferred, record that live public path as unrun.
Close each issue against its actual evidence; source merging alone is
insufficient.
