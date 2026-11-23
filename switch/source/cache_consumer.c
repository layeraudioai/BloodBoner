// SPDX-License-Identifier: GPL-3.0-or-later
// Portable NRO-side verifier for cache-index.tsv. This validates cached files;
// it does not load or execute game code.
#include "cache_consumer.h"

#include <ctype.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define BBR_LINE_MAX 8192
#define BBR_PATH_MAX 4096
#define BBR_CHUNK 65536

static const char *const kStages[] = {"audio", "aot_code", "boot_image", "game_files", "textures"};
#define BBR_STAGE_COUNT (sizeof(kStages) / sizeof(kStages[0]))

typedef struct Sha256 {
    uint32_t h[8];
    uint64_t bits;
    uint8_t block[64];
    size_t used;
} Sha256;

static const uint32_t kShaK[64] = {
    0x428a2f98u,0x71374491u,0xb5c0fbcfu,0xe9b5dba5u,0x3956c25bu,0x59f111f1u,0x923f82a4u,0xab1c5ed5u,
    0xd807aa98u,0x12835b01u,0x243185beu,0x550c7dc3u,0x72be5d74u,0x80deb1feu,0x9bdc06a7u,0xc19bf174u,
    0xe49b69c1u,0xefbe4786u,0x0fc19dc6u,0x240ca1ccu,0x2de92c6fu,0x4a7484aau,0x5cb0a9dcu,0x76f988dau,
    0x983e5152u,0xa831c66du,0xb00327c8u,0xbf597fc7u,0xc6e00bf3u,0xd5a79147u,0x06ca6351u,0x14292967u,
    0x27b70a85u,0x2e1b2138u,0x4d2c6dfcu,0x53380d13u,0x650a7354u,0x766a0abbu,0x81c2c92eu,0x92722c85u,
    0xa2bfe8a1u,0xa81a664bu,0xc24b8b70u,0xc76c51a3u,0xd192e819u,0xd6990624u,0xf40e3585u,0x106aa070u,
    0x19a4c116u,0x1e376c08u,0x2748774cu,0x34b0bcb5u,0x391c0cb3u,0x4ed8aa4au,0x5b9cca4fu,0x682e6ff3u,
    0x748f82eeu,0x78a5636fu,0x84c87814u,0x8cc70208u,0x90befffau,0xa4506cebu,0xbef9a3f7u,0xc67178f2u
};

static uint32_t rotr32(uint32_t x, unsigned n) { return (x >> n) | (x << (32u - n)); }

static void sha256_transform(Sha256 *s, const uint8_t *p) {
    uint32_t w[64];
    for (unsigned i = 0; i < 16; ++i)
        w[i] = ((uint32_t)p[4*i] << 24) | ((uint32_t)p[4*i+1] << 16) | ((uint32_t)p[4*i+2] << 8) | p[4*i+3];
    for (unsigned i = 16; i < 64; ++i) {
        uint32_t a = rotr32(w[i-15], 7) ^ rotr32(w[i-15], 18) ^ (w[i-15] >> 3);
        uint32_t b = rotr32(w[i-2], 17) ^ rotr32(w[i-2], 19) ^ (w[i-2] >> 10);
        w[i] = w[i-16] + a + w[i-7] + b;
    }
    uint32_t a=s->h[0], b=s->h[1], c=s->h[2], d=s->h[3];
    uint32_t e=s->h[4], f=s->h[5], g=s->h[6], h=s->h[7];
    for (unsigned i = 0; i < 64; ++i) {
        uint32_t s1 = rotr32(e,6) ^ rotr32(e,11) ^ rotr32(e,25);
        uint32_t ch = (e & f) ^ (~e & g);
        uint32_t t1 = h + s1 + ch + kShaK[i] + w[i];
        uint32_t s0 = rotr32(a,2) ^ rotr32(a,13) ^ rotr32(a,22);
        uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
        uint32_t t2 = s0 + maj;
        h=g; g=f; f=e; e=d+t1; d=c; c=b; b=a; a=t1+t2;
    }
    s->h[0]+=a; s->h[1]+=b; s->h[2]+=c; s->h[3]+=d;
    s->h[4]+=e; s->h[5]+=f; s->h[6]+=g; s->h[7]+=h;
}

static void sha256_init(Sha256 *s) {
    static const uint32_t init[8] = {0x6a09e667u,0xbb67ae85u,0x3c6ef372u,0xa54ff53au,
                                      0x510e527fu,0x9b05688cu,0x1f83d9abu,0x5be0cd19u};
    memcpy(s->h, init, sizeof init); s->bits = 0; s->used = 0;
}

