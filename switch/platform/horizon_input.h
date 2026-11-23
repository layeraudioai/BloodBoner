/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef BBR_HORIZON_INPUT_H
#define BBR_HORIZON_INPUT_H
#include <stdint.h>

enum BbrInputButton {
    BBR_INPUT_A      = 1u << 0,
    BBR_INPUT_B      = 1u << 1,
    BBR_INPUT_X      = 1u << 2,
    BBR_INPUT_Y      = 1u << 3,
    BBR_INPUT_L      = 1u << 4,
    BBR_INPUT_R      = 1u << 5,
    BBR_INPUT_ZL     = 1u << 6,
    BBR_INPUT_ZR     = 1u << 7,
    BBR_INPUT_PLUS   = 1u << 8,
    BBR_INPUT_MINUS  = 1u << 9,
    BBR_INPUT_UP     = 1u << 10,
    BBR_INPUT_DOWN   = 1u << 11,
    BBR_INPUT_LEFT   = 1u << 12,
    BBR_INPUT_RIGHT  = 1u << 13,
    BBR_INPUT_LSTICK = 1u << 14,
    BBR_INPUT_RSTICK = 1u << 15
};

typedef struct BbrInputState {
    uint32_t buttons;
    uint32_t pressed;
    int16_t left_x, left_y;
    int16_t right_x, right_y;
} BbrInputState;

/* Initializes libnx's standard Npad input and polls one frame into a stable API. */
void bbr_horizon_input_init(void);
void bbr_horizon_input_poll(BbrInputState *out);
#endif
