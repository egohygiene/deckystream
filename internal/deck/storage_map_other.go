//go:build !linux

package deck

import (
	"errors"
)

func validateDeckyStorageMap(_ Paths, _ string) error {
	if deckEnv("DECKYSTREAM_DECKY_STORAGE_MAP") != "" {
		return errors.New("Decky storage context requires Linux")
	}
	return nil
}
