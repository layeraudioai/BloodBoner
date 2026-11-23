/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "bbr_runtime.h"

#include <string.h>

/* AOT table module provides a strong definition when linked. */
#if defined(__GNUC__) || defined(__clang__)
__attribute__((weak))
#endif
uint64_t bbr_image_base;

/* Early bring-up uses one bound table. This is deliberately not thread-safe. */
static BbrRuntimeConfig g_config;
static int g_bound;
static BbrRuntimeFault g_last_fault;
static uint64_t g_last_detail;

void bbr_guest_state_reset(GuestState *state) {
    if (!state) return;
    memset(state, 0, sizeof(*state));
    state->pf_raw = 1;
    state->flags[1] = 1;
    state->flags[9] = 1;
    state->flags[10] = 1;
    state->flags[27] = 1u << 5;
    state->mxcsr = 0x1f80;
    state->FCW = 0x37f;
    state->segment_arrays[0] = state->private_gdt;
    state->segment_arrays[1] = state->private_gdt;
    state->cs_idx = 6u << 3;
    state->private_gdt[6].Limit0 = 0xffff;
    state->private_gdt[6].Limit1 = 0xf;
    state->private_gdt[6].L = 1;
    state->cs_cached = 0;
}

static void report_fault(BbrRuntimeFault fault, const GuestState *state, uint64_t detail) {
    g_last_fault = fault;
    g_last_detail = detail;
    if (g_bound && g_config.on_fault)
        g_config.on_fault(g_config.fault_context, fault, state, detail);
}

int bbr_runtime_bind(const BbrRuntimeConfig *config) {
    if (!config || (config->unit_count && !config->units) ||
        config->unit_count > (uint64_t)(SIZE_MAX / sizeof(BbrUnit)) ||
        (config->image_size && config->image_base > UINT64_MAX - config->image_size)) {
        g_bound = 0;
        report_fault(BBR_RUNTIME_FAULT_BAD_TABLE, NULL, 0);
        return -1;
    }
    for (uint64_t i = 0; i < config->unit_count; ++i) {
        if (!config->units[i].fn || (i && config->units[i - 1].vaddr >= config->units[i].vaddr)) {
            g_bound = 0;
            report_fault(BBR_RUNTIME_FAULT_BAD_TABLE, NULL, i);
            return -1;
        }
    }
    g_config = *config;
    g_bound = 1;
    g_last_fault = BBR_RUNTIME_FAULT_NONE;
    g_last_detail = 0;
    bbr_image_base = config->image_base;
    return 0;
}

static int module_range(const BbrElfModule *module, uintptr_t address, size_t size, int writable) {
    const uintptr_t base = (uintptr_t)(writable ? module->memory.rw : module->memory.rx);
    if (!base || address < base || address - base > module->memory.capacity) return 0;
    return size <= module->memory.capacity - (size_t)(address - base);
}

