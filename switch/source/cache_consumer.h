// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct BbCacheInfo {
    char target[16];
    char cache_key[65];
    unsigned long long files_verified;
    unsigned long long bytes_verified;
    unsigned stage_count;
} BbCacheInfo;

// Verifies the portable TSV index and hashes every listed regular file.
// expected_target must be "switch1" or "switch2". Returns 0 on success.
int bb_cache_verify(const char *root, const char *expected_target,
                    BbCacheInfo *info, char *error, size_t error_size);

#ifdef __cplusplus
}
#endif
