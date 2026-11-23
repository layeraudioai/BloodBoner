/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "bbr_elf_loader.h"

#include <elf.h>
#include <limits.h>
#include <stdlib.h>
#include <string.h>

#ifndef R_AARCH64_NONE
#define R_AARCH64_NONE 0
#define R_AARCH64_ABS64 257
#define R_AARCH64_PREL32 261
#define R_AARCH64_MOVW_UABS_G0 263
#define R_AARCH64_MOVW_UABS_G0_NC 264
#define R_AARCH64_MOVW_UABS_G1 265
#define R_AARCH64_MOVW_UABS_G1_NC 266
#define R_AARCH64_MOVW_UABS_G2 267
#define R_AARCH64_MOVW_UABS_G2_NC 268
#define R_AARCH64_MOVW_UABS_G3 269
#define R_AARCH64_ADR_PREL_LO21 274
#define R_AARCH64_ADR_PREL_PG_HI21 275
#define R_AARCH64_ADR_PREL_PG_HI21_NC 276
#define R_AARCH64_ADD_ABS_LO12_NC 277
#define R_AARCH64_LDST64_ABS_LO12_NC 286
#define R_AARCH64_JUMP26 282
#define R_AARCH64_CALL26 283
#endif

#define BBR_MAX_ELF_FILE ((size_t)1 << 31)

typedef struct BbrElfPrivate {
    uint8_t *file;
    size_t file_size;
    Elf64_Ehdr eh;
    Elf64_Shdr *sections;
    size_t *section_offsets;
    uint8_t *section_loaded;
} BbrElfPrivate;

