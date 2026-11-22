package v1

import "testing"

func TestCustomProviderLegacyDefaultKeyIsExplicitAndNeverOverridesCurrent(t *testing.T) {
	provider := RTMPProvider{Name: "custom", DefaultKeyEnv: "DECKYSTREAM_STREAM_KEY"}
	config := ProviderConfig{ID: "custom", Server: "rtmp://localhost/live"}
	for _, fixture := range []struct {
		name     string
		values   map[string]string
		explicit bool
		want     string
		valid    bool
	}{
		{"legacy default", map[string]string{"OBSGOD_STREAM_KEY": "old-key"}, false, "old-key", true},
		{"current wins", map[string]string{"DECKYSTREAM_STREAM_KEY": "current-key", "OBSGOD_STREAM_KEY": "old-key"}, false, "current-key", true},
		{"empty current refuses old", map[string]string{"DECKYSTREAM_STREAM_KEY": "", "OBSGOD_STREAM_KEY": "old-key"}, false, "", false},
		{"explicit reference has no alias", map[string]string{"OBSGOD_STREAM_KEY": "old-key"}, true, "", false},
	} {
		t.Run(fixture.name, func(t *testing.T) {
			selected := config
			if fixture.explicit {
				selected.KeyEnv = "DECKYSTREAM_STREAM_KEY"
			}
			service, err := provider.Resolve(selected, func(key string) (string, bool) { value, ok := fixture.values[key]; return value, ok })
			if (err == nil) != fixture.valid || err == nil && service.Key != fixture.want {
				t.Fatal("custom provider default alias/precedence changed", err)
			}
		})
	}
	independent := RTMPProvider{Name: "independent", DefaultKeyEnv: "DECKYSTREAM_STREAM_KEY"}
	_, err := independent.Resolve(ProviderConfig{ID: "independent", Server: config.Server}, func(key string) (string, bool) {
		return "old-key", key == "OBSGOD_STREAM_KEY"
	})
	if err == nil {
		t.Fatal("independent providers must not acquire a built-in credential alias")
	}
}
