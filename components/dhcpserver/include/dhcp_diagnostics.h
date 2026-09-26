#pragma once
#include <stddef.h>
#include <stdint.h>
typedef enum {
    DHCP_FORCERENEW_UNKNOWN = 0,
    DHCP_FORCERENEW_SUPPORTED,
    DHCP_FORCERENEW_NOT_ADVERTISED
} dhcp_forcerenew_t;
/* RFC 6704 diagnostic only: no OFFER advertisement, nonce or FORCERENEW sender. */
static inline dhcp_forcerenew_t dhcp_forcerenew_capability(const uint8_t *p, size_t len)
{
    unsigned type = 0;
    int advertised = 0, overloaded = 0, ended = 0, unsupported = 0;
    for (size_t i = 0; i < len;) {
        unsigned code = p[i++];
        if (code == 0) continue;
        if (code == 255) { ended = 1; break; }
        if (i == len) return DHCP_FORCERENEW_UNKNOWN;
        unsigned n = p[i++];
        if (n > len - i) return DHCP_FORCERENEW_UNKNOWN;
        if (code == 53) {
            if (n != 1 || type) return DHCP_FORCERENEW_UNKNOWN;
            type = p[i];
        }
        if (code == 52) overloaded = 1; /* no inference from unparsed sname/file */
        if (code == 145) {
            if (!n) return DHCP_FORCERENEW_UNKNOWN;
            unsupported = 1;
            for (unsigned j = 0; j < n; ++j) if (p[i+j] == 1) advertised = 1;
        }
        i += n;
    }
    if (!ended || (type != 1 && type != 3)) return DHCP_FORCERENEW_UNKNOWN;
    if (advertised) return DHCP_FORCERENEW_SUPPORTED; /* advertises algorithm 1 */
    return (overloaded || unsupported) ? DHCP_FORCERENEW_UNKNOWN : DHCP_FORCERENEW_NOT_ADVERTISED;
}
static inline const char *dhcp_forcerenew_name(dhcp_forcerenew_t value)
{
    return value == DHCP_FORCERENEW_SUPPORTED ? "supported" :
           value == DHCP_FORCERENEW_NOT_ADVERTISED ? "not advertised" : "unknown";
}
