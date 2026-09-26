#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "dhcp_diagnostics.h"
#define CHECK(expected, ...) do { const uint8_t p[]={__VA_ARGS__}; assert(dhcp_forcerenew_capability(p,sizeof p)==expected); } while(0)
int main(void) {
    CHECK(DHCP_FORCERENEW_SUPPORTED,53,1,1,145,1,1,255);
    CHECK(DHCP_FORCERENEW_SUPPORTED,0,53,1,3,145,3,9,1,8,255);
    CHECK(DHCP_FORCERENEW_NOT_ADVERTISED,53,1,1,255);
    CHECK(DHCP_FORCERENEW_NOT_ADVERTISED,53,1,3,0,255);
    CHECK(DHCP_FORCERENEW_UNKNOWN,53,1,1,145,1,9,255);
    CHECK(DHCP_FORCERENEW_UNKNOWN,53,1,1,145,0,255);
    CHECK(DHCP_FORCERENEW_UNKNOWN,53,1,1,145,2,1);
    CHECK(DHCP_FORCERENEW_UNKNOWN,53,1,1,145);
    CHECK(DHCP_FORCERENEW_UNKNOWN,53,1,1,145,1,1);
    CHECK(DHCP_FORCERENEW_UNKNOWN,53,1,2,145,1,1,255);
    CHECK(DHCP_FORCERENEW_UNKNOWN,53,1,1,53,1,3,145,1,1,255);
    CHECK(DHCP_FORCERENEW_UNKNOWN,53,1,1,52,1,1,255);
    CHECK(DHCP_FORCERENEW_UNKNOWN,145,1,1,255);
    assert(dhcp_forcerenew_capability(NULL,0)==DHCP_FORCERENEW_UNKNOWN);
    assert(!strcmp(dhcp_forcerenew_name(DHCP_FORCERENEW_UNKNOWN),"unknown"));
    assert(!strcmp(dhcp_forcerenew_name(DHCP_FORCERENEW_NOT_ADVERTISED),"not advertised"));
    assert(!strcmp(dhcp_forcerenew_name(DHCP_FORCERENEW_SUPPORTED),"supported"));
    puts("PASS: Option 145 diagnostic, absent, malformed, unsupported, overload, no live DHCP");
}
