package deck

import (
	"runtime"
	"testing"
)

// Keep pure validation/protocol tests portable. Only tests exercising Linux
// runtime locks, guardians, ownership or disk-space probes need this guard.
func requireLinuxDeckRuntime(t *testing.T) {
	t.Helper()
	if runtime.GOOS != "linux" {
		t.Skip("requires the Linux Steam Deck runtime locks, guardians or filesystem probes")
	}
}

// Windows does not expose chmod(0600)/POSIX path semantics. These tests model
// the private files on the Linux Deck, rather than a Windows installer contract.
func requirePOSIXDeckFiles(t *testing.T) {
	t.Helper()
	if runtime.GOOS == "windows" {
		t.Skip("requires POSIX private-file permissions and paths on the Steam Deck host")
	}
}
