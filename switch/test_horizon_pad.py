# SPDX-License-Identifier: GPL-3.0-or-later
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent


class HorizonPadBridgeTests(unittest.TestCase):
    def test_npad_to_ps4_pad_read_bridge(self):
        compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
        if not compiler:
            self.skipTest("host C compiler unavailable")
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            (temp / "switch").mkdir()
            (temp / "switch.h").write_text(r'''#pragma once
#include <stdint.h>
typedef uint64_t u64; typedef struct { int32_t x,y; } HidAnalogStickState;
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
            harness = temp / "bridge_test.c"
            harness.write_text(r'''#include "switch/platform/horizon_pad.h"
#include <assert.h>
#include <stdint.h>
#include <switch.h>
static u64 buttons, down; static int updates, configured;
void padConfigureInput(int n,int styles){assert(n==1&&styles==HidNpadStyleSet_NpadStandard);configured++;}
void padInitializeDefault(PadState*p){(void)p;}
void padUpdate(PadState*p){(void)p;updates++;}
u64 padGetButtons(PadState*p){(void)p;return buttons;}
u64 padGetButtonsDown(PadState*p){(void)p;return down;}
HidAnalogStickState padGetStickPos(PadState*p,int i){(void)p;return i==0?(HidAnalogStickState){INT32_MAX,INT32_MIN}:(HidAnalogStickState){0,0};}
int main(void){
 BbrPs4PadData report;
 bbr_horizon_pad_init(0,0); assert(configured==1);
 assert(bbr_ps4_pad_open(1,0,0)==BBR_PAD_HANDLE);
 buttons=HidNpadButton_A|HidNpadButton_ZL|HidNpadButton_Up;
 down=buttons;
 assert(bbr_horizon_pad_read_state(BBR_PAD_HANDLE,987654,&report)==0);
 assert(updates==1 && report.timestamp==987654 && report.connected);
 assert(report.buttons==(0x4000u|0x100u|0x10u));
 assert(report.l2==255 && report.left_x==255 && report.left_y==255);
 assert(bbr_horizon_pad_read(BBR_PAD_HANDLE,123,&report,3)==1 && updates==2);
 assert(bbr_horizon_pad_read(BBR_PAD_HANDLE,123,&report,0)==BBR_PAD_ERR_INVALID_ARG);
 return 0;
}
''', encoding="utf-8")
            exe = temp / "bridge-test"
            sources = [ROOT / "switch/platform/horizon_input.c",
                       ROOT / "switch/platform/ps4_pad.c",
                       ROOT / "switch/platform/horizon_pad.c", harness]
            subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-I", str(temp), "-I", str(ROOT), *map(str, sources),
                            "-o", str(exe)], check=True, capture_output=True)
            subprocess.run([str(exe)], check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()
