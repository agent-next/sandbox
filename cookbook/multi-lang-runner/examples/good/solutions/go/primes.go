package main

import (
	"bufio"
	"fmt"
	"os"
	"strconv"
	"strings"
)

func main() {
	sc := bufio.NewScanner(os.Stdin)
	sc.Scan()
	parts := strings.Fields(sc.Text())
	lo, _ := strconv.Atoi(parts[0])
	hi, _ := strconv.Atoi(parts[1])
	if hi < 2 {
		fmt.Println(0)
		return
	}
	sieve := make([]bool, hi+1)
	for i := 2; i*i <= hi; i++ {
		if !sieve[i] {
			for j := i * i; j <= hi; j += i {
				sieve[j] = true
			}
		}
	}
	count := 0
	for i := lo; i <= hi; i++ {
		if i >= 2 && !sieve[i] {
			count++
		}
	}
	fmt.Println(count)
}
