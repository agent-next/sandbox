/*
 * main.c -- firmware entry point.
 *
 * Boots, prints the banner, then serves the UART shell forever.
 */
#include "common.h"

static const char banner[] =
    "firmware-qemu 1.0 cortex-m3 lm3s6965evb ready\r\n";

void kernel_main(void)
{
    uart_init();
    shell_init();

    /* The UART receive path is interrupt driven, so interrupts must be on
     * before the first byte can arrive. */
    irq_enable();

    uart_write(banner, sizeof(banner) - 1u);

    for (;;) {
        shell_poll();
    }
}
