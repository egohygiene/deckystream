# deckystream command reference

Generated from the current command tree. Built-in defaults are shown; use `config show` for effective settings. Commands marked JSON keep that format. Other commands retain their existing human output.

## deckystream

deckystream is a command-line remote control for OBS

```text
deckystream [flags]
```

```sh
  deckystream version
  deckystream config show --json
  deckystream stream status --json
```

```text
      --config string               OBS connection config file (env: DECKYSTREAM_CONFIG; default: XDG deckystream/config.json)
      --connection-profile string   Named connection profile (env: DECKYSTREAM_CONNECTION_PROFILE)
  -h, --help                        help for deckystream
      --host string                 OBS host (env: DECKYSTREAM_HOST or legacy OBS_HOST) (default "localhost")
      --no-color                    Disable optional terminal color in verbose diagnostics (also respects NO_COLOR/TERM)
      --password string             OBS password; prefer --password-file or OBS_PASSWORD to avoid shell history
      --password-file string        Private single-line OBS password file; avoids secret command arguments
  -p, --port uint32                 OBS port (env: DECKYSTREAM_PORT or legacy OBS_PORT) (default 4455)
      --verbose                     Write credential-free command/stage diagnostics to stderr
```

## deckystream api

Versioned public OBS API adapter; emits one JSON result, preserves legacy commands

```text
deckystream api
```

```sh
  deckystream api capabilities
  deckystream api snapshot
  deckystream api stream start --approve
```

```text
      --json   Emit versioned JSON (always enabled for this command family) (default true)
```

## deckystream api capabilities

Discover the public contract offline

```text
deckystream api capabilities
```

## deckystream api collection

List or select existing OBS collection settings

```text
deckystream api collection
```

## deckystream api collection list

List existing collection names

```text
deckystream api collection list
```

## deckystream api collection select

Select an existing collection (structural changes require idle outputs)

```text
deckystream api collection select NAME [flags]
```

```text
      --approve   Approve this settings change for this invocation
```

## deckystream api profile

List or select existing OBS profile settings

```text
deckystream api profile
```

## deckystream api profile list

List existing profile names

```text
deckystream api profile list
```

## deckystream api profile select

Select an existing profile (structural changes require idle outputs)

```text
deckystream api profile select NAME [flags]
```

```text
      --approve   Approve this settings change for this invocation
```

## deckystream api recording

Explicitly control local recording output

```text
deckystream api recording
```

## deckystream api recording start

start recording with confirmation

```text
deckystream api recording start [flags]
```

```text
      --approve   Approve this local output action for this invocation
```

## deckystream api recording stop

stop recording with confirmation

```text
deckystream api recording stop [flags]
```

```text
      --approve   Approve this local output action for this invocation
```

## deckystream api replay

Explicitly control local replay output

```text
deckystream api replay
```

## deckystream api replay save

save replay with confirmation

```text
deckystream api replay save [flags]
```

```text
      --approve   Approve this local output action for this invocation
```

## deckystream api replay start

start replay with confirmation

```text
deckystream api replay start [flags]
```

```text
      --approve   Approve this local output action for this invocation
```

## deckystream api replay stop

stop replay with confirmation

```text
deckystream api replay stop [flags]
```

```text
      --approve   Approve this local output action for this invocation
```

## deckystream api scene

List or select existing OBS scene settings

```text
deckystream api scene
```

## deckystream api scene list

List existing scene names

```text
deckystream api scene list
```

## deckystream api scene select

Select an existing scene (structural changes require idle outputs)

```text
deckystream api scene select NAME [flags]
```

```text
      --approve   Approve this settings change for this invocation
```

## deckystream api scene-items

Read or explicitly change a scene item's visibility

```text
deckystream api scene-items
```

## deckystream api scene-items hide

hide a scene item by numeric ID

```text
deckystream api scene-items hide SCENE ID [flags]
```

```text
      --approve   Approve this visibility change for this invocation
```

## deckystream api scene-items list

List scene items with stable IDs

```text
deckystream api scene-items list SCENE
```

## deckystream api scene-items show

show a scene item by numeric ID

```text
deckystream api scene-items show SCENE ID [flags]
```

```text
      --approve   Approve this visibility change for this invocation
```

## deckystream api snapshot

Observe outputs, profiles, collections and scenes

```text
deckystream api snapshot
```

Aliases: status.

## deckystream api stream

Query or explicitly change OBS streaming

```text
deckystream api stream
```

## deckystream api stream start

Explicitly start streaming and confirm observed state

```text
deckystream api stream start [flags]
```

