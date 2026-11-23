# Steam Deck preview qualification

## Current candidate selection

Use the exact successful renamed build recorded in
[finalization #1](https://github.com/egohygiene/deckystream/issues/1), its manifest
and checksums. The operational naming transition requires fresh source/artifact
qualification; an older `obsgod` package is not relabeled as the new plugin.
The [testing booklet](testing-booklet.md) describes our device session and the
[naming contract](product-naming.md) covers existing installations.

The public repository's hosted workflows run. Read their actual conclusions at
the selected revision, including platform, dependency-review and package checks.
The [pre-rename qualification guide](history/steam-deck-qualification-before-primary-rename.md)
retains older candidate counts, pins and account refusals unchanged as history.
No old software receipt is a new source, Steam Deck or provider-viewer pass.

## Historical previews and evidence interpretation

Each [preview release](https://github.com/szmyty/obsgod/releases) carries its exact
source revision in `manifest.json`, artifact hashes in `SHA256SUMS`, and commands,
outcomes and limitations in `qualification.json`. Use that release's receipts;
an earlier passing run does not qualify newer source. This is a hardware preview
and does not establish stable v1 readiness.

## Required evidence

- Go unit/protocol tests, race detection, vet and reachable-vulnerability scan.
- Desktop setup HTTP security and installer safety checks.
- Decky typecheck/build, status-indicator tests and browser rendering checks.
- Reproducible package checksums and a clean-home install from the actual archive.
- Real Linux OBS with synthetic PipeWire video/audio, local recording, local RTMP,
  repeated start/stop, frame dimensions and audio content.
- Real SteamOS / AMD VAAPI / controller / Kick viewer acceptance, explicitly
  unavailable in the cloud runtime and retained under #10.

No user stream key, live provider account or paid resource is used by cloud tests.

## Interpretation

| Environment | Evidence meaning |
| --- | --- |
| Linux x86_64 cloud | Unit/protocol, race, static, installer, browser and native OBS checks can run here. |
| Native OBS container | Real pinned OBS/GStreamer/PipeWire/PulseAudio with synthetic game video, software encoding and local RTMP; record actual versions per run. |
| Simulated Decky host | Actual ZIP frontend and SDK browser imports; loader calls and Steam components are fixtures. |
| Hosted macOS / Windows | Generic CLI builds/tests run on the named hosted runners; they do not qualify the managed Steam Deck runtime. |
| Other cross-build targets | Compilation and archive auditing are separate from native runtime execution. |
| Steam Deck / SteamOS | Unavailable here: actual Flatpak sandbox, Gamescope, AMD VAAPI, audio devices, controller focus and session lifecycle. |
| Kick viewer | Unrun here: user URL/key and real channel picture/audio must be checked on the device. |
| GitHub Actions | Read the current public repository workflow runs at the selected revision; unavailable or skipped jobs are not passes. Local results remain separate. |

The native harness verifies moving, nonblank recorded video, nonblank streamed
video, audio content, repeated start/stop, failed-start cleanup and no unexpected
late connection when a receiver appears. See [reproduction](steam-deck-building.md).
Source repairs were prompted by real integration failures: a first-run wizard,
zero scene scale, preview-dependent capture startup and a transient PipeWire node.

Remaining product acceptance is tracked in
[finalization #1](https://github.com/egohygiene/deckystream/issues/1), with original
criteria and historical statuses preserved. Optional auth research stays in #8.
A source merge, renamed artifact or local harness does not close device/viewer
or stable-release gates.
