"""wgopt9: attribute direct udp_sendto ERR_MEM to STA linkoutput or upstream.

Only wrap a synchronous call with passive owner-tagged probes.
Preserve original arguments, return, packet ownership and send-both logic.
"""
from derp_header_overlay import once

def apply(component):
    mgr = component / "src/ml_wg_mgr.c"
    s = mgr.read_text()
    begin = s.index("static err_t wgopt1_udp_pbuf_output_cb(")
    end = s.index("static err_t wg_udp_output_cb(", begin)
    body = s[begin:end]
    body = once(body,
        "    err_t err = udp_sendto(s_wg_output_pcb, p, &dst, dest_port);\n    wg_diag_tx(3, err);",
        "    wg9_direct_udp_begin();\n"
        "    err_t err = udp_sendto(s_wg_output_pcb, p, &dst, dest_port);\n"
        "    wg9_direct_udp_end(err);\n"
        "    wg_diag_tx(3, err);")
    mgr.write_text(s[:begin] + body + s[end:])
