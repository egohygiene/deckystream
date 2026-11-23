// Package naming holds the narrow shared filesystem checks used during the
// primary-name transition. It never creates, moves or removes application data.
package naming

import (
	"errors"
	"os"
	"path/filepath"
	"runtime"
	"strings"
)

var ErrUnsafe = errors.New("application naming context is unsafe or unavailable; inspect the naming migration before changing either installation")

func absolutePath(path string) bool {
	if !filepath.IsAbs(path) || strings.ContainsAny(path, "\x00\r\n") {
		return false
	}
	for _, part := range strings.Split(filepath.ToSlash(path), "/") {
		if part == ".." {
			return false
		}
	}
	return true
}

func safeDirectory(info os.FileInfo) bool {
	return info.IsDir() && ownerAllowed(info) && (runtime.GOOS == "windows" || info.Mode().Perm()&0o022 == 0 || info.Mode()&os.ModeSticky != 0)
}

// NormalizeHome permits only a trusted HOME-prefix alias. Application/XDG
// subtrees are deliberately not resolved through EvalSymlinks here.
func NormalizeHome(home string) (string, error) {
	if !absolutePath(home) {
		return "", ErrUnsafe
	}
	home = filepath.Clean(home)
	for path := home; ; path = filepath.Dir(path) {
		before, err := os.Lstat(path)
		if err != nil || !ownerAllowed(before) {
			return "", ErrUnsafe
		}
		target, err := os.Stat(path)
		if err != nil || !safeDirectory(target) {
			return "", ErrUnsafe
		}
		if path == filepath.Dir(path) {
			break
		}
	}
	canonical, err := filepath.EvalSymlinks(home)
	if err != nil || !absolutePath(canonical) {
		return "", ErrUnsafe
	}
	for path := canonical; ; path = filepath.Dir(path) {
		info, err := os.Lstat(path)
		if err != nil || info.Mode()&os.ModeSymlink != 0 || !safeDirectory(info) {
			return "", ErrUnsafe
		}
		if path == filepath.Dir(path) {
			break
		}
	}
	return canonical, nil
}

// NormalizeHomePath substitutes only a validated HOME prefix. It does not
// follow symlinks in the XDG/application path or change an unrelated root.
func NormalizeHomePath(path, originalHome, canonicalHome string) (string, error) {
	if !absolutePath(path) || !absolutePath(originalHome) || !absolutePath(canonicalHome) {
		return "", ErrUnsafe
	}
	path = filepath.Clean(path)
	relative, err := filepath.Rel(filepath.Clean(originalHome), path)
	if err == nil && relative != ".." && !strings.HasPrefix(relative, ".."+string(filepath.Separator)) && !filepath.IsAbs(relative) {
		return filepath.Join(canonicalHome, relative), nil
	}
	return path, nil
}

func legacyPluginPath(home, deckyHome string) (string, error) {
	canonical, err := NormalizeHome(home)
	if err != nil {
		return "", err
	}
	if deckyHome == "" {
		deckyHome = filepath.Join(home, "homebrew")
	}
	deckyHome, err = NormalizeHomePath(deckyHome, home, canonical)
	if err != nil {
		return "", err
	}
	relative, err := filepath.Rel(canonical, deckyHome)
	if err != nil || relative == ".." || strings.HasPrefix(relative, ".."+string(filepath.Separator)) || filepath.IsAbs(relative) {
		return "", ErrUnsafe
	}
	return filepath.Join(deckyHome, "plugins", "obsgod"), nil
}
