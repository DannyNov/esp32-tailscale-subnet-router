/* Execute production UI functions with a minimal DOM, no reimplemented renderer. */
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const html = fs.readFileSync('main/index.html', 'utf8');
for (const m of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)) new vm.Script(m[1]);
function fn(name) {
  const start = html.indexOf('    function ' + name + '(');
  assert(start >= 0, name);
  const end = html.indexOf('\n    }', start);
  return html.slice(start, end + 6);
}
const nodes = {};
const ctx = vm.createContext({document: {
  getElementById: id => nodes[id] ||= {innerHTML: '', scrollIntoView() {}},
  querySelectorAll: () => []
}, showToast() {}, s_dhcp_res_list: [], s_dhcp_res_max: 16});
for (const name of ['escapeHtml', 'markDhcpDirty', 'snapshotDhcpResListFromDOM', 'renderDhcpResList',
                    'reserveDhcpClient', 'bindDhcpReserveButtons', 'renderDhcpRemembered', 'renderDhcpClients'])
  vm.runInContext(fn(name), ctx);
const mac = 'a0:92:08:96:67:69', ip = '10.71.0.4';
ctx.renderDhcpRemembered([{mac, ip, name: '', type: 'auto', status: 'offline'}]);
let output = nodes['dhcp-remembered-body'].innerHTML;
assert(output.includes('unnamed') && output.includes('offline') && output.includes('Reserve'));
assert(output.includes(ip));
ctx.renderDhcpRemembered([{mac, ip, name: '<script>x</script>', type: 'manual', status: 'online'}]);
output = nodes['dhcp-remembered-body'].innerHTML;
assert(!output.includes('<script>') && !output.includes('>Reserve<'));
ctx.renderDhcpClients([{mac, ip, ip_source: 'observed', forcerenew: 'unknown'}]);
output = nodes['dhcp-clients-body'].innerHTML;
assert(output.includes('temporary') && output.includes('>Reserve<') && output.includes('unknown'));
ctx.renderDhcpClients([{mac, ip, ip_conflict: true, stable: true}]);
output = nodes['dhcp-clients-body'].innerHTML;
assert(output.includes('IP conflict') && !output.includes('>Reserve<'));
ctx.reserveDhcpClient(mac, ip, '');
ctx.reserveDhcpClient(mac.toUpperCase(), ip, '');
assert.equal(ctx.s_dhcp_res_list.length, 1);
assert.equal(ctx.s_dhcp_res_list[0].ip, ip);
assert.equal(ctx.s_dhcp_res_list[0].fixed, true);
assert.equal((nodes['dhcp-res-list'].innerHTML.match(/readonly/g) || []).length, 2);
assert(!/dhcp-res-name[^>]+readonly/.test(nodes['dhcp-res-list'].innerHTML));
console.log('PASS: UI syntax, offline remembered, escaping, temporary Reserve, conflicts, dedup, fixed MAC/IP and editable name');
