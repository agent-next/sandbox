/*
 * shell.c -- command shell over the UART.
 *
 * Reads lines from the UART, splits them into tokens, runs one command and
 * writes exactly one response line.  No libc string functions: this is bare
 * metal, so `str_eq` is local.
 */
#include "common.h"

#define OUT_MAX  512u

static char in_line[LINE_MAX];
static size_t in_len;
static int pending_cr;
static ring_t rb_storage;    /* the software ring the `RB` commands drive */

static void run_line(void);

static const char hexd[] = "0123456789abcdef";

static int str_eq(const char *a, const char *b)
{
    while (*a && *b) {
        if (*a != *b) {
            return 0;
        }
        a++;
        b++;
    }
    return *a == *b;
}

static int hexval(int c)
{
    if (c >= '0' && c <= '9') {
        return c - '0';
    }
    if (c >= 'a' && c <= 'f') {
        return c - 'a' + 10;
    }
    if (c >= 'A' && c <= 'F') {
        return c - 'A' + 10;
    }
    return -1;
}

static int is_space(int c)
{
    return c == ' ' || c == '\t';
}

/* Decode a hex string into buf; returns -1 on a bad argument. */
static int hexdecode(const char *s, uint8_t *buf, size_t bufsz, size_t *outlen)
{
    size_t n = 0;
    while (s[0] != '\0') {
        int hi, lo;
        if (s[1] == '\0') {
            return -1;                      /* odd length */
        }
        hi = hexval(s[0]);
        lo = hexval(s[1]);
        if (hi < 0 || lo < 0) {
            return -1;
        }
        if (n >= bufsz) {
            return -1;
        }
        buf[n++] = (uint8_t)((hi << 4) | lo);
        s += 2;
    }
    *outlen = n;
    return 0;
}

static char *out_str(char *p, char *end, const char *s)
{
    while (*s && p < end) {
        *p++ = *s++;
    }
    return p;
}

static char *out_hex8(char *p, uint32_t v)
{
    int i;
    *p++ = '0';
    *p++ = 'x';
    for (i = 7; i >= 0; i--) {
        *p++ = hexd[(v >> (unsigned)(i * 4)) & 0xFu];
    }
    return p;
}

static char *out_dec(char *p, unsigned v)
{
    char tmp[12];
    int n = 0;
    int i;
    do {
        tmp[n++] = (char)('0' + (int)(v % 10u));
        v /= 10u;
    } while (v != 0u);
    for (i = n - 1; i >= 0; i--) {
        *p++ = tmp[i];
    }
    return p;
}

/*
 * Copies the want-th whitespace-separated token of line into tok, NUL-terminated.
 * Non-destructive to line, so the caller may fetch several tokens in turn.
 * Returns 0 if the token exists, -1 otherwise.
 */
static int token(const char *line, int want, char *tok, size_t tokcap)
{
    int n = 0;
    const char *s = line;
    size_t k = 0;

    if (tokcap == 0u) {
        return -1;
    }
    for (;;) {
        while (*s != '\0' && is_space(*s)) {
            s++;
        }
        if (*s == '\0') {
            return -1;
        }
        if (n == want) {
            while (*s != '\0' && !is_space(*s) && k + 1u < tokcap) {
                tok[k++] = *s++;
            }
            tok[k] = '\0';
            return 0;
        }
        while (*s != '\0' && !is_space(*s)) {
            s++;
        }
        n++;
    }
}

