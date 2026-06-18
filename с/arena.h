#pragma once

#include <cstring>
#include <stdlib.h>
#include <stddef.h>
#include <stdbool.h>

typedef struct {
    bool valid;
    void* ptr;
    size_t capacity;
    size_t offset;
} Arena;

Arena arena_init(size_t size) {
    Arena arena;

    void* ptr = malloc(size);

    arena.valid = ptr == 0;
    arena.ptr = ptr;
    arena.capacity = size;
    arena.offset = 0;

    return arena;
}

Arena arena_realloc(Arena arena, size_t append) {
    size_t new_size = arena.capacity + append;

    void* old_ptr = arena.ptr;
    void* new_ptr = malloc(new_size);

    if (new_ptr == 0) {
        arena.valid = false;
        goto _EXIT;
    }

    memcpy(old_ptr, new_ptr, arena.offset);

    free(old_ptr);

    arena.capacity = new_size;
    arena.ptr = new_ptr;

    _EXIT:
    return arena;
}
