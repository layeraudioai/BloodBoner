/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef BBR_HORIZON_RUNTIME_H
#define BBR_HORIZON_RUNTIME_H
#include <stddef.h>
#include <stdint.h>
#include "bbr_runtime_abi.h"
#include "bbr_elf_loader.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum BbrRuntimeFault {
    BBR_RUNTIME_FAULT_NONE = 0,
    BBR_RUNTIME_FAULT_NOT_BOUND,
    BBR_RUNTIME_FAULT_BAD_TABLE,
    BBR_RUNTIME_FAULT_ADDRESS_OUT_OF_RANGE,
    BBR_RUNTIME_FAULT_MISSING_UNIT,
    BBR_RUNTIME_FAULT_DIRTY_CODE_NEEDS_INTERPRETER,
    BBR_RUNTIME_FAULT_GUEST_TRAP,
    BBR_RUNTIME_FAULT_SYSCALL_BACKEND_MISSING,
    BBR_RUNTIME_FAULT_UNSUPPORTED_HELPER
} BbrRuntimeFault;

typedef void (*BbrRuntimeFaultFn)(void *context, BbrRuntimeFault fault,
                                  const GuestState *state, uint64_t detail);

typedef struct BbrRuntimeConfig {
    const BbrUnit *units;          /* sorted strictly by vaddr */
    uint64_t unit_count;
    const uint8_t *dirty;          /* optional array indexed like units */
    uint64_t image_base;           /* absolute guest address corresponding to vaddr 0 */
    uint64_t image_size;           /* zero disables range checks */
    BbrRuntimeFaultFn on_fault;
    void *fault_context;
} BbrRuntimeConfig;

/* Prototype dispatcher for already-linked AOT tables. This is not an ELF loader. */
int bbr_runtime_bind(const BbrRuntimeConfig *config);
/* Validate ABI metadata exported by a loaded module and bind its unit/dirty tables. */
int bbr_runtime_bind_elf(const BbrElfModule *module, uint64_t guest_image_base,
                         uint64_t guest_image_size, uint64_t expected_image_hash,
                         BbrRuntimeFaultFn on_fault, void *fault_context);
void bbr_runtime_unbind(void);
/* Resolve the compiler's bbr_* runtime imports; unknown names return zero. */
uintptr_t bbr_runtime_resolve_import(void *context, const char *name);
BbrRuntimeFault bbr_runtime_last_fault(void);
uint64_t bbr_runtime_last_detail(void);
void bbr_runtime_run(GuestState *state, uint64_t target);

#ifdef __cplusplus
}
#endif
#endif
