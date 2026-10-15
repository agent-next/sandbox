#include <stdio.h>
#include <stdlib.h>

int main(void) {
    int n;
    if (scanf("%d", &n) != 1) return 1;
    long long total = 0;
    long long cap = 1000000000000000000LL;
    for (int i = 0; i < n; i++) {
        long long x;
        scanf("%lld", &x);
        total += x * x;
        if (total > cap) { total = cap; break; }
    }
    printf("%lld\n", total);
    return 0;
}