static int range_ok(size_t total, uint64_t offset, uint64_t length) {
    return offset <= total && length <= (uint64_t)total - offset;
}
static int align_size(size_t value, size_t align, size_t *out) {
    if (align <= 1) { *out = value; return 1; }
    if ((align & (align - 1)) != 0 || value > SIZE_MAX - (align - 1)) return 0;
    *out = (value + align - 1) & ~(align - 1);
    return 1;
}
static uint32_t read32(const uint8_t *p) { uint32_t v; memcpy(&v, p, sizeof(v)); return v; }
static void write64(uint8_t *p, uint64_t v) { memcpy(p, &v, sizeof(v)); }
static void write32(uint8_t *p, uint32_t v) { memcpy(p, &v, sizeof(v)); }
static int add_signed(uintptr_t base, int64_t addend, uintptr_t *out) {
    if (addend >= 0) {
        if ((uint64_t)addend > UINTPTR_MAX - base) return 0;
        *out = base + (uintptr_t)addend;
    } else {
        const uint64_t magnitude = (uint64_t)(-(addend + 1)) + 1;
        if (magnitude > base) return 0;
        *out = base - (uintptr_t)magnitude;
    }
    return 1;
}
static int signed_fits(int64_t value, unsigned bits) {
    const int64_t lo = -((int64_t)1 << (bits - 1));
    const int64_t hi = ((int64_t)1 << (bits - 1)) - 1;
    return value >= lo && value <= hi;
}
static int get_str(const uint8_t *strings, size_t size, uint32_t offset, const char **out) {
    if (offset >= size) return 0;
    const char *s = (const char *)(strings + offset);
    if (!memchr(s, 0, size - offset)) return 0;
    *out = s;
    return 1;
}
static int pointer_delta(uintptr_t to, uintptr_t from, int64_t *out) {
    if (to >= from) {
        uintptr_t d = to - from;
        if (d > INT64_MAX) return 0;
        *out = (int64_t)d;
    } else {
        uintptr_t d = from - to;
        if (d > (uintptr_t)INT64_MAX + 1u) return 0;
        *out = d == (uintptr_t)INT64_MAX + 1u ? INT64_MIN : -(int64_t)d;
    }
    return 1;
}
static uintptr_t section_base(const BbrElfModule *m, const BbrElfPrivate *p, uint32_t index) {
    const Elf64_Shdr *s = &p->sections[index];
    uint8_t *base = (s->sh_flags & SHF_EXECINSTR) ? m->memory.rx :
                    (s->sh_flags & SHF_WRITE) ? m->memory.rw : m->memory.rx;
    if (!base) return 0;
    return (uintptr_t)(base + p->section_offsets[index]);
}
static int symbol_value(const BbrElfModule *m, const BbrElfPrivate *p,
                        const Elf64_Sym *sym, const char *name,
                        BbrElfResolveFn resolver, void *resolver_context,
                        uintptr_t *out) {
    if (sym->st_shndx == SHN_UNDEF) {
        if (ELF64_ST_BIND(sym->st_info) == STB_WEAK) { *out = 0; return 1; }
        uintptr_t v = resolver ? resolver(resolver_context, name) : 0;
        if (!v) return 0;
        *out = v;
        return 1;
    }
    if (sym->st_shndx == SHN_ABS) { *out = (uintptr_t)sym->st_value; return 1; }
    if (sym->st_shndx >= p->eh.e_shnum || !p->section_loaded[sym->st_shndx]) return 0;
    const Elf64_Shdr *sec = &p->sections[sym->st_shndx];
    if (sym->st_value > sec->sh_size || sym->st_size > sec->sh_size - sym->st_value) return 0;
    uintptr_t base = section_base(m, p, sym->st_shndx);
    if (sym->st_value > UINTPTR_MAX - base) return 0;
    *out = base + (uintptr_t)sym->st_value;
    return 1;
}
static int patch_relocation(uint32_t type, uint8_t *patch, uintptr_t place,
                            uintptr_t symbol, int64_t addend) {
    uintptr_t value;
    int64_t delta;
    uint32_t insn;
    switch (type) {
    case R_AARCH64_NONE: return 1;
    case R_AARCH64_ABS64:
        if (!add_signed(symbol, addend, &value)) return 0;
        write64(patch, (uint64_t)value); return 1;
    case R_AARCH64_PREL32:
        if (!add_signed(symbol, addend, &value) || !pointer_delta(value, place, &delta) ||
            !signed_fits(delta, 32)) return 0;
        write32(patch, (uint32_t)(int32_t)delta); return 1;
    case R_AARCH64_CALL26: case R_AARCH64_JUMP26:
        if (!add_signed(symbol, addend, &value) || !pointer_delta(value, place, &delta) ||
            (delta & 3) || !signed_fits(delta, 28)) return 0;
        insn = read32(patch);
        insn = (insn & 0xfc000000u) | ((uint32_t)(delta >> 2) & 0x03ffffffu);
        write32(patch, insn); return 1;
    case R_AARCH64_ADR_PREL_LO21:
        if (!add_signed(symbol, addend, &value) || !pointer_delta(value, place, &delta) ||
            !signed_fits(delta, 21)) return 0;
        insn = read32(patch);
        insn = (insn & 0x9f00001fu) | (((uint32_t)delta & 3u) << 29) |
               ((((uint32_t)(delta >> 2)) & 0x7ffffu) << 5);
        write32(patch, insn); return 1;
    case R_AARCH64_ADR_PREL_PG_HI21: case R_AARCH64_ADR_PREL_PG_HI21_NC: {
        uintptr_t target_page, place_page;
        if (!add_signed(symbol, addend, &value)) return 0;
        target_page = value & ~(uintptr_t)0xfff;
        place_page = place & ~(uintptr_t)0xfff;
        if (!pointer_delta(target_page, place_page, &delta) || (delta & 0xfff)) return 0;
        delta >>= 12;
        if (type == R_AARCH64_ADR_PREL_PG_HI21 && !signed_fits(delta, 21)) return 0;
        if (!signed_fits(delta, 21)) return 0; /* imm21 cannot encode more even for NC */
        insn = read32(patch);
        insn = (insn & 0x9f00001fu) | (((uint32_t)delta & 3u) << 29) |
               ((((uint32_t)(delta >> 2)) & 0x7ffffu) << 5);
        write32(patch, insn); return 1;
    }
    case R_AARCH64_ADD_ABS_LO12_NC:
        if (!add_signed(symbol, addend, &value)) return 0;
        insn = read32(patch);
        insn = (insn & ~(0xfffu << 10)) | (((uint32_t)value & 0xfffu) << 10);
        write32(patch, insn); return 1;
    case R_AARCH64_LDST64_ABS_LO12_NC:
        if (!add_signed(symbol, addend, &value) || (value & 7u)) return 0;
        insn = read32(patch);
        insn = (insn & ~(0xfffu << 10)) | ((((uint32_t)value >> 3) & 0xfffu) << 10);
        write32(patch, insn); return 1;
    case R_AARCH64_MOVW_UABS_G0: case R_AARCH64_MOVW_UABS_G0_NC:
    case R_AARCH64_MOVW_UABS_G1: case R_AARCH64_MOVW_UABS_G1_NC:
    case R_AARCH64_MOVW_UABS_G2: case R_AARCH64_MOVW_UABS_G2_NC:
    case R_AARCH64_MOVW_UABS_G3: {
        unsigned shift = type <= R_AARCH64_MOVW_UABS_G0_NC ? 0 :
                         type <= R_AARCH64_MOVW_UABS_G1_NC ? 16 :
                         type == R_AARCH64_MOVW_UABS_G2 || type == R_AARCH64_MOVW_UABS_G2_NC ? 32 : 48;
        if (!add_signed(symbol, addend, &value)) return 0;
        if (type != R_AARCH64_MOVW_UABS_G0_NC && type != R_AARCH64_MOVW_UABS_G1_NC &&
            type != R_AARCH64_MOVW_UABS_G2_NC && shift < 48 && (value >> (shift + 16))) return 0;
        insn = read32(patch);
        insn = (insn & ~(0xffffu << 5)) | (((uint32_t)(value >> shift) & 0xffffu) << 5);
        write32(patch, insn); return 1;
    }
    default: return -1;
    }
}

