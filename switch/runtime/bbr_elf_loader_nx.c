/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "bbr_elf_loader_nx.h"
#include <string.h>

static int reserve_jit(void *context, size_t size, size_t alignment, BbrElfMemory *out) {
    if (alignment > 0x1000) return 0; /* libnx's allocation base is page aligned. */
    BbrNxElfAllocator *allocator = (BbrNxElfAllocator *)context;
    memset(out, 0, sizeof(*out));
    if (R_FAILED(bbr_jit_code_create(&allocator->jit, size))) return 0;
    out->rw = (uint8_t *)bbr_jit_code_write_address(&allocator->jit);
    out->rx = (uint8_t *)bbr_jit_code_exec_address(&allocator->jit);
    out->capacity = bbr_jit_code_capacity(&allocator->jit);
    out->owner = allocator;
    return out->rw && out->rx && out->capacity >= size;
}

static int seal_jit(void *context, BbrElfMemory *memory) {
    BbrNxElfAllocator *allocator = (BbrNxElfAllocator *)context;
    return memory && memory->owner == allocator &&
           R_SUCCEEDED(bbr_jit_code_seal_executable(&allocator->jit));
}

static void release_jit(void *context, BbrElfMemory *memory) {
    BbrNxElfAllocator *allocator = (BbrNxElfAllocator *)context;
    if (memory && memory->owner == allocator) (void)bbr_jit_code_destroy(&allocator->jit);
    if (memory) memset(memory, 0, sizeof(*memory));
}

void bbr_elf_nx_allocator_init(BbrNxElfAllocator *allocator) {
    if (!allocator) return;
    memset(allocator, 0, sizeof(*allocator));
    allocator->allocator.context = allocator;
    allocator->allocator.reserve = reserve_jit;
    allocator->allocator.seal = seal_jit;
    allocator->allocator.release = release_jit;
}
