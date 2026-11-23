// SPDX-License-Identifier: GPL-3.0-or-later
// Horizon bring-up and cache validation only; no game-code loader is present.
#include <switch.h>
#include <stdbool.h>
#include <stdio.h>

#include "cache_consumer.h"

#ifndef BBR_SWITCH_TARGET
#ifdef BBR_SWITCH_TARGET_SWITCH2
#define BBR_SWITCH_TARGET "switch2"
#else
#define BBR_SWITCH_TARGET "switch1"
#endif
#endif

#define BBR_CACHE_ROOT "sdmc:/switch/bloodboner/cache/active"

static void draw_screen(bool details, bool sd_mounted, bool cache_ok,
                        const BbCacheInfo *cache, const char *cache_error) {
    consoleClear();
    printf("BloodBoner — Horizon bootstrap\n");
    printf("================================\n\n");
    printf("Bring-up and cache validation only; no game runtime.\n\n");
    printf("Build target: %s\n", BBR_SWITCH_TARGET);
    printf("SD card:      %s\n", sd_mounted ? "mounted" : "unavailable");
    printf("Cache:        %s\n", cache_ok ? "verified" : "not ready");
    if (cache_ok) {
        printf("Files:        %llu verified (%llu bytes)\n",
               cache->files_verified, cache->bytes_verified);
    }

    if (details) {
        printf("\nExpected cache directory:\n%s\n", BBR_CACHE_ROOT);
        if (cache_ok) {
            printf("Target:       %s\n", cache->target);
            printf("Cache key:    %.64s\n", cache->cache_key);
            printf("Stages:       %u/5 verified\n", cache->stage_count);
            printf("\nThe cache is data only. No AOT loader or\n"
                   "game services are implemented in this build.\n");
        } else {
            printf("\nCache status: %.120s\n", cache_error ? cache_error : "unknown error");
            printf("PC setup must publish a complete cache here.\n");
        }
    } else {
        printf("\nA: details\n");
    }

    printf("\nA: toggle details       Plus: exit\n");
}

int main(int argc, char **argv) {
    (void)argc;
    (void)argv;

    consoleInit(NULL);
    padConfigureInput(1, HidNpadStyleSet_NpadStandard);
    PadState pad;
    padInitializeDefault(&pad);

    const Result mount_result = fsdevMountSdmc();
    const bool sd_mounted = R_SUCCEEDED(mount_result);
    BbCacheInfo cache = {0};
    char cache_error[256] = "SD card mount failed";
    if (sd_mounted) {
        consoleClear();
        printf("BloodBoner cache check\n");
        printf("Reading and hashing cache files...\n");
        consoleUpdate(NULL);
    }
    const bool cache_ok = sd_mounted &&
        bb_cache_verify(BBR_CACHE_ROOT, BBR_SWITCH_TARGET, &cache,
                        cache_error, sizeof cache_error) == 0;
    bool details = false;
    draw_screen(details, sd_mounted, cache_ok, &cache, cache_error);

    while (appletMainLoop()) {
        padUpdate(&pad);
        const u64 down = padGetButtonsDown(&pad);
        if (down & HidNpadButton_Plus) break;
        if (down & HidNpadButton_A) {
            details = !details;
            draw_screen(details, sd_mounted, cache_ok, &cache, cache_error);
        }
        consoleUpdate(NULL);
    }

    if (sd_mounted) fsdevUnmountDevice("sdmc");
    consoleExit(NULL);
    return 0;
}