```text
      --approve   Approve this output action for this invocation
```

## deckystream api stream status

Observe OBS stream output; provider reception stays unknown

```text
deckystream api stream status
```

## deckystream api stream stop

Explicitly stop streaming and confirm observed state

```text
deckystream api stream stop [flags]
```

```text
      --approve   Approve this output action for this invocation
```

## deckystream api virtual-camera

Explicitly control local virtual-camera output

```text
deckystream api virtual-camera
```

## deckystream api virtual-camera start

start virtual-camera with confirmation

```text
deckystream api virtual-camera start [flags]
```

```text
      --approve   Approve this local output action for this invocation
```

## deckystream api virtual-camera stop

stop virtual-camera with confirmation

```text
deckystream api virtual-camera stop [flags]
```

```text
      --approve   Approve this local output action for this invocation
```

## deckystream api workflow

Apply an existing declarative workflow; never starts streaming

```text
deckystream api workflow NAME [flags]
```

```text
      --allow-recording       Approve requested local recording
      --allow-replay-buffer   Approve requested replay capture
      --approve               Approve settings for this invocation
```

## deckystream completion

Generate offline shell completions to stdout

```text
deckystream completion [bash|zsh|fish]
```

## deckystream config

Inspect and validate connection configuration without starting OBS

```text
deckystream config
```

## deckystream config path

Print the configured file location, even if its contents are invalid

```text
deckystream config path
```

## deckystream config profiles

List available connection profiles; this does not change OBS profiles

```text
deckystream config profiles [flags]
```

```text
      --json   Print versioned profile names
```

## deckystream config show

Show resolved configuration with credentials redacted (no OBS connection)

```text
deckystream config show [flags]
```

```text
      --json   Print versioned redacted JSON
```

## deckystream config validate

Check the selected configuration and credential reference without connecting

```text
deckystream config validate [flags]
```

Aliases: check.

```text
      --json   Print versioned redacted JSON
```

## deckystream creator

Optional local creator orchestration through the public OBS API

```text
deckystream creator
```

```sh
  deckystream creator plan --profile creator.json
  deckystream creator start --profile creator.json --approve --allow-streaming
  deckystream creator status
```

```text
      --json             Emit versioned JSON (always enabled for this command family) (default true)
      --profile string   Creator profile file (env: DECKYSTREAM_CREATOR_PROFILE; default: XDG deckystream/creator.json)
```

## deckystream creator extensions

Discover local provider/event/content extension boundaries offline

```text
deckystream creator extensions
```

## deckystream creator plan

Review resolved creator intent offline; no secrets are read

```text
deckystream creator plan
```

## deckystream creator start

start the reviewed creator workflow; leaves OBS running

```text
deckystream creator start [flags]
```

```text
      --allow-recording       Approve local recording actions for this invocation
      --allow-replay-buffer   Approve local replay actions for this invocation
      --allow-streaming       Approve streaming output for this invocation
      --approve               Approve reviewed OBS settings for this invocation
```

## deckystream creator status

Observe current OBS state without provider account access

```text
deckystream creator status
```

## deckystream creator stop

stop the reviewed creator workflow; leaves OBS running

```text
deckystream creator stop [flags]
```

```text
      --allow-recording       Approve local recording actions for this invocation
      --allow-replay-buffer   Approve local replay actions for this invocation
      --allow-streaming       Approve streaming output for this invocation
      --approve               Approve reviewed OBS settings for this invocation
```

## deckystream deck

Manage the optional Steam Deck streaming preview (JSON output)

```text
deckystream deck
```

## deckystream deck change-obs-password

Change or generate the local control password from JSON stdin while OBS is closed

```text
deckystream deck change-obs-password
```

## deckystream deck clear-logs

Clear local filtered diagnostic history

```text
deckystream deck clear-logs
```

## deckystream deck configuration

Read non-secret stream settings, defaults and safe edit/close availability

```text
deckystream deck configuration
```

## deckystream deck configure

Save settings and key from JSON stdin, never argv

```text
deckystream deck configure
```

## deckystream deck configure-fields

Merge private stream settings from bounded JSON stdin while managed OBS is closed

```text
deckystream deck configure-fields
```

## deckystream deck connection-info

Read credential-free local OBS connection details

```text
deckystream deck connection-info
```

## deckystream deck doctor

Diagnose installation, capture and OBS

```text
deckystream deck doctor
```

## deckystream deck media

Manage local recording, replay, clips and storage using JSON stdin; never broadcasts

```text
deckystream deck media
```

## deckystream deck mixer

