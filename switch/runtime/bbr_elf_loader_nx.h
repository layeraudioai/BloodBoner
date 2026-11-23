/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef BBR_HORIZON_ELF_LOADER_NX_H
#define BBR_HORIZON_ELF_LOADER_NX_H
#include "bbr_elf_loader.h"
#include "jit_code_memory_nx.h"

typedef struct BbrNxElfAllocator {
    BbrJitCodeMemory jit;
    BbrElfAllocator allocator;
} BbrNxElfAllocator;

/* Prepare an allocator for one loaded ET_REL module. Keep it alive until unload. */
void bbr_elf_nx_allocator_init(BbrNxElfAllocator *allocator);
#endif