int shell_exec(const char *line, char *out, size_t outsz)
{
    static uint8_t hexbuf[2048];
    static char work[LINE_MAX];
    static char t0[LINE_MAX];
    static char t1[LINE_MAX];
    static char t2[LINE_MAX];
    char *p = out;
    char *end = out + outsz - 8u;
    size_t i = 0;
    size_t hexlen = 0;
    uint32_t crc = 0;

    if (outsz < 8u) {
        return 0;
    }

    /* local copy, so the caller's line is untouched */
    while (line[i] != '\0' && i + 1u < sizeof(work)) {
        work[i] = line[i];
        i++;
    }
    work[i] = '\0';

    t0[0] = t1[0] = t2[0] = '\0';
    (void)token(work, 0, t0, sizeof(t0));
    (void)token(work, 1, t1, sizeof(t1));
    (void)token(work, 2, t2, sizeof(t2));

    if (str_eq(t0, "HELP")) {
        p = out_str(p, end, "OK commands: HELP VER ID CRC RB PING ECHO");
    } else if (str_eq(t0, "VER")) {
        p = out_str(p, end, "OK firmware-qemu 1.0 cortex-m3");
    } else if (str_eq(t0, "ID")) {
        p = out_str(p, end, "OK lm3s6965evb");
    } else if (str_eq(t0, "PING")) {
        p = out_str(p, end, "OK pong");
    } else if (str_eq(t0, "CRC")) {
        if (t1[0] == '\0' || hexdecode(t1, hexbuf, sizeof(hexbuf), &hexlen) != 0) {
            p = out_str(p, end, "ERR bad hex");
        } else {
            crc = crc32_ieee(hexbuf, hexlen);
            p = out_str(p, end, "OK ");
            p = out_hex8(p, crc);
        }
    } else if (str_eq(t0, "RB")) {
        if (str_eq(t1, "push")) {
            if (t2[0] == '\0' || hexdecode(t2, hexbuf, sizeof(hexbuf), &hexlen) != 0) {
                p = out_str(p, end, "ERR bad hex");
            } else {
                size_t k;
                for (k = 0; k < hexlen; k++) {
                    rb_push(&rb_storage, hexbuf[k]);
                }
                p = out_str(p, end, "OK ");
                p = out_dec(p, rb_count(&rb_storage));
            }
        } else if (str_eq(t1, "pop")) {
            if (rb_pop(&rb_storage) < 0) {
                p = out_str(p, end, "ERR empty");
            } else {
                p = out_str(p, end, "OK ");
                p = out_dec(p, rb_count(&rb_storage));
            }
        } else if (str_eq(t1, "count")) {
            p = out_str(p, end, "OK ");
            p = out_dec(p, rb_count(&rb_storage));
        } else if (str_eq(t1, "clear")) {
            rb_clear(&rb_storage);
            p = out_str(p, end, "OK 0");
        } else if (str_eq(t1, "dump")) {
            unsigned k;
            unsigned n = rb_count(&rb_storage);
            unsigned first = 1u;
            ring_t tmp = rb_storage;
            p = out_str(p, end, "OK ");
            for (k = 0; k < n; k++) {
                int b = rb_pop(&tmp);
                if (p + 3u > end) {
                    break;
                }
                if (first == 0u) {
                    *p++ = ' ';
                }
                first = 0u;
                *p++ = hexd[(b >> 4) & 0xF];
                *p++ = hexd[b & 0xF];
            }
        } else {
            p = out_str(p, end, "ERR unknown");
        }
    } else if (str_eq(t0, "ECHO")) {
        /*
         * Echo everything after the command word, internal whitespace intact:
         * that is the whole point of the command, and it exercises the
         * tokeniser on input that is not token-shaped.  `t1` is the second
         * token, so the reply has to be built from the line itself: skip past
         * the command word, then past the whitespace that followed it.
         */
        const char *arg = line + 4;      /* skip "ECHO" */
        while (*arg == ' ' || *arg == '\t') {
            arg++;
        }
        if (*arg == '\0') {
            p = out_str(p, end, "ERR unknown");
        } else {
            p = out_str(p, end, "OK ");
            p = out_str(p, end, arg);
        }
    } else if (t0[0] == '\0') {
        p = out_str(p, end, "ERR empty");
    } else {
        p = out_str(p, end, "ERR unknown");
    }

    if (p + 2u <= end + 2u) {
        *p++ = '\r';
        *p++ = '\n';
    }
    *p = '\0';
    return (int)(p - out);
}

void shell_init(void)
{
    rb_init(&rb_storage, RB_CAP);
    in_len = 0;
    pending_cr = 0;
}

/* Run whatever has accumulated in in_line, then start a fresh one. */
static void run_line(void)
{
    static char out[OUT_MAX];
    int n;

    in_line[in_len] = '\0';
    n = shell_exec(in_line, out, sizeof(out));
    uart_write(out, (size_t)n);
    in_len = 0;
}

void shell_poll(void)
{
    int c = uart_getc();
    if (c < 0) {
        return;
    }
    if (c == '\r') {
        /*
         * CR ends a line.  CRLF is one terminator, not two: if a LF arrives
         * straight after, it is swallowed rather than running an empty line.
         */
        pending_cr = 1;
        run_line();
        return;
    }
    if (c == '\n') {
        if (pending_cr != 0) {
            pending_cr = 0;
            return;
        }
        run_line();
        return;
    }
    pending_cr = 0;
    if (in_len + 1u < sizeof(in_line)) {
        in_line[in_len++] = (char)c;
    }
}
