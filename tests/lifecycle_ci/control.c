/* Positive control model only: not a patch or an upstream runtime test. */
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
static bool teardown(bool rx_parked) { return rx_parked; }
int main(void) {
    assert(!teardown(false));
    assert(teardown(true));
    puts("PASS positive control model: teardown requires acknowledgement");
    return 0;
}
