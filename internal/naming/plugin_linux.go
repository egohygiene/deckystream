//go:build linux

package naming

import (
	"encoding/json"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"syscall"
)

var legacyVersion = regexp.MustCompile(`^[0-9][A-Za-z0-9.-]{0,79}$`)

func pluginDirectory(path string) (os.FileInfo, error) {
	var leaf os.FileInfo
	for current := path; ; current = filepath.Dir(current) {
		info, err := os.Lstat(current)
		if err != nil || info.Mode()&os.ModeSymlink != 0 || !safeDirectory(info) || current == path && info.Mode().Perm()&0o022 != 0 {
			return nil, ErrUnsafe
		}
		if current == path {
			leaf = info
		}
		if current == filepath.Dir(current) {
			break
		}
	}
	return leaf, nil
}

func pluginMetadata(path string) (map[string]any, error) {
	before, err := os.Lstat(path)
	if err != nil || !before.Mode().IsRegular() || !ownerAllowed(before) || !singleLink(before) || before.Mode().Perm()&0o022 != 0 || before.Size() > 65536 {
		return nil, ErrUnsafe
	}
	file, err := os.OpenFile(path, os.O_RDONLY|syscall.O_NOFOLLOW, 0)
	if err != nil {
		return nil, ErrUnsafe
	}
	defer file.Close()
	opened, err := file.Stat()
	if err != nil || !os.SameFile(before, opened) || !opened.Mode().IsRegular() || !singleLink(opened) || !ownerAllowed(opened) || opened.Mode().Perm()&0o022 != 0 || opened.Size() > 65536 {
		return nil, ErrUnsafe
	}
	data, err := io.ReadAll(io.LimitReader(file, 65537))
	if err != nil || len(data) > 65536 {
		return nil, ErrUnsafe
	}
	after, err := os.Lstat(path)
	if err != nil || !after.Mode().IsRegular() || !os.SameFile(opened, after) || !singleLink(after) || !ownerAllowed(after) || after.Mode().Perm()&0o022 != 0 || after.Size() > 65536 {
		return nil, ErrUnsafe
	}
	var value map[string]any
	if json.Unmarshal(data, &value) != nil || value == nil {
		return nil, ErrUnsafe
	}
	return value, nil
}

// LegacyPluginPresent recognizes only the verified old plugin in its exact
// owned slot. A malformed occupied slot is an error, never evidence of absence.
func LegacyPluginPresent(home, deckyHome string) (bool, error) {
	path, err := legacyPluginPath(home, deckyHome)
	if err != nil {
		return false, err
	}
	if _, err := os.Lstat(path); os.IsNotExist(err) {
		return false, nil
	} else if err != nil {
		return false, ErrUnsafe
	}
	before, err := pluginDirectory(path)
	if err != nil {
		return false, err
	}
	plugin, err := pluginMetadata(filepath.Join(path, "plugin.json"))
	if err != nil || plugin["name"] != "OBSGod" {
		return false, ErrUnsafe
	}
	metadata, err := pluginMetadata(filepath.Join(path, "package.json"))
	if err != nil || metadata["name"] != "obsgod" && metadata["name"] != "obsgod-decky" {
		return false, ErrUnsafe
	}
	version, ok := metadata["version"].(string)
	if !ok || !legacyVersion.MatchString(version) {
		return false, ErrUnsafe
	}
	after, err := pluginDirectory(path)
	if err != nil || !os.SameFile(before, after) {
		return false, ErrUnsafe
	}
	return true, nil
}
