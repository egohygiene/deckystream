package config

import (
	"os"
	"path/filepath"
	"runtime"
	"testing"
)

func allowLegacyEnvironment(t *testing.T) {
	t.Helper()
	for current := range legacyEnvironment {
		t.Setenv(current, "")
		if err := os.Unsetenv(current); err != nil {
			t.Fatal(err)
		}
	}
}

func TestRenamedEnvironmentRetainsExplicitLegacyAliasesAndCanonicalPrecedence(t *testing.T) {
	root := isolateEnvironment(t)
	t.Setenv("OBSGOD_UNREVIEWED_OPTION", "not-an-application-option")
	if _, present := lookupEnvironment("DECKYSTREAM_UNREVIEWED_OPTION"); present {
		t.Fatal("unrecognized old-prefix variables must not gain implicit authority")
	}
	path := writeConfig(t, root, `{"version":1,"connection":{"host":"file.example"}}`)
	allowLegacyEnvironment(t)
	t.Setenv("OBSGOD_HOST", "old.example")
	t.Setenv("OBSGOD_PORT", "4458")
	t.Setenv("OBSGOD_PASSWORD", "fixture-legacy-secret")
	t.Setenv("OBS_HOST", "older.example")
	t.Setenv("OBS_PASSWORD", "fixture-older-secret")
	resolved, err := Resolve(Config{Host: "localhost", Port: 4455}, Options{Path: path})
	if err != nil || resolved.Config.Host != "old.example" || resolved.Config.Port != 4458 || resolved.Config.Password != "fixture-legacy-secret" {
		t.Fatal("legacy environment did not retain its existing configuration authority", err)
	}
	t.Setenv("DECKYSTREAM_HOST", "current.example")
	t.Setenv("DECKYSTREAM_PORT", "4459")
	t.Setenv("DECKYSTREAM_PASSWORD", "")
	resolved, err = Resolve(Config{Host: "localhost", Port: 4455}, Options{Path: path})
	if err != nil || resolved.Config.Host != "current.example" || resolved.Config.Port != 4459 || resolved.Config.Password != "" {
		t.Fatal("current variables must override legacy aliases, including an explicitly empty password", err)
	}
	oldPath := filepath.Join(root, "old-explicit.json")
	t.Setenv("OBSGOD_CONFIG", oldPath)
	if err := os.Unsetenv("DECKYSTREAM_CONFIG"); err != nil {
		t.Fatal(err)
	}
	if got, required, err := ConfigPath(""); err != nil || got != oldPath || !required {
		t.Fatal("legacy explicit config path was ignored", err)
	}
	t.Setenv("DECKYSTREAM_CONFIG", path)
	if got, required, err := ConfigPath(""); err != nil || got != path || !required {
		t.Fatal("current explicit config path did not win", err)
	}
}

func TestGenericDefaultNamespacePreservesExistingLegacyStoreWithoutMoving(t *testing.T) {
	root := isolateEnvironment(t)
	t.Setenv("HOME", root)
	t.Setenv("APPDATA", root)
	root, err := os.UserConfigDir()
	if err != nil {
		t.Fatal(err)
	}
	current := filepath.Join(root, "deckystream")
	legacy := filepath.Join(root, "obsgod")
	path, err := DefaultPath()
	if err != nil || path != filepath.Join(current, "config.json") {
		t.Fatal("fresh configuration must use the primary namespace", path, err)
	}
	if err := os.MkdirAll(legacy, 0o700); err != nil {
		t.Fatal(err)
	}
	oldFile := filepath.Join(legacy, "config.json")
	body := []byte(`{"version":1,"connection":{"host":"legacy.example"}}`)
	if err := os.WriteFile(oldFile, body, 0o600); err != nil {
		t.Fatal(err)
	}
	before, _ := os.Stat(oldFile)
	resolved, err := Resolve(Config{Host: "localhost", Port: 4455}, Options{})
	if err != nil || resolved.Config.Host != "legacy.example" || resolved.File != oldFile {
		t.Fatal("existing legacy config must remain readable at the original location", err)
	}
	after, _ := os.Stat(oldFile)
	if !os.SameFile(before, after) {
		t.Fatal("read-only configuration discovery changed its inode")
	}
	if _, err := os.Lstat(current); !os.IsNotExist(err) {
		t.Fatal("read-only legacy fallback created a second namespace")
	}
	if err := os.Mkdir(current, 0o700); err != nil {
		t.Fatal(err)
	}
	if _, err := DefaultPath(); err == nil {
		t.Fatal("ambiguous current and old stores must require an explicit path")
	}
	if _, err := Resolve(Config{Host: "localhost", Port: 4455}, Options{Path: oldFile}); err != nil {
		t.Fatal("an explicitly chosen valid config remains usable", err)
	}
}

