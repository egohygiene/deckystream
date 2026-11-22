package deck

import (
	"errors"
	"os"
	"path/filepath"
	"strings"

	appnaming "github.com/egohygiene/deckystream/internal/naming"
)

const primaryNamespace = "deckystream"
const legacyNamespace = "obsgod"
const legacyOBSIdentity = "OBSGod"

var errNamespaceConflict = errors.New("both current and previous application stores exist, or a store is unsafe; inspect the naming migration before changing either installation")
var ErrLegacyBackend = errors.New("the previous Decky plugin is still installed; use the Desktop migration installer to close its managed OBS and replace that backend before changing settings or starting output")

// selectNamespace reads only metadata. Existing installations keep the same
// credentials, state and lock inode; renaming never silently copies or moves it.
func selectNamespace(originalHome, home, config, state string) (string, error) {
	roots := []string{config, state, filepath.Join(home, ".var/app/com.obsproject.Studio/config")}
	for name, fallback := range map[string]string{"XDG_DATA_HOME": ".local/share", "XDG_CACHE_HOME": ".cache"} {
		root := os.Getenv(name)
		if root == "" {
			root = filepath.Join(home, fallback)
		}
		if !filepath.IsAbs(root) || filepath.Clean(root) != root || strings.ContainsAny(root, "\x00\r\n") {
			return "", errNamespaceConflict
		}
		var err error
		root, err = appnaming.NormalizeHomePath(root, originalHome, home)
		if err != nil {
			return "", errNamespaceConflict
		}
		roots = append(roots, root)
	}
	// The Desktop installer already supports a pre-XDG default data location.
	roots = append(roots, filepath.Join(home, ".local/share"))
	found := map[string]bool{}
	for _, root := range roots {
		for _, name := range []string{primaryNamespace, legacyNamespace} {
			present, err := namespacePathPresent(filepath.Join(root, name))
			if err != nil {
				return "", errNamespaceConflict
			}
			found[name] = found[name] || present
		}
	}
	legacyPlugin, err := appnaming.LegacyPluginPresent(originalHome, os.Getenv("DECKY_HOME"))
	if err != nil {
		return "", errNamespaceConflict
	}
	found[legacyNamespace] = found[legacyNamespace] || legacyPlugin
	if found[primaryNamespace] && found[legacyNamespace] {
		return "", errNamespaceConflict
	}
	if found[legacyNamespace] {
		return legacyNamespace, nil
	}
	return primaryNamespace, nil
}

func RequirePrimaryBackend() error {
	home, err := os.UserHomeDir()
	if err != nil {
		return ErrLegacyBackend
	}
	legacy, err := appnaming.LegacyPluginPresent(home, os.Getenv("DECKY_HOME"))
	if err != nil || legacy {
		return ErrLegacyBackend
	}
	return nil
}

func (p Paths) legacyStore() bool {
	return filepath.Base(filepath.Dir(p.Config)) == legacyNamespace &&
		filepath.Base(p.State) == legacyNamespace && filepath.Base(p.OBSConfig) == legacyNamespace
}

func (p Paths) namespace() string {
	if p.legacyStore() {
		return legacyNamespace
	}
	return primaryNamespace
}

// Legacy identity is recovery-only: capture and output Start still require the
// new primary profile. A verified old instance can be observed, stopped or closed.
func managedForRecovery(p Paths, profile, collection string) bool {
	return profile == primaryNamespace && collection == primaryNamespace ||
		p.legacyStore() && profile == legacyOBSIdentity && collection == legacyOBSIdentity
}

var legacyDeckEnvironment = map[string]string{
	"DECKYSTREAM_DECK_PROFILE":      "OBSGOD_DECK_PROFILE",
	"DECKYSTREAM_DECK_BITRATE":      "OBSGOD_DECK_BITRATE",
	"DECKYSTREAM_DECK_FPS":          "OBSGOD_DECK_FPS",
	"DECKYSTREAM_DECK_WIDTH":        "OBSGOD_DECK_WIDTH",
	"DECKYSTREAM_DECK_HEIGHT":       "OBSGOD_DECK_HEIGHT",
	"DECKYSTREAM_DECK_ENCODER":      "OBSGOD_DECK_ENCODER",
	"DECKYSTREAM_DECK_CAPTURE_MODE": "OBSGOD_DECK_CAPTURE_MODE",
	"DECKYSTREAM_DECK_MICROPHONE":   "OBSGOD_DECK_MICROPHONE",
	"DECKYSTREAM_DECKY_STORAGE_MAP": "OBSGOD_DECKY_STORAGE_MAP",
	"DECKYSTREAM_DECKY_RUNTIME_DIR": "OBSGOD_DECKY_RUNTIME_DIR",
	"DECKYSTREAM_DECKY_LOG_DIR":     "OBSGOD_DECKY_LOG_DIR",
}

func deckLookupEnv(name string) (string, bool) {
	if value, present := os.LookupEnv(name); present {
		return value, true
	}
	if legacy, supported := legacyDeckEnvironment[name]; supported {
		return os.LookupEnv(legacy)
	}
	return "", false
}

func deckEnv(name string) string {
	value, _ := deckLookupEnv(name)
	return value
}
