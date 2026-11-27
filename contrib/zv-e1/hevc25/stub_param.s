.text
stp x29, x30, [sp, #-16]!
mov x29, sp
nop
ldr w9, [x23, #0x178]
cbnz w9, 1f
ldr w9, [x23, #0x17c]
cmp w9, #12
b.ne 1f
ldr w9, [x23, #0x180]
cmp w9, #2
b.ne 1f
mov w9, #5
str w9, [x23, #0x178]
1: ldp x29, x30, [sp], #16
ret