int bbr_runtime_bind_elf(const BbrElfModule *module, uint64_t guest_image_base,
                         uint64_t guest_image_size, uint64_t expected_image_hash,
                         BbrRuntimeFaultFn on_fault, void *fault_context) {
    if (!module || !module->private_state || !module->memory.rw || !module->memory.rx) {
        report_fault(BBR_RUNTIME_FAULT_BAD_TABLE, NULL, 0);
        return -1;
    }
    const uintptr_t units_addr = bbr_elf_find_symbol(module, "bbr_units");
    const uintptr_t count_addr = bbr_elf_find_symbol(module, "bbr_unit_count");
    const uintptr_t hash_addr = bbr_elf_find_symbol(module, "bbr_image_hash");
    const uintptr_t version_addr = bbr_elf_find_symbol(module, "bbr_abi_version");
    const uintptr_t flags_addr = bbr_elf_find_symbol(module, "bbr_abi_flags");
    const uintptr_t base_addr = bbr_elf_find_symbol(module, "bbr_image_base");
    const uintptr_t dirty_addr = bbr_elf_find_symbol(module, "bbr_dirty");
    uint64_t unit_count = 0, image_hash = 0, flags = 0;
    uint32_t version = 0;
    if (!units_addr || !count_addr || !hash_addr || !version_addr || !flags_addr || !base_addr || !dirty_addr ||
        !module_range(module, units_addr, sizeof(BbrUnit), 0) ||
        !module_range(module, count_addr, sizeof(unit_count), 0) ||
        !module_range(module, hash_addr, sizeof(image_hash), 0) ||
        !module_range(module, version_addr, sizeof(version), 0) ||
        !module_range(module, flags_addr, sizeof(flags), 0) ||
        !module_range(module, base_addr, sizeof(uint64_t), 1) ||
        !module_range(module, dirty_addr, 1, 1)) {
        report_fault(BBR_RUNTIME_FAULT_BAD_TABLE, NULL, 0);
        return -1;
    }
    memcpy(&unit_count, (const void *)count_addr, sizeof(unit_count));
    memcpy(&image_hash, (const void *)hash_addr, sizeof(image_hash));
    memcpy(&version, (const void *)version_addr, sizeof(version));
    memcpy(&flags, (const void *)flags_addr, sizeof(flags));
    /* This bring-up runtime implements ordinary and dirty-checked tables only.
       Resume entries, variants, hook slots, and granular dispatch are rejected. */
    if (version != BBR_HORIZON_RUNTIME_ABI_VERSION || (flags & ~UINT64_C(2)) ||
        (expected_image_hash && image_hash != expected_image_hash) ||
        unit_count > SIZE_MAX / sizeof(BbrUnit) ||
        !module_range(module, units_addr, (size_t)unit_count * sizeof(BbrUnit), 0) ||
        !module_range(module, dirty_addr, (size_t)unit_count, 1)) {
        report_fault(BBR_RUNTIME_FAULT_BAD_TABLE, NULL, version);
        return -1;
    }
    memcpy((void *)base_addr, &guest_image_base, sizeof(guest_image_base));
    BbrRuntimeConfig config = {
        (const BbrUnit *)units_addr, unit_count, (const uint8_t *)dirty_addr,
        guest_image_base, guest_image_size, on_fault, fault_context
    };
    return bbr_runtime_bind(&config);
}

void bbr_runtime_unbind(void) {
    memset(&g_config, 0, sizeof(g_config));
    g_bound = 0;
    g_last_fault = BBR_RUNTIME_FAULT_NONE;
    g_last_detail = 0;
}

uintptr_t bbr_runtime_resolve_import(void *context, const char *name) {
    (void)context;
    if (!name) return 0;
#define RESOLVE(n, fn) if (strcmp(name, (n)) == 0) return (uintptr_t)(fn)
    RESOLVE("bbr_dispatch", bbr_dispatch);
    RESOLVE("bbr_dispatch_tail", bbr_dispatch_tail);
    RESOLVE("bbr_dirty_entry", bbr_dirty_entry);
    RESOLVE("bbr_trap", bbr_trap);
    RESOLVE("bbr_cpuid", bbr_cpuid);
    RESOLVE("bbr_rdtsc", bbr_rdtsc);
    RESOLVE("bbr_syscall", bbr_syscall);
    RESOLVE("bbr_xgetbv", bbr_xgetbv);
    RESOLVE("bbr_processor_id", bbr_processor_id);
    RESOLVE("bbr_set_rounding", bbr_set_rounding);
    RESOLVE("bbr_get_rounding", bbr_get_rounding);
    RESOLVE("bbr_push_rounding", bbr_push_rounding);
    RESOLVE("bbr_pop_rounding", bbr_pop_rounding);
#undef RESOLVE
    return 0;
}

BbrRuntimeFault bbr_runtime_last_fault(void) { return g_last_fault; }
uint64_t bbr_runtime_last_detail(void) { return g_last_detail; }

static const BbrUnit *find_unit(uint64_t target, uint64_t *index_out, BbrRuntimeFault *fault_out) {
    *fault_out = BBR_RUNTIME_FAULT_NONE;
    if (!g_bound) {
        *fault_out = BBR_RUNTIME_FAULT_NOT_BOUND;
        return NULL;
    }
    if (target < g_config.image_base) {
        *fault_out = BBR_RUNTIME_FAULT_ADDRESS_OUT_OF_RANGE;
        return NULL;
    }
    const uint64_t vaddr = target - g_config.image_base;
    if (g_config.image_size && vaddr >= g_config.image_size) {
        *fault_out = BBR_RUNTIME_FAULT_ADDRESS_OUT_OF_RANGE;
        return NULL;
    }
    uint64_t lo = 0, hi = g_config.unit_count;
    while (lo < hi) {
        const uint64_t mid = lo + (hi - lo) / 2;
        if (g_config.units[mid].vaddr < vaddr) lo = mid + 1;
        else hi = mid;
    }
    if (lo == g_config.unit_count || g_config.units[lo].vaddr != vaddr) {
        *fault_out = BBR_RUNTIME_FAULT_MISSING_UNIT;
        return NULL;
    }
    if (index_out) *index_out = lo;
    return &g_config.units[lo];
}

