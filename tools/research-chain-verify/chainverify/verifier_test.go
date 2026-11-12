package chainverify

import (
	"bytes"
	"os"
	"path/filepath"
	"testing"
)

func golden(t *testing.T) []byte {
	t.Helper()
	b, err := os.ReadFile(filepath.Join("..", "testdata", "golden.jsonl"))
	if err != nil {
		t.Fatal(err)
	}
	return b
}

func TestPythonGeneratedGoldenFixture(t *testing.T) {
	path, err := filepath.Abs(filepath.Join("..", "testdata", "golden.jsonl"))
	if err != nil {
		t.Fatal(err)
	}
	report, err := Verify(path)
	if err != nil {
		t.Fatalf("Python-generated fixture rejected: %v", err)
	}
	if report.Records != 2 {
		t.Fatalf("records = %d, want 2", report.Records)
	}
	if report.LastRecordSHA256 != "968f53b59f9eddaedb75df9f7b035e0a8229593504186ae15ce3550fe1c07bff" {
		t.Fatalf("unexpected final digest: %s", report.LastRecordSHA256)
	}
}

func TestAdversarialHistoryIsRejected(t *testing.T) {
	base := golden(t)
	cases := map[string][]byte{
		"record digest tamper":     bytes.Replace(base, []byte(`"record_sha256":"`), []byte(`"record_sha256":"0`), 1),
		"duplicate key":            bytes.Replace(base, []byte(`"version":1`), []byte(`"version":1,"version":1`), 1),
		"trailing partial":         base[:len(base)-1],
		"duplicate document":       append(append([]byte{}, base...), bytes.Split(base, []byte{'\n'})[0]...),
		"impossible calendar day":  bytes.Replace(base, []byte("2026-01-02T03:04:05+00:00"), []byte("2026-02-30T03:04:05+00:00"), 1),
		"short timestamp fraction": bytes.Replace(base, []byte("2026-01-02T03:04:06.123456+00:00"), []byte("2026-01-02T03:04:06.1+00:00"), 1),
	}
	for name, data := range cases {
		t.Run(name, func(t *testing.T) {
			if _, err := verifyBytes(data); err == nil {
				t.Fatal("accepted adversarial history")
			}
		})
	}
}

func TestSecureFileRequirementsAndNoSymlink(t *testing.T) {
	dir := t.TempDir()
	good := filepath.Join(dir, "history.jsonl")
	if err := os.WriteFile(good, golden(t), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := Verify(good); err != nil {
		t.Fatalf("secure regular file rejected: %v", err)
	}
	if err := os.Chmod(good, 0644); err != nil {
		t.Fatal(err)
	}
	if _, err := Verify(good); err == nil {
		t.Fatal("world-readable file accepted")
	}
	if err := os.Chmod(good, 0600); err != nil {
		t.Fatal(err)
	}
	link := filepath.Join(dir, "link.jsonl")
	if err := os.Symlink(good, link); err != nil {
		t.Fatal(err)
	}
	if _, err := Verify(link); err == nil {
		t.Fatal("symlink accepted")
	}
}

func TestPythonGeneratedUnicodeFixture(t *testing.T) {
	path, err := filepath.Abs(filepath.Join("..", "testdata", "unicode.jsonl"))
	if err != nil {
		t.Fatal(err)
	}
	report, err := Verify(path)
	if err != nil {
		t.Fatalf("Python-generated Unicode fixture rejected: %v", err)
	}
	if report.Records != 1 || report.LastRecordSHA256 != "9399e60e07d86e3d9687ed759685e33d9a10d8dca943640881bdd154cf1c65d9" {
		t.Fatalf("unexpected Unicode fixture report: %+v", report)
	}
}

func TestPythonCanonicalStringEscaping(t *testing.T) {
	got := string(canonicalString("café 😀\x01\n"))
	want := `"caf\u00e9 \ud83d\ude00\u0001\n"`
	if got != want {
		t.Fatalf("canonicalString() = %q, want %q", got, want)
	}
}

func TestCanonicalTimestampMatchesPythonRules(t *testing.T) {
	valid := []string{"2026-01-02T03:04:05+00:00", "2026-01-02T03:04:05.123456+00:00"}
	invalid := []string{
		"2026-01-02T03:04:05.1+00:00", // Python normalizes to six digits.
		"2026-02-30T03:04:05+00:00",   // Regex-only validation used to accept this.
		"2026-01-02T03:04:05Z",
		"2026-01-02 03:04:05+00:00",
	}
	for _, value := range valid {
		if !canonicalTimestamp(value) {
			t.Errorf("rejected Python-canonical timestamp %q", value)
		}
	}
	for _, value := range invalid {
		if canonicalTimestamp(value) {
			t.Errorf("accepted non-canonical timestamp %q", value)
		}
	}
}

func TestInvalidUTF8IsRejected(t *testing.T) {
	if _, err := strictJSON([]byte(`{"x":"` + string([]byte{0xff}) + `"}`)); err == nil {
		t.Fatal("invalid UTF-8 JSON was accepted")
	}
}
