; create at 0x04a14000

        mov eax, [ebp-0xf8]
        test eax, eax
        jns count_positive
        xor eax, eax
    count_positive:
        cmp eax, 32766
        jle count_valid
        xor eax, eax
    count_valid:
        mov dword ptr [77680384], eax
        push 0x112f38c
        push 0x112f358
        push 32496
        push 108
        push edi
        call 77677056
        push 0x112f3f4
        push 0x112f3c0
        push 32497
        push 231
        push edi
        call 77677056
        xor esi, esi
        mov [ebp-0xf0], esi
        jmp 0x828738
    
; button at 0x04a14200

        push ebp
        mov ebp, esp
        push esi
        push 0x11b5950
        push 0x120
        call 0xe624ae
        add esp, 8
        test eax, eax
        jz button_done
        mov ecx, eax
        call 0x84eab0
        mov esi, eax
        push 0
        push 0
        push dword ptr [ebp+20]
        mov ecx, esi
        call 0x8657a0
        push 0
        push 1
        push dword ptr [ebp+24]
        mov ecx, esi
        call 0x8657a0
        push 0
        push 2
        push dword ptr [ebp+24]
        mov ecx, esi
        call 0x8657a0
        push dword ptr [esi+0xb8]
        push dword ptr [esi+0xb4]
        mov ecx, esi
        call 0xa7b470
        mov eax, [esi]
        push 252
        push dword ptr [ebp+12]
        mov ecx, esi
        call dword ptr [eax+0x10]
        mov eax, [esi]
        push dword ptr [ebp+16]
        mov ecx, esi
        call dword ptr [eax+0xb4]
        push esi
        mov ecx, [ebp+8]
        call 0xa7a080
    button_done:
        pop esi
        pop ebp
        ret 20
    
; lookup at 0x04a14400

        push ebp
        mov ebp, esp
        sub esp, 4
        push ebx
        push esi
        push edi
        mov dword ptr [ebp-4], 0
        lea eax, [ebp-4]
        push eax
        cmp dword ptr [ebp+24], 0
        je size_query
        push dword ptr [ebp+16]
        push dword ptr [ebp+20]
        push 0x10e0eb4
        jmp query_string
    size_query:
        push dword ptr [ebp+20]
        push 0x10df0e4
    query_string:
        sub esp, 24
        mov ebx, esp
        mov dword ptr [ebx], 0
        mov dword ptr [ebx+16], 0
        mov dword ptr [ebx+20], 15
        push 48
        mov ecx, ebx
        call 0x4fa050
        mov [ebx], eax
        mov ecx, [ebp+12]
        mov [ebx+16], ecx
        mov dword ptr [ebx+20], 47
        inc ecx
        mov edi, eax
        mov esi, [ebp+8]
        cld
        rep movsb
        push dword ptr [0x1738010]
        call 0xafc9a0
        add esp, 40
        cmp dword ptr [ebp+24], 0
        je query_done
        add esp, 4
    query_done:
        mov eax, [ebp-4]
        pop edi
        pop esi
        pop ebx
        mov esp, ebp
        pop ebp
        ret 20
    
; dispatch at 0x04a14600

        mov eax, [ebp+0x10]
        cmp eax, 0x1ef
        je default_button
        cmp eax, 32496
        je arrow
        cmp eax, 32497
        jne 0x82d37a
    arrow:
        cmp dword ptr [77680384], 0
        jle 0x82d37a
        mov eax, [edi+0x7c]
        push 1
        push 0x112f730
        push dword ptr [eax+0x94]
        push 33
        push 77680448
        call 77677568
        cmp dword ptr [ebp+0x10], 32496
        je previous_color
        inc eax
        cmp eax, dword ptr [77680384]
        jg first_color
        cmp eax, 1
        jge resolve_color
    first_color:
        mov eax, 1
        jmp resolve_color
    previous_color:
        dec eax
        cmp eax, 1
        jl last_color
        cmp eax, dword ptr [77680384]
        jle resolve_color
    last_color:
        mov eax, dword ptr [77680384]
    resolve_color:
        push 1
        push 0x112f730
        push eax
        push 20
        push 77680512
        call 77677568
        test eax, eax
        jle 0x82d37a
        cmp eax, 32766
        jg 0x82d37a
        lea esi, [eax-1]
        mov [ebp+0x18], esi
        jmp 0x82d213
    default_button:
        mov eax, [ebp+8]
        cmp eax, [edi+0x94]
        je 0x82d34a
        jmp 0x82d37a
    
; draw at 0x04a14800

        push ebp
        mov ebp, esp
        sub esp, 64
        push esi
        mov esi, ecx
        call 0x829c30
        push 77679872
        push 233
        push 71
        mov ecx, esi
        call 77679616
        mov eax, [esi+0x7c]
        test eax, eax
        jz draw_done
        push 1
        push 0x112f730
        push dword ptr [eax+0x94]
        push 33
        push 77680448
        call 77677568
        test eax, eax
        jns display_index
        xor eax, eax
    display_index:
        push dword ptr [77680384]
        push eax
        push 77680400
        push 64
        lea eax, [ebp-64]
        push eax
        call 0x602b00
        add esp, 20
        push 0
        push 0
        push 0x303030
        push 11
        push 0
        push 0
        lea eax, [ebp-64]
        push eax
        push 253
        push 124
        mov ecx, esi
        call 0xa84360
    draw_done:
        pop esi
        mov esp, ebp
        pop ebp
        ret
    