func TestGenericLegacyNamespaceRejectsSymlinksAndWritableDirectories(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("POSIX namespace permissions/symlink fixture; native Windows ACLs are separate")
	}
	root := t.TempDir()
	target := t.TempDir()
	legacy := filepath.Join(root, "obsgod")
	if err := os.Symlink(target, legacy); err != nil {
		t.Fatal(err)
	}
	if _, _, err := namespaceDirectory(root, "obsgod"); err == nil {
		t.Fatal("legacy discovery must not follow an app namespace symlink")
	}
	if err := os.Remove(legacy); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(legacy, 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.Chmod(legacy, 0o777); err != nil {
		t.Fatal(err)
	}
	if _, _, err := namespaceDirectory(root, "obsgod"); err == nil {
		t.Fatal("legacy discovery must reject a directory writable by another user")
	}
}

func TestGenericDefaultNamespaceUsesEveryExistingApplicationFamily(t *testing.T) {
	for _, family := range []string{"state", "data", "cache", "flatpak", "pre-xdg-data"} {
		t.Run(family, func(t *testing.T) {
			home := isolateEnvironment(t)
			config, err := os.UserConfigDir()
			if err != nil {
				t.Fatal(err)
			}
			roots := map[string]string{
				"state":        os.Getenv("XDG_STATE_HOME"),
				"data":         os.Getenv("XDG_DATA_HOME"),
				"cache":        os.Getenv("XDG_CACHE_HOME"),
				"flatpak":      filepath.Join(home, ".var/app/com.obsproject.Studio/config"),
				"pre-xdg-data": filepath.Join(home, ".local/share"),
			}
			legacy := filepath.Join(roots[family], "obsgod")
			if err := os.MkdirAll(legacy, 0o700); err != nil {
				t.Fatal(err)
			}
			before, _ := os.Stat(legacy)
			path, err := DefaultPath()
			if err != nil || path != filepath.Join(config, "obsgod", "config.json") {
				t.Fatal("generic and managed discovery must select the same legacy namespace", path, err)
			}
			after, _ := os.Stat(legacy)
			if !os.SameFile(before, after) {
				t.Fatal("discovery changed an existing store inode")
			}
			for _, name := range []string{"deckystream", "obsgod"} {
				if _, err := os.Lstat(filepath.Join(config, name)); !os.IsNotExist(err) {
					t.Fatal("read-only discovery created a new configuration directory")
				}
			}
			if err := os.MkdirAll(filepath.Join(config, "deckystream"), 0o700); err != nil {
				t.Fatal(err)
			}
			if _, err := DefaultPath(); err == nil {
				t.Fatal("current config plus any legacy application family must refuse ambiguous selection")
			}
		})
	}
}

