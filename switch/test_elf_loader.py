# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent


def make_runtime_object():
    names = b"\0host_unit\0bbr_units\0bbr_unit_count\0bbr_image_hash\0bbr_abi_version\0bbr_abi_flags\0bbr_image_base\0bbr_dirty\0"
    offs = {name: names.index(name.encode()) for name in
            ("host_unit", "bbr_units", "bbr_unit_count", "bbr_image_hash",
             "bbr_abi_version", "bbr_abi_flags", "bbr_image_base", "bbr_dirty")}
    text = struct.pack("<I", 0xD65F03C0)
    rodata = struct.pack("<QQ", 0x20, 0)
    data = bytearray(48)
    struct.pack_into("<Q", data, 0, 1)
    struct.pack_into("<Q", data, 8, 0x123456789ABCDEF0)
    struct.pack_into("<I", data, 16, 2)
    struct.pack_into("<Q", data, 24, 2)  # only dirty-byte ABI feature
    symbols = [bytes(24)]
    symbols.extend([
        struct.pack("<IBBHQQ", offs["host_unit"], 0x12, 0, 0, 0, 0),
        struct.pack("<IBBHQQ", offs["bbr_units"], 0x11, 0, 2, 0, 16),
        struct.pack("<IBBHQQ", offs["bbr_unit_count"], 0x11, 0, 3, 0, 8),
        struct.pack("<IBBHQQ", offs["bbr_image_hash"], 0x11, 0, 3, 8, 8),
        struct.pack("<IBBHQQ", offs["bbr_abi_version"], 0x11, 0, 3, 16, 4),
        struct.pack("<IBBHQQ", offs["bbr_abi_flags"], 0x11, 0, 3, 24, 8),
        struct.pack("<IBBHQQ", offs["bbr_image_base"], 0x11, 0, 3, 32, 8),
        struct.pack("<IBBHQQ", offs["bbr_dirty"], 0x11, 0, 3, 40, 1),
    ])
    symtab = b"".join(symbols)
    rela = struct.pack("<QQq", 8, (1 << 32) | 257, 0)
    shstr = b"\0.text\0.rodata\0.data\0.rela.rodata\0.symtab\0.strtab\0.shstrtab\0"
    section_names = (".text", ".rodata", ".data", ".rela.rodata", ".symtab", ".strtab", ".shstrtab")
    name_offsets = {name: shstr.index(name.encode()) for name in section_names}
    chunks = [(text, 4), (rodata, 8), (bytes(data), 8), (rela, 8), (symtab, 8), (names, 1), (shstr, 1)]
    blob = bytearray(64); offsets = []
    for chunk, alignment in chunks:
        while len(blob) % alignment: blob.append(0)
        offsets.append(len(blob)); blob.extend(chunk)
    while len(blob) % 8: blob.append(0)
    shoff = len(blob)
    headers = [bytes(64)]
    defs = [
        (1, 0x6, offsets[0], len(text), 0, 0, 4, 0),
        (1, 0x2, offsets[1], len(rodata), 0, 0, 8, 0),
        (1, 0x3, offsets[2], len(data), 0, 0, 8, 0),
        (4, 0, offsets[3], len(rela), 5, 2, 8, 24),
        (2, 0, offsets[4], len(symtab), 6, 1, 8, 24),
        (3, 0, offsets[5], len(names), 0, 0, 1, 0),
        (3, 0, offsets[6], len(shstr), 0, 0, 1, 0),
    ]
    for name, (kind, flags, offset, size, link, info, alignment, entsize) in zip(section_names, defs):
        headers.append(struct.pack("<IIQQQQIIQQ", name_offsets[name], kind, flags, 0,
                                   offset, size, link, info, alignment, entsize))
    blob.extend(b"".join(headers))
    ident = b"\x7fELF" + bytes([2, 1, 1, 0, 0]) + bytes(7)
    blob[:64] = struct.pack("<16sHHIQQQIHHHHHH", ident, 1, 183, 1, 0, 0, shoff,
                            0, 64, 0, 0, 64, len(headers), 7)
    return bytes(blob)


