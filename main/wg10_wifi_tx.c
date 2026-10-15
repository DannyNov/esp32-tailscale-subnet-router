/* wgopt10: observability only. GNU ld --wrap on *external* Wi-Fi callsites.
 * Do not change any packet bytes, ownership, return values or scheduling.
 * Real esp_wifi_internal_tx[_by_ref] are called exactly once each time.
 * Call counts establish whether the linker wrap is exercised on hardware. */
#include "esp_err.h"
#include "esp_wifi.h"
#include <stddef.h>
#include <stdint.h>
extern void wg10_wifi_driver_result(int raw_err, int by_ref);
extern esp_err_t __real_esp_wifi_internal_tx_by_ref(wifi_interface_t wifi_if,
                                   void *buffer, size_t len, void *netstack_buf);
esp_err_t __wrap_esp_wifi_internal_tx_by_ref(wifi_interface_t wifi_if,
                                   void *buffer, size_t len, void *netstack_buf) {
    esp_err_t raw = __real_esp_wifi_internal_tx_by_ref(wifi_if, buffer, len, netstack_buf);
    wg10_wifi_driver_result(raw, 1);
    return raw;
}
extern int __real_esp_wifi_internal_tx(wifi_interface_t wifi_if,
                                      void *buffer, uint16_t len);
int __wrap_esp_wifi_internal_tx(wifi_interface_t wifi_if,
                               void *buffer, uint16_t len) {
    int raw = __real_esp_wifi_internal_tx(wifi_if, buffer, len);
    wg10_wifi_driver_result(raw, 0);
    return raw;
}
