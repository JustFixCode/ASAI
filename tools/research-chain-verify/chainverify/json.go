package chainverify

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"strconv"
	"strings"
	"unicode/utf8"
)

func verifyBytes(raw []byte) (Report, error) {
	if len(raw) == 0 {
		return Report{}, nil
	}
	if raw[len(raw)-1] != '\n' {
		return Report{}, errors.New("history ends with a partial record")
	}
	lines := bytes.Split(raw[:len(raw)-1], []byte{'\n'})
	if len(lines) > MaxRecords {
		return Report{}, errors.New("history exceeds record limit")
	}
	var previous *string
	seen := make(map[string]struct{}, len(lines))
	var last string
	for i, line := range lines {
		if len(line) == 0 || len(line) > MaxRecordBytes {
			return Report{}, fmt.Errorf("record %d is empty or too large", i+1)
		}
		v, err := strictJSON(line)
		if err != nil {
			return Report{}, fmt.Errorf("record %d invalid JSON: %w", i+1, err)
		}
		record, ok := v.(map[string]any)
		if !ok {
			return Report{}, fmt.Errorf("record %d is not an object", i+1)
		}
		got, content, err := validateRecord(record, i+1, previous)
		if err != nil {
			return Report{}, fmt.Errorf("record %d: %w", i+1, err)
		}
		if _, duplicate := seen[content]; duplicate {
			return Report{}, fmt.Errorf("record %d duplicates a document", i+1)
		}
		seen[content] = struct{}{}
		last = got
		previous = &last
	}
	return Report{Records: len(lines), LastRecordSHA256: last}, nil
}

func strictJSON(line []byte) (any, error) {
	if !utf8.Valid(line) {
		return nil, errors.New("JSON is not valid UTF-8")
	}
	dec := json.NewDecoder(bytes.NewReader(line))
	dec.UseNumber()
	v, err := decodeValue(dec)
	if err != nil {
		return nil, err
	}
	if _, err := dec.Token(); err != io.EOF {
		return nil, errors.New("trailing JSON data")
	}
	return v, nil
}
func decodeValue(dec *json.Decoder) (any, error) {
	t, err := dec.Token()
	if err != nil {
		return nil, err
	}
	switch x := t.(type) {
	case json.Delim:
		switch x {
		case '{':
			m := map[string]any{}
			for dec.More() {
				k, e := dec.Token()
				if e != nil {
					return nil, e
				}
				key, ok := k.(string)
				if !ok {
					return nil, errors.New("non-string object key")
				}
				if _, exists := m[key]; exists {
					return nil, errors.New("duplicate JSON field")
				}
				v, e := decodeValue(dec)
				if e != nil {
					return nil, e
				}
				m[key] = v
			}
			if end, e := dec.Token(); e != nil || end != json.Delim('}') {
				return nil, errors.New("unterminated object")
			}
			return m, nil
		case '[':
			var a []any
			for dec.More() {
				v, e := decodeValue(dec)
				if e != nil {
					return nil, e
				}
				a = append(a, v)
			}
			if end, e := dec.Token(); e != nil || end != json.Delim(']') {
				return nil, errors.New("unterminated array")
			}
			return a, nil
		}
	}
	return t, nil
}

func expectObject(v any, keys ...string) (map[string]any, error) {
	m, ok := v.(map[string]any)
	if !ok {
		return nil, errors.New("expected object")
	}
	if len(m) != len(keys) {
		return nil, errors.New("unexpected object fields")
	}
	for _, k := range keys {
		if _, ok := m[k]; !ok {
			return nil, errors.New("missing object field")
		}
	}
	return m, nil
}
func expectString(v any) (string, error) {
	s, ok := v.(string)
	if !ok {
		return "", errors.New("expected string")
	}
	return s, nil
}
func expectInt(v any, want int) error {
	n, ok := v.(json.Number)
	if !ok || n.String() != strconv.Itoa(want) {
		return errors.New("invalid integer field")
	}
	return nil
}
func expectBool(v any, want bool) error {
	b, ok := v.(bool)
	if !ok || b != want {
		return errors.New("invalid boolean field")
	}
	return nil
}
func text(v any, label string, maximum int, multiline, rejectURL bool) (string, error) {
	s, e := expectString(v)
	if e != nil || s == "" || len([]byte(s)) > maximum {
		return "", fmt.Errorf("%s must be nonempty bounded text", label)
	}
	if strings.ContainsRune(s, 0) || (!multiline && (strings.ContainsAny(s, "\r\n"))) {
		return "", fmt.Errorf("%s has prohibited controls", label)
	}
	if secret.MatchString(s) {
		return "", fmt.Errorf("%s appears to contain credential", label)
	}
	if rejectURL && url.MatchString(s) {
		return "", fmt.Errorf("%s must not be URL", label)
	}
	return s, nil
}
