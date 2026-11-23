# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent


class HorizonInputTests(unittest.TestCase):
    def test_button_and_analog_mapping_with_libnx_mock(self):
        compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
        if not compiler:
            self.skipTest("host C compiler unavailable")
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            (temp / "switch").mkdir()
            (temp / "switch.h").write_text(r'''#pragma once
#include <stdint.h>
typedef uint64_t u64;
typedef struct { int32_t x,y; } HidAnalogStickState;
typedef struct { int unused; } PadState;
enum { HidNpadStyleSet_NpadStandard=1 };
enum {
 HidNpadButton_A=1ull<<0, HidNpadButton_B=1ull<<1, HidNpadButton_X=1ull<<2,
 HidNpadButton_Y=1ull<<3, HidNpadButton_StickL=1ull<<4, HidNpadButton_StickR=1ull<<5,
 HidNpadButton_L=1ull<<6, HidNpadButton_R=1ull<<7, HidNpadButton_ZL=1ull<<8,
 HidNpadButton_ZR=1ull<<9, HidNpadButton_Plus=1ull<<10, HidNpadButton_Minus=1ull<<11,
 HidNpadButton_Left=1ull<<12, HidNpadButton_Up=1ull<<13,
 HidNpadButton_Right=1ull<<14, HidNpadButton_Down=1ull<<15
};
void padConfigureInput(int, int); void padInitializeDefault(PadState*); void padUpdate(PadState*);
u64 padGetButtons(PadState*); u64 padGetButtonsDown(PadState*);
HidAnalogStickState padGetStickPos(PadState*, int);
''', encoding="utf-8")
            harness = temp / "input_test.c"
            harness.write_text(r'''#include "switch/platform/horizon_input.h"
#include <assert.h>
#include <stdint.h>
#include <switch.h>
static u64 buttons, down; static int init_called, poll_called;
void padConfigureInput(int n,int styles){assert(n==1 && styles==HidNpadStyleSet_NpadStandard);}
void padInitializeDefault(PadState*p){(void)p;init_called++;}
void padUpdate(PadState*p){(void)p;poll_called++;}
u64 padGetButtons(PadState*p){(void)p;return buttons;}
u64 padGetButtonsDown(PadState*p){(void)p;return down;}
HidAnalogStickState padGetStickPos(PadState*p,int i){(void)p;return i==0?(HidAnalogStickState){-40000,1234}:(HidAnalogStickState){20000,-2345};}
int main(void){
 BbrInputState s;
 bbr_horizon_input_poll(&s); assert(s.buttons==0 && poll_called==0);
 bbr_horizon_input_init(); assert(init_called==1);
 buttons=HidNpadButton_A|HidNpadButton_ZR|HidNpadButton_Up|HidNpadButton_StickL;
 down=HidNpadButton_A|HidNpadButton_Plus;
 bbr_horizon_input_poll(&s);
 assert(poll_called==1);
 assert(s.buttons==(BBR_INPUT_A|BBR_INPUT_ZR|BBR_INPUT_UP|BBR_INPUT_LSTICK));
 assert(s.pressed==(BBR_INPUT_A|BBR_INPUT_PLUS));
 assert(s.left_x==INT16_MIN && s.left_y==1234);
 assert(s.right_x==20000 && s.right_y==-2345);
 return 0;
}
''', encoding="utf-8")
            exe = temp / "input-test"
            subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-I", str(temp), "-I", str(ROOT),
                            str(ROOT / "switch/platform/horizon_input.c"), str(harness),
                            "-o", str(exe)], check=True, capture_output=True)
            subprocess.run([str(exe)], check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()
