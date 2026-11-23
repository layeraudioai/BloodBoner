/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef BBR_HORIZON_ELF_LOADER_H
#define BBR_HORIZON_ELF_LOADER_H
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum BbrElfError {
    BBR_ELF_OK = 0,
    BBR_ELF_BAD_ARGUMENT,
    BBR_ELF_BAD_FORMAT,
    BBR_ELF_UNSUPPORTED,
    BBR_ELF_OUT_OF_MEMORY,
    BBR_ELF_UNRESOLVED_SYMBOL,
    BBR_ELF_BAD_RELOCATION,
    BBR_ELF_RELOCATION_OVERFLOW,
    BBR_ELF_MEMORY_ERROR,
    BBR_ELF_NOT_FOUND
} BbrElfError;

typedef struct BbrElfMemory {
    uint8_t *rw;       /* writable alias used for copying/relocation */
    uint8_t *rx;       /* executable/read-only alias used by relocated code */
    size_t capacity;
    void *owner;
} BbrElfMemory;

typedef struct BbrElfAllocator {
    void *context;
    int (*reserve)(void *context, size_t size, size_t alignment, BbrElfMemory *out);
    int (*seal)(void *context, BbrElfMemory *memory);
    void (*release)(void *context, BbrElfMemory *memory);
} BbrElfAllocator;

typedef uintptr_t (*BbrElfResolveFn)(void *context, const char *name);

typedef struct BbrElfModule {
    BbrElfMemory memory;
    void *private_state;
    const BbrElfAllocator *allocator;
} BbrElfModule;

/* Loads little-endian ELF64 EM_AARCH64 ET_REL, applies supported RELA records,
 * resolves undefined global symbols via resolve, then seals memory before return.
 * Unsupported sections/relocations fail closed; this is not a general ELF loader. */
BbrElfError bbr_elf_load(BbrElfModule *out, const void *file, size_t file_size,
                         const BbrElfAllocator *allocator,
                         BbrElfResolveFn resolve, void *resolve_context);
uintptr_t bbr_elf_find_symbol(const BbrElfModule *module, const char *name);
void bbr_elf_unload(BbrElfModule *module);
const char *bbr_elf_error_string(BbrElfError error);

#ifdef __cplusplus
}
#endif
#endif
