package commands

import "github.com/muesli/coral"

// Preserve canonical commands while supplying discoverable aliases and precise
// argument validation across the legacy tree. New commands retain explicit Args.
func auditCommandUsage(root *coral.Command) {
	root.Example = "  deckystream version\n  deckystream config show --json\n  deckystream stream status --json"
	var walk func(*coral.Command)
	walk = func(command *coral.Command) {
		switch command.CommandPath() {
		case "deckystream scene":
			command.Example = "  deckystream scene list\n  deckystream scene set Game"
		case "deckystream scene current":
			command.Aliases = []string{"set"}
			command.Use = "current NAME..."
			command.Args = coral.MinimumNArgs(1)
		case "deckystream scene preview", "deckystream scene switch", "deckystream profile set", "deckystream scenecollection set":
			command.Use = command.Name() + " NAME..."
			command.Args = coral.MinimumNArgs(1)
		case "deckystream scenecollection":
			command.Aliases = []string{"scene-collection"}
		case "deckystream sceneitem":
			command.Aliases = []string{"scene-item"}
		case "deckystream replaybuffer":
			command.Aliases = []string{"replay-buffer"}
		case "deckystream virtualcam":
			command.Aliases = []string{"virtual-camera"}
		case "deckystream studiomode":
			command.Aliases = []string{"studio-mode"}
		case "deckystream label text":
			command.Use = "text SOURCE TEXT..."
			command.Args = coral.MinimumNArgs(2)
		case "deckystream label countdown":
			command.Use = "countdown SOURCE DURATION"
			command.Args = coral.ExactArgs(2)
			command.Example = "  deckystream label countdown Countdown 30s"
			command.Short = "Update a text label with a cancellable duration countdown (for example 30s)"
		case "deckystream source toggle-mute":
			command.Use = "toggle-mute NAME..."
			command.Args = coral.MinimumNArgs(1)
		case "deckystream sceneitem list":
			command.Use = "list SCENE"
			command.Args = coral.ExactArgs(1)
		case "deckystream sceneitem toggle", "deckystream sceneitem show", "deckystream sceneitem hide", "deckystream sceneitem visible", "deckystream sceneitem center":
			command.Use = command.Name() + " SCENE ITEM..."
			command.Args = coral.MinimumNArgs(2)
		}
		if command.Runnable() && command.Args == nil {
			command.Args = coral.NoArgs
		}
		for _, child := range command.Commands() {
			walk(child)
		}
	}
	walk(root)
}
