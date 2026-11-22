//go:build linux

package naming

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func writeMetadata(t *testing.T, path string, value map[string]any) {
	t.Helper()
	data, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, data, 0o600); err != nil {
		t.Fatal(err)
	}
}

func legacyFixture(t *testing.T) (string, string) {
	t.Helper()
	home := t.TempDir()
	plugin := filepath.Join(home, "homebrew/plugins/obsgod")
	if err := os.MkdirAll(plugin, 0o700); err != nil {
		t.Fatal(err)
	}
	// Real plugin.json has no version. Package metadata owns that field.
	writeMetadata(t, filepath.Join(plugin, "plugin.json"), map[string]any{"name": "OBSGod", "api_version": 1})
	writeMetadata(t, filepath.Join(plugin, "package.json"), map[string]any{"name": "obsgod", "version": "0.1.0-deck.9"})
	return home, plugin
}

func TestLegacyPluginMarkerIsReadOnlyAndUsesAuthoritativePackageVersion(t *testing.T) {
	home := t.TempDir()
	if found, err := LegacyPluginPresent(home, ""); found || err != nil {
		t.Fatal("a missing old plugin is not a migration marker", found, err)
	}
	if _, err := os.Lstat(filepath.Join(home, "homebrew")); !os.IsNotExist(err) {
		t.Fatal("read-only detection created a Decky root")
	}
	home, plugin := legacyFixture(t)
	before, _ := os.Stat(plugin)
	if found, err := LegacyPluginPresent(home, ""); !found || err != nil {
		t.Fatal("valid old plugin was not recognized", found, err)
	}
	after, _ := os.Stat(plugin)
	if !os.SameFile(before, after) {
		t.Fatal("read-only detection changed the plugin inode")
	}
	writeMetadata(t, filepath.Join(plugin, "package.json"), map[string]any{"name": "obsgod-decky", "version": "0.1.0-deck.3"})
	if found, err := LegacyPluginPresent(home, filepath.Join(home, "homebrew")); !found || err != nil {
		t.Fatal("old development package name must remain supported", found, err)
	}
	alias := filepath.Join(t.TempDir(), "home-alias")
	if err := os.Symlink(home, alias); err != nil {
		t.Fatal(err)
	}
	if found, err := LegacyPluginPresent(alias, filepath.Join(alias, "homebrew")); !found || err != nil {
		t.Fatal("trusted HOME alias must keep the same plugin marker", found, err)
	}
}

func TestMalformedOccupiedLegacySlotsFailClosed(t *testing.T) {
	for _, change := range []string{"plugin-name", "package-name", "version", "missing-version", "oversize", "symlink-file", "hardlink-file", "writable-file", "writable-parent", "symlink-slot"} {
		t.Run(change, func(t *testing.T) {
			home, plugin := legacyFixture(t)
			metadata := filepath.Join(plugin, "package.json")
			var err error
			switch change {
			case "plugin-name":
				writeMetadata(t, filepath.Join(plugin, "plugin.json"), map[string]any{"name": "Other"})
			case "package-name":
				writeMetadata(t, metadata, map[string]any{"name": "another-plugin", "version": "1.0.0"})
			case "version":
				writeMetadata(t, metadata, map[string]any{"name": "obsgod", "version": "private-marker invalid"})
			case "missing-version":
				writeMetadata(t, metadata, map[string]any{"name": "obsgod"})
			case "oversize":
				err = os.WriteFile(metadata, []byte(strings.Repeat(" ", 65537)), 0o600)
			case "symlink-file":
				target := filepath.Join(home, "metadata.json")
				err = os.Rename(metadata, target)
				if err == nil {
					err = os.Symlink(target, metadata)
				}
			case "hardlink-file":
				err = os.Link(metadata, filepath.Join(home, "metadata-link.json"))
			case "writable-file":
				err = os.Chmod(metadata, 0o666)
			case "writable-parent":
				err = os.Chmod(filepath.Dir(plugin), 0o777)
			case "symlink-slot":
				target := filepath.Join(home, "saved-plugin")
				err = os.Rename(plugin, target)
				if err == nil {
					err = os.Symlink(target, plugin)
				}
			}
			if err != nil {
				t.Fatal(err)
			}
			if found, err := LegacyPluginPresent(home, ""); found || err == nil || strings.Contains(err.Error(), "private-marker") {
				t.Fatal("invalid occupied legacy slot must be an error without private metadata", found, err)
			}
		})
	}
}

func TestLegacyPluginRootCannotEscapeHome(t *testing.T) {
	home, _ := legacyFixture(t)
	if found, err := LegacyPluginPresent(home, t.TempDir()); found || err == nil {
		t.Fatal("external Decky root must not authorize a migration", found, err)
	}
}
