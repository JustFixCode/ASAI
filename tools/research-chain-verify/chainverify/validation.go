package chainverify

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"regexp"
	"strings"
	"time"
)

const recordType = "untrusted_research_capture_no_risk_authority"

var (
	identifier = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$`)
	digest     = regexp.MustCompile(`^[0-9a-f]{64}$`)
	url        = regexp.MustCompile(`[A-Za-z][A-Za-z0-9+.-]*://`)
	secret     = regexp.MustCompile(`(?i)(?:api[_ -]?key|secret|password|credential|authorization|private[_ -]?key|access[_ -]?token)\s*[:=]|(?:AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{36})|(?:\bbearer[ \t]+[A-Za-z0-9._~+/-]{16,}={0,2}\b)`)
)

func validateRecord(r map[string]any, version int, previous *string) (string, string, error) {
	if _, e := expectObject(r, "version", "document", "previous_record_sha256", "record_sha256"); e != nil {
		return "", "", e
	}
	if e := expectInt(r["version"], version); e != nil {
		return "", "", e
	}
	if previous == nil {
		if r["previous_record_sha256"] != nil {
			return "", "", errors.New("first previous digest must be null")
		}
	} else {
		p, e := expectString(r["previous_record_sha256"])
		if e != nil || p != *previous {
			return "", "", errors.New("previous digest mismatch")
		}
	}
	d, e := expectObject(r["document"], "schema_version", "record_type", "untrusted", "risk_authority", "provenance", "title", "text", "content_sha256")
	if e != nil {
		return "", "", e
	}
	if e = expectInt(d["schema_version"], 1); e != nil {
		return "", "", e
	}
	typ, e := expectString(d["record_type"])
	if e != nil || typ != recordType {
		return "", "", errors.New("invalid record type")
	}
	if e = expectBool(d["untrusted"], true); e != nil {
		return "", "", e
	}
	if e = expectBool(d["risk_authority"], false); e != nil {
		return "", "", e
	}
	p, e := expectObject(d["provenance"], "source_id", "source_kind", "source_label", "source_reference", "captured_at")
	if e != nil {
		return "", "", e
	}
	sid, e := expectString(p["source_id"])
	if e != nil || !identifier.MatchString(sid) || secret.MatchString(sid) {
		return "", "", errors.New("invalid source_id")
	}
	kind, e := expectString(p["source_kind"])
	if e != nil || (kind != "manual_external_research" && kind != "user_supplied_research" && kind != "local_research_note") {
		return "", "", errors.New("invalid source_kind")
	}
	if _, e = text(p["source_label"], "source_label", 256, false, false); e != nil {
		return "", "", e
	}
	if _, e = text(p["source_reference"], "source_reference", 512, false, true); e != nil {
		return "", "", e
	}
	ts, e := expectString(p["captured_at"])
	if e != nil || !canonicalTimestamp(ts) {
		return "", "", errors.New("captured_at is not supported canonical UTC ISO-8601")
	}
	if _, e = text(d["title"], "title", 512, false, false); e != nil {
		return "", "", e
	}
	if _, e = text(d["text"], "text", MaxDocumentBytes, true, false); e != nil {
		return "", "", e
	}
	content, e := expectString(d["content_sha256"])
	if e != nil || !digest.MatchString(content) {
		return "", "", errors.New("invalid content digest")
	}
	payload := map[string]any{"schema_version": d["schema_version"], "record_type": d["record_type"], "untrusted": d["untrusted"], "risk_authority": d["risk_authority"], "provenance": p, "title": d["title"], "text": d["text"]}
	canon := canonical(payload)
	if len(canon) > MaxDocumentBytes {
		return "", "", errors.New("document too large")
	}
	if hex.EncodeToString(sha256Bytes(canon)) != content {
		return "", "", errors.New("content digest mismatch")
	}
	recordPayload := map[string]any{"version": r["version"], "document": d, "previous_record_sha256": r["previous_record_sha256"]}
	want := hex.EncodeToString(sha256Bytes(canonical(recordPayload)))
	got, e := expectString(r["record_sha256"])
	if e != nil || got != want {
		return "", "", errors.New("record digest mismatch")
	}
	return got, content, nil
}
func sha256Bytes(b []byte) []byte { h := sha256.Sum256(b); return h[:] }

// canonicalTimestamp mirrors Python's datetime.fromisoformat(value) followed by
// parsed.isoformat() == value and a zero UTC offset. Python emits either no
// fractional seconds or exactly six digits, never a shortened fraction.
func canonicalTimestamp(s string) bool {
	if len(s) > 40 {
		return false
	}
	layout := "2006-01-02T15:04:05-07:00"
	if strings.Contains(s, ".") {
		if !regexp.MustCompile(`^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}\+00:00$`).MatchString(s) {
			return false
		}
		layout = "2006-01-02T15:04:05.000000-07:00"
	} else if !regexp.MustCompile(`^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$`).MatchString(s) {
		return false
	}
	parsed, err := time.Parse(layout, s)
	return err == nil && parsed.UTC().Format(layout) == s
}
