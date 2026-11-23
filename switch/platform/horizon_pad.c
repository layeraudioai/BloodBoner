/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "horizon_pad.h"
#include "horizon_input.h"
#include <switch.h>

void bbr_horizon_pad_init(BbrPs4RumbleFn rumble, void *rumble_context) {
    bbr_horizon_input_init();
    bbr_ps4_pad_init(rumble, rumble_context);
}

int32_t bbr_horizon_pad_read_state(int32_t handle, uint64_t timestamp_us,
                                   BbrPs4PadData *out) {
    BbrInputState input;
    bbr_horizon_input_poll(&input);
    return bbr_ps4_pad_read_state(handle, &input, timestamp_us, out);
}

int32_t bbr_horizon_pad_read(int32_t handle, uint64_t timestamp_us,
                             BbrPs4PadData *out, int32_t count) {
    if (count < 1 || count > 64) return BBR_PAD_ERR_INVALID_ARG;
    int32_t result = bbr_horizon_pad_read_state(handle, timestamp_us, out);
    return result ? result : 1;
}
