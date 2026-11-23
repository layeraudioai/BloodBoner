/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "jit_code_memory_nx.h"

#include <string.h>

Result bbr_jit_code_create(BbrJitCodeMemory *memory, size_t requested_size) {
    if (!memory || requested_size == 0) return MAKERESULT(Module_Libnx, LibnxError_BadInput);
    memset(memory, 0, sizeof(*memory));
    Result result = jitCreate(&memory->jit, requested_size);
    if (R_FAILED(result)) {
        memset(memory, 0, sizeof(*memory));
        return result;
    }
    memory->initialized = 1;
    return 0;
}

void *bbr_jit_code_write_address(BbrJitCodeMemory *memory) {
    return memory && memory->initialized ? jitGetRwAddr(&memory->jit) : NULL;
}

void *bbr_jit_code_exec_address(BbrJitCodeMemory *memory) {
    return memory && memory->initialized ? jitGetRxAddr(&memory->jit) : NULL;
}

size_t bbr_jit_code_capacity(const BbrJitCodeMemory *memory) {
    return memory && memory->initialized ? memory->jit.size : 0;
}

Result bbr_jit_code_begin_write(BbrJitCodeMemory *memory) {
    if (!memory || !memory->initialized) return MAKERESULT(Module_Libnx, LibnxError_BadInput);
    Result result = jitTransitionToWritable(&memory->jit);
    if (R_SUCCEEDED(result)) memory->executable = 0;
    return result;
}

Result bbr_jit_code_seal_executable(BbrJitCodeMemory *memory) {
    if (!memory || !memory->initialized) return MAKERESULT(Module_Libnx, LibnxError_BadInput);
    Result result = jitTransitionToExecutable(&memory->jit);
    if (R_SUCCEEDED(result)) memory->executable = 1;
    return result;
}

Result bbr_jit_code_destroy(BbrJitCodeMemory *memory) {
    if (!memory) return MAKERESULT(Module_Libnx, LibnxError_BadInput);
    if (!memory->initialized) return 0;
    Result result = jitClose(&memory->jit);
    if (R_SUCCEEDED(result)) memset(memory, 0, sizeof(*memory));
    return result;
}
