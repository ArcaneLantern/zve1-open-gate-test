.text
stp x29, x30, [sp, #-16]!
mov x29, sp
nop
cmp w0, #2
b.ne 1f
mov w0, #3
1: ldp x29, x30, [sp], #16
ret
