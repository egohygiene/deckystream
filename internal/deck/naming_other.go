//go:build !linux

package deck

import "os"

func namespacePathPresent(path string) (bool, error) {
	_, err := os.Lstat(path)
	if os.IsNotExist(err) {
		return false, nil
	}
	// The managed runtime's ownership/lock semantics are Linux-only. Never
	// infer a safe migration on a platform that cannot validate those semantics.
	return false, errNamespaceConflict
}