def make_object(undefined=False, unsupported=False):
    # ELF64 little-endian AArch64 ET_REL: .text: RET; .data: pointer to foo.
    names = b"\0foo\0missing_runtime_import\0"
    foo_name = names.index(b"foo")
    missing_name = names.index(b"missing_runtime_import")
    strtab = names
    sym0 = bytes(24)
    if undefined:
        sym1 = struct.pack("<IBBHQQ", missing_name, 0x12, 0, 0, 0, 0)
    else:
        sym1 = struct.pack("<IBBHQQ", foo_name, 0x12, 0, 1, 0, 4)
    symtab = sym0 + sym1
    reloc_type = 999 if unsupported else 257  # R_AARCH64_ABS64
    rela = struct.pack("<QQq", 0, (1 << 32) | reloc_type, 0)
    text = struct.pack("<I", 0xD65F03C0)
    data = bytes(8)
    shstr = b"\0.text\0.data\0.rela.data\0.symtab\0.strtab\0.shstrtab\0"
    sh_names = {name: shstr.index(name.encode()) for name in
                (".text", ".data", ".rela.data", ".symtab", ".strtab", ".shstrtab")}
    chunks = [(text, 4), (data, 8), (rela, 8), (symtab, 8), (strtab, 1), (shstr, 1)]
    blob = bytearray(64)
    offsets = []
    for chunk, alignment in chunks:
        while len(blob) % alignment:
            blob.append(0)
        offsets.append(len(blob))
        blob.extend(chunk)
    while len(blob) % 8:
        blob.append(0)
    shoff = len(blob)
    headers = [bytes(64)]
    # sh_type, flags, offset, size, link, info, alignment, entsize
    definitions = [
        (1, 0x6, offsets[0], len(text), 0, 0, 4, 0),
        (1, 0x3, offsets[1], len(data), 0, 0, 8, 0),
        (4, 0, offsets[2], len(rela), 4, 2, 8, 24),
        (2, 0, offsets[3], len(symtab), 5, 1, 8, 24),
        (3, 0, offsets[4], len(strtab), 0, 0, 1, 0),
        (3, 0, offsets[5], len(shstr), 0, 0, 1, 0),
    ]
    for i, (kind, flags, offset, size, link, info, alignment, entsize) in enumerate(definitions, 1):
        name = (".text", ".data", ".rela.data", ".symtab", ".strtab", ".shstrtab")[i-1]
        headers.append(struct.pack("<IIQQQQIIQQ", sh_names[name], kind, flags, 0,
                                   offset, size, link, info, alignment, entsize))
    blob.extend(b"".join(headers))
    ident = b"\x7fELF" + bytes([2, 1, 1, 0, 0]) + bytes(7)
    ehdr = struct.pack("<16sHHIQQQIHHHHHH", ident, 1, 183, 1, 0, 0, shoff,
                        0, 64, 0, 0, 64, len(headers), 6)
    blob[:64] = ehdr
    return bytes(blob)


