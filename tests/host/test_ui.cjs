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
                    'reserveDhcpClient', 'bindDhcpReserveButtons', 'formatDhcpLastSeen', 'renderDhcpRemembered', 'renderDhcpClients'])
  vm.runInContext(fn(name), ctx);
const mac = '02:00:00:00:00:01', ip = '192.0.2.4';
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

const nowS = Math.floor(Date.now() / 1000);
for (const value of [undefined, null, 0, -1, 1, 'bad', Infinity]) assert.equal(ctx.formatDhcpLastSeen(value, false).label, 'unknown');
for (const [age, label] of [[720, '12 min ago'], [7200, '2 h ago'], [259200, '3 d ago']]) {
  const seen = ctx.formatDhcpLastSeen(nowS - age, false);
  assert.equal(seen.label, label);
  assert.equal(seen.exact, new Date((nowS - age) * 1000).toLocaleString());
}
assert.equal(ctx.formatDhcpLastSeen(nowS, true).label, 'online now');
ctx.renderDhcpRemembered([{mac, ip, type:'manual', status:'offline', last_seen:nowS-720}]);
output = nodes['dhcp-remembered-body'].innerHTML;
assert(output.includes('12 min ago') && output.includes('title="'));
assert(output.indexOf('<th>Status</th>') < output.indexOf('<th>Last seen</th>'));
assert(output.indexOf('<th>Last seen</th>') < output.indexOf('<th>Type</th>'));
assert(output.includes('table-wrap'));
console.log('PASS: Last seen unknown, relative age, online, exact browser-local timestamp and table overflow wrapper');