static void sha256_update(Sha256 *s, const uint8_t *p, size_t n) {
    while (n) {
        size_t take = 64 - s->used;
        if (take > n) take = n;
        memcpy(s->block + s->used, p, take); s->used += take; p += take; n -= take;
        if (s->used == 64) { sha256_transform(s, s->block); s->bits += 512; s->used = 0; }
    }
}

static void sha256_final(Sha256 *s, uint8_t out[32]) {
    s->bits += (uint64_t)s->used * 8u;
    s->block[s->used++] = 0x80;
    if (s->used > 56) { while (s->used < 64) s->block[s->used++] = 0; sha256_transform(s, s->block); s->used = 0; }
    while (s->used < 56) s->block[s->used++] = 0;
    for (unsigned i = 0; i < 8; ++i) s->block[63-i] = (uint8_t)(s->bits >> (8*i));
    sha256_transform(s, s->block);
    for (unsigned i = 0; i < 8; ++i) {
        out[4*i]=(uint8_t)(s->h[i]>>24); out[4*i+1]=(uint8_t)(s->h[i]>>16);
        out[4*i+2]=(uint8_t)(s->h[i]>>8); out[4*i+3]=(uint8_t)s->h[i];
    }
}

static int hash_file(const char *path, unsigned long long *size, char hex[65]) {
    FILE *f = fopen(path, "rb");
    if (!f) return -1;
    Sha256 sha; sha256_init(&sha); *size = 0;
    uint8_t buf[BBR_CHUNK]; size_t n;
    while ((n = fread(buf, 1, sizeof buf, f)) != 0) { sha256_update(&sha, buf, n); *size += (unsigned long long)n; }
    int failed = ferror(f); fclose(f);
    if (failed) return -1;
    uint8_t digest[32]; sha256_final(&sha, digest);
    static const char digits[] = "0123456789abcdef";
    for (unsigned i = 0; i < 32; ++i) { hex[2*i]=digits[digest[i]>>4]; hex[2*i+1]=digits[digest[i]&15]; }
    hex[64] = 0; return 0;
}

static int fail(char *error, size_t cap, const char *message) {
    if (cap) snprintf(error, cap, "%s", message);
    return -1;
}

static int hex64(const char *s) {
    if (strlen(s) != 64) return 0;
    for (size_t i=0; i<64; ++i) if (!isxdigit((unsigned char)s[i])) return 0;
    return 1;
}

static int safe_relpath(const char *s) {
    if (!s || !*s || *s=='/' || strchr(s, '\\') || strchr(s, ':')) return 0;
    const char *part=s;
    for (const char *p=s;; ++p) {
        unsigned char c=(unsigned char)*p;
        if ((c < 32 && c != 0) || c == 127) return 0;
        if (c=='/' || c==0) {
            size_t n=(size_t)(p-part);
            if (!n || (n==1 && part[0]=='.') || (n==2 && part[0]=='.' && part[1]=='.')) return 0;
            if (!c) break;
            part=p+1;
        }
    }
    return 1;
}

static int stage_index(const char *name) {
    for (unsigned i=0; i<BBR_STAGE_COUNT; ++i) if (!strcmp(name,kStages[i])) return (int)i;
    return -1;
}

static char *next_field(char **cursor) {
    char *start=*cursor;
    char *tab=strchr(start,'\t');
    if (tab) { *tab=0; *cursor=tab+1; } else *cursor=NULL;
    return start;
}

