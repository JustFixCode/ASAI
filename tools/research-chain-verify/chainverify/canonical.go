package chainverify

import (
	"bytes"
	"encoding/json"
	"fmt"
	"sort"
	"strconv"
)

func canonical(v any) []byte {
	switch x := v.(type) {
	case nil:
		return []byte("null")
	case bool:
		if x {
			return []byte("true")
		}
		return []byte("false")
	case string:
		return canonicalString(x)
	case json.Number:
		return []byte(x.String())
	case map[string]any:
		ks := make([]string, 0, len(x))
		for k := range x {
			ks = append(ks, k)
		}
		sort.Strings(ks)
		var b bytes.Buffer
		b.WriteByte('{')
		for i, k := range ks {
			if i > 0 {
				b.WriteByte(',')
			}
			b.WriteString(strconv.Quote(k))
			b.WriteByte(':')
			b.Write(canonical(x[k]))
		}
		b.WriteByte('}')
		return b.Bytes()
	default:
		panic("unsupported canonical value")
	}
}

// canonicalString reproduces json.dumps(..., ensure_ascii=True): it uses JSON's
// fixed short escapes and emits every non-ASCII rune as lowercase UTF-16 \u escapes.
// strconv.Quote is not suitable because it leaves printable Unicode unescaped.
func canonicalString(s string) []byte {
	var b bytes.Buffer
	b.WriteByte('"')
	for _, r := range s {
		switch r {
		case '\\':
			b.WriteString(`\\`)
		case '"':
			b.WriteString(`\"`)
		case '\b':
			b.WriteString(`\b`)
		case '\t':
			b.WriteString(`\t`)
		case '\n':
			b.WriteString(`\n`)
		case '\f':
			b.WriteString(`\f`)
		case '\r':
			b.WriteString(`\r`)
		default:
			if r < 0x20 {
				fmt.Fprintf(&b, `\u%04x`, r)
			} else if r <= 0x7e {
				b.WriteRune(r)
			} else if r <= 0xffff {
				fmt.Fprintf(&b, `\u%04x`, r)
			} else {
				r -= 0x10000
				fmt.Fprintf(&b, `\u%04x\u%04x`, 0xd800+(r>>10), 0xdc00+(r&0x3ff))
			}
		}
	}
	b.WriteByte('"')
	return b.Bytes()
}
