/*
 * cookbook/plc-st scan-cycle engine.
 *
 * Reads one line per scan from stdin:
 *     start estop high_ls low_ls level_cm
 * writes one line after running the compiled controller body once:
 *     pump inlet_valve outlet_valve alarm running
 *
 * The program instance and generated code come from the artifact under test
 * (compiled to POUS.c / RESOURCE.c / <cfg>.c by iec2c in the build dir).
 * This file lives in the judge and is linked against the generated sources.
 */
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#include "iec_types.h"
#include "POUS.h"

/* instance created in RESOURCE.c */
extern TANK_CTRL RESOURCE__P1;
#define P1 RESOURCE__P1

/* generated configuration + program sources (in build dir) */
#include "RESOURCE.c"
#include "tank_cfg.c"

/* the PLC clock the generated runtime reads */
TIME __CURRENT_TIME;

static const long long SCAN_NS = 10LL * 1000 * 1000; /* 10 ms */

int main(void) {
    char line[512];
    long long tick = 0;

    config_init__();
    __CURRENT_TIME = (TIME){0, 0};

    while (fgets(line, sizeof(line), stdin)) {
        int start = 0, estop = 0, high = 0, low = 0;
        double lvl = 0.0;
        if (sscanf(line, "%d %d %d %d %lf", &start, &estop, &high, &low, &lvl) != 5) {
            fprintf(stderr, "engine: bad input line: %s", line);
            return 2;
        }
        P1.START.value   = start ? __BOOL_LITERAL(TRUE) : __BOOL_LITERAL(FALSE);
        P1.ESTOP.value   = estop ? __BOOL_LITERAL(TRUE) : __BOOL_LITERAL(FALSE);
        P1.HIGH_LS.value = high  ? __BOOL_LITERAL(TRUE) : __BOOL_LITERAL(FALSE);
        P1.LOW_LS.value  = low   ? __BOOL_LITERAL(TRUE) : __BOOL_LITERAL(FALSE);
        P1.LEVEL.value   = lvl;

        config_run__((unsigned long)tick++);
        __CURRENT_TIME = (TIME){ (tick * SCAN_NS) / 1000000000LL,
                                 (tick * SCAN_NS) % 1000000000LL };

        printf("%d %d %d %d %d\n",
               (int)P1.PUMP.value,
               (int)P1.INLET_VALVE.value,
               (int)P1.OUTLET_VALVE.value,
               (int)P1.ALARM.value,
               (int)P1.RUNNING.value);
        fflush(stdout);
    }
    return 0;
}