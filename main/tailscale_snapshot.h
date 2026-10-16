/* SPDX-License-Identifier: MIT
 * EXPERIMENTAL: task-context snapshots, protecting instance lifetime
 * against manager connect/disconnect. Does not solve microlink's internal
 * mutable-state races, stop/destroy lifetime defects, or DERP TLS teardown.
 */
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "microlink.h"

#define TAILSCALE_SNAPSHOT_MAX_DERP_RTTS 32

typedef struct {
    microlink_diag_t diag;
    bool connected;
    uint32_t vpn_ip; /* host order */
    uint32_t generation;
    int peer_count;
    int peers_online;
} tailscale_status_snapshot_t;

typedef struct {
    microlink_peer_info_t peer;
    char derp_region_name[64];
} tailscale_peer_snapshot_t;

/* All calls are non-blocking, for task context (not an ISR/tcpip raw hook).
 * Contention, missing instance, or reinitialization -> false/zero output.
 * No pointer into the instance is returned. */
bool tailscale_snapshot_status(tailscale_status_snapshot_t *out);
bool tailscale_snapshot_diag(microlink_diag_t *out);
bool tailscale_snapshot_peer(uint32_t generation, int index, tailscale_peer_snapshot_t *out);
/* RTT capacity must be 1..TAILSCALE_SNAPSHOT_MAX_DERP_RTTS. Valid buffers
 * are cleared even on contention or a stale generation. Invalid arguments
 * are rejected without touching the buffer. */
int tailscale_snapshot_derp_rtts(uint32_t generation, microlink_derp_rtt_t *out, int capacity);
bool tailscale_snapshot_region_name(uint32_t generation, uint16_t region, char *out, size_t capacity);
