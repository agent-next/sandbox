/*
 * common.h -- shared declarations for the firmware-qemu demo artifact.
 *
 * Bare-metal C for the Stellaris/TI LM3S6965 EVB board as emulated by
 * QEMU (`-M lm3s6965evb`).  No libc, no OS, no dynamic allocation.
 */
#ifndef COMMON_H
#define COMMON_H

#include <stddef.h>
#include <stdint.h>

/* ---------------------------------------------------------------- board --- */
#define CPU_HZ      12000000u   /* crystal on the LM3S6965 EVB */
#define UART_BAUD   115200u

/* ---------------------------------------------------------------- limits -- */
#define LINE_MAX    256u        /* one command line, including NUL */
#define TOKEN_MAX   8u          /* whitespace-separated words in a line */
#define RB_CAP      16u         /* ring buffer capacity, bytes */

/* ------------------------------------------------------------ ring buffer */
/*
 * One ring type, many capacities: the shell's `RB` ring is RB_CAP bytes, the
 * UART receive ring has to swallow a whole pasted line at once and is sized
 * by its owner.  `cap` is how much of `buf` the ring is allowed to use.
 */
#define RB_MAX_CAP 288u

typedef struct {
    uint8_t  buf[RB_MAX_CAP];
    unsigned head;
    unsigned tail;
    unsigned count;
    unsigned cap;
} ring_t;

void     rb_init(ring_t *r, unsigned cap);
int      rb_push(ring_t *r, uint8_t b);       /* -> count after push */
int      rb_pop(ring_t *r);                   /* -> 0..255, or -1 if empty */
int      rb_peek(const ring_t *r);            /* -> oldest byte, or -1 */
unsigned rb_count(const ring_t *r);
void     rb_clear(ring_t *r);

/* -------------------------------------------------------------------- crc */
uint32_t crc32_ieee(const uint8_t *data, size_t len);

/* ------------------------------------------------------------------- uart */
void uart_init(void);
void uart_putc(char c);
void uart_puts(const char *s);
void uart_write(const char *p, size_t n);
int  uart_getc(void);              /* non-blocking; -1 when nothing to read */

/* ------------------------------------------------------------------ shell */
void shell_init(void);
void shell_poll(void);            /* consume at most one received byte */
int  shell_exec(const char *line, char *out, size_t outsz); /* -> out len */

/* ---------------------------------------------------------------- startup */
void kernel_main(void);

/* Cortex-M3 primitive. */
static inline void irq_enable(void)
{
    __asm__ volatile("cpsie i" ::: "memory");
}

#endif /* COMMON_H */
