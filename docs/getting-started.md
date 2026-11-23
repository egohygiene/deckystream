# Get started with deckystream

Start with a local clip. Once picture and sound look right, choose your capture
mode and explicitly go live.

This is a **development preview**. The first stable release and real Steam
Deck/provider acceptance are tracked in
[finalization #1](https://github.com/egohygiene/deckystream/issues/1). Automated
checks apply to their exact source revision; they do not replace the device tests.

## 1. Choose the right build

You need SteamOS on a Steam Deck and [Decky Loader](https://decky.xyz/).
Decky appears in Gaming Mode's **••• Quick Access menu**, not as a normal Desktop
application. OBS 28+ includes its WebSocket server; a second WebSocket plugin is
unnecessary.

Use a candidate supplied for your testing session, or open a successful
[Steam Deck candidate workflow](https://github.com/egohygiene/deckystream/actions/workflows/steam-deck.yml)
for the source you intend to try. Download its candidate artifact and extract
the bundle; GitHub may require signing in to download CI artifacts.

Keep the installable **`deckystream-decky.zip`**, matching `SHA256SUMS`, manifest
and source revision together. The outer CI artifact ZIP and GitHub's source-code
ZIP are not installable Decky plugins. Follow the selected candidate's installation
instructions; an authenticated CI artifact URL is not a public plugin download URL.
If your candidate includes an optional Desktop installer archive, extract the
whole archive before running its installer.

The [one-command Desktop bootstrap](installer-delivery.md) is being prepared
with verified runtime delivery and explicit dependency consent. A supplied local
review bundle can be verified offline; its public command becomes usable only
after the matching release assets are approved and published. Do not substitute
a source archive or an unrelated installer version.

In Desktop Mode, verify the supplied checksums from their containing folder:

```sh
sha256sum --check SHA256SUMS
```

Stop streaming, recording and replay before replacing an installation. Preserve
existing settings and media; do not delete plugin or OBS folders to rename them.
Follow the [update and recovery guide](steam-deck.md#updates-and-recovery) when
an older installation cannot confirm that output is idle.

## 2. Finish setup in Gaming Mode

1. Install the exact verified plugin using the candidate's Decky installation
   flow, then open **••• → Decky → deckystream**.
2. Review any missing OBS Studio/capture dependencies. Choose **Install** to
   approve the listed user-scoped Flatpaks, or **Later** to postpone. Declining
   does not start a download or a broadcast; you can return to setup later.
3. In **Stream destination**, choose your provider and save its server and
   private stream key. **STEAM + X** opens the keyboard. A saved key is not
   read back into the panel.

Manual keys work with Kick, Twitch, YouTube and custom RTMP(S) destinations.
Provider/phone login is [separate research](https://github.com/egohygiene/deckystream/issues/8).
The optional Desktop Setup page is available for advanced settings; do not share
its private local URL. See [destinations and password recovery](stream-destinations.md).

## 3. Check a local clip

Choose the intended picture and audio, then make a **10-second test clip**.
It records locally and does not broadcast. A stopped streaming indicator during
that clip is normal.

Play the saved clip and confirm moving video, game sound and any microphone you
intend to use. In Desktop Mode, open the save location shown by deckystream.
Use the [microphone guide](microphone.md) for headset selection, mute, gain,
meters and focused-panel hold-to-talk.

For **game-only** video, select an intentional between-game screen for when no
verified game capture is available. It must not silently become desktop capture.
Game-only video does not isolate system audio per app.

## 4. Go live deliberately

Select **Start streaming**, then check your channel from another device. Verify
both picture and sound. A healthy OBS output indicator is not proof that the
provider received audible video.

Use **Stop streaming** when output is active, or **Cancel operation** during a
start. Status updates automatically; **Refresh status** remains available when
needed. If output is unknown, use the named recovery action and inspect OBS and
the channel before another install, replacement or removal.

## Next steps

- [Quality and profiles](advanced-profiles.md), [between-game media](idle-media.md),
  [recordings and replay](recording-replay.md).
- [Diagnostic console and support](../SUPPORT.md), [runtime recovery](runtime-resilience.md).
- [Guided testing booklet](testing-booklet.md) for the full step-by-step device session.
- [Steam Deck guide](steam-deck.md) for updates, optional Desktop installation,
  uninstall/reset and scoped cleanup. Shared OBS and unrelated plugins are separate.
