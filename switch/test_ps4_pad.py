# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent


class Ps4PadTests(unittest.TestCase):
    def test_ps4_pad_service_contract_and_mapping(self):
        compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
        if not compiler:
            self.skipTest("host C compiler unavailable")
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            harness = temp / "pad_test.c"
            harness.write_text(r'''#include "switch/platform/ps4_pad.h"
#include <assert.h>
#include <stdint.h>
#include <string.h>
static unsigned rumble_calls; static unsigned rumble_large, rumble_small;
static void rumble(void *ctx,uint8_t large,uint8_t small){assert(ctx==(void*)0x1234);++rumble_calls;rumble_large=large;rumble_small=small;}
int main(void){
 BbrInputState in={0}; BbrPs4PadData d; BbrPs4PadInfo info;
 assert(sizeof(BbrPs4PadData)==120 && sizeof(BbrPs4PadInfo)==28);
 assert(bbr_ps4_pad_open(1,0,0)==BBR_PAD_ERR_NOT_INITIALIZED);
 bbr_ps4_pad_init(rumble,(void*)0x1234);
 assert(bbr_ps4_pad_open(2,0,0)==BBR_PAD_ERR_INVALID_ARG);
 assert(bbr_ps4_pad_open(1,0,0)==BBR_PAD_HANDLE);
 assert(bbr_ps4_pad_open(1,0,0)==BBR_PAD_ERR_ALREADY_OPEN);
 in.buttons=BBR_INPUT_A|BBR_INPUT_B|BBR_INPUT_X|BBR_INPUT_Y|BBR_INPUT_L|BBR_INPUT_R|BBR_INPUT_ZL|BBR_INPUT_ZR|BBR_INPUT_PLUS|BBR_INPUT_UP;
 in.left_x=0;in.left_y=INT16_MIN;in.right_x=INT16_MAX;in.right_y=0;
 assert(bbr_ps4_pad_read_state(BBR_PAD_HANDLE,&in,123456,&d)==0);
 assert(d.buttons==(0x4000u|0x2000u|0x8000u|0x1000u|0x400u|0x800u|0x100u|0x200u|0x8u|0x10u));
 assert(d.left_x==128 && d.left_y==255 && d.right_x==255 && d.right_y==128);
 assert(d.l2==255 && d.r2==255 && d.connected==1 && d.connected_count==1 && d.timestamp==123456);
 assert(bbr_ps4_pad_read(BBR_PAD_HANDLE,&in,1,&d,0)==BBR_PAD_ERR_INVALID_ARG);
 assert(bbr_ps4_pad_read(BBR_PAD_HANDLE,&in,1,&d,2)==1);
 assert(bbr_ps4_pad_get_info(BBR_PAD_HANDLE,&info)==0 && info.connected && info.connected_count==1);
 const uint8_t motors[2]={17,203}; assert(bbr_ps4_pad_set_vibration(BBR_PAD_HANDLE,motors)==0);
 assert(rumble_calls==1 && rumble_large==17 && rumble_small==203);
 assert(bbr_ps4_pad_close(BBR_PAD_HANDLE)==0);
 assert(bbr_ps4_pad_read_state(BBR_PAD_HANDLE,&in,0,&d)==BBR_PAD_ERR_INVALID_HANDLE);
 bbr_ps4_pad_reset(); return 0;
}
''', encoding="utf-8")
            exe = temp / "pad-test"
            subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-I", str(ROOT), str(ROOT / "switch/platform/ps4_pad.c"),
                            str(harness), "-o", str(exe)], check=True, capture_output=True)
            subprocess.run([str(exe)], check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()