static void private_free(BbrElfPrivate *p) {
    if (!p) return;
    free(p->file); free(p->sections); free(p->section_offsets); free(p->section_loaded); free(p);
}

BbrElfError bbr_elf_load(BbrElfModule *out, const void *input, size_t file_size,
                         const BbrElfAllocator *allocator,
                         BbrElfResolveFn resolver, void *resolver_context) {
    if (!out || !input || !allocator || !allocator->reserve || !allocator->seal || !allocator->release)
        return BBR_ELF_BAD_ARGUMENT;
    memset(out, 0, sizeof(*out));
    if (file_size < sizeof(Elf64_Ehdr) || file_size > BBR_MAX_ELF_FILE) return BBR_ELF_BAD_FORMAT;
    BbrElfPrivate *p = (BbrElfPrivate *)calloc(1, sizeof(*p));
    if (!p) return BBR_ELF_OUT_OF_MEMORY;
    p->file = (uint8_t *)malloc(file_size);
    if (!p->file) { private_free(p); return BBR_ELF_OUT_OF_MEMORY; }
    memcpy(p->file, input, file_size); p->file_size = file_size;
    memcpy(&p->eh, p->file, sizeof(p->eh));
    const unsigned char *id = p->eh.e_ident;
    if (memcmp(id, ELFMAG, SELFMAG) || id[EI_CLASS] != ELFCLASS64 ||
        id[EI_DATA] != ELFDATA2LSB || id[EI_VERSION] != EV_CURRENT ||
        p->eh.e_type != ET_REL || p->eh.e_machine != EM_AARCH64 ||
        p->eh.e_version != EV_CURRENT || p->eh.e_ehsize != sizeof(Elf64_Ehdr) ||
        p->eh.e_shentsize != sizeof(Elf64_Shdr) || !p->eh.e_shnum ||
        (p->eh.e_shoff % _Alignof(Elf64_Shdr)) != 0 ||
        !range_ok(file_size, p->eh.e_shoff, (uint64_t)p->eh.e_shnum * sizeof(Elf64_Shdr))) {
        private_free(p); return BBR_ELF_BAD_FORMAT;
    }
    p->sections = (Elf64_Shdr *)malloc((size_t)p->eh.e_shnum * sizeof(Elf64_Shdr));
    p->section_offsets = (size_t *)calloc(p->eh.e_shnum, sizeof(size_t));
    p->section_loaded = (uint8_t *)calloc(p->eh.e_shnum, 1);
    if (!p->sections || !p->section_offsets || !p->section_loaded) {
        private_free(p); return BBR_ELF_OUT_OF_MEMORY;
    }
    memcpy(p->sections, p->file + p->eh.e_shoff, (size_t)p->eh.e_shnum * sizeof(Elf64_Shdr));
    size_t total = 0, max_align = 0x1000;
    for (uint16_t i = 0; i < p->eh.e_shnum; ++i) {
        Elf64_Shdr *s = &p->sections[i];
        if (s->sh_addralign && (s->sh_addralign & (s->sh_addralign - 1))) { private_free(p); return BBR_ELF_BAD_FORMAT; }
        if (!(s->sh_flags & SHF_ALLOC) || s->sh_type == SHT_NULL) continue;
        if (s->sh_type != SHT_PROGBITS && s->sh_type != SHT_NOBITS) { private_free(p); return BBR_ELF_UNSUPPORTED; }
        if (s->sh_size > BBR_MAX_ELF_FILE ||
            (s->sh_type == SHT_PROGBITS && !range_ok(file_size, s->sh_offset, s->sh_size))) {
            private_free(p); return BBR_ELF_BAD_FORMAT;
        }
        size_t aligned;
        size_t a = s->sh_addralign ? (size_t)s->sh_addralign : 1;
        if (a > max_align) max_align = a;
        if (!align_size(total, a, &aligned) || s->sh_size > SIZE_MAX - aligned) { private_free(p); return BBR_ELF_BAD_FORMAT; }
        p->section_offsets[i] = aligned;
        total = aligned + (size_t)s->sh_size;
        p->section_loaded[i] = 1;
    }
    if (!total) { private_free(p); return BBR_ELF_BAD_FORMAT; }
    if (!allocator->reserve(allocator->context, total, max_align, &out->memory) ||
        !out->memory.rw || !out->memory.rx || out->memory.capacity < total) {
        if (out->memory.rw || out->memory.owner) allocator->release(allocator->context, &out->memory);
        private_free(p); memset(out, 0, sizeof(*out)); return BBR_ELF_MEMORY_ERROR;
    }
    memset(out->memory.rw, 0, total);
    out->private_state = p; out->allocator = allocator;
    for (uint16_t i = 0; i < p->eh.e_shnum; ++i) {
        Elf64_Shdr *s = &p->sections[i];
        if (!p->section_loaded[i] || s->sh_type == SHT_NOBITS || !s->sh_size) continue;
        memcpy(out->memory.rw + p->section_offsets[i], p->file + s->sh_offset, (size_t)s->sh_size);
    }
    for (uint16_t ri = 0; ri < p->eh.e_shnum; ++ri) {
        Elf64_Shdr *rel = &p->sections[ri];
        if (rel->sh_type == SHT_REL && rel->sh_info < p->eh.e_shnum &&
            (p->sections[rel->sh_info].sh_flags & SHF_ALLOC)) goto unsupported_reloc;
        if (rel->sh_type != SHT_RELA) continue;
        if (rel->sh_info >= p->eh.e_shnum || rel->sh_link >= p->eh.e_shnum) goto bad_format;
        if (!(p->sections[rel->sh_info].sh_flags & SHF_ALLOC)) continue;
        if (!p->section_loaded[rel->sh_info] || rel->sh_entsize != sizeof(Elf64_Rela) ||
            rel->sh_size % sizeof(Elf64_Rela) || rel->sh_offset % _Alignof(Elf64_Rela) ||
            !range_ok(file_size, rel->sh_offset, rel->sh_size))
            goto bad_format;
        Elf64_Shdr *symtab = &p->sections[rel->sh_link];
        if (symtab->sh_type != SHT_SYMTAB || symtab->sh_entsize != sizeof(Elf64_Sym) ||
            symtab->sh_size % sizeof(Elf64_Sym) || symtab->sh_offset % _Alignof(Elf64_Sym) ||
            symtab->sh_link >= p->eh.e_shnum)
            goto bad_format;
        Elf64_Shdr *strsec = &p->sections[symtab->sh_link];
        if (strsec->sh_type != SHT_STRTAB || !range_ok(file_size, symtab->sh_offset, symtab->sh_size) ||
            !range_ok(file_size, strsec->sh_offset, strsec->sh_size)) goto bad_format;
        Elf64_Shdr *target = &p->sections[rel->sh_info];
        const size_t target_len = (size_t)target->sh_size;
        uintptr_t target_base = section_base(out, p, rel->sh_info);
        uint8_t *write_base = out->memory.rw + p->section_offsets[rel->sh_info];
        const Elf64_Sym *symbols = (const Elf64_Sym *)(p->file + symtab->sh_offset);
        const char *strings = (const char *)(p->file + strsec->sh_offset);
        const size_t string_size = (size_t)strsec->sh_size;
        const size_t symbol_count = (size_t)(symtab->sh_size / sizeof(Elf64_Sym));
        const Elf64_Rela *records = (const Elf64_Rela *)(p->file + rel->sh_offset);
        const size_t count = (size_t)(rel->sh_size / sizeof(Elf64_Rela));
        for (size_t j = 0; j < count; ++j) {
            const uint64_t symidx = ELF64_R_SYM(records[j].r_info);
            const uint32_t type = (uint32_t)ELF64_R_TYPE(records[j].r_info);
            const uint64_t off = records[j].r_offset;
            const size_t patch_size = (type == R_AARCH64_ABS64) ? 8 :
                                      (type == R_AARCH64_PREL32) ? 4 : 4;
            if (symidx >= symbol_count || off > target_len || patch_size > target_len - off) goto bad_reloc;
            const Elf64_Sym *sym = &symbols[symidx];
            const char *name;
            if (!get_str((const uint8_t *)strings, string_size, sym->st_name, &name)) goto bad_format;
            uintptr_t S;
            if (!symbol_value(out, p, sym, name, resolver, resolver_context, &S)) {
                allocator->release(allocator->context, &out->memory); private_free(p); memset(out,0,sizeof(*out));
                return sym->st_shndx == SHN_UNDEF ? BBR_ELF_UNRESOLVED_SYMBOL : BBR_ELF_BAD_RELOCATION;
            }
            if (off > UINTPTR_MAX - target_base) goto bad_reloc;
            uintptr_t P = target_base + (uintptr_t)off;
            int patched = patch_relocation(type, write_base + (size_t)off, P, S, records[j].r_addend);
            if (patched == 0) goto reloc_overflow;
            if (patched < 0) goto unsupported_reloc;
        }
    }
    if (!allocator->seal(allocator->context, &out->memory)) {
        allocator->release(allocator->context, &out->memory); private_free(p); memset(out,0,sizeof(*out));
        return BBR_ELF_MEMORY_ERROR;
    }
    return BBR_ELF_OK;

bad_format:
    allocator->release(allocator->context, &out->memory); private_free(p); memset(out,0,sizeof(*out)); return BBR_ELF_BAD_FORMAT;
bad_reloc:
    allocator->release(allocator->context, &out->memory); private_free(p); memset(out,0,sizeof(*out)); return BBR_ELF_BAD_RELOCATION;
reloc_overflow:
    allocator->release(allocator->context, &out->memory); private_free(p); memset(out,0,sizeof(*out)); return BBR_ELF_RELOCATION_OVERFLOW;
unsupported_reloc:
    allocator->release(allocator->context, &out->memory); private_free(p); memset(out,0,sizeof(*out)); return BBR_ELF_UNSUPPORTED;
}