; preview_draw at 0x04a14a00

        push esi
        mov esi, ecx
        call 0x829d10
        cmp byte ptr [esi+0xb0], 0
        jne preview_done
        push 77680000
        push 24
        push 4
        mov ecx, esi
        call 77679616
        push 32
        push 77680544
        push 0x8c
        push 2
        mov ecx, esi
        call 77679360
        push 54
        push 77680576
        push 0x98
        push 3
        mov ecx, esi
        call 77679360
    preview_done:
        pop esi
        ret
    
; label at 0x04a14b00

        push ebp
        mov ebp, esp
        sub esp, 96
        push ebx
        push esi
        push edi
        mov esi, ecx
        lea eax, [ebp+8]
        push eax
        lea eax, [ebp-24]
        push eax
        call 0x8264a0
        mov edi, eax
        cmp dword ptr [edi+20], 16
        jb table_ready
        mov edi, [edi]
    table_ready:
        push 0
        push edi
        push 0
        push 26
        push 77680608
        call 77677568
        mov ebx, eax
        mov eax, [ebp+12]
        push 1
        push edi
        push dword ptr [esi+eax]
        push 33
        push 77680448
        call 77677568
        test eax, eax
        jns label_index
        xor eax, eax
    label_index:
        push ebx
        push eax
        push dword ptr [ebp+16]
        push 64
        lea eax, [ebp-88]
        push eax
        call 0x602b00
        add esp, 20
        lea ecx, [ebp-24]
        call 0x4f98a0
        push 0
        push 0
        push 0x303030
        push 12
        push 0
        push 0
        lea eax, [ebp-88]
        push eax
        push dword ptr [ebp+20]
        push 48
        mov ecx, esi
        call 0xa84360
        pop edi
        pop esi
        pop ebx
        mov esp, ebp
        pop ebp
        ret 16
    
; bitmap at 0x04a14c00

        push ebp
        mov ebp, esp
        push esi
        push edi
        mov edi, ecx
        call 0xaf1620
        mov esi, eax
        push dword ptr [ebp+16]
        call 0xb01200
        add esp, 4
        push eax
        mov ecx, esi
        call 0xaee770
        test eax, eax
        jz bitmap_done
        push 0
        push eax
        push dword ptr [ebp+12]
        push dword ptr [ebp+8]
        mov ecx, edi
        call 0xa7bb60
    bitmap_done:
        pop edi
        pop esi
        pop ebp
        ret 12
    
; reset_sentinel at 0x04a14e00

        cmp dword ptr [ebp-0x8a8], 0
        jne reset_done
        mov dword ptr [ebp-0x8a8], 0xffffffff
    reset_done:
        jmp 0x8251ca
    
; costume_count at 0x04a14c40

        push ebp
        mov ebp, esp
        sub esp, 4
        push ebx
        push esi
        push edi
        mov dword ptr [ebp-4], 0
        mov ecx, 0x1732638
        call 0xdddfe0
        lea ecx, [ebp-4]
        push ecx
        push eax
        push 0x10df238
        sub esp, 24
        mov ebx, esp
        mov dword ptr [ebx], 0
        mov dword ptr [ebx+16], 0
        mov dword ptr [ebx+20], 15
        push 48
        mov ecx, ebx
        call 0x4fa050
        mov [ebx], eax
        mov dword ptr [ebx+16], 26
        mov dword ptr [ebx+20], 47
        mov edi, eax
        mov esi, 0x112f314
        mov ecx, 27
        cld
        rep movsb
        push dword ptr [0x1738010]
        call 0xafc9a0
        add esp, 40
        mov eax, [ebp-4]
        pop edi
        pop esi
        pop ebx
        mov esp, ebp
        pop ebp
        ret
    
; costume_tab at 0x04a14e40

        call 77679680
        test eax, eax
        jg 0x82970d
        push 0x88
        jmp 0x8296be
    
; costume_click at 0x04a14e60

        call 77679680
        test eax, eax
        jg 0x82dea7
        cmp esi, 583
        jmp 0x82dea1
    
; fav_name at 0x04a14900

        push esi
        push edi
        call 0xe08c70
        mov esi, eax
        mov edi, 77680288
        mov ecx, 17
    fav_copy:
        mov al, [esi]
        test al, al
        jz fav_copied
        mov [edi], al
        inc esi
        inc edi
        dec ecx
        jnz fav_copy
    fav_copied:
        mov byte ptr [edi], 0
        mov ecx, 0x1732638
        call 0xdddfe0
        push eax
        push 77680352
        push 7
        push edi
        call 0x602b00
        add esp, 16
        mov eax, 77680288
        pop edi
        pop esi
        ret
    