# Documentation

**[Get started with deckystream →](getting-started.md)**

Install the preview, make an audible local clip, then explicitly start your first
stream. Current testing and release work is tracked in
[finalization #1](https://github.com/egohygiene/deckystream/issues/1).

## Use deckystream

| Task | Guide |
| --- | --- |
| Install, configure and make a first stream | [Getting started](getting-started.md), [Steam Deck guide](steam-deck.md), [first-run dependencies](dependency-setup.md) |
| Set a provider, key or OBS control password | [Destinations and control recovery](stream-destinations.md) |
| Choose a microphone or headset | [Microphone controls](microphone.md) |
| Choose quality and capture settings | [Quality profiles](advanced-profiles.md), [between-game media](idle-media.md) |
| Record, replay and export clips | [Recording and replay](recording-replay.md) |
| Understand status or recover safely | [Stream health](stream-health.md), [runtime recovery](runtime-resilience.md), [support](../SUPPORT.md) |
| Update, uninstall or inspect an older installation | [Steam Deck guide](steam-deck.md#updates-and-recovery), [legacy cleanup](legacy-cleanup-kit.md) |
| Work through the device tests | [Testing booklet](testing-booklet.md), [printable PDF](testing-booklet.pdf), [results template](testing-results-template.md) |

Use the exact installable plugin ZIP and checksums supplied with your selected
candidate. A repository source ZIP is not the plugin. Build/package details live
in the [standard package guide](decky-package.md); historical downloads are not
current installation recommendations.

## CLI and automation

| Task | Guide |
| --- | --- |
| Control an existing OBS instance | [CLI usage](cli-usage.md), [command reference](cli-reference.md) |
| Configure flags, environment and profiles | [Configuration](configuration.md) |
| Build integrations | [Versioned API](api-v1.md), [creator workflows](creator-workflows.md) |
| Inspect CLI distribution | [CLI archives](generic-cli-distribution.md), [native packages](generic-packaging.md) |

The standalone CLI controls an existing OBS instance. It does not install the
managed Steam Deck application, OBS or Decky.

## Build and contribute

Start with [contributing](../CONTRIBUTING.md), [repository instructions](../AGENTS.md)
and [current work](../CONTINUITY.md). Use the pinned tools in the build guide.

| Task | Guide |
| --- | --- |
| Build and validate | [Steam Deck building](steam-deck-building.md), [package contract](decky-package.md), [local CI](local-ci.md) |
| Understand the design | [Architecture](../ARCHITECTURE.md), [vocabulary](../ONTOLOGY.md), [decisions](../DECISIONS.md) |
| Change settings, storage or lifecycle | [Native configuration](native-configuration.md), [Decky storage](decky-storage.md), [runtime correctness](runtime-correctness.md), [cleanup](cleanup-recovery.md) |
| Prepare a release | [Finalization checklist](finalization-checklist.md), [release engineering](release-engineering.md), [brand adoption](migration-brand-packet.md) |
| Maintain repository access | [Main branch protection](main-branch-protection.md) |
| Report a bug or vulnerability | [Support](../SUPPORT.md), [security reporting](../SECURITY.md) |

## Evidence and history

- [Finalization #1](https://github.com/egohygiene/deckystream/issues/1) links the
  current source, automated checks and remaining owner acceptance. A passing CI
  run is not physical Steam Deck or provider-viewer proof.
- [Qualification guide](steam-deck-qualification.md) explains those evidence
  boundaries. The [original criterion ledger](evidence/completion-criteria.json)
  preserves the original acceptance requirements and dependencies.
- [Earlier qualified checkpoint](pre-migration-qualified-checkpoint.md),
  [pre-migration readiness](pretest-readiness.md) and old installer guides retain
  their exact historical revisions and checksums. They do not qualify newer code.
- [Project memorial](../MEMORIAL.md) and [portable tracker history](history/README.md)
  explain the project's origins and preserved records.
- [Selected brand kit](../branding/aurora/README.md) includes ordinary PNGs and
  an offline gallery; [brand review](branding-review.md) records its rights and
  adoption status.

For the primary naming transition and existing installations, read
[product naming and upgrades](product-naming.md).
