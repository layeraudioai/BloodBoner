/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "horizon_input.h"
#include <switch.h>
#include <string.h>

static PadState g_pad;
static int g_initialized;

static int16_t clamp_stick(int32_t value) {
    if (value > INT16_MAX) return INT16_MAX;
    if (value < INT16_MIN) return INT16_MIN;
    return (int16_t)value;
}

static uint32_t map_buttons(u64 raw) {
    uint32_t out = 0;
#define MAP_BUTTON(nx, bbr) do { if (raw & (nx)) out |= (bbr); } while (0)
    MAP_BUTTON(HidNpadButton_A, BBR_INPUT_A);
    MAP_BUTTON(HidNpadButton_B, BBR_INPUT_B);
    MAP_BUTTON(HidNpadButton_X, BBR_INPUT_X);
    MAP_BUTTON(HidNpadButton_Y, BBR_INPUT_Y);
    MAP_BUTTON(HidNpadButton_L, BBR_INPUT_L);
    MAP_BUTTON(HidNpadButton_R, BBR_INPUT_R);
    MAP_BUTTON(HidNpadButton_ZL, BBR_INPUT_ZL);
    MAP_BUTTON(HidNpadButton_ZR, BBR_INPUT_ZR);
    MAP_BUTTON(HidNpadButton_Plus, BBR_INPUT_PLUS);
    MAP_BUTTON(HidNpadButton_Minus, BBR_INPUT_MINUS);
    MAP_BUTTON(HidNpadButton_Up, BBR_INPUT_UP);
    MAP_BUTTON(HidNpadButton_Down, BBR_INPUT_DOWN);
    MAP_BUTTON(HidNpadButton_Left, BBR_INPUT_LEFT);
    MAP_BUTTON(HidNpadButton_Right, BBR_INPUT_RIGHT);
    MAP_BUTTON(HidNpadButton_StickL, BBR_INPUT_LSTICK);
    MAP_BUTTON(HidNpadButton_StickR, BBR_INPUT_RSTICK);
#undef MAP_BUTTON
    return out;
}

void bbr_horizon_input_init(void) {
    padConfigureInput(1, HidNpadStyleSet_NpadStandard);
    padInitializeDefault(&g_pad);
    g_initialized = 1;
}

void bbr_horizon_input_poll(BbrInputState *out) {
    if (!out) return;
    memset(out, 0, sizeof(*out));
    if (!g_initialized) return;
    padUpdate(&g_pad);
    out->buttons = map_buttons(padGetButtons(&g_pad));
    out->pressed = map_buttons(padGetButtonsDown(&g_pad));
    const HidAnalogStickState left = padGetStickPos(&g_pad, 0);
    const HidAnalogStickState right = padGetStickPos(&g_pad, 1);
    out->left_x = clamp_stick(left.x);
    out->left_y = clamp_stick(left.y);
    out->right_x = clamp_stick(right.x);
    out->right_y = clamp_stick(right.y);
}
