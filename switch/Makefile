# SPDX-License-Identifier: GPL-3.0-or-later
# Minimal devkitPro/libnx NRO bootstrap. See switch/README.md.

.SUFFIXES:

ifeq ($(strip $(DEVKITPRO)),)
$(error DEVKITPRO is not set. Install devkitPro with the Switch/libnx toolchain.)
endif

TARGET_PROFILE ?= switch1
TARGET      := bloodboner-bootstrap-$(TARGET_PROFILE)
BUILD       := build/$(TARGET_PROFILE)
SOURCES     := source runtime platform
DATA        :=
INCLUDES    :=

APP_TITLE   := BloodBoner Switch Bootstrap ($(TARGET_PROFILE))
APP_AUTHOR  := BloodBoner contributors
APP_VERSION := 0.1.0
ifeq ($(filter $(TARGET_PROFILE),switch1 switch2),)
$(error TARGET_PROFILE must be switch1 or switch2)
endif

CFLAGS      = -O2 -g -Wall -Wextra -ffunction-sections -fdata-sections $(if $(filter switch2,$(TARGET_PROFILE)),-DBBR_SWITCH_TARGET_SWITCH2,) $(INCLUDE)
CXXFLAGS    = $(CFLAGS) -fno-rtti -fno-exceptions
LDFLAGS     := -specs=$(DEVKITPRO)/libnx/switch.specs -Wl,--gc-sections

LIBS        := -lnx

include $(DEVKITPRO)/libnx/switch_rules
