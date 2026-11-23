# Product naming and upgrades

The primary product name is **deckystream**. The owner approved the operational
rename after moving the source to `egohygiene/deckystream`.

| Surface | Primary identity |
| --- | --- |
| Repository and Go module | `github.com/egohygiene/deckystream` |
| CLI and Decky plugin | `deckystream` |
| Standard plugin archive | `deckystream-decky.zip` |
| Fresh XDG app directories | `deckystream` under the configured config/data/state/cache bases |
| New environment variables | `DECKYSTREAM_*` |
| Native capture library | `libgstdeckystreamcapture.so` |
| Native capture element | `deckystreamgamescopesrc` |

## Existing installations

Inspect the installed version, output state and paths before replacing it.
Streaming, recording and replay must be positively stopped; a red streaming dot
alone is insufficient. Close the old managed OBS instance before handing control
to the renamed plugin. Installation, migration and local recording never imply
permission to broadcast.

Fresh installations use the new namespace. Existing validated legacy stores
retain their original paths and shared control-lock inode, so keys, preferences,
recordings and recovery state remain together. Config, data, state, cache and
the isolated Flatpak config participate in namespace selection. If old and new
stores coexist, or a candidate path is linked or foreign-owned, repair is
required; the tool does not guess, merge directories or copy credentials.
Changing XDG base directories is a separate explicit migration.

The old managed OBS profile is recognized only for authenticated observation,
explicit Stop and idle Close. A subsequent launch prepares the primary profile
from the retained settings. Capture and mixer mutations cannot silently convert
an active old profile. The supported replacement flow must retire the old plugin
backend before the new one can control the shared endpoint.

Legacy environment names remain explicit compatibility inputs. New names take
precedence; normal CLI/file/environment precedence and secret redaction still
apply. Loader storage-map activation clears both name families before attaching
a validated context. This is not permission to pass arbitrary environment keys
or trust a different update publisher.

## Historical names

`obsgod` and `OBSGod` remain where they identify a real older installation,
rollback artifact, original issue, source revision, copyright attribution or
immutable receipt. Those records are not rewritten to pretend older builds used
the new name. Original migration/export helpers keep their original-source
contracts. Selected artwork and provenance remain intact.

## Qualification

The rename changes source and packaging identities. Earlier passing receipts do
not qualify its new artifacts. Use the exact candidate, checksum and observations
recorded in [finalization #1](https://github.com/egohygiene/deckystream/issues/1)
for the shared Steam Deck test session. Hardware, provider-viewer, rights and
release gates remain separate from this naming change.