Control managed OBS audio, devices and optional hold-to-talk using JSON stdin

```text
deckystream deck mixer
```

## deckystream deck open-obs

Open the isolated OBS window visibly for Desktop recovery without starting output

```text
deckystream deck open-obs
```

## deckystream deck restart

Close idle managed OBS to apply saved settings

```text
deckystream deck restart
```

## deckystream deck retry-recovery

Retry bounded audio recovery for already-active managed output; never starts output

```text
deckystream deck retry-recovery
```

## deckystream deck set-capture-mode

Choose screen or game video for the next explicit output (JSON stdin)

```text
deckystream deck set-capture-mode
```

## deckystream deck set-idle-media

Import local between-game media with rights acknowledgement using JSON stdin

```text
deckystream deck set-idle-media
```

## deckystream deck start

Capture Gaming Mode and wait for real stream output

```text
deckystream deck start
```

## deckystream deck status

Read live output state without starting OBS

```text
deckystream deck status
```

## deckystream deck stop

Stop streaming and confirm it stopped

```text
deckystream deck stop
```

## deckystream deck stream-health

Read a bounded local OBS health sample; provider reception remains unknown

```text
deckystream deck stream-health
```

## deckystream deck stream-profiles

Preview, validate, save, apply or export stream profiles using JSON stdin

```text
deckystream deck stream-profiles [flags]
```

```text
      --bitrate int           Override JSON/environment profile bitrate for this action
      --capture-mode string   Override JSON/environment profile capture-mode for this action
      --encoder string        Override JSON/environment profile encoder for this action
      --fps int               Override JSON/environment profile fps for this action
      --height int            Override JSON/environment profile height for this action
      --microphone            Override the initial profile microphone default; saved live mixer preferences take precedence
      --width int             Override JSON/environment profile width for this action
```

## deckystream deck support-bundle

Export filtered diagnostic facts without credentials, URLs or private paths

```text
deckystream deck support-bundle
```

## deckystream deck test-connection

Authenticate and read managed OBS without launching or broadcasting

```text
deckystream deck test-connection
```

## deckystream deck test-recording

Save a ten-second local clip without broadcasting

```text
deckystream deck test-recording
```

## deckystream doctor

Diagnose managed Steam Deck installation, OBS and capture (JSON)

```text
deckystream doctor
```

## deckystream help

Help about any command

```text
deckystream help [command]
```

## deckystream label

manage text labels

```text
deckystream label
```

## deckystream label countdown

Update a text label with a cancellable duration countdown (for example 30s)

```text
deckystream label countdown SOURCE DURATION
```

```sh
  deckystream label countdown Countdown 30s
```

## deckystream label text

Changes a text label

```text
deckystream label text SOURCE TEXT...
```

## deckystream profile

manage profiles

```text
deckystream profile
```

## deckystream profile get

Get the current profile

```text
deckystream profile get
```

## deckystream profile list

List all profiles

```text
deckystream profile list
```

## deckystream profile set

Set the current profile

```text
deckystream profile set NAME...
```

## deckystream recording

manage recordings

```text
deckystream recording
```

## deckystream recording pause

manage paused state

```text
deckystream recording pause
```

## deckystream recording pause enable

Pause recording

```text
deckystream recording pause enable
```

## deckystream recording pause resume

Resume recording

```text
deckystream recording pause resume
```

## deckystream recording pause toggle

Pause/resume recording

```text
deckystream recording pause toggle
```

## deckystream recording start

Starts recording

```text
deckystream recording start
```

## deckystream recording status

Reports recording status

```text
deckystream recording status [flags]
```

```text
      --json    Print versioned recording status JSON
      --quiet   Suppress successful status output; errors still fail
```

## deckystream recording stop

Stops recording

```text
deckystream recording stop
```

## deckystream recording toggle

Toggle recording

```text
deckystream recording toggle
```

## deckystream reference

Generate a deterministic offline Markdown command reference

```text
deckystream reference [flags]
```

```text
  -h, --help   help for reference
```

## deckystream replaybuffer

manage replay buffer

```text
deckystream replaybuffer
```

Aliases: replay-buffer.

## deckystream replaybuffer save

Saves replay buffer

```text
deckystream replaybuffer save
```

## deckystream replaybuffer start

Starts replay buffer

```text
deckystream replaybuffer start
```

## deckystream replaybuffer status

Reports replay buffer status

```text
deckystream replaybuffer status
```

## deckystream replaybuffer stop

Stops replay buffer

```text
deckystream replaybuffer stop
```

## deckystream scene

manage scenes

```text
deckystream scene
```

