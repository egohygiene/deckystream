//go:build !(aix || android || darwin || dragonfly || freebsd || illumos || linux || netbsd || openbsd || solaris)

package naming

import (
	"os"
	"runtime"
)

func ownerAllowed(_ os.FileInfo) bool {
	// Windows user-profile ACLs cannot be inferred from Unix UID/mode bits.
	// Existing legacy plugin metadata still fails closed outside Linux.
	return runtime.GOOS == "windows"
}

func singleLink(_ os.FileInfo) bool { return false }
