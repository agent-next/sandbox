/*
 * keycheck -- licence-key checker with a hidden rule.
 *
 * stdin supplies one line: a key of the form XXXXX-XXXXX-XXXXX (17 bytes)
 * over the alphabet "ABCDEFGHJKLMNPQRSTUVWXYZ23456789" (32 symbols).
 * Values v[0..14] are the alphabet indices of the 15 key characters.
 * The key is accepted iff ALL of:
 *     (v[0] + v[5] + v[10]) % 32 == 9
 *     v[7] == (v[0] ^ v[14])
 *     sum(v[i] * (i % 5 + 1)) % 29 == 11
 *
 * Prints "OK\n" and exits 0 when accepted, else "DENIED\n" and exits 1.
 *
 * This source is judge ground truth.  The agent never sees it; it only sees
 * the stripped binary in targets/.
 */
#include <stdio.h>
#include <string.h>

static const char ALPHA[] = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";

static int alpha_value(int c)
{
    const char *q = strchr(ALPHA, c);
    return q ? (int)(q - ALPHA) : -1;
}

static int __attribute__((noinline))
key_verify(const char *key)
{
    int v[15];
    int i, j = 0;
    long w = 0;

    if (strlen(key) != 17 || key[5] != '-' || key[11] != '-')
        return 0;
    for (i = 0; i < 17; i++) {
        if (i == 5 || i == 11)
            continue;
        v[j] = alpha_value((unsigned char)key[i]);
        if (v[j] < 0)
            return 0;
        w += (long)v[j] * (j % 5 + 1);
        j++;
    }
    if ((v[0] + v[5] + v[10]) % 32 != 9)
        return 0;
    if (v[7] != (v[0] ^ v[14]))
        return 0;
    if (w % 29 != 11)
        return 0;
    return 1;
}

int main(void)
{
    char key[64];
    if (!fgets(key, sizeof key, stdin)) {
        puts("DENIED");
        return 1;
    }
    key[strcspn(key, "\r\n")] = '\0';
    if (key_verify(key)) {
        puts("OK");
        return 0;
    }
    puts("DENIED");
    return 1;
}
