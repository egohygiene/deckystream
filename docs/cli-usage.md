# Original remote OBS CLI usage

The stable executable remains `deckystream`. See [configuration](configuration.md)
for the development candidate’s layered settings and machine output.

New reusable automation should use the versioned [public API and JSON command
family](api-v1.md). The compatible commands below retain their original
acknowledgement/output behavior. Optional [creator workflows](creator-workflows.md)
compose the public API without provider-specific behavior in the OBS core.

## Usage

All commands support the following flags:

- `--host`: which OBS instance to connect to
- `--port`: port to connect to
- `--password`: password used for authentication

### Streams

Change the streaming state:

```
deckystream stream start
deckystream stream stop
deckystream stream toggle
```

Display streaming status:

```
deckystream stream status
```

### Recordings

Change the recording state:

```
deckystream recording start
deckystream recording stop
deckystream recording toggle
```

Pause or resume a recording:

```
deckystream recording pause enable
deckystream recording pause resume
deckystream recording pause toggle
```

Display recording status:

```
deckystream recording status
```

### Scenes

List all scene names:

```
deckystream scene list
```

Show the current scene name:

```
deckystream scene get
```

Switch program to a scene:

```
deckystream scene current <scene>
```

Switch preview to a scene (studio mode must be enabled):

```
deckystream scene preview <scene>
```

Switch program (studio mode disabled) or preview (studio mode enabled) to a scene:

```
deckystream scene switch <scene>
```

### Scene Collections

List all scene collections:

```
deckystream scenecollection list
```

Show the current scene collection:

```
deckystream scenecollection get
```

Switch to a scene collection:

```
deckystream scenecollection set <scenecollection>
```

### Scene Items

List all items of a scene:

```
deckystream sceneitem list <scene>
```

Change the visibility of a scene-item:

```
deckystream sceneitem show <scene> <item>
deckystream sceneitem hide <scene> <item>
deckystream sceneitem toggle <scene> <item>
```

Display the visibility of a scene-item:

```
deckystream sceneitem visible <scene> <item>
```

Center a scene-item horizontally:

```
deckystream sceneitem center <scene> <item>
```

### Labels

Change a text label:

```
deckystream label text <label> <text>
```

Trigger a countdown and continuously update a label with the remaining time:

```
deckystream label countdown <label> <duration>
```

### Sources

List special sources:

```
deckystream source list
```

Toggle mute status of a source:

```
deckystream source toggle-mute <source>
```

### Studio Mode

Enable or disable Studio Mode:

```
deckystream studiomode enable
deckystream studiomode disable
deckystream studiomode toggle
```

Display studio mode status:

```
deckystream studiomode status
```

Transition to program (when the studio mode is enabled):

```
deckystream studiomode transition
```

### Profiles

List all profiles:

```
deckystream profile list
```

Show the current profile:

```
deckystream profile get
```

Switch to a profile:

```
deckystream profile set <profile>
```

### Replay Buffer

Change the replay buffer state:

```
deckystream replaybuffer start
deckystream replaybuffer stop
```

Save the replay buffer:

```
deckystream replaybuffer save
```

Display replay buffer status:

```
deckystream replaybuffer status
```

### Virtual Camera

Change the virtual camera state:

```
deckystream virtualcam start
deckystream virtualcam stop
deckystream virtualcam toggle
```

Display virtual camera status:

```
deckystream virtualcam status
```