class ElfLoaderTests(unittest.TestCase):
    def test_loaded_table_binds_to_runtime_dispatcher(self):
        compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
        if not compiler:
            self.skipTest("host C compiler unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            obj = tmp / "runtime-module.o"; obj.write_bytes(make_runtime_object())
            harness = tmp / "bind.c"
            harness.write_text(r'''#include "switch/runtime/bbr_runtime.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static int reserve(void*c,size_t n,size_t a,BbrElfMemory*m){(void)c;(void)a;m->rw=calloc(1,n);m->rx=m->rw;m->capacity=n;m->owner=m->rw;return m->rw!=0;}
static int seal(void*c,BbrElfMemory*m){(void)c;(void)m;return 1;}
static void release(void*c,BbrElfMemory*m){(void)c;free(m->owner);memset(m,0,sizeof(*m));}
static void synthetic_unit(GuestState*s){s->gregs[0]+=99;}
static uintptr_t resolve(void*c,const char*n){(void)c;return strcmp(n,"host_unit")==0?(uintptr_t)synthetic_unit:0;}
int main(int argc,char**argv){assert(argc==2);FILE*f=fopen(argv[1],"rb");assert(f);fseek(f,0,SEEK_END);long n=ftell(f);rewind(f);void*b=malloc((size_t)n);assert(b&&fread(b,1,(size_t)n,f)==(size_t)n);fclose(f);
 BbrElfAllocator a={0,reserve,seal,release};BbrElfModule m;assert(bbr_elf_load(&m,b,(size_t)n,&a,resolve,0)==BBR_ELF_OK);
 assert(bbr_runtime_bind_elf(&m,0x100000,0x1000,UINT64_C(0x123456789ABCDEF0),0,0)==0);
 uintptr_t image_base=bbr_elf_find_symbol(&m,"bbr_image_base");uint64_t base=0;memcpy(&base,(void*)image_base,8);assert(base==0x100000);
 GuestState s;bbr_guest_state_reset(&s);bbr_runtime_run(&s,0x100020);assert(s.gregs[0]==99&&bbr_runtime_last_fault()==BBR_RUNTIME_FAULT_NONE);
 bbr_runtime_unbind();bbr_elf_unload(&m);free(b);return 0;}
''', encoding="utf-8")
            exe = tmp / "bind-test"
            subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-I", str(ROOT), str(ROOT / "switch/runtime/bbr_elf_loader.c"),
                            str(ROOT / "switch/runtime/bbr_runtime.c"), str(harness),
                            "-o", str(exe)], check=True, capture_output=True)
            result = subprocess.run([str(exe), str(obj)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))

    def test_relocates_synthetic_aarch64_et_rel(self):
        compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
        if not compiler:
            self.skipTest("host C compiler unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            obj = tmp / "synthetic.o"
            obj.write_bytes(make_object())
            harness = tmp / "load.c"
            harness.write_text(r'''#include "switch/runtime/bbr_elf_loader.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static int reserve(void*c,size_t n,size_t a,BbrElfMemory*m){(void)c;(void)a;m->rw=calloc(1,n);m->rx=m->rw;m->capacity=n;m->owner=m->rw;return m->rw!=0;}
static int seal(void*c,BbrElfMemory*m){(void)c;(void)m;return 1;}
static void release(void*c,BbrElfMemory*m){(void)c;free(m->owner);memset(m,0,sizeof(*m));}
int main(int argc,char**argv){assert(argc==2);FILE*f=fopen(argv[1],"rb");assert(f);fseek(f,0,SEEK_END);long n=ftell(f);rewind(f);void*b=malloc((size_t)n);assert(b&&fread(b,1,(size_t)n,f)==(size_t)n);fclose(f);
 BbrElfAllocator a={0,reserve,seal,release};BbrElfModule m;BbrElfError e=bbr_elf_load(&m,b,(size_t)n,&a,0,0);assert(e==BBR_ELF_OK);
 assert((uintptr_t)bbr_elf_find_symbol(&m,"foo")== (uintptr_t)(m.memory.rx));
 uint64_t relocated;memcpy(&relocated,m.memory.rw+8,8);assert(relocated==(uint64_t)(uintptr_t)m.memory.rx);
 bbr_elf_unload(&m);free(b);return 0;}
''', encoding="utf-8")
            exe = tmp / "loader-test"
            subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-I", str(ROOT), str(ROOT / "switch/runtime/bbr_elf_loader.c"),
                            str(harness), "-o", str(exe)], check=True, capture_output=True)
            result = subprocess.run([str(exe), str(obj)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))

    def test_fails_closed_on_unresolved_import_and_unknown_relocation(self):
        compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
        if not compiler:
            self.skipTest("host C compiler unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            harness = tmp / "errors.c"
            harness.write_text(r'''#include "switch/runtime/bbr_elf_loader.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static int reserve(void*c,size_t n,size_t a,BbrElfMemory*m){(void)c;(void)a;m->rw=calloc(1,n);m->rx=m->rw;m->capacity=n;m->owner=m->rw;return m->rw!=0;}
static int seal(void*c,BbrElfMemory*m){(void)c;(void)m;return 1;}
static void release(void*c,BbrElfMemory*m){(void)c;free(m->owner);memset(m,0,sizeof(*m));}
int main(int argc,char**argv){assert(argc==3);BbrElfAllocator a={0,reserve,seal,release};
 for(int i=1;i<=2;i++){FILE*f=fopen(argv[i],"rb");assert(f);fseek(f,0,SEEK_END);long n=ftell(f);rewind(f);void*b=malloc((size_t)n);assert(b&&fread(b,1,(size_t)n,f)==(size_t)n);fclose(f);BbrElfModule m;BbrElfError e=bbr_elf_load(&m,b,(size_t)n,&a,0,0);assert(e==(i==1?BBR_ELF_UNRESOLVED_SYMBOL:BBR_ELF_UNSUPPORTED));assert(!m.private_state&&!m.memory.rw);free(b);}return 0;}
''', encoding="utf-8")
            unresolved = tmp / "unresolved.o"; unresolved.write_bytes(make_object(undefined=True))
            unsupported = tmp / "unsupported.o"; unsupported.write_bytes(make_object(unsupported=True))
            exe = tmp / "loader-errors"
            subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-I", str(ROOT), str(ROOT / "switch/runtime/bbr_elf_loader.c"),
                            str(harness), "-o", str(exe)], check=True, capture_output=True)
            result = subprocess.run([str(exe), str(unresolved), str(unsupported)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))


if __name__ == "__main__":
    unittest.main()
