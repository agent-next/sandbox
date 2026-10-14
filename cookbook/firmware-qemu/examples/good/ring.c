/*
 * ring.c -- fixed-capacity byte ring buffer.
 *
 * Overflow drops the oldest byte, which is what a UART receive queue should
 * do: a slow reader loses the start of the line, never the end.
 */
#include "common.h"

void rb_init(ring_t *r, unsigned cap)
{
    unsigned i;

    if (cap == 0u || cap > RB_MAX_CAP) {
        cap = RB_MAX_CAP;
    }
    for (i = 0; i < cap; i++) {
        r->buf[i] = 0;
    }
    r->head = 0;
    r->tail = 0;
    r->count = 0;
    r->cap = cap;
}

int rb_push(ring_t *r, uint8_t b)
{
    if (r->count >= r->cap) {
        /* full: the oldest byte falls out the front */
        r->head = (r->head + 1u) % r->cap;
        r->count--;
    }
    r->buf[r->tail] = b;
    r->tail = (r->tail + 1u) % r->cap;
    r->count++;
    return (int)r->count;
}

int rb_pop(ring_t *r)
{
    int b;
    if (r->count == 0) {
        return -1;
    }
    b = r->buf[r->head];
    r->buf[r->head] = 0;
    r->head = (r->head + 1u) % r->cap;
    r->count--;
    return b & 0xFF;
}

int rb_peek(const ring_t *r)
{
    if (r->count == 0) {
        return -1;
    }
    return r->buf[r->head] & 0xFF;
}

unsigned rb_count(const ring_t *r)
{
    return r->count;
}

void rb_clear(ring_t *r)
{
    r->head = 0;
    r->tail = 0;
    r->count = 0;
}