uintptr_t bbr_elf_find_symbol(const BbrElfModule *module, const char *name) {
    if (!module || !module->private_state || !name) return 0;
    const BbrElfPrivate *p = (const BbrElfPrivate *)module->private_state;
    for (uint16_t si = 0; si < p->eh.e_shnum; ++si) {
        const Elf64_Shdr *tab = &p->sections[si];
        if (tab->sh_type != SHT_SYMTAB || tab->sh_entsize != sizeof(Elf64_Sym) ||
            tab->sh_link >= p->eh.e_shnum || !range_ok(p->file_size, tab->sh_offset, tab->sh_size)) continue;
        const Elf64_Shdr *str = &p->sections[tab->sh_link];
        if (str->sh_type != SHT_STRTAB || !range_ok(p->file_size, str->sh_offset, str->sh_size)) continue;
        const Elf64_Sym *syms = (const Elf64_Sym *)(p->file + tab->sh_offset);
        size_t n = (size_t)(tab->sh_size / sizeof(Elf64_Sym));
        for (size_t j = 0; j < n; ++j) {
            const char *sym_name;
            if (!get_str(p->file + str->sh_offset, (size_t)str->sh_size, syms[j].st_name, &sym_name) || strcmp(sym_name,name)) continue;
            uintptr_t value;
            if (symbol_value(module, p, &syms[j], sym_name, NULL, NULL, &value)) return value;
        }
    }
    return 0;
}

