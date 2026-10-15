/*
 * proto -- tiny frame-protocol parser.
 *
 * stdin is a byte stream of frames:
 *     0xAA <cmd> <len> <payload[len]> <chk>
 * with  len <= 64 and
 *     chk = (cmd*7 + len*3 + sum(payload[i]*(i+1))) & 0xFF
 *
 * For each frame prints one line:
 *     "OK cmd=%02x len=%d chk=%02x\n"     frame valid
 *     "ERR %d sync\n"                     byte != 0xAA at this offset, stop
 *     "ERR %d trunc\n"                    frame cut short at this offset, stop
 *     "ERR %d chk\n"                      bad check byte at this offset, stop
 * After the loop: "DONE %d\n" with the count of valid frames.
 * Always exits 0.
 *
 * This source is judge ground truth.  The agent never sees it; it only sees
 * the stripped binary in targets/.
 */
#include <stdio.h>

static int __attribute__((noinline))
proto_parse(const unsigned char *p, int n)
{
    int off = 0, ok = 0;
    while (off < n) {
        if (p[off] != 0xAA) {
            printf("ERR %d sync\n", off);
            break;
        }
        if (off + 3 > n) {
            printf("ERR %d trunc\n", off);
            break;
        }
        int cmd = p[off + 1];
        int len = p[off + 2];
        if (len > 64 || off + 3 + len + 1 > n) {
            printf("ERR %d trunc\n", off);
            break;
        }
        unsigned int chk = (unsigned int)(cmd * 7 + len * 3);
        for (int i = 0; i < len; i++)
            chk += (unsigned int)(p[off + 3 + i] * (i + 1));
        chk &= 0xFF;
        if (p[off + 3 + len] != chk) {
            printf("ERR %d chk\n", off);
            break;
        }
        printf("OK cmd=%02x len=%d chk=%02x\n", cmd, len, (int)chk);
        ok++;
        off += 3 + len + 1;
    }
    return ok;
}

int main(void)
{
    static unsigned char buf[1 << 20];
    int n = (int)fread(buf, 1, sizeof buf, stdin);
    printf("DONE %d\n", proto_parse(buf, n));
    return 0;
}
