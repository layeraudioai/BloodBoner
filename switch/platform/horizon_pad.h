/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef BBR_HORIZON_PAD_H
#define BBR_HORIZON_PAD_H
#include "ps4_pad.h"

/* Bridge Horizon Npad input sampling to the AOT runtime's PS4 PadData ABI. */
void bbr_horizon_pad_init(BbrPs4RumbleFn rumble, void *rumble_context);
int32_t bbr_horizon_pad_read_state(int32_t handle, uint64_t timestamp_us,
                                   BbrPs4PadData *out);
int32_t bbr_horizon_pad_read(int32_t handle, uint64_t timestamp_us,
                             BbrPs4PadData *out, int32_t count);
#endif
