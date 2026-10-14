/*
 * uart.c -- Stellaris UART0 driver (polled TX, interrupt-driven RX).
 *
 * Register map from the LM3S6965 datasheet.  QEMU wires UART0 to the
 * `-serial` backend, so a byte written here appears on the emulator's serial
 * port and a byte typed there arrives in the receive register.
 */
#include "common.h"

#define UART0_BASE    0x4000C000u

#define UART_DR       (*(volatile uint32_t *)(UART0_BASE + 0x000u))
#define UART_RSR      (*(volatile uint32_t *)(UART0_BASE + 0x004u))
#define UART_FR       (*(volatile uint32_t *)(UART0_BASE + 0x018u))
#define UART_IBRD     (*(volatile uint32_t *)(UART0_BASE + 0x024u))
#define UART_FBRD     (*(volatile uint32_t *)(UART0_BASE + 0x028u))
#define UART_LCRH     (*(volatile uint32_t *)(UART0_BASE + 0x02Cu))
#define UART_CTL      (*(volatile uint32_t *)(UART0_BASE + 0x030u))
#define UART_IM       (*(volatile uint32_t *)(UART0_BASE + 0x038u))
#define UART_ICR      (*(volatile uint32_t *)(UART0_BASE + 0x044u))
#define UART_ILPR     (*(volatile uint32_t *)(UART0_BASE + 0x020u))

#define FR_BUSY       (1u << 3)
#define FR_RXFE       (1u << 4)
#define FR_TXFF       (1u << 5)

#define LCRH_WLEN_8   (0x3u << 5)
#define LCRH_FEN      (1u << 4)

#define CTL_UARTEN    (1u << 0)
#define CTL_TXE       (1u << 8)
#define CTL_RXE       (1u << 9)

#define IM_RXIM       (1u << 4)
#define IM_RTIM       (1u << 6)

#define ICR_RXIC      (1u << 4)
#define ICR_RTIC      (1u << 6)

/*
 * Received bytes land in this ring; the shell drains it.  A whole pasted line
 * can arrive faster than one shell poll consumes it, so the ring has to be at
 * least as large as the longest line the shell can buffer.
 */
#define RX_RING_CAP (LINE_MAX + 16u)

static ring_t rx_ring;

void uart_init(void)
{
    unsigned divider;

    /* 8 data bits, enable the FIFOs. */
    UART_LCRH = LCRH_WLEN_8 | LCRH_FEN;
    UART_ILPR = 0;                     /* no irda */

    divider = (CPU_HZ * 4u) / UART_BAUD;
    UART_IBRD = divider >> 6;
    UART_FBRD = divider & 0x3Fu;

    rb_init(&rx_ring, RX_RING_CAP);

    /* Arm the receive interrupts.  On QEMU's lm3s6965evb these never fire, so
     * rx_fill() below is what actually moves bytes; the handler is kept
     * correct for real hardware, where the poll would race the FIFO. */
    UART_IM = IM_RXIM | IM_RTIM;
    UART_ICR = ICR_RXIC | ICR_RTIC;

    UART_CTL = CTL_UARTEN | CTL_TXE | CTL_RXE;
}

void uart_putc(char c)
{
    while (UART_FR & FR_TXFF) {
        /* wait for room in the transmit FIFO */
    }
    UART_DR = (uint32_t)(unsigned char)c;
}

void uart_write(const char *p, size_t n)
{
    size_t i;
    for (i = 0; i < n; i++) {
        uart_putc(p[i]);
    }
}

void uart_puts(const char *s)
{
    while (*s) {
        uart_putc(*s++);
    }
}

/*
 * Move everything the hardware FIFO is holding into the ring.  Called by
 * uart_getc(), because on QEMU's lm3s6965evb the receive interrupt never
 * fires and the only thing that moves bytes is a poll.
 */
static void rx_fill(void)
{
    unsigned guard;

    /* the FIFO is 16 deep; the guard stops a stuck flag spinning forever */
    for (guard = 0; guard < 64u; guard++) {
        uint8_t b;
        if (UART_FR & FR_RXFE) {
            break;
        }
        b = (uint8_t)(UART_DR & 0xFFu);
        rb_push(&rx_ring, b);
    }
}

int uart_getc(void)
{
    int b;

    /* Drain the hardware into the ring first, then take the oldest byte.
     * A byte already here (published by the IRQ) is never read twice, because
     * the FIFO read is what fills the ring. */
    rx_fill();
    b = rb_pop(&rx_ring);
    if (b >= 0) {
        return b;
    }
    return -1;
}

/*
 * UART0 is IRQ 5 on the LM3S6965, which is vector index 16 + 5 = 21.  QEMU's
 * lm3s6965evb never asserts that line, so this is never entered here; it is
 * kept because it is the correct handler for the real part, and it publishes
 * to the same ring the shell already drains.
 */
void UART0_Handler(void)
{
    rx_fill();
    UART_ICR = ICR_RXIC | ICR_RTIC;
}
