package config

import "os"

// Compatibility aliases are enumerated: arbitrary old-prefix variables must
// not acquire authority merely because their names resemble a current option.
var legacyEnvironment = map[string]string{
	"DECKYSTREAM_CONFIG":                         "OBSGOD_CONFIG",
	"DECKYSTREAM_CONNECTION_PROFILE":             "OBSGOD_CONNECTION_PROFILE",
	"DECKYSTREAM_HOST":                           "OBSGOD_HOST",
	"DECKYSTREAM_PORT":                           "OBSGOD_PORT",
	"DECKYSTREAM_PASSWORD":                       "OBSGOD_PASSWORD",
	"DECKYSTREAM_PASSWORD_FILE":                  "OBSGOD_PASSWORD_FILE",
	"DECKYSTREAM_WORKFLOW":                       "OBSGOD_WORKFLOW",
	"DECKYSTREAM_WORKFLOW_OBS_PROFILE":           "OBSGOD_WORKFLOW_OBS_PROFILE",
	"DECKYSTREAM_WORKFLOW_SCENE_COLLECTION":      "OBSGOD_WORKFLOW_SCENE_COLLECTION",
	"DECKYSTREAM_WORKFLOW_STARTING_SCENE":        "OBSGOD_WORKFLOW_STARTING_SCENE",
	"DECKYSTREAM_WORKFLOW_LIVE_SCENE":            "OBSGOD_WORKFLOW_LIVE_SCENE",
	"DECKYSTREAM_WORKFLOW_READINESS_TIMEOUT":     "OBSGOD_WORKFLOW_READINESS_TIMEOUT",
	"DECKYSTREAM_WORKFLOW_POST_START_DELAY":      "OBSGOD_WORKFLOW_POST_START_DELAY",
	"DECKYSTREAM_WORKFLOW_RECORDING_ENABLED":     "OBSGOD_WORKFLOW_RECORDING_ENABLED",
	"DECKYSTREAM_WORKFLOW_REPLAY_BUFFER_ENABLED": "OBSGOD_WORKFLOW_REPLAY_BUFFER_ENABLED",
}

func lookupEnvironment(key string) (string, bool) {
	if value, present := os.LookupEnv(key); present {
		return value, true
	}
	if old := legacyEnvironment[key]; old != "" {
		return os.LookupEnv(old)
	}
	return "", false
}

func environmentValue(key string) string {
	value, _ := lookupEnvironment(key)
	return value
}
