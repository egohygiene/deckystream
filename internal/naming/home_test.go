package naming

import (
	"os"
	"path/filepath"
	"runtime"
	"testing"
)

func TestTrustedHomeAliasNormalizesOnlyItsOwnPrefix(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("real POSIX home alias fixture")
	}
	base := t.TempDir()
	home := filepath.Join(base, "actual-home")
	if err := os.Mkdir(home, 0o700); err != nil {
		t.Fatal(err)
	}
	alias := filepath.Join(base, "home-alias")
	if err := os.Symlink(home, alias); err != nil {
		t.Fatal(err)
	}
	wanted, err := filepath.EvalSymlinks(home)
	if err != nil {
		t.Fatal(err)
	}
	canonical, err := NormalizeHome(alias)
	if err != nil || canonical != wanted {
		t.Fatal("trusted HOME alias was not preserved", canonical, err)
	}
	outside := filepath.Join(base, "outside")
	if err := os.Mkdir(outside, 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(outside, filepath.Join(home, "app-link")); err != nil {
		t.Fatal(err)
	}
	got, err := NormalizeHomePath(filepath.Join(alias, "app-link", "store"), alias, canonical)
	if err != nil || got != filepath.Join(canonical, "app-link", "store") {
		t.Fatal("application symlinks must remain unresolved for the caller's validation", got, err)
	}
	unrelated := alias + "-different"
	got, err = NormalizeHomePath(unrelated, alias, canonical)
	if err != nil || got != unrelated {
		t.Fatal("HOME replacement matched a string prefix rather than a path boundary", got, err)
	}
	if _, err := NormalizeHomePath(alias+string(filepath.Separator)+".."+string(filepath.Separator)+"outside", alias, canonical); err == nil {
		t.Fatal("parent traversal must not be normalized into an authorized path")
	}
}

func TestHomeAliasRejectsWritableUntrustedPrefix(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("POSIX home-prefix permissions")
	}
	base := t.TempDir()
	home := filepath.Join(base, "home")
	if err := os.Mkdir(home, 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.Chmod(base, 0o777); err != nil {
		t.Fatal(err)
	}
	if _, err := NormalizeHome(home); err == nil {
		t.Fatal("a writable nonsticky HOME prefix must fail closed")
	}
}
