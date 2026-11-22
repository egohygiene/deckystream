//go:build linux

package deck

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func namingHome(t *testing.T) (string, map[string]string) {
	t.Helper()
	home := t.TempDir()
	t.Setenv("HOME", home)
	roots := map[string]string{"config": filepath.Join(home, "configuration"), "state": filepath.Join(home, "state"), "data": filepath.Join(home, "data"), "cache": filepath.Join(home, "cache"), "flatpak": filepath.Join(home, ".var/app/com.obsproject.Studio/config"), "default-data": filepath.Join(home, ".local/share")}
	for key, name := range map[string]string{"config": "XDG_CONFIG_HOME", "state": "XDG_STATE_HOME", "data": "XDG_DATA_HOME", "cache": "XDG_CACHE_HOME"} {
		t.Setenv(name, roots[key])
	}
	t.Setenv("DECKYSTREAM_DECKY_STORAGE_MAP", "")
	t.Setenv("OBSGOD_DECKY_STORAGE_MAP", "")
	t.Setenv("XDG_VIDEOS_DIR", "")
	return home, roots
}

func TestPrimaryNamingUsesNewStoreWithoutCreatingIt(t *testing.T) {
	home, roots := namingHome(t)
	p, err := UserPaths()
	if err != nil || p.Config != filepath.Join(roots["config"], "deckystream/deck.json") || p.State != filepath.Join(roots["state"], "deckystream") || p.Videos != filepath.Join(home, "Videos/deckystream") || p.legacyStore() {
		t.Fatal("fresh paths do not use the primary namespace", p, err)
	}
	for _, root := range roots {
		if _, err := os.Lstat(root); !os.IsNotExist(err) {
			t.Fatal("read-only path selection created state", root, err)
		}
	}
}

func TestEachLegacyStoreSelectsOneCoherentNamespace(t *testing.T) {
	for _, family := range []string{"config", "state", "data", "cache", "flatpak", "default-data"} {
		t.Run(family, func(t *testing.T) {
			home, roots := namingHome(t)
			if err := os.MkdirAll(filepath.Join(roots[family], legacyNamespace), 0700); err != nil {
				t.Fatal(err)
			}
			p, err := UserPaths()
			if err != nil || !p.legacyStore() || p.Config != filepath.Join(roots["config"], "obsgod/deck.json") || p.State != filepath.Join(roots["state"], "obsgod") || p.OBSConfig != filepath.Join(roots["flatpak"], "obsgod") || p.Videos != filepath.Join(home, "Videos/OBSGod") {
				t.Fatal("legacy family split the canonical paths", p, err)
			}
		})
	}
}