void bbr_elf_unload(BbrElfModule *module) {
    if (!module) return;
    if (module->allocator && module->allocator->release && module->memory.rw)
        module->allocator->release(module->allocator->context, &module->memory);
    private_free((BbrElfPrivate *)module->private_state);
    memset(module, 0, sizeof(*module));
}

const char *bbr_elf_error_string(BbrElfError error) {
    switch (error) {
    case BBR_ELF_OK: return "ok";
    case BBR_ELF_BAD_ARGUMENT: return "bad loader argument";
    case BBR_ELF_BAD_FORMAT: return "invalid ELF64 AArch64 relocatable object";
    case BBR_ELF_UNSUPPORTED: return "unsupported ELF section or relocation";
    case BBR_ELF_OUT_OF_MEMORY: return "out of memory";
    case BBR_ELF_UNRESOLVED_SYMBOL: return "unresolved AOT runtime import";
    case BBR_ELF_BAD_RELOCATION: return "invalid relocation target or symbol";
    case BBR_ELF_RELOCATION_OVERFLOW: return "AArch64 relocation value out of range";
    case BBR_ELF_MEMORY_ERROR: return "executable memory allocation/seal failed";
    case BBR_ELF_NOT_FOUND: return "symbol not found";
    default: return "unknown ELF loader error";
    }
}
