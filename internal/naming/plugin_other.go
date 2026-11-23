//go:build !linux

package naming

import "os"

func LegacyPluginPresent(home, deckyHome string) (bool, error) {
	path, err := legacyPluginPath(home, deckyHome)
	if err != nil {
		return false, err
	}
	if _, err := os.Lstat(path); os.IsNotExist(err) {
		return false, nil
	}
	// Legacy Decky runtime ownership cannot be established on this platform.
	return false, ErrUnsafe
}
