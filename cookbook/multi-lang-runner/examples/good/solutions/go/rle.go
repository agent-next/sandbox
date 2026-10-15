package main

import (
	"bufio"
	"fmt"
	"os"
)

func main() {
	sc := bufio.NewScanner(os.Stdin)
	sc.Scan()
	s := sc.Text()
	if s == "" {
		return
	}
	w := bufio.NewWriter(os.Stdout)
	defer w.Flush()
	prev := s[0]
	count := 1
	for i := 1; i < len(s); i++ {
		if s[i] == prev {
			count++
		} else {
			fmt.Fprintf(w, "%d%c", count, prev)
			prev = s[i]
			count = 1
		}
	}
	fmt.Fprintf(w, "%d%c", count, prev)
	fmt.Fprintln(w)
}
