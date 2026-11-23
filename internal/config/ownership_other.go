//go:build !(aix || android || darwin || dragonfly || freebsd || illumos || linux || netbsd || openbsd || solaris)

package config

import "os"

func configurationOwner(_ os.FileInfo, _ bool) bool {
	// Windows ACLs, rather than POSIX owner/mode bits, govern the existing
	// native user configuration directory. Do not infer an ACL from Unix bits.
	return true
}
