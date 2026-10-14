/*
 * startup.c -- Cortex-M3 bare-metal startup.
 *
 * Provides the vector table, Reset_Handler (SP, .data copy, .bss clear,
 * call into the firmware), and the UART0 IRQ hook.  No libc.
 */
#include "common.h"

/*
 * These are values the linker script computes, not objects.  They are used by
 * address (`&_estack`) to read the value the linker placed there.
 */
extern uint32_t _sidata[], _sdata[], _edata[], _sbss[], _ebss[], _estack[];

void Default_Handler(void)
{
    for (;;) {
        /* traps: an unexpected interrupt lands here and stays here */
    }
}

void Reset_Handler(void)
{
    uint32_t *src = _sidata;
    uint32_t *dst = _sdata;
    uint32_t *end;

    /* copy .data from flash to RAM */
    for (end = _edata; dst < end;) {
        *dst++ = *src++;
    }

    /* zero .bss */
    for (dst = _sbss, end = _ebss; dst < end;) {
        *dst++ = 0;
    }

    kernel_main();

    for (;;) {
        /* if kernel_main ever returns, hold */
    }
}

/* The vector table.  Slot 0 is the initial SP, slot 1 is the reset vector;
 * the rest are the IRQ handlers, mostly Default_Handler except UART0 (IRQ 21).
 * Weak aliases let user code override a single handler without editing this
 * list.
 */
typedef void (*vector_fn)(void);

extern void SysTick_Handler(void) __attribute__((weak, alias("Default_Handler")));
extern void UART0_Handler(void) __attribute__((weak, alias("Default_Handler")));

