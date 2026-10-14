# Makefile -- firmware-qemu reference build.
#
# The judge builds any artifact with:
#     make CROSS=arm-none-eabi- build/firmware.elf
# so every artifact must accept CROSS and produce build/firmware.elf.

CROSS  ?= arm-none-eabi-
CC     := $(CROSS)gcc
OBJCOPY := $(CROSS)objcopy
OBJDUMP := $(CROSS)objdump
SIZE   := $(CROSS)size
READELF := $(CROSS)readelf

BUILD := build
ELF   := $(BUILD)/firmware.elf
BIN   := $(BUILD)/firmware.bin

SRCS := startup.c ring.c crc.c uart.c shell.c main.c
OBJS := $(patsubst %.c,$(BUILD)/%.o,$(SRCS))

CFLAGS := -Wall -Werror -Wextra -std=gnu11 -Os -g3
CFLAGS += -mcpu=cortex-m3 -mthumb -mfloat-abi=soft
CFLAGS += -ffreestanding -ffunction-sections -fdata-sections
CFLAGS += -fno-common -nostdlib -I.

LDFLAGS := -T link.ld -mcpu=cortex-m3 -mthumb -mfloat-abi=soft
LDFLAGS += -nostdlib -nostartfiles -Wl,--gc-sections -Wl,-Map=$(BUILD)/firmware.map
LDFLAGS += -Wl,--print-memory-usage

all: $(ELF)

$(BUILD):
	mkdir -p $(BUILD)

$(BUILD)/%.o: %.c common.h | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

$(ELF): $(OBJS)
	$(CC) $(CFLAGS) $(OBJS) $(LDFLAGS) -o $@

$(BIN): $(ELF)
	$(OBJCOPY) -O binary $< $@

size: $(ELF)
	$(SIZE) $<

clean:
	rm -rf $(BUILD)

.PHONY: all size clean
