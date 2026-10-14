/* Judge linker script: flat 64 KiB RAM at 0x0, entry at 0x0. */
OUTPUT_ARCH( "riscv" )
ENTRY(_start)

SECTIONS
{
  . = 0x00000000;
  .text.init : { *(.text.init) }
  .text : { *(.text) *(.text.*) }
  . = ALIGN(0x1000);
  .data : { *(.data) *(.data.*) *(.sdata) *(.sdata.*) *(.tohost) }
  .srodata : { *(.srodata*) }
  .rodata : { *(.rodata) *(.rodata.*) }
  .bss : { *(.bss) *(.bss.*) *(.sbss*) }
  _end = .;
  /DISCARD/ : { *(.comment) *(.riscv.attributes) *(.eh_frame*) *(.note*) }
}