int bb_cache_verify(const char *root, const char *expected_target,
                    BbCacheInfo *info, char *error, size_t error_size) {
    if (!root || !expected_target || !info || !error || !error_size)
        return fail(error,error_size,"invalid verifier arguments");
    memset(info,0,sizeof *info); error[0]=0;
    char index_path[BBR_PATH_MAX];
    int written=snprintf(index_path,sizeof index_path,"%s/%s",root,"cache-index.tsv");
    if (written<0 || (size_t)written>=sizeof index_path) return fail(error,error_size,"cache root path too long");
    FILE *f=fopen(index_path,"rb");
    if (!f) return fail(error,error_size,"cache-index.tsv is missing or unreadable");

    char line[BBR_LINE_MAX];
    if (!fgets(line,sizeof line,f) || strcmp(line,"BBRCACHE\t1\n")) { fclose(f); return fail(error,error_size,"unsupported cache index header"); }
    if (!fgets(line,sizeof line,f)) { fclose(f); return fail(error,error_size,"cache target row missing"); }
    size_t n=strlen(line);
    if (n && line[n-1]=='\n') line[--n]=0;
    if (strncmp(line,"target\t",7) || strcmp(line+7,expected_target)) { fclose(f); return fail(error,error_size,"cache target mismatch"); }
    snprintf(info->target,sizeof info->target,"%s",line+7);

    if (!fgets(line,sizeof line,f)) { fclose(f); return fail(error,error_size,"cache key row missing"); }
    n=strlen(line); if (n && line[n-1]=='\n') line[--n]=0;
    if (strncmp(line,"cache_key\t",10) || !hex64(line+10)) { fclose(f); return fail(error,error_size,"invalid cache key row"); }
    snprintf(info->cache_key,sizeof info->cache_key,"%s",line+10);

    if (!fgets(line,sizeof line,f)) { fclose(f); return fail(error,error_size,"manifest hash row missing"); }
    n=strlen(line); if (n && line[n-1]=='\n') line[--n]=0;
    if (strncmp(line,"manifest_sha256\t",16) || !hex64(line+16)) { fclose(f); return fail(error,error_size,"invalid manifest hash row"); }
    char manifest_path[BBR_PATH_MAX];
    written=snprintf(manifest_path,sizeof manifest_path,"%s/%s",root,"cache-manifest.json");
    if (written<0 || (size_t)written>=sizeof manifest_path) { fclose(f); return fail(error,error_size,"cache root path too long"); }
    unsigned long long manifest_size=0; char manifest_hash[65];
    if (hash_file(manifest_path,&manifest_size,manifest_hash) || strcmp(manifest_hash,line+16)) {
        fclose(f); return fail(error,error_size,"cache-manifest.json hash mismatch");
    }

    unsigned char stage_seen[BBR_STAGE_COUNT]={0};
    while (fgets(line,sizeof line,f)) {
        n=strlen(line);
        if (!n || line[n-1]!='\n') { fclose(f); return fail(error,error_size,"cache index line is too long or unterminated"); }
        line[--n]=0;
        char *cursor=line;
        char *kind=next_field(&cursor);
        char *stage=next_field(&cursor);
        char *path=next_field(&cursor);
        char *size_text=next_field(&cursor);
        char *digest=cursor;
        if (!kind || strcmp(kind,"file") || !stage || !path || !size_text || !digest || strchr(digest,'\t')) {
            fclose(f); return fail(error,error_size,"malformed cache file row");
        }
        int si=stage_index(stage);
        if (si<0 || !safe_relpath(path) || !hex64(digest)) { fclose(f); return fail(error,error_size,"invalid stage, path, or SHA-256 in cache index"); }
        if (!*size_text) { fclose(f); return fail(error,error_size,"invalid file size"); }
        for (const char *p=size_text; *p; ++p) if (!isdigit((unsigned char)*p)) { fclose(f); return fail(error,error_size,"invalid file size"); }
        char *end=NULL; unsigned long long expected_size=strtoull(size_text,&end,10);
        if (!end || *end) { fclose(f); return fail(error,error_size,"invalid file size"); }
        char full_path[BBR_PATH_MAX];
        written=snprintf(full_path,sizeof full_path,"%s/%s",root,path);
        if (written<0 || (size_t)written>=sizeof full_path) { fclose(f); return fail(error,error_size,"cache file path too long"); }
        unsigned long long actual_size=0; char actual_hash[65];
        if (hash_file(full_path,&actual_size,actual_hash) || actual_size!=expected_size || strcmp(actual_hash,digest)) {
            fclose(f); snprintf(error,error_size,"cache file failed verification: %.160s",path); return -1;
        }
        stage_seen[si]=1; ++info->files_verified; info->bytes_verified+=actual_size;
    }
    int io_error=ferror(f); fclose(f);
    if (io_error) return fail(error,error_size,"error reading cache index");
    for (unsigned i=0; i<BBR_STAGE_COUNT; ++i) {
        if (!stage_seen[i]) { snprintf(error,error_size,"required cache stage is empty: %s",kStages[i]); return -1; }
        ++info->stage_count;
    }
    if (!info->files_verified) return fail(error,error_size,"cache contains no files");
    return 0;
}

#ifdef BBR_CACHE_CONSUMER_STANDALONE
int main(int argc, char **argv) {
    if (argc!=3) { fprintf(stderr,"usage: cache-consumer ROOT switch1|switch2\n"); return 2; }
    BbCacheInfo info; char error[256];
    if (bb_cache_verify(argv[1],argv[2],&info,error,sizeof error)) { fprintf(stderr,"cache invalid: %s\n",error); return 1; }
    printf("verified %s cache %s: %llu files, %llu bytes\n",info.target,info.cache_key,info.files_verified,info.bytes_verified);
    return 0;
}
#endif
