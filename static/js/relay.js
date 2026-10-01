/* Relay mode: loaded only when the pages are served from AWS instead of the Pi.
 *
 * The Lambda injects `window.RELAY = {ws, version}` before this file. In that mode:
 *   - `io()` returns an emulated socket that speaks the relay's WebSocket protocol, so
 *     the existing dashboard code (which expects Socket.IO) keeps working unchanged;
 *   - `fetch()` for the app's data endpoints is tunnelled over that WebSocket as
 *     request/reply frames answered by the Pi, and comes back as a normal Response;
 *   - `relayDownload(url)` fetches an export over the tunnel and saves it.
 * Replies are gzipped + base64 and chunked to stay under API Gateway's frame limit.
 */
/* global DecompressionStream */
(function () {
    'use strict';
    const cfg = window.RELAY;
    if (!cfg || !cfg.ws) return;
    // Never run on the login page: without a session the token fetch is a 401 and the
    // redirect below would reload /login endlessly.
    if (window.location.pathname === '/login') return;

    const API_PREFIXES = [
        '/status', '/summary', '/stats', '/stats-payload', '/history', '/recent-readings',
        '/day-readings', '/outages', '/data-gaps', '/raw-data', '/export-readings', '/warnings',
        '/savings', '/fesco', '/ai', '/config', '/refresh-extras', '/recompute-daily',
        '/inverter', '/set-output-priority', '/set-charger-priority',
    ];
    const isApiPath = (url) => {
        if (typeof url !== 'string' || !url.startsWith('/') || url.startsWith('//')) return false;
        const path = url.split('?')[0];
        return API_PREFIXES.some((p) => path === p || path.startsWith(p + '/'));
    };
    const canGunzip = typeof DecompressionStream === 'function';
    const realFetch = window.fetch.bind(window);

    class RelaySocket {
        constructor() {
            this.handlers = {};
            this.pending = new Map();
            this.parts = new Map();
            this.nextId = 1;
            this.connected = false;
            this.deviceOnline = null;
            this.ws = null;
            this.backoff = 1000;
            this.pingTimer = null;
            this.connect();
        }

        on(ev, cb) {
            (this.handlers[ev] = this.handlers[ev] || []).push(cb);
            // Pages register their handlers on DOMContentLoaded, often after the relay has
            // already said hello; replay the connect so they never sit on "Connecting…".
            if (ev === 'connect' && this.connected) { try { cb(); } catch (e) { console.error('relay handler', ev, e); } }
            return this;
        }
        off(ev, cb) { this.handlers[ev] = (this.handlers[ev] || []).filter((h) => h !== cb); return this; }
        _fire(ev, data) {
            for (const cb of (this.handlers[ev] || [])) {
                try { cb(data); } catch (e) { console.error('relay handler', ev, e); }
            }
        }

        async connect() {
            let info;
            try {
                const r = await realFetch('/relay/token', { credentials: 'same-origin', cache: 'no-store' });
                if (r.status === 401) {
                    // Session expired: go to login once, never from the login page itself.
                    if (window.location.pathname !== '/login') {
                        window.location.href = '/login?next=' + encodeURIComponent(window.location.pathname);
                    }
                    return;
                }
                if (!r.ok) throw new Error('token ' + r.status);
                info = await r.json();
            } catch (e) {
                console.warn('relay: token fetch failed', e);
                this._scheduleReconnect();
                return;
            }
            const ws = new WebSocket(info.ws_url + '?role=viewer&t=' + encodeURIComponent(info.token));
            this.ws = ws;
            ws.onopen = () => {
                this.backoff = 1000;
                ws.send(JSON.stringify({ action: 'hello' }));
                this.pingTimer = setInterval(() => {
                    if (ws.readyState === 1) ws.send(JSON.stringify({ action: 'ping' }));
                }, 240000);
            };
            ws.onmessage = (ev) => {
                let msg;
                try { msg = JSON.parse(ev.data); } catch (_e) { return; }
                this._onMessage(msg);
            };
            ws.onclose = () => {
                clearInterval(this.pingTimer);
                if (this.connected) { this.connected = false; this._fire('disconnect'); }
                for (const [, p] of this.pending) { clearTimeout(p.timer); p.reject(new Error('relay disconnected')); }
                this.pending.clear();
                this.parts.clear();
                this._scheduleReconnect();
            };
            ws.onerror = () => { this._fire('connect_error', new Error('relay socket error')); };
        }

        _scheduleReconnect() {
            setTimeout(() => this.connect(), this.backoff);
            this.backoff = Math.min(this.backoff * 2, 30000);
        }

        _onMessage(msg) {
            switch (msg.type) {
                case 'hello':
                    this.connected = true;
                    this._fire('connect');
                    this.deviceOnline = !!msg.device_online;
                    if (msg.device_online) this._prime(msg); else this._offline(msg);
                    this._fire('relay_hello', msg);
                    break;
                case 'inverter_update':
                    this.deviceOnline = true;
                    this._fire('inverter_update', msg.data);
                    break;
                case 'stats_update':
                    this._fire('stats_update', msg.data);
                    break;
                case 'rpc':
                    this._rpcPart(msg);
                    break;
                default:
                    break;
            }
        }

        // The Pi only starts pushing once the relay tells it a viewer arrived, so the first live
        // frame lands a second or two after hello. Until then show the snapshot the Pi stored
        // (at most a few minutes old) rather than a page full of zeros.
        _prime(msg) {
            const snap = msg.snapshot || {};
            if (snap.stats) this._fire('stats_update', snap.stats);
            if (snap.status && snap.status.metrics) this._fire('inverter_update', snap.status);
        }

        _offline(msg) {
            const seen = msg.last_seen ? new Date(msg.last_seen * 1000).toLocaleString() : 'unknown';
            const snap = msg.snapshot || {};
            if (snap.stats) this._fire('stats_update', snap.stats);
            const status = snap.status || {};
            this._fire('inverter_update', {
                success: false,
                error: 'Raspberry Pi is offline (last seen ' + seen + ')',
                metrics: status.metrics || {},
                system: status.system || {},
                stale: true,
            });
        }

        emit(ev) {
            if (ev === 'request_update') {
                this.rpc('GET', '/status').then((r) => (r.ok ? r.json() : null))
                    .then((d) => { if (d) this._fire('inverter_update', d); }).catch(() => {});
                this.emit('request_stats');
            } else if (ev === 'request_stats') {
                this.rpc('GET', '/stats-payload').then((r) => (r.ok ? r.json() : null))
                    .then((d) => { if (d) this._fire('stats_update', d); }).catch(() => {});
            }
            return this;
        }

        // Pages fire their first fetch() while the socket is still connecting; hold those
        // calls until the relay has said hello instead of failing them.
        _ready() {
            if (this.connected && this.ws && this.ws.readyState === 1) return Promise.resolve();
            return new Promise((resolve, reject) => {
                const ok = () => { clearTimeout(timer); this.off('connect', ok); resolve(); };
                const timer = setTimeout(() => { this.off('connect', ok); reject(new Error('relay not connected')); }, 20000);
                this.on('connect', ok);
            });
        }

        rpc(method, url, init = {}) {
            return this._ready().then(() => this._rpc(method, url, init));
        }

        _rpc(method, url, init) {
            return new Promise((resolve, reject) => {
                if (!this.ws || this.ws.readyState !== 1) { reject(new Error('relay not connected')); return; }
                const id = this.nextId++;
                const qIdx = url.indexOf('?');
                const path = qIdx === -1 ? url : url.slice(0, qIdx);
                const query = qIdx === -1 ? '' : url.slice(qIdx + 1);
                const timeoutMs = /^\/(export-readings|recompute-daily)/.test(path) ? 180000 : 30000;
                const timer = setTimeout(() => {
                    this.pending.delete(id); this.parts.delete(id);
                    reject(new Error('relay timeout for ' + path));
                }, timeoutMs);
                this.pending.set(id, { resolve, reject, timer });
                let body = init.body;
                if (body != null && typeof body !== 'string') body = String(body);
                let ctype = null;
                if (init.headers) ctype = new Headers(init.headers).get('content-type');
                this.ws.send(JSON.stringify({
                    action: 'rpc', id, method: (method || 'GET').toUpperCase(), path, query,
                    body: body == null ? null : body, ctype,
                    accept_enc: canGunzip ? 'gzip+b64' : 'identity',
                }));
            });
        }

        async _rpcPart(msg) {
            const p = this.pending.get(msg.id);
            if (!p) return;
            let entry = this.parts.get(msg.id);
            if (!entry) {
                entry = { chunks: new Array(msg.parts || 1), got: 0, meta: msg };
                this.parts.set(msg.id, entry);
            }
            if (entry.chunks[msg.part] === undefined) { entry.chunks[msg.part] = msg.data; entry.got++; }
            if (msg.headers) entry.meta.headers = msg.headers;
            if (entry.got < (msg.parts || 1)) return;
            this.pending.delete(msg.id);
            this.parts.delete(msg.id);
            clearTimeout(p.timer);
            try {
                const all = entry.chunks.join('');
                let bodyInit;
                if (entry.meta.enc === 'gzip+b64') {
                    const bin = atob(all);
                    const bytes = new Uint8Array(bin.length);
                    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
                    const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
                    bodyInit = await new Response(stream).arrayBuffer();
                } else {
                    bodyInit = all;
                }
                const status = entry.meta.status || 200;
                const headers = { 'content-type': entry.meta.ctype || 'application/octet-stream', ...(entry.meta.headers || {}) };
                const nullBody = status === 204 || status === 205 || status === 304;
                p.resolve(new Response(nullBody ? null : bodyInit, { status, headers }));
            } catch (e) {
                p.reject(e);
            }
        }
    }

    const sock = new RelaySocket();

    window.fetch = function (input, init) {
        const url = typeof input === 'string' ? input : (input && input.url) || '';
        if (isApiPath(url)) return sock.rpc((init && init.method) || 'GET', url, init || {});
        return realFetch(input, init);
    };

    // The pages expect Socket.IO's `io()`; hand them the relay socket instead. The setter
    // swallows any later assignment from a socket.io script tag that slipped through.
    Object.defineProperty(window, 'io', { configurable: true, get() { return () => sock; }, set() { /* ignore */ } });

    window.relayDownload = async function (url) {
        try {
            const r = await window.fetch(url);
            if (!r.ok) throw new Error('HTTP ' + r.status);
            const blob = await r.blob();
            const cd = r.headers.get('content-disposition') || '';
            const m = /filename=([^;]+)/.exec(cd);
            const name = m ? m[1].trim().replace(/"/g, '') : 'export';
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = name;
            document.body.appendChild(a);
            a.click();
            setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
        } catch (e) {
            alert('Export failed: ' + e.message);
        }
    };

    window.relaySocket = sock;
})();