void bbr_runtime_run(GuestState *state, uint64_t target) {
    if (!state) {
        report_fault(BBR_RUNTIME_FAULT_BAD_TABLE, NULL, target);
        return;
    }
    state->rip = target;
    g_last_fault = BBR_RUNTIME_FAULT_NONE;
    g_last_detail = 0;
    uint64_t index = 0;
    BbrRuntimeFault fault = BBR_RUNTIME_FAULT_NONE;
    const BbrUnit *unit = find_unit(target, &index, &fault);
    if (!unit) {
        report_fault(fault, state, target);
        return;
    }
    if (g_config.dirty && g_config.dirty[index]) {
        report_fault(BBR_RUNTIME_FAULT_DIRTY_CODE_NEEDS_INTERPRETER, state, target);
        return;
    }
    unit->fn(state);
}

/* Recompiler imports. Unsupported behavior faults closed; no fake fallback CPU. */
void bbr_dispatch(GuestState *state, uint64_t target) { bbr_runtime_run(state, target); }
void bbr_dispatch_tail(GuestState *state) {
    if (!state) report_fault(BBR_RUNTIME_FAULT_BAD_TABLE, NULL, 0);
    else bbr_runtime_run(state, state->rip);
}
void bbr_dirty_entry(GuestState *state, uint64_t vaddr) {
    if (!g_bound || vaddr > UINT64_MAX - g_config.image_base) {
        report_fault(BBR_RUNTIME_FAULT_NOT_BOUND, state, vaddr);
        return;
    }
    if (state) state->rip = g_config.image_base + vaddr;
    report_fault(BBR_RUNTIME_FAULT_DIRTY_CODE_NEEDS_INTERPRETER, state, vaddr);
}
void bbr_trap(GuestState *state, uint64_t kind) {
    report_fault(BBR_RUNTIME_FAULT_GUEST_TRAP, state, kind);
}
BbrCpuidResult bbr_cpuid(GuestState *state, uint64_t leaf, uint64_t subleaf) {
    report_fault(BBR_RUNTIME_FAULT_UNSUPPORTED_HELPER, state, (leaf << 32) ^ subleaf);
    BbrCpuidResult result = {0, 0};
    return result;
}
uint64_t bbr_rdtsc(void) {
    report_fault(BBR_RUNTIME_FAULT_UNSUPPORTED_HELPER, NULL, 0);
    return 0;
}
void bbr_syscall(GuestState *state) {
    report_fault(BBR_RUNTIME_FAULT_SYSCALL_BACKEND_MISSING, state, 0);
}
uint64_t bbr_xgetbv(uint64_t ecx) {
    report_fault(BBR_RUNTIME_FAULT_UNSUPPORTED_HELPER, NULL, ecx);
    return 0;
}
uint64_t bbr_processor_id(void) { return 0; }
void bbr_set_rounding(uint64_t round_mode, uint64_t mxcsr, uint64_t set_daz) {
    (void)mxcsr;
    (void)set_daz;
    report_fault(BBR_RUNTIME_FAULT_UNSUPPORTED_HELPER, NULL, round_mode);
}
uint64_t bbr_get_rounding(void) {
    report_fault(BBR_RUNTIME_FAULT_UNSUPPORTED_HELPER, NULL, 0);
    return 0;
}
uint64_t bbr_push_rounding(uint64_t mode) {
    report_fault(BBR_RUNTIME_FAULT_UNSUPPORTED_HELPER, NULL, mode);
    return 0;
}
void bbr_pop_rounding(uint64_t saved) {
    report_fault(BBR_RUNTIME_FAULT_UNSUPPORTED_HELPER, NULL, saved);
}
