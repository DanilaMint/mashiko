/**/

#pragma once

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