```sh
  deckystream scene list
  deckystream scene set Game
```

## deckystream scene current

Switch program to a different scene

```text
deckystream scene current NAME...
```

Aliases: set.

## deckystream scene get

Get the current scene

```text
deckystream scene get
```

## deckystream scene list

List all scene names

```text
deckystream scene list
```

## deckystream scene preview

Switch preview to a different scene (studio mode must be enabled)

```text
deckystream scene preview NAME...
```

## deckystream scene switch

Switch program or preview in studio mode to a different scene

```text
deckystream scene switch NAME...
```

## deckystream scenecollection

manage scene collections

```text
deckystream scenecollection
```

Aliases: scene-collection.

## deckystream scenecollection get

Get the current scene collection

```text
deckystream scenecollection get
```

## deckystream scenecollection list

List all scene collections

```text
deckystream scenecollection list
```

## deckystream scenecollection set

Set the current scene collection

```text
deckystream scenecollection set NAME...
```

## deckystream sceneitem

manage scene items

```text
deckystream sceneitem
```

Aliases: scene-item.

## deckystream sceneitem center

Horizontally centers a scene-item

```text
deckystream sceneitem center SCENE ITEM...
```

## deckystream sceneitem hide

Hides a scene-item

```text
deckystream sceneitem hide SCENE ITEM...
```

## deckystream sceneitem list

Lists all items of a scene

```text
deckystream sceneitem list SCENE
```

## deckystream sceneitem show

Makes a scene-item visible

```text
deckystream sceneitem show SCENE ITEM...
```

## deckystream sceneitem toggle

Toggles visibility of a scene-item

```text
deckystream sceneitem toggle SCENE ITEM...
```

## deckystream sceneitem visible

Show visibility status of a scene-item

```text
deckystream sceneitem visible SCENE ITEM...
```

## deckystream source

manage sources

```text
deckystream source
```

## deckystream source list

Lists all sources

```text
deckystream source list
```

## deckystream source toggle-mute

Toggles mute

```text
deckystream source toggle-mute NAME...
```

## deckystream stream

manage streams

```text
deckystream stream
```

## deckystream stream start

Starts streaming

```text
deckystream stream start
```

## deckystream stream status

Reports streaming status

```text
deckystream stream status [flags]
```

```text
      --json    Print versioned stream status JSON
      --quiet   Suppress successful status output; errors still fail
```

## deckystream stream stop

Stops streaming

```text
deckystream stream stop
```

## deckystream stream toggle

Toggle streaming

```text
deckystream stream toggle
```

## deckystream studiomode

manage studio mode

```text
deckystream studiomode
```

Aliases: studio-mode.

## deckystream studiomode disable

Disables the studio mode

```text
deckystream studiomode disable
```

## deckystream studiomode enable

Enables the studio mode

```text
deckystream studiomode enable
```

## deckystream studiomode status

Reports studio mode status

```text
deckystream studiomode status
```

## deckystream studiomode toggle

Toggles the studio mode (enable/disable)

```text
deckystream studiomode toggle
```

## deckystream studiomode transition

Transition to program

```text
deckystream studiomode transition
```

## deckystream version

Print build version without connecting to OBS

```text
deckystream version [flags]
```

```text
      --json   Print versioned build JSON
```

## deckystream virtualcam

manage virtual camera

```text
deckystream virtualcam
```

Aliases: virtual-camera.

## deckystream virtualcam start

Starts virtual camera

```text
deckystream virtualcam start
```

## deckystream virtualcam status

Reports virtual camera status

```text
deckystream virtualcam status
```

## deckystream virtualcam stop

Stops virtual camera

```text
deckystream virtualcam stop
```

## deckystream virtualcam toggle

Toggle virtual camera status

```text
deckystream virtualcam toggle
```

## deckystream workflow

Plan or explicitly apply provider-neutral OBS settings; never starts streaming

```text
deckystream workflow
```

## deckystream workflow apply

Apply reviewed settings to confirmed idle OBS; explicit approvals required

```text
deckystream workflow apply [NAME] [flags]
```

```text
      --allow-recording       Also approve local recording when requested by this workflow
      --allow-replay-buffer   Also approve local replay-buffer capture when requested
      --approve               Approve the reviewed settings changes for this invocation
      --dry-run               Show the plan offline without connecting or applying
```

## deckystream workflow list

List declarative workflow profiles without connecting to OBS

```text
deckystream workflow list
```

## deckystream workflow plan

Show resolved workflow intent offline; applies no changes

```text
deckystream workflow plan [NAME]
```
