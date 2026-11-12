// Package chainverify verifies Python research.ingestion JSONL histories without mutation.
// It is Linux-only because safe component-by-component no-follow opening requires openat.
package chainverify

import (
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"syscall"
)

const (
	MaxDocumentBytes = 65536
	MaxRecordBytes   = 131072
	MaxStoreBytes    = 1048576
	MaxRecords       = 10000
)

// Report contains only facts derived from a completed read-only verification.
type Report struct {
	Records          int
	LastRecordSHA256 string
}

func (r Report) String() string {
	if r.Records == 0 {
		return "VERIFIED LOCAL FORMAT: 0 records (empty history; not audit/completeness evidence)"
	}
	return fmt.Sprintf("VERIFIED LOCAL FORMAT: %d records; final_record_sha256=%s; not audit/completeness evidence", r.Records, r.LastRecordSHA256)
}

// Verify reads and validates path. It never creates, truncates, chmods, locks exclusively,
// executes content, or accesses the network. A valid chain is not tamper-proof: valid-prefix
// truncation and rollback are inherently undetectable.
func Verify(path string) (Report, error) {
	fd, err := openSecureReadOnly(path)
	if err != nil {
		return Report{}, err
	}
	f := os.NewFile(uintptr(fd), "research-history")
	if f == nil {
		syscall.Close(fd)
		return Report{}, errors.New("cannot wrap opened history")
	}
	defer f.Close()
	if err := syscall.Flock(fd, syscall.LOCK_SH); err != nil {
		return Report{}, fmt.Errorf("safe shared lock unavailable: %w", err)
	}
	defer syscall.Flock(fd, syscall.LOCK_UN)
	var st syscall.Stat_t
	if err := syscall.Fstat(fd, &st); err != nil {
		return Report{}, fmt.Errorf("stat opened history: %w", err)
	}
	if err := safeStat(&st); err != nil {
		return Report{}, err
	}
	raw, err := io.ReadAll(io.LimitReader(f, MaxStoreBytes+1))
	if err != nil {
		return Report{}, fmt.Errorf("read history: %w", err)
	}
	if len(raw) > MaxStoreBytes {
		return Report{}, errors.New("history exceeds maximum size")
	}
	// A cooperating writer cannot change the file while our shared flock is held.
	// Re-stat nevertheless: an uncooperative process can add a hard link or change
	// permissions after the first check. Do not report success for such an inode.
	var after syscall.Stat_t
	if err := syscall.Fstat(fd, &after); err != nil {
		return Report{}, fmt.Errorf("restat opened history: %w", err)
	}
	if err := safeStat(&after); err != nil {
		return Report{}, err
	}
	return verifyBytes(raw)
}

func openSecureReadOnly(path string) (int, error) {
	if runtime.GOOS != "linux" {
		return -1, errors.New("secure no-follow traversal is supported only on Linux")
	}
	if path == "" {
		return -1, errors.New("history path is required")
	}
	clean := filepath.Clean(path)
	if clean != path || strings.Contains(path, "..") {
		return -1, errors.New("history path must be canonical and contain no traversal")
	}
	parts := strings.Split(path, string(os.PathSeparator))
	if !filepath.IsAbs(path) {
		return -1, errors.New("history path must be absolute")
	}
	root, err := syscall.Open("/", syscall.O_RDONLY|syscall.O_DIRECTORY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC, 0)
	if err != nil {
		return -1, fmt.Errorf("open root: %w", err)
	}
	fd := root
	defer func() {
		if fd >= 0 {
			syscall.Close(fd)
		}
	}()
	components := parts[1:]
	if len(components) == 0 || components[len(components)-1] == "" {
		return -1, errors.New("history needs a concrete filename")
	}
	for _, part := range components[:len(components)-1] {
		if part == "" || part == "." || part == ".." {
			return -1, errors.New("invalid history path component")
		}
		next, e := syscall.Openat(fd, part, syscall.O_RDONLY|syscall.O_DIRECTORY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC, 0)
		if e != nil {
			return -1, fmt.Errorf("open history parent safely: %w", e)
		}
		syscall.Close(fd)
		fd = next
	}
	leaf := components[len(components)-1]
	if leaf == "." || leaf == ".." {
		return -1, errors.New("invalid history filename")
	}
	result, err := syscall.Openat(fd, leaf, syscall.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC, 0)
	if err != nil {
		return -1, fmt.Errorf("open history safely: %w", err)
	}
	return result, nil
}

func safeStat(st *syscall.Stat_t) error {
	if st.Mode&syscall.S_IFMT != syscall.S_IFREG || st.Nlink != 1 || st.Uid != uint32(os.Geteuid()) || st.Mode&0777 != 0600 || st.Size > MaxStoreBytes {
		return errors.New("history is not a bounded owner-only unlinked regular 0600 file")
	}
	return nil
}
