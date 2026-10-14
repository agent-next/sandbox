// No-CSR riscv_test.h for the fpga-agent-loop judge.
//
// Replaces riscv-tests' env/p/riscv_test.h for the rv32ui suite.
// Same macro surface, but PASS/FAIL are pure RV32I stores to the
// memory-mapped tohost address 0x1000_0000 instead of CSRs/ecall:
//   PASS: store 1
//   FAIL: store (TESTNUM << 1) | 1
//
// Included via -I<judge dir> when compiling judge/tests sources.

#ifndef _JUDGE_RISCV_TEST_H
#define _JUDGE_RISCV_TEST_H

#define TESTNUM gp

// "init" macro hook used by RVTEST_CODE_BEGIN; rv32ui tests only need
// the RV32U/RV64U variants but the others are defined for completeness.
#define RVTEST_RV64U    .macro init; .endm
#define RVTEST_RV32U    .macro init; .endm
#define RVTEST_RV64UF   .macro init; .endm
#define RVTEST_RV32UF   .macro init; .endm
#define RVTEST_RV64UV   .macro init; .endm
#define RVTEST_RV32UV   .macro init; .endm
#define RVTEST_RV64UVX  .macro init; .endm
#define RVTEST_RV32UVX  .macro init; .endm
#define RVTEST_RV64M    .macro init; .endm
#define RVTEST_RV32M    .macro init; .endm
#define RVTEST_RV64S    .macro init; .endm
#define RVTEST_RV32S    .macro init; .endm

#define INIT_XREG                               \
        li x1, 0; li x2, 0; li x3, 0; li x4, 0;  \
        li x5, 0; li x6, 0; li x7, 0; li x8, 0;  \
        li x9, 0; li x10, 0; li x11, 0; li x12, 0;\
        li x13, 0; li x14, 0; li x15, 0; li x16, 0;\
        li x17, 0; li x18, 0; li x19, 0; li x20, 0;\
        li x21, 0; li x22, 0; li x23, 0; li x24, 0;\
        li x25, 0; li x26, 0; li x27, 0; li x28, 0;\
        li x29, 0; li x30, 0; li x31, 0;

#define EXTRA_INIT
#define EXTRA_DATA

#define RVTEST_CODE_BEGIN                       \
        .section .text.init;                    \
        .align 6;                               \
        .globl _start;                          \
_start:                                         \
        INIT_XREG;                              \
        li TESTNUM, 0;                          \
        init;                                   \
        EXTRA_INIT;

#define RVTEST_CODE_END                         \
        1: j 1b

#define RVTEST_PASS                             \
        fence;                                  \
        li TESTNUM, 1;                          \
        li t6, 0x10000000;                      \
        sw TESTNUM, 0(t6);                      \
        1: j 1b

#define RVTEST_FAIL                             \
        fence;                                  \
        1: beqz TESTNUM, 1b;                    \
        slli TESTNUM, TESTNUM, 1;               \
        ori TESTNUM, TESTNUM, 1;                \
        li t6, 0x10000000;                      \
        sw TESTNUM, 0(t6);                      \
        2: j 2b

// Signature symbols kept for compatibility with test_macros.h.
// tohost/fromhost exist only as data labels; the pass/fail path above
// uses the absolute MMIO address and never touches them.
#define RVTEST_DATA_BEGIN                       \
        EXTRA_DATA                              \
        .align 6;                               \
        .global tohost;  tohost:   .dword 0;    \
        .global fromhost; fromhost: .dword 0;   \
        .align 4;                               \
        .global begin_signature; begin_signature:

#define RVTEST_DATA_END                         \
        .align 4;                               \
        .global end_signature; end_signature:

#endif
