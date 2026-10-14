// Verilator testbench for the fpga-agent-loop judge.
//
// Models the 64 KiB RAM, the tohost write at 0x10000000, trap detection,
// and (with --latency) a mem_ready delay of 0-7 stall cycles drawn from a
// seeded PRNG (SPEC G4). Prints exactly one RESULT line:
//
//   RESULT <PASS|FAIL|TRAP|TIMEOUT|QUIET-FAIL> TOHOST=0x........ CYCLES=n FETCHES=n
//
// Usage:
//   sim_cpu --hex prog.hex [--seed N] [--latency] [--max-cycles N]
//           [--dump out.hex] [--expect-trap]

#include "Vcpu.h"
#include "verilated.h"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <random>
#include <string>
#include <vector>

static const uint32_t MEM_WORDS = 64 * 1024 / 4;
static const uint32_t TOHOST_ADDR = 0x10000000u;

static bool load_memh(const char* path, std::vector<uint32_t>& mem) {
    FILE* f = fopen(path, "r");
    if (!f) return false;
    uint32_t addr = 0;
    char tok[64];
    while (fscanf(f, "%63s", tok) == 1) {
        if (tok[0] == '@') {
            addr = (uint32_t)strtoul(tok + 1, nullptr, 16);
        } else {
            uint32_t w = (uint32_t)strtoul(tok, nullptr, 16);
            if (addr < MEM_WORDS) mem[addr] = w;
            addr++;
        }
    }
    fclose(f);
    return true;
}

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);

    const char* hex = nullptr;
    const char* dump = nullptr;
    uint32_t seed = 1;
    uint64_t max_cycles = 200000;
    bool latency = false;
    bool expect_trap = false;

    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--hex")) hex = argv[++i];
        else if (!strcmp(argv[i], "--dump")) dump = argv[++i];
        else if (!strcmp(argv[i], "--seed")) seed = (uint32_t)strtoul(argv[++i], nullptr, 0);
        else if (!strcmp(argv[i], "--max-cycles")) max_cycles = strtoull(argv[++i], nullptr, 0);
        else if (!strcmp(argv[i], "--latency")) latency = true;
        else if (!strcmp(argv[i], "--expect-trap")) expect_trap = true;
    }
    if (!hex) {
        fprintf(stderr, "missing --hex\n");
        return 2;
    }

    std::vector<uint32_t> mem(MEM_WORDS, 0);
    if (!load_memh(hex, mem)) {
        fprintf(stderr, "cannot read %s\n", hex);
        return 2;
    }

    std::mt19937 rng(seed);
    Vcpu* top = new Vcpu;
    top->clk = 0;
    top->resetn = 0;
    top->mem_ready = 0;
    top->mem_rdata = 0;
    top->eval();

    int wait_count = -1;          // -1 = no pending request
    bool ready_now = false;
    uint32_t rdata_now = 0;
    uint64_t fetches = 0, cycles = 0;
    uint32_t tohost = 0;
    bool have_tohost = false, trapped = false;
    int trap_cycle = -1;
    int post_trap_stores = 0;     // stores completed after trap (must be 0)

    // reset for 8 cycles
    for (int i = 0; i < 8; i++) {
        top->clk = 0; top->eval();
        top->clk = 1; top->eval();
    }
    top->resetn = 1;

    for (cycles = 0; cycles < max_cycles && !have_tohost; cycles++) {
        // drive inputs for the upcoming posedge
        top->mem_ready = ready_now ? 1 : 0;
        top->mem_rdata = rdata_now;
        top->clk = 0; top->eval();
        top->clk = 1; top->eval();   // posedge: cpu samples mem_ready/mem_rdata

        bool v = top->mem_valid;
        bool r = ready_now;
        if (v && r) {
            // transaction completes this posedge
            uint32_t a = top->mem_addr;
            uint8_t ws = top->mem_wstrb & 0xF;
            if (top->mem_instr) fetches++;
            if (ws) {
                if (trapped) post_trap_stores++;
                if (a == TOHOST_ADDR) {
                    tohost = top->mem_wdata;
                    have_tohost = true;
                } else if ((a >> 2) < MEM_WORDS) {
                    uint32_t& w = mem[a >> 2];
                    if (ws & 1) w = (w & 0xFFFFFF00) | (top->mem_wdata & 0xFF);
                    if (ws & 2) w = (w & 0xFFFF00FF) | (top->mem_wdata & 0xFF00);
                    if (ws & 4) w = (w & 0xFF00FFFF) | (top->mem_wdata & 0xFF0000);
                    if (ws & 8) w = (w & 0x00FFFFFF) | (top->mem_wdata & 0xFF000000);
                }
            }
            wait_count = -1;
            ready_now = false;
        } else if (v) {
            if (wait_count < 0) wait_count = latency ? (int)(rng() % 8) : 0;
            if (wait_count == 0) {
                ready_now = true;
                uint32_t a = top->mem_addr;
                rdata_now = ((a >> 2) < MEM_WORDS) ? mem[a >> 2] : 0;
            } else {
                wait_count--;
                ready_now = false;
            }
        } else {
            ready_now = false;
        }

        if (top->trap && !trapped) {
            trapped = true;
            trap_cycle = (int)cycles;
        }
        // "no state change after trap": watch 32 cycles, then require quiet
        if (trapped && cycles - (uint64_t)trap_cycle >= 32) {
            if (!top->mem_valid) post_trap_stores += 0;  // quiet, good
            else post_trap_stores++;                     // still issuing: bad
            break;
        }
    }

    const char* status;
    if (expect_trap) {
        status = (trapped && post_trap_stores == 0) ? "PASS" : "FAIL";
    } else if (trapped) {
        status = "TRAP";
    } else if (!have_tohost) {
        status = "TIMEOUT";
    } else {
        status = (tohost == 1) ? "PASS" : "FAIL";
    }

    if (dump) {
        FILE* f = fopen(dump, "w");
        if (f) {
            fprintf(f, "@0\n");
            for (uint32_t i = 0; i < MEM_WORDS; i++)
                fprintf(f, "%08x\n", mem[i]);
            fclose(f);
        }
    }

    printf("RESULT %s TOHOST=0x%08x CYCLES=%llu FETCHES=%llu\n",
           status, have_tohost ? tohost : 0,
           (unsigned long long)cycles, (unsigned long long)fetches);
    delete top;
    return 0;
}
