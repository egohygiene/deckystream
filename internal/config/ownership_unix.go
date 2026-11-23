//go:build aix || android || darwin || dragonfly || freebsd || illumos || linux || netbsd || openbsd || solaris

package config

import (
	"os"
	"syscall"
)

func configurationOwner(info os.FileInfo, ancestor bool) bool {
	owner, ok := info.Sys().(*syscall.Stat_t)
	return ok && (int(owner.Uid) == os.Getuid() || ancestor && owner.Uid == 0)
}
