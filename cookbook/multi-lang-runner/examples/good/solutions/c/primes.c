#include <stdio.h>
#include <stdlib.h>

int main(void) {
    int lo, hi;
    if (scanf("%d %d", &lo, &hi) != 2) return 1;
    if (hi < 2) { printf("0\n"); return 0; }
    char *sieve = calloc(hi + 1, 1);
    if (!sieve) return 1;
    for (int i = 2; (long long)i * i <= hi; i++) {
        if (!sieve[i]) {
            for (int j = i * i; j <= hi; j += i) sieve[j] = 1;
        }
    }
    int count = 0;
    for (int i = lo; i <= hi; i++) {
        if (i >= 2 && !sieve[i]) count++;
    }
    printf("%d\n", count);
    free(sieve);
    return 0;
}
