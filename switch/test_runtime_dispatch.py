# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent


class RuntimeDispatchTests(unittest.TestCase):
    def test_dispatch_faults_and_guest_state_abi(self):
        compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
        if not compiler:
            self.skipTest("host C compiler unavailable")
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            harness = temp / "runtime_test.c"
            harness.write_text(r'''#include "switch/runtime/bbr_runtime.h"
#include <assert.h>
#include <stdint.h>
#include <string.h>

static unsigned calls, faults;
static BbrRuntimeFault last_fault;
static const GuestState *last_state;
static void unit_a(GuestState *s) { ++calls; s->gregs[0] += 7; }
static void unit_b(GuestState *s) { ++calls; s->gregs[1] += 3; }
static void on_fault(void *ctx, BbrRuntimeFault fault, const GuestState *s, uint64_t detail) {
    (void)ctx; (void)detail; ++faults; last_fault=fault; last_state=s;
}
int main(void) {
    assert(bbr_runtime_resolve_import(0,"bbr_dispatch") != 0);
    assert(bbr_runtime_resolve_import(0,"bbr_cpuid") != 0);
    assert(bbr_runtime_resolve_import(0,"bbr_unimplemented") == 0);
    GuestState state;
    bbr_guest_state_reset(&state);
    assert(state.pf_raw==1 && state.mxcsr==0x1f80 && state.FCW==0x37f);
    assert(state.cs_idx==(6u<<3) && state.segment_arrays[0]==state.private_gdt);
    assert(state.private_gdt[6].L==1 && state.flags[27]==(1u<<5));

    const BbrUnit units[]={{0x20,unit_a},{0x40,unit_b}};
    uint8_t dirty[]={0,0};
    BbrRuntimeConfig cfg={units,2,dirty,0x100000,0x1000,on_fault,0};
    assert(bbr_runtime_bind(&cfg)==0 && bbr_image_base==0x100000);
    bbr_runtime_run(&state,0x100020);
    assert(calls==1 && state.gregs[0]==7 && bbr_runtime_last_fault()==BBR_RUNTIME_FAULT_NONE);
    state.rip=0x100040; bbr_dispatch_tail(&state);
    assert(calls==2 && state.gregs[1]==3);
    bbr_dispatch(&state,0x100021);
    assert(calls==2 && last_fault==BBR_RUNTIME_FAULT_MISSING_UNIT && last_state==&state);
    bbr_dispatch(&state,0x102020);
    assert(last_fault==BBR_RUNTIME_FAULT_ADDRESS_OUT_OF_RANGE && last_state==&state);
    dirty[1]=1; bbr_dispatch(&state,0x100040);
    assert(last_fault==BBR_RUNTIME_FAULT_DIRTY_CODE_NEEDS_INTERPRETER && last_state==&state);

    const BbrUnit bad[]={{0x40,unit_a},{0x20,unit_b}};
    cfg.units=bad;
    assert(bbr_runtime_bind(&cfg)!=0);
    assert(bbr_runtime_last_fault()==BBR_RUNTIME_FAULT_BAD_TABLE);
    bbr_runtime_unbind();
    assert(bbr_runtime_last_fault()==BBR_RUNTIME_FAULT_NONE);
    return 0;
}
''', encoding="utf-8")
            exe = temp / "runtime-test"
            subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-I", str(ROOT), str(ROOT / "switch/runtime/bbr_runtime.c"),
                            str(ROOT / "switch/runtime/bbr_elf_loader.c"),
                            str(harness), "-o", str(exe)], check=True, capture_output=True)
            subprocess.run([str(exe)], check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()