func TestNamingPreservesSavedSecretsAndControllerLockInode(t *testing.T) {
	_, roots := namingHome(t)
	if err := os.MkdirAll(filepath.Join(roots["config"], legacyNamespace), 0700); err != nil {
		t.Fatal(err)
	}
	p, err := UserPaths()
	if err != nil {
		t.Fatal(err)
	}
	if _, err = Configure(p, strings.NewReader(fixtureSettings)); err != nil {
		t.Fatal(err)
	}
	secrets, _ := os.ReadFile(p.Secrets)
	before, _ := os.Stat(p.Secrets)
	unlock, err := Lock(context.Background(), p)
	if err != nil {
		t.Fatal(err)
	}
	defer unlock()
	current, err := UserPaths()
	if err != nil || current != p {
		t.Fatal("selection moved an existing store", current, err)
	}
	after, err := os.Stat(current.Secrets)
	if err != nil || !os.SameFile(before, after) {
		t.Fatal("credential inode changed", err)
	}
	data, _ := os.ReadFile(current.Secrets)
	if string(data) != string(secrets) {
		t.Fatal("credential bytes changed")
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if release, err := Lock(ctx, current); err == nil {
		release()
		t.Fatal("a new selection escaped the existing controller lease")
	}
}

func TestNamingRejectsAmbiguousSymlinkedAndWritableStores(t *testing.T) {
	for _, kind := range []string{"both", "symlink", "file", "writable"} {
		t.Run(kind, func(t *testing.T) {
			_, roots := namingHome(t)
			old := filepath.Join(roots["config"], legacyNamespace)
			if err := os.MkdirAll(filepath.Dir(old), 0700); err != nil {
				t.Fatal(err)
			}
			switch kind {
			case "both":
				_ = os.Mkdir(old, 0700)
				_ = os.MkdirAll(filepath.Join(roots["state"], primaryNamespace), 0700)
			case "symlink":
				_ = os.Symlink(t.TempDir(), old)
			case "file":
				_ = os.WriteFile(old, []byte("not a store"), 0600)
			case "writable":
				_ = os.Mkdir(old, 0700)
				_ = os.Chmod(old, 0777)
			}
			if _, err := UserPaths(); err == nil {
				t.Fatal("unsafe or ambiguous namespace was accepted")
			}
		})
	}
}

func TestLegacyRuntimeRecoveryCannotAuthorizeNewCapture(t *testing.T) {
	p := Paths{Config: "/unused/config/obsgod/deck.json", State: "/unused/state/obsgod", OBSConfig: "/unused/flatpak/obsgod", Videos: "/unused/videos"}
	f := newVideoFixture(t)
	f.profile, f.collection = legacyOBSIdentity, legacyOBSIdentity
	c, _ := videoClient(t, f)
	if _, err := verifyManagedRecovery(context.Background(), c, p); err != nil {
		t.Fatal("legacy owned identity could not be explicitly recovered", err)
	}
	if result := mediaSnapshotFrom(context.Background(), p, c, MediaSnapshot{}); !result.Known {
		t.Fatal("legacy outputs could not be observed before explicit close")
	}
	if _, err := verifyManaged(context.Background(), c); err == nil {
		t.Fatal("legacy identity authorized primary Start/capture")
	}
	c, _ = videoClient(t, f)
	p.Config = "/unused/config/deckystream/deck.json"
	if _, err := verifyManagedRecovery(context.Background(), c, p); err == nil {
		t.Fatal("legacy profile outside a coherent legacy store was accepted")
	}
	assertNoOutputCommands(t, f)
}

func TestLegacyDeckEnvironmentUsesExplicitFallbackAndPrimaryPresence(t *testing.T) {
	t.Setenv("OBSGOD_DECK_BITRATE", "3300")
	old, hadOld := os.LookupEnv("DECKYSTREAM_DECK_BITRATE")
	_ = os.Unsetenv("DECKYSTREAM_DECK_BITRATE")
	t.Cleanup(func() {
		if hadOld {
			_ = os.Setenv("DECKYSTREAM_DECK_BITRATE", old)
		} else {
			_ = os.Unsetenv("DECKYSTREAM_DECK_BITRATE")
		}
	})
	if deckEnv("DECKYSTREAM_DECK_BITRATE") != "3300" {
		t.Fatal("legacy built-in variable was ignored")
	}
	t.Setenv("DECKYSTREAM_DECK_BITRATE", "4400")
	if deckEnv("DECKYSTREAM_DECK_BITRATE") != "4400" {
		t.Fatal("legacy variable overrode the primary value")
	}
	t.Setenv("DECKYSTREAM_DECK_BITRATE", "")
	if value, present := deckLookupEnv("DECKYSTREAM_DECK_BITRATE"); !present || value != "" {
		t.Fatal("explicit primary empty value fell back to legacy")
	}
	t.Setenv("OBSGOD_UNREVIEWED", "do not translate")
	if _, present := deckLookupEnv("DECKYSTREAM_UNREVIEWED"); present {
		t.Fatal("arbitrary legacy environment variables were translated")
	}
}

func TestTrustedHomeAliasNormalizesOnlyTheHomePrefix(t *testing.T) {
	realHome, roots := namingHome(t)
	alias := filepath.Join(t.TempDir(), "trusted-home")
	if err := os.Symlink(realHome, alias); err != nil {
		t.Fatal(err)
	}
	t.Setenv("HOME", alias)
	for key, variable := range map[string]string{"config": "XDG_CONFIG_HOME", "state": "XDG_STATE_HOME", "data": "XDG_DATA_HOME", "cache": "XDG_CACHE_HOME"} {
		rel, _ := filepath.Rel(realHome, roots[key])
		t.Setenv(variable, filepath.Join(alias, rel))
	}
	p, err := UserPaths()
	if err != nil || p.Config != filepath.Join(realHome, "configuration/deckystream/deck.json") || p.State != filepath.Join(realHome, "state/deckystream") {
		t.Fatal("trusted home alias was rejected or leaked into canonical paths", p, err)
	}
	if err := os.MkdirAll(roots["config"], 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(t.TempDir(), filepath.Join(roots["config"], primaryNamespace)); err != nil {
		t.Fatal(err)
	}
	if _, err := UserPaths(); err == nil {
		t.Fatal("application-internal link was normalized instead of refused")
	}
}

func TestLegacyPluginWithoutDataSelectsLegacyAndBlocksNewMutations(t *testing.T) {
	home, roots := namingHome(t)
	plugin := filepath.Join(home, "homebrew/plugins/obsgod")
	if err := os.MkdirAll(plugin, 0755); err != nil {
		t.Fatal(err)
	}
	for name, value := range map[string]map[string]string{"plugin.json": {"name": "OBSGod"}, "package.json": {"name": "obsgod", "version": "0.1.0-deck.9"}} {
		data, _ := json.Marshal(value)
		if err := os.WriteFile(filepath.Join(plugin, name), data, 0644); err != nil {
			t.Fatal(err)
		}
	}
	p, err := UserPaths()
	if err != nil || !p.legacyStore() {
		t.Fatal("installed old plugin did not preserve the future lock namespace", p, err)
	}
	if release, err := Lock(context.Background(), p); !errors.Is(err, ErrLegacyBackend) {
		if release != nil {
			release()
		}
		t.Fatal("normal control mutation passed the old backend", err)
	}
	if _, err := Configure(p, strings.NewReader(fixtureSettings)); !errors.Is(err, ErrLegacyBackend) {
		t.Fatal("setup wrote alongside the old backend", err)
	}
	if _, err := os.Lstat(p.State); !os.IsNotExist(err) {
		t.Fatal("blocked mutation created a state root", err)
	}
	release, err := RecoveryLock(context.Background(), p)
	if err != nil {
		t.Fatal("explicit recovery could not acquire the original namespace", err)
	}
	release()
	if err := os.RemoveAll(plugin); err != nil {
		t.Fatal(err)
	}
	after, err := UserPaths()
	if err != nil || after != p {
		t.Fatal("retiring the backend split its retained state lock", after, err)
	}
	if err := os.MkdirAll(filepath.Join(roots["config"], primaryNamespace), 0700); err != nil {
		t.Fatal(err)
	}
	if _, err := UserPaths(); err == nil {
		t.Fatal("dual application stores were accepted after retirement")
	}
}
