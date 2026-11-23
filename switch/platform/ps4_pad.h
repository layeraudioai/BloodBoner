/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef BBR_HORIZON_PS4_PAD_H
#define BBR_HORIZON_PS4_PAD_H
#include <stdint.h>
#include "horizon_input.h"

#ifdef __cplusplus
extern "C" {
#endif

enum {
    BBR_PAD_ERR_INVALID_ARG = (int32_t)0x80920001,
    BBR_PAD_ERR_INVALID_HANDLE = (int32_t)0x80920003,
    BBR_PAD_ERR_ALREADY_OPEN = (int32_t)0x80920004,
    BBR_PAD_ERR_NOT_INITIALIZED = (int32_t)0x80920005,
    BBR_PAD_HANDLE = 1
};

typedef struct BbrPs4PadTouch {
    uint16_t x, y;
    uint8_t id, reserve[3];
} BbrPs4PadTouch;

typedef struct BbrPs4PadData {
    uint32_t buttons;
    uint8_t left_x, left_y, right_x, right_y;
    uint8_t l2, r2, analog_padding[2];
    float orientation[4], acceleration[3], angular_velocity[3];
    uint8_t touch_count, touch_reserve[3];
    uint32_t touch_held_time;
    BbrPs4PadTouch touches[2];
    uint8_t connected, pad0[3];
    uint64_t timestamp;
    uint8_t extension[16];
    uint8_t connected_count, reserve[2], unique_length, unique[12];
} BbrPs4PadData;

typedef struct BbrPs4PadInfo {
    float pixel_density;
    uint16_t resolution_x, resolution_y;
    uint8_t dead_zone_left, dead_zone_right, connection_type, connected_count;
    uint8_t connected, pad[3];
    int32_t device_class;
    uint8_t reserve[8];
} BbrPs4PadInfo;

typedef void (*BbrPs4RumbleFn)(void *context, uint8_t large, uint8_t small);

void bbr_ps4_pad_init(BbrPs4RumbleFn rumble, void *context);
int32_t bbr_ps4_pad_open(int32_t user_id, int32_t type, int32_t index);
int32_t bbr_ps4_pad_close(int32_t handle);
int32_t bbr_ps4_pad_read_state(int32_t handle, const BbrInputState *input,
                               uint64_t timestamp_us, BbrPs4PadData *out);
int32_t bbr_ps4_pad_read(int32_t handle, const BbrInputState *input,
                         uint64_t timestamp_us, BbrPs4PadData *out, int32_t count);
int32_t bbr_ps4_pad_get_info(int32_t handle, BbrPs4PadInfo *out);
int32_t bbr_ps4_pad_set_vibration(int32_t handle, const uint8_t motors[2]);
void bbr_ps4_pad_reset(void);

#ifdef __cplusplus
}
#endif
#endif
