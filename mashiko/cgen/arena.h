/**/

#pragma once

#include <cstdint>
#include <stdlib.h>

typedef struct {
    void* ptr;
    size_t capacity;
    size_t offset;
    bool valid;
} Arena;

Arena arena_init(size_t size) {
    Arena arena;

    arena.capacity = size;
    arena.offset = 0;

    void* ptr = malloc(size);

    arena.valid = ptr != nullptr;

    arena.ptr = ptr;

    return arena;
}

void* arena_alloc(Arena* arena, size_t size, short alignment) {
    if ((alignment & (alignment - 1)) != 0 || alignment == 0) {
        return nullptr;
    }

    uintptr_t raw = (uintptr_t)arena->ptr + arena->offset;

    uintptr_t aligned = raw + 1 - raw % alignment;
}
