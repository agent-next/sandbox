/*
 * checksum -- reads stdin, prints a custom 64-bit checksum as 16 lowercase
 * hex digits followed by a newline.  Always exits 0.
 *
 * This source is judge ground truth.  The agent never sees it; it only sees
 * the stripped binary in targets/.
 */
#include <stdint.h>
#include <stdio.h>

static uint64_t __attribute__((noinline))
checksum_update(uint64_t h, const unsigned char *p, size_t n)
{
    for (size_t i = 0; i < n; i++) {
        h ^= p[i];
        h = (h << 5) | (h >> 59);
        h += 0x9E3779B97F4A7C15ULL;
        h ^= h >> 29;
    }
    return h;
}

int main(void)
{
    static unsigned char buf[1 << 20];
    size_t n = fread(buf, 1, sizeof buf, stdin);
    printf("%016llx\n",
           (unsigned long long)checksum_update(0xCBF29CE484222325ULL, buf, n));
    return 0;
}
