/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef BBR_JIT_CODE_MEMORY_NX_H
#define BBR_JIT_CODE_MEMORY_NX_H
#include <stddef.h>
#include <switch/kernel/jit.h>

/* Dual-mapped Horizon JIT region: writable alias for relocations, RX alias for execution. */
typedef struct BbrJitCodeMemory {
    Jit jit;
    size_t used;
    int initialized;
    int executable;
} BbrJitCodeMemory;

Result bbr_jit_code_create(BbrJitCodeMemory *memory, size_t requested_size);
void *bbr_jit_code_write_address(BbrJitCodeMemory *memory);
void *bbr_jit_code_exec_address(BbrJitCodeMemory *memory);
size_t bbr_jit_code_capacity(const BbrJitCodeMemory *memory);
Result bbr_jit_code_begin_write(BbrJitCodeMemory *memory);
Result bbr_jit_code_seal_executable(BbrJitCodeMemory *memory);
Result bbr_jit_code_destroy(BbrJitCodeMemory *memory);
#endif
