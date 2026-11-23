# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent


class JitMemoryWrapperTests(unittest.TestCase):
    def test_libnx_jit_memory_wrapper_state_and_lifecycle(self):
        compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
        if not compiler:
            self.skipTest("host C compiler unavailable")
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            include = temp / "switch/kernel"
            include.mkdir(parents=True)
            (include / "jit.h").write_text(r'''#pragma once
#include <stddef.h>
#include <stdint.h>
typedef uint32_t Result;
enum { Module_Libnx=345, LibnxError_BadInput=11 };
#define MAKERESULT(m,d) ((Result)(((m)&0x1ff)|(((d)&0x1fff)<<9)))
#define R_FAILED(r) ((r)!=0)
#define R_SUCCEEDED(r) ((r)==0)
typedef struct Jit { size_t size; void *rw_addr; void *rx_addr; int executable; } Jit;
Result jitCreate(Jit*,size_t); Result jitTransitionToWritable(Jit*);
Result jitTransitionToExecutable(Jit*); Result jitClose(Jit*);
static inline void *jitGetRwAddr(Jit *j){return j->rw_addr;}
static inline void *jitGetRxAddr(Jit *j){return j->rx_addr;}
''', encoding="utf-8")
            harness = temp / "test.c"
            harness.write_text(r'''#include "switch/runtime/jit_code_memory_nx.h"
#include <assert.h>
#include <stdlib.h>
Result jitCreate(Jit *j,size_t n){j->size=(n+4095)&~(size_t)4095;j->rw_addr=malloc(j->size);j->rx_addr=j->rw_addr;return j->rw_addr?0:1;}
Result jitTransitionToWritable(Jit *j){j->executable=0;return 0;}
Result jitTransitionToExecutable(Jit *j){j->executable=1;return 0;}
Result jitClose(Jit *j){free(j->rw_addr);return 0;}
int main(void){
 BbrJitCodeMemory m={0};
 assert(bbr_jit_code_create(&m,5000)==0);
 assert(bbr_jit_code_capacity(&m)==8192);
 assert(bbr_jit_code_write_address(&m)!=0 && bbr_jit_code_exec_address(&m)!=0);
 assert(bbr_jit_code_seal_executable(&m)==0 && m.executable==1);
 assert(bbr_jit_code_begin_write(&m)==0 && m.executable==0);
 assert(bbr_jit_code_destroy(&m)==0 && !m.initialized);
 assert(bbr_jit_code_create(&m,0)!=0);
 return 0;
}
''', encoding="utf-8")
            exe = temp / "jit-test"
            source = ROOT / "switch/runtime/jit_code_memory_nx.c"
            header_root = ROOT
            subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-I", str(temp), "-I", str(header_root), str(source),
                            str(harness), "-o", str(exe)], check=True, capture_output=True)
            subprocess.run([str(exe)], check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()
