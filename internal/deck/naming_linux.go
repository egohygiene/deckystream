//go:build linux

package deck

import (
	"os"
)

func namespacePathPresent(path string) (bool, error) {
	if err := deckyOwnedPath(path, true, false, true); err != nil {
		return false, err
	}
	_, err := os.Lstat(path)
	if os.IsNotExist(err) {
		return false, nil
	}
	return err == nil, err
}
