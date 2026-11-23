/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "ps4_pad.h"
#include <stddef.h>
#include <string.h>

#define BTN_L3       0x00000002u
#define BTN_R3       0x00000004u
#define BTN_OPTIONS  0x00000008u
#define BTN_UP       0x00000010u
#define BTN_RIGHT    0x00000020u
#define BTN_DOWN     0x00000040u
#define BTN_LEFT     0x00000080u
#define BTN_L2       0x00000100u
#define BTN_R2       0x00000200u
#define BTN_L1       0x00000400u
#define BTN_R1       0x00000800u
#define BTN_TRIANGLE 0x00001000u
#define BTN_CIRCLE   0x00002000u
#define BTN_CROSS    0x00004000u
#define BTN_SQUARE   0x00008000u
#define BTN_TOUCHPAD 0x00100000u

_Static_assert(sizeof(BbrPs4PadTouch) == 8, "PS4 pad touch ABI");
_Static_assert(offsetof(BbrPs4PadData, touches) == 60, "PS4 pad touch offset");
_Static_assert(offsetof(BbrPs4PadData, timestamp) == 80, "PS4 pad timestamp offset");
_Static_assert(sizeof(BbrPs4PadData) == 120, "PS4 pad data ABI");
_Static_assert(sizeof(BbrPs4PadInfo) == 28, "PS4 pad info ABI");

static int g_initialized;
static int g_open;
static BbrPs4RumbleFn g_rumble;
static void *g_rumble_context;

static uint8_t axis_to_u8(int16_t value, int invert) {
    int32_t v = invert ? -(int32_t)value : (int32_t)value;
    v += 32768;
    if (v < 0) v = 0;
    if (v > 65535) v = 65535;
    return (uint8_t)((v + 128) / 257);
}

static uint32_t translate_buttons(uint32_t buttons) {
    uint32_t out = 0;
#define X(src, dst) do { if (buttons & (src)) out |= (dst); } while (0)
    X(BBR_INPUT_LSTICK, BTN_L3); X(BBR_INPUT_RSTICK, BTN_R3);
    X(BBR_INPUT_PLUS, BTN_OPTIONS);
    X(BBR_INPUT_UP, BTN_UP); X(BBR_INPUT_RIGHT, BTN_RIGHT);
    X(BBR_INPUT_DOWN, BTN_DOWN); X(BBR_INPUT_LEFT, BTN_LEFT);
    X(BBR_INPUT_ZL, BTN_L2); X(BBR_INPUT_ZR, BTN_R2);
    X(BBR_INPUT_L, BTN_L1); X(BBR_INPUT_R, BTN_R1);
    /* Nintendo A/B/X/Y -> PlayStation Cross/Circle/Square/Triangle. */
    X(BBR_INPUT_A, BTN_CROSS); X(BBR_INPUT_B, BTN_CIRCLE);
    X(BBR_INPUT_X, BTN_SQUARE); X(BBR_INPUT_Y, BTN_TRIANGLE);
#undef X
    return out;
}

void bbr_ps4_pad_init(BbrPs4RumbleFn rumble, void *context) {
    g_initialized = 1;
    g_open = 0;
    g_rumble = rumble;
    g_rumble_context = context;
}

int32_t bbr_ps4_pad_open(int32_t user_id, int32_t type, int32_t index) {
    if (!g_initialized) return BBR_PAD_ERR_NOT_INITIALIZED;
    if (user_id != 1 || (type != 0 && type != 2) || index != 0)
        return BBR_PAD_ERR_INVALID_ARG;
    if (g_open) return BBR_PAD_ERR_ALREADY_OPEN;
    g_open = 1;
    return BBR_PAD_HANDLE;
}

int32_t bbr_ps4_pad_close(int32_t handle) {
    if (handle != BBR_PAD_HANDLE || !g_open) return BBR_PAD_ERR_INVALID_HANDLE;
    g_open = 0;
    return 0;
}

int32_t bbr_ps4_pad_read_state(int32_t handle, const BbrInputState *input,
                               uint64_t timestamp_us, BbrPs4PadData *out) {
    if (handle != BBR_PAD_HANDLE || !g_open) return BBR_PAD_ERR_INVALID_HANDLE;
    if (!input || !out) return BBR_PAD_ERR_INVALID_ARG;
    memset(out, 0, sizeof(*out));
    out->buttons = translate_buttons(input->buttons);
    out->left_x = axis_to_u8(input->left_x, 0);
    out->left_y = axis_to_u8(input->left_y, 1);
    out->right_x = axis_to_u8(input->right_x, 0);
    out->right_y = axis_to_u8(input->right_y, 1);
    out->l2 = (input->buttons & BBR_INPUT_ZL) ? 255 : 0;
    out->r2 = (input->buttons & BBR_INPUT_ZR) ? 255 : 0;
    out->connected = 1;
    out->connected_count = 1;
    out->timestamp = timestamp_us;
    return 0;
}

int32_t bbr_ps4_pad_read(int32_t handle, const BbrInputState *input,
                         uint64_t timestamp_us, BbrPs4PadData *out, int32_t count) {
    if (handle != BBR_PAD_HANDLE || !g_open) return BBR_PAD_ERR_INVALID_HANDLE;
    if (!out || count < 1 || count > 64) return BBR_PAD_ERR_INVALID_ARG;
    int32_t result = bbr_ps4_pad_read_state(handle, input, timestamp_us, out);
    return result ? result : 1;
}

int32_t bbr_ps4_pad_get_info(int32_t handle, BbrPs4PadInfo *out) {
    if (handle != BBR_PAD_HANDLE || !g_open) return BBR_PAD_ERR_INVALID_HANDLE;
    if (!out) return BBR_PAD_ERR_INVALID_ARG;
    memset(out, 0, sizeof(*out));
    out->pixel_density = 44.86f;
    out->resolution_x = 1920;
    out->resolution_y = 943;
    out->dead_zone_left = out->dead_zone_right = 2;
    out->connected_count = out->connected = 1;
    return 0;
}

int32_t bbr_ps4_pad_set_vibration(int32_t handle, const uint8_t motors[2]) {
    if (handle != BBR_PAD_HANDLE || !g_open) return BBR_PAD_ERR_INVALID_HANDLE;
    if (!motors) return BBR_PAD_ERR_INVALID_ARG;
    if (g_rumble) g_rumble(g_rumble_context, motors[0], motors[1]);
    return 0;
}

void bbr_ps4_pad_reset(void) {
    g_initialized = 0;
    g_open = 0;
    g_rumble = NULL;
    g_rumble_context = NULL;
}
