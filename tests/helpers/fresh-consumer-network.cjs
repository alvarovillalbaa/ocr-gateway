// Runtime-only tripwire. Public artifact installation runs before this preload.
const fs = require('node:fs');
const net = require('node:net');
const dns = require('node:dns');
const origin = 'http://127.0.0.1:38473';
const audit = process.env.FRESH_NETWORK_AUDIT;
if (!audit || !audit.startsWith(process.env.FRESH_ROOT + '/')) throw Error('Owned audit required');
function record(event, details = {}) {
  if (fs.existsSync(audit) && fs.statSync(audit).size > 128 * 1024) throw Error('Network audit exceeded its bound');
  fs.appendFileSync(audit, JSON.stringify({pid: process.pid, event, ...details}) + '\n', {mode: 0o600});
}
function endpoint(args) {
  let value = args[0];
  if (Array.isArray(value)) value = value[0];
  return value && typeof value === 'object' ? {host: value.host ?? value.hostname ?? 'localhost', port: Number(value.port)}
    : {host: typeof args[1] === 'string' ? args[1] : 'localhost', port: Number(value)};
}
const connect = net.Socket.prototype.connect;
net.Socket.prototype.connect = function (...args) {
  const target = endpoint(args);
  if (!['127.0.0.1', 'localhost', '::1'].includes(target.host) || target.port !== 38473) {
    record('connect_denied'); throw Error('Unexpected runtime connection');
  }
  record('connect_allowed', target);
  return connect.apply(this, args);
};
const listen = net.Server.prototype.listen;
net.Server.prototype.listen = function (...args) {
  const target = endpoint(args);
  if (target.host !== '127.0.0.1' || target.port !== 38473) { record('listen_denied'); throw Error('Unexpected runtime listener'); }
  record('listen_allowed', target);
  return listen.apply(this, args);
};
const lookup = dns.lookup;
dns.lookup = function (hostname, ...args) {
  if (!['127.0.0.1', 'localhost', '::1'].includes(hostname)) { record('dns_denied'); throw Error('Unexpected runtime DNS'); }
  return lookup.call(this, hostname, ...args);
};
const fetch = globalThis.fetch;
globalThis.fetch = async function (input, options) {
  const url = new URL(input instanceof Request ? input.url : String(input));
  if (url.origin !== origin || url.username || url.password || url.search || url.hash || !['/health', '/v1/providers', '/v1/parse'].includes(url.pathname)) {
    record('fetch_denied'); throw Error('Unexpected runtime fetch');
  }
  const response = await fetch.call(this, input, options);
  record('fetch_completed', {path: url.pathname, method: options?.method ?? 'GET', status: response.status});
  return response;
};
