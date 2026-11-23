/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef BBR_HORIZON_RUNTIME_ABI_H
#define BBR_HORIZON_RUNTIME_ABI_H

/*
 * Shared declarations for the current bb-recomp AOT ABI (RECOMP_ABI.md).
 * This is an interface contract, not a completed runtime implementation.
 * Keep GuestState opaque here; its exact layout must be ported and asserted
 * against the compiler/runtime before loading an AOT object.
 */
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define BBR_HORIZON_RUNTIME_ABI_VERSION 2u

typedef struct GuestState GuestState;
typedef void (*BbrUnitFn)(GuestState *state);

typedef struct BbrUnit {
    uint64_t vaddr;
    BbrUnitFn fn;
} BbrUnit;

typedef struct BbrFunction {
    uint32_t start;
    uint32_t end;
    uint32_t first_unit;
    uint32_t unit_count;
} BbrFunction;

typedef struct BbrCpuidResult {
    uint64_t lo; /* EAX | (EBX << 32) */
    uint64_t hi; /* ECX | (EDX << 32) */
} BbrCpuidResult;

/* Exports produced by the AOT compiler/table module. */
extern const BbrUnit bbr_units[];
extern const uint64_t bbr_unit_count;
extern const uint64_t bbr_image_hash;
extern const uint32_t bbr_abi_version;
extern const uint64_t bbr_abi_flags;
extern uint64_t bbr_image_base;
extern const uint64_t bbr_unit_end[];
extern const uint8_t bbr_unit_extra[];
extern uint8_t bbr_dirty[];
extern const BbrFunction bbr_funcs[];
extern const uint64_t bbr_func_count;

/* Runtime imports required by the lowered AArch64 code. */
void bbr_dispatch(GuestState *state, uint64_t target);
void bbr_dispatch_tail(GuestState *state);
void bbr_dirty_entry(GuestState *state, uint64_t vaddr);
void bbr_trap(GuestState *state, uint64_t kind);
BbrCpuidResult bbr_cpuid(GuestState *state, uint64_t leaf, uint64_t subleaf);
uint64_t bbr_rdtsc(void);
void bbr_syscall(GuestState *state);
uint64_t bbr_xgetbv(uint64_t ecx);
uint64_t bbr_processor_id(void);
void bbr_set_rounding(uint64_t round_mode, uint64_t mxcsr, uint64_t set_daz);
uint64_t bbr_get_rounding(void);
uint64_t bbr_push_rounding(uint64_t mode);
void bbr_pop_rounding(uint64_t saved);

#ifdef __cplusplus
}
#endif
#endif
