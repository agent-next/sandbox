package main

import (
	"bufio"
	"fmt"
	"os"
	"strconv"
)

func main() {
	sc := bufio.NewScanner(os.Stdin)
	sc.Split(bufio.ScanWords)
	sc.Scan()
	n, _ := strconv.Atoi(sc.Text())
	total := int64(0)
	for i := 0; i < n; i++ {
		sc.Scan()
		x, _ := strconv.ParseInt(sc.Text(), 10, 64)
		total += x * x
		if total > 1_000_000_000_000_000_000 {
			total = 1_000_000_000_000_000_000
			break
		}
	}
	fmt.Println(total)
}