__attribute__((section(".isr_vector"), used))
const vector_fn g_vector_table[128] = {
    (vector_fn)&_estack,      /*  0 initial stack pointer */
    Reset_Handler,            /*  1 reset */
    Default_Handler,          /*  2 NMI */
    Default_Handler,          /*  3 HardFault */
    Default_Handler,          /*  4 MemManage */
    Default_Handler,          /*  5 BusFault */
    Default_Handler,          /*  6 UsageFault */
    0, 0, 0, 0,               /*  7-10 reserved */
    Default_Handler,          /* 11 SVCall */
    Default_Handler,          /* 12 Debug monitor */
    0,                        /* 13 reserved */
    Default_Handler,          /* 14 PendSV */
    SysTick_Handler,          /* 15 SysTick */
    Default_Handler,          /* 16..  IRQ 0 (first device) is at index 16 */
    Default_Handler,          /* 17    IRQ 1   GPIOA */
    Default_Handler,          /* 18    IRQ 2   GPIOB */
    Default_Handler,          /* 19    IRQ 3   GPIOC */
    Default_Handler,          /* 20    IRQ 4   GPIOD */
    UART0_Handler,            /* 21    IRQ 5   UART0 */
    Default_Handler,          /* 22    IRQ 6   UART1 */
    Default_Handler,          /* 23    IRQ 7   SSI0 */
    Default_Handler,          /* 24    IRQ 8   I2C0 */
    Default_Handler,          /* 25    IRQ 9   PWM fault */
    Default_Handler,          /* 26    IRQ 10  PWM0 */
    Default_Handler,          /* 27    IRQ 11  hibernate */
    Default_Handler,          /* 28    IRQ 12  USB0 */
    Default_Handler,          /* 29    IRQ 13  watchdog */
    Default_Handler,          /* 30    IRQ 14  ADC0 seq 0 */
    Default_Handler,          /* 31    IRQ 15  ADC0 seq 1 */
    Default_Handler,          /* 32    IRQ 16  ADC0 seq 2 */
    Default_Handler,          /* 33    IRQ 17  ADC0 seq 3 */
    Default_Handler,          /* 34    IRQ 18  ADC1 seq 0 */
    Default_Handler,          /* 35    IRQ 19  ADC1 seq 1 */
    Default_Handler,          /* 36    IRQ 20  ADC1 seq 2 */
    Default_Handler,          /* 37    IRQ 21  ADC1 seq 3 */
    Default_Handler,          /* 38    IRQ 22  timers 0a */
    Default_Handler,          /* 39    IRQ 23  timers 0b */
    Default_Handler,          /* 40    IRQ 24  timers 1a */
    Default_Handler,          /* 41    IRQ 25  timers 1b */
    Default_Handler,          /* 42    IRQ 26  timers 2a */
    Default_Handler,          /* 43    IRQ 27  timers 2b */
    Default_Handler,          /* 44    IRQ 28  analog cmp 0 */
    Default_Handler,          /* 45    IRQ 29  analog cmp 1 */
    Default_Handler,          /* 46    IRQ 30  analog cmp 2 */
    Default_Handler,          /* 47    IRQ 31  system control */
    Default_Handler,          /* 48    IRQ 32  flash ctl */
    Default_Handler,          /* 49    IRQ 33  GPIO e-h */
    Default_Handler,          /* 50    IRQ 34  UART1 */
    Default_Handler,          /* 51    IRQ 35  SSI1 */
    Default_Handler,          /* 52    IRQ 36  timers 3a */
    Default_Handler,          /* 53    IRQ 37  timers 3b */
    Default_Handler,          /* 54    IRQ 38  i2c1 */
    Default_Handler,          /* 55    IRQ 39  quadrature 0 */
    Default_Handler,          /* 56    IRQ 40  quadrature 1 */
    Default_Handler,          /* 57    IRQ 41  CAN0 */
    Default_Handler,          /* 58    IRQ 42  CAN1 */
    Default_Handler,          /* 59    IRQ 43  ethernet */
    Default_Handler,          /* 60    IRQ 44  hibernate */
    Default_Handler,          /* 61    IRQ 45  usb */
    Default_Handler,          /* 62    IRQ 46  pwm1 fault */
    Default_Handler,          /* 63    IRQ 47  pwm1 0 */
    Default_Handler,          /* 64    IRQ 48  pwm1 1 */
    Default_Handler,          /* 65    IRQ 49  pwm1 2 */
    Default_Handler,          /* 66    IRQ 50  pwm1 3 */
    Default_Handler,          /* 67    IRQ 51  pwm1 fault */
    Default_Handler,          /* 68    IRQ 52  hibernate */
    Default_Handler,          /* 69    IRQ 53  uDMA software */
    Default_Handler,          /* 70    IRQ 54  uDMA error */
    Default_Handler,          /* 71    IRQ 55 */
    Default_Handler,          /* 72    IRQ 56  AES */
    Default_Handler,          /* 73    IRQ 57  DES3 */
    Default_Handler,          /* 74    IRQ 58  sha md5 */
    /* 75-79 spare */
    Default_Handler,          /* 75 */
    Default_Handler,          /* 76 */
    Default_Handler,          /* 77 */
    Default_Handler,          /* 78 */
    Default_Handler,          /* 79 */
    /* 80-95 pwm */
    Default_Handler,          /* 80 */
    Default_Handler,          /* 81 */
    Default_Handler,          /* 82 */
    Default_Handler,          /* 83 */
    Default_Handler,          /* 84 */
    Default_Handler,          /* 85 */
    Default_Handler,          /* 86 */
    Default_Handler,          /* 87 */
    Default_Handler,          /* 88 */
    Default_Handler,          /* 89 */
    Default_Handler,          /* 90 */
    Default_Handler,          /* 91 */
    Default_Handler,          /* 92 */
    Default_Handler,          /* 93 */
    Default_Handler,          /* 94 */
    Default_Handler,          /* 95 */
    /* 96-111 pwm1 */
    Default_Handler,          /* 96 */
    Default_Handler,          /* 97 */
    Default_Handler,          /* 98 */
    Default_Handler,          /* 99 */
    Default_Handler,          /* 100 */
    Default_Handler,          /* 101 */
    Default_Handler,          /* 102 */
    Default_Handler,          /* 103 */
    Default_Handler,          /* 104 */
    Default_Handler,          /* 105 */
    Default_Handler,          /* 106 */
    Default_Handler,          /* 107 */
    Default_Handler,          /* 108 */
    Default_Handler,          /* 109 */
    Default_Handler,          /* 110 */
    Default_Handler,          /* 111 */
    /* 112-127 spare */
    Default_Handler,          /* 112 */
    Default_Handler,          /* 113 */
    Default_Handler,          /* 114 */
    Default_Handler,          /* 115 */
    Default_Handler,          /* 116 */
    Default_Handler,          /* 117 */
    Default_Handler,          /* 118 */
    Default_Handler,          /* 119 */
    Default_Handler,          /* 120 */
    Default_Handler,          /* 121 */
    Default_Handler,          /* 122 */
    Default_Handler,          /* 123 */
    Default_Handler,          /* 124 */
    Default_Handler,          /* 125 */
    Default_Handler,          /* 126 */
    Default_Handler           /* 127 */
};
