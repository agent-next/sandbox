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

    bool have_req = false;        // a request is being served (latency running)
    int wait_count = 0;           // stall cycles still to impose on it
    uint64_t fetches = 0, cycles = 0;
    uint32_t tohost = 0;
    bool have_tohost = false, trapped = false;
    bool trap_drain = false;     // request in flight when trap asserted (allowed to drain)
    int trap_cycle = -1;
    int post_trap_stores = 0;     // bus activity issued after trap (must be 0)

    // reset for 8 cycles
    for (int i = 0; i < 8; i++) {
        top->clk = 0; top->eval();
        top->clk = 1; top->eval();
    }
    top->resetn = 1;
    top->eval();

    for (cycles = 0; cycles < max_cycles && !have_tohost; cycles++) {
        // Combinational memory response, settled before the posedge so the
        // CPU samples mem_ready/mem_rdata exactly at the completing edge.
        bool ready_this = false;
        if (top->mem_valid) {
            if (!have_req) {
                // new request: draw its mem_ready latency from the PRNG
                have_req = true;
                wait_count = latency ? (int)(rng() % 8) : 0;
            }
            if (wait_count > 0) {
                wait_count--;
            } else {
                ready_this = true;
            }
        } else {
            have_req = false;
            wait_count = 0;
        }

        top->mem_ready = ready_this ? 1 : 0;
        // SPEC: mem_rdata is valid only in the cycle mem_ready is high.
        top->mem_rdata = 0;
        if (ready_this && (top->mem_addr >> 2) < MEM_WORDS)
            top->mem_rdata = mem[top->mem_addr >> 2];
        top->clk = 0; top->eval();

        if (top->mem_valid && ready_this) {
            // transaction completes at the upcoming posedge
            uint32_t a = top->mem_addr;
            uint8_t ws = top->mem_wstrb & 0xF;
            if (top->mem_instr) fetches++;
            if (ws) {
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
            have_req = false;      // next valid, even back-to-back, is a new request
            if (trapped) trap_drain = false;  // the in-flight request drained
        }
        top->clk = 1; top->eval();   // posedge: cpu samples mem_ready/mem_rdata

        if (top->trap && !trapped) {
            trapped = true;
            trap_cycle = (int)cycles;
            // a request already in flight when trap asserted may drain; only
            // requests *newly issued* after trap violate "no state change"
            trap_drain = top->mem_valid;
        }
        // "no state change after trap": watch 32 cycles, then require quiet.
        // A new request issued after trap (mem_valid rose again after the
        // in-flight one drained) is a hard failure.
        if (trapped) {
            if (!top->mem_valid) trap_drain = false;
            else if (!trap_drain) post_trap_stores++;
            if (cycles - (uint64_t)trap_cycle >= 32) break;
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
