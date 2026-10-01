/* Execute upstream load/save UI code, including UTF-8 validation. */
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const html = fs.readFileSync('main/index.html', 'utf8');
const start = html.indexOf('    function loadSnmp() {');
const end = html.indexOf('    /* Idle-timeout dropdown', start);
assert(start >= 0 && end > start);
const nodes = {};
function node(id) {
  return nodes[id] ||= {value: '', checked: false, disabled: false, events: {},
    addEventListener(event, fn) { this.events[event] = fn; }};
}
let reply = {}, calls = [], toasts = [];
const ctx = vm.createContext({document: {getElementById: node}, TextEncoder,
  apiFetch(url, options) { calls.push({url, options}); return Promise.resolve({json: () => reply}); },
  showToast(...args) { toasts.push(args); }, setTimeout() {}});
vm.runInContext(html.slice(start, end), ctx);
const settle = () => new Promise(resolve => setImmediate(resolve));
(async () => {
  reply = {enabled: true, running: true, community: 'private', sys_name: 'router', sys_contact: 'test', sys_location: 'room'};
  ctx.loadSnmp(); await settle();
  assert.equal(node('sys-snmp-badge').textContent, 'Running');
  assert.equal(node('sys-snmp-community').value, 'private');
  assert.equal(node('sys-snmp-save').disabled, true);
  node('sys-snmp-en').events.change(); assert.equal(node('sys-snmp-save').disabled, false);
  calls = []; node('sys-snmp-community').value = '';
  node('sys-snmp-save').events.click(); assert.equal(calls.length, 0);
  assert.equal(toasts.at(-1)[1], 'Invalid community');
  node('sys-snmp-community').value = 'private'; node('sys-snmp-location').value = 'я'.repeat(128);
  node('sys-snmp-save').events.click(); assert.equal(calls.length, 0);
  assert.equal(toasts.at(-1)[1], 'Field too long');
  node('sys-snmp-location').value = 'x'.repeat(255); reply = {ok: true};
  node('sys-snmp-save').events.click(); await settle();
  assert.equal(calls[0].url, '/api/snmp'); assert.equal(calls[0].options.method, 'POST');
  const saved = JSON.parse(calls[0].options.body);
  assert.equal(saved.enabled, true); assert.equal(saved.sys_location.length, 255);
  assert.equal(saved.sys_name, 'router'); assert.equal(saved.sys_contact, 'test');
  reply = {enabled: false, running: false, community: ''};
  ctx.loadSnmp(); await settle();
  assert.equal(node('sys-snmp-badge').textContent, 'Stopped');
  calls = []; reply = {ok: false}; node('sys-snmp-save').events.click(); await settle();
  assert.equal(calls.length, 1); assert.equal(JSON.parse(calls[0].options.body).enabled, false);
  assert.equal(node('sys-snmp-save').disabled, false);
  console.log('PASS: production SNMP UI load/save, status, dirty tracking, empty community, UTF-8 byte limit, full form and failed save');
})().catch(error => { console.error(error); process.exitCode = 1; });
