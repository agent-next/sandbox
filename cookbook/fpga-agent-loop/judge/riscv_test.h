/* No-CSR riscv_test.h for fpga-agent-loop judge
 * Replaces the standard test harness to store results to tohost
 * PASS: 1
 * FAIL: (testnum << 1) | 1
 */

#include <stdint.h>

/* tohost address - from SPEC: stores to 0x1000_0000 end the test */
#define TOHOST_ADDR 0x10000000

/* Standard test macros redefined for tohost */
#define TEST_START() \
    do { \
        *(volatile uint32_t*)TOHOST_ADDR = 0; \
    } while(0)

#define TEST_PASS() \
    do { \
        *(volatile uint32_t*)TOHOST_ADDR = 1; \
        break; \
    } while(0)

#define TEST_FAIL(testnum) \
    do { \
        *(volatile uint32_t*)TOHOST_ADDR = ((testnum) << 1) | 1; \
        break; \
    } while(0)

#define TEST_CODE() /* Empty - no special test code needed */

#include "rvtest/rvtest.h"