func TestGenericDefaultRecognizesPluginOnlyLegacyInstallation(t *testing.T) {
	if runtime.GOOS != "linux" {
		t.Skip("legacy Decky ownership is Linux-only; other platforms fail closed on an occupied old slot")
	}
	home := isolateEnvironment(t)
	plugin := filepath.Join(home, "homebrew/plugins/obsgod")
	if err := os.MkdirAll(plugin, 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(plugin, "plugin.json"), []byte(`{"name":"OBSGod","api_version":1}`), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(plugin, "package.json"), []byte(`{"name":"obsgod","version":"0.1.0-deck.9"}`), 0o600); err != nil {
		t.Fatal(err)
	}
	path, err := DefaultPath()
	if err != nil || path != filepath.Join(home, "obsgod/config.json") {
		t.Fatal("a validated old backend must reserve its namespace before its first write", path, err)
	}
	if _, err := os.Lstat(filepath.Join(home, "obsgod")); !os.IsNotExist(err) {
		t.Fatal("read-only marker discovery created a store")
	}
	if err := os.Mkdir(filepath.Join(home, "deckystream"), 0o700); err != nil {
		t.Fatal(err)
	}
	if _, err := DefaultPath(); err == nil {
		t.Fatal("new store plus a live old backend marker must not split controller state")
	}
}

func TestGenericDefaultAllowsTrustedHomeAliasButNotApplicationSymlinks(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("real POSIX HOME alias fixture")
	}
	home := isolateEnvironment(t)
	alias := filepath.Join(t.TempDir(), "home-alias")
	if err := os.Symlink(home, alias); err != nil {
		t.Fatal(err)
	}
	t.Setenv("HOME", alias)
	t.Setenv("XDG_CONFIG_HOME", filepath.Join(alias, "configuration"))
	t.Setenv("XDG_STATE_HOME", filepath.Join(alias, "state"))
	t.Setenv("XDG_DATA_HOME", filepath.Join(alias, "data"))
	t.Setenv("XDG_CACHE_HOME", filepath.Join(alias, "cache"))
	t.Setenv("DECKY_HOME", filepath.Join(alias, "homebrew"))
	if err := os.MkdirAll(filepath.Join(home, "state/obsgod"), 0o700); err != nil {
		t.Fatal(err)
	}
	configRoot := filepath.Join(home, "configuration")
	if runtime.GOOS == "darwin" {
		configRoot = filepath.Join(home, "Library/Application Support")
	}
	path, err := DefaultPath()
	if err != nil || path != filepath.Join(configRoot, "obsgod/config.json") {
		t.Fatal("trusted HOME alias must retain the canonical existing store", path, err)
	}
	if err := os.MkdirAll(filepath.Dir(configRoot), 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(t.TempDir(), configRoot); err != nil {
		t.Fatal(err)
	}
	if _, err := DefaultPath(); err == nil {
		t.Fatal("HOME-prefix normalization must not follow an XDG application subtree symlink")
	}
}

func TestLegacyWorkflowAliasesRemainIntentOnlyAndCanonicalOverrides(t *testing.T) {
	root := isolateEnvironment(t)
	path := writeConfig(t, root, `{"version":1,"workflow_profiles":{"studio":{"obs_profile":"Studio"},"local":{"starting_scene":"Local"}}}`)
	allowLegacyEnvironment(t)
	t.Setenv("OBSGOD_WORKFLOW", "studio")
	t.Setenv("OBSGOD_WORKFLOW_OBS_PROFILE", "Old Studio")
	t.Setenv("OBSGOD_WORKFLOW_RECORDING_ENABLED", "true")
	plan, name, err := ResolveWorkflow(path, "")
	if err != nil || name != "studio" || plan.OBSProfile != "Old Studio" || !plan.RecordingEnabled {
		t.Fatal("legacy workflow intent was not retained", err)
	}
	t.Setenv("DECKYSTREAM_WORKFLOW", "local")
	t.Setenv("DECKYSTREAM_WORKFLOW_OBS_PROFILE", "Current Studio")
	t.Setenv("DECKYSTREAM_WORKFLOW_RECORDING_ENABLED", "false")
	plan, name, err = ResolveWorkflow(path, "")
	if err != nil || name != "local" || plan.OBSProfile != "Current Studio" || plan.RecordingEnabled {
		t.Fatal("current workflow intent did not take precedence", err)
	}
}
