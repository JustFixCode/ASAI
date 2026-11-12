// research-chain-verify is a read-only offline verifier for research.ingestion JSONL.
package main

import (
	"fmt"
	"os"

	chainverify "asai/research-chain-verify/chainverify"
)

func main() {
	if len(os.Args) != 2 {
		fmt.Fprintln(os.Stderr, "INVALID: usage: research-chain-verify ABSOLUTE_HISTORY_PATH")
		os.Exit(2)
	}
	report, err := chainverify.Verify(os.Args[1])
	if err != nil {
		fmt.Fprintf(os.Stderr, "INVALID: %v\n", err)
		os.Exit(1)
	}
	fmt.Println(report.String())
}
