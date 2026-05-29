function csrfToken() {
    const m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.getAttribute('content') : '';
}

class SolarFlowDashboard {
    constructor() {
        this.socket = io();
        this.lastUpdate = null;
        this.isConnected = false;
        this.dismissedWarningKeys = new Set();

        this.MODE_STYLE = {
            L: { label: 'Line Mode',    bg: 'bg-blue-500/25',    text: 'text-blue-100',    dot: 'bg-blue-300' },
            B: { label: 'Battery Mode', bg: 'bg-emerald-500/25', text: 'text-emerald-100', dot: 'bg-emerald-300' },
            S: { label: 'Standby',      bg: 'bg-slate-500/25',   text: 'text-slate-100',   dot: 'bg-slate-300' },
            P: { label: 'Power On',     bg: 'bg-sky-500/25',     text: 'text-sky-100',     dot: 'bg-sky-300' },
            H: { label: 'Power Saving', bg: 'bg-indigo-500/25',  text: 'text-indigo-100',  dot: 'bg-indigo-300' },
            C: { label: 'Charging',     bg: 'bg-amber-500/25',   text: 'text-amber-100',   dot: 'bg-amber-300' },
            F: { label: 'Fault',        bg: 'bg-red-500/30',     text: 'text-red-100',     dot: 'bg-red-400' },
            D: { label: 'Shutdown',     bg: 'bg-gray-600/30',    text: 'text-gray-100',    dot: 'bg-gray-300' },
        };

        this.latestMetrics = {};
        this.latestConfig = {};
        this.passwordRequired = false;
        this.currentModal = null;
        // Discrete charge-current values the inverter accepts (QMCHGCR/QMUCHGCR), loaded lazily.
        this.selectableCurrents = null;
        // Sticky modal toast {cls,text}: the sheet re-renders on every live reading, so the
        // toast is held here and re-applied after each rebuild instead of living only in the DOM.
        this.modalToast = null;
        this._modalToastTimer = null;

        this.initializeSocketEvents();
        this.initializeWarningBanner();
        this.initializeComponentModals();
        this.startUpdateTimer();
    }

    initializeSocketEvents() {
        this.socket.on('connect', () => {
            this.isConnected = true;
            this.updateConnectionStatus('Connected');
            // After a dropped socket, tell the live chart to reload so it can't stay stale.
            // (Skipped on the very first connect — there's nothing to reconcile yet.)
            if (this._hadDisconnect) {
                window.dispatchEvent(new CustomEvent('inverter_reconnect'));
            }
        });
        this.socket.on('disconnect', () => {
            this.isConnected = false;
            this._hadDisconnect = true;
            this.updateConnectionStatus('Disconnected');
            this.setAllComponentsInactive();
        });
        this.socket.on('inverter_update', (data) => {
            this.lastUpdate = new Date();
            this.updateSystem(data);
            window.dispatchEvent(new CustomEvent('inverter_update', { detail: data }));
        });
        this.socket.on('stats_update', (data) => {
            this.updateStatsPayload(data);
        });
        this.socket.on('connect_error', () => {
            this.updateConnectionStatus('Connection Error');
            this.setAllComponentsInactive();
        });
    }

    initializeWarningBanner() {
        const toggle = document.getElementById('warnings-banner-toggle');
        if (toggle) {
            toggle.addEventListener('click', () => {
                const banner = document.getElementById('warnings-banner');
                if (banner) banner.classList.add('hidden');
            });
        }
    }

    updateSystem(data) {
        if (data && data.success) {
            this.updateMetrics(data.metrics || {});
            this.updateSystemInfo(data.system || {}, data.metrics || {});
            this.updateComponentStates(data.metrics || {});
            this.updateFlowAnimations(data.metrics || {});
            this.updateTiming(data.timing);
        } else {
            this.updateConnectionStatus('Inverter Offline');
            this.setAllComponentsInactive();
        }
    }

    updateMetrics(metrics) {
        this.latestMetrics = metrics || {};
        if (this.currentModal) this.rerenderCurrentModal();
        const solar = metrics.solar || {};
        const battery = metrics.battery || {};
        const grid = metrics.grid || {};
        const load = metrics.load || {};

        this.updateElement('solar-power', Math.round(solar.power || 0));
        this.updateElement('solar-voltage', (solar.voltage || 0).toFixed(1));
        this.updateElement('solar-voltage-status', (solar.voltage || 0).toFixed(0));
        this.updateElement('solar-current', (solar.current || 0).toFixed(2));
        this.updateElement('solar-power-status', Math.round(solar.power || 0));

        this.updateElement('battery-percentage', Math.round(battery.percentage || 0));
        this.updateElement('battery-voltage', (battery.voltage || 0).toFixed(1));
        this.updateElement('battery-voltage-status', (battery.voltage || 0).toFixed(1));
        const batCurrent = Math.abs(battery.current || 0);
        this.updateElement('battery-current', batCurrent.toFixed(2));
        this.updateElement('battery-percentage-status', Math.round(battery.percentage || 0));
        this.updateElement('battery-power-status', Math.round(Math.abs(battery.power || 0)));
        this.updateElement('battery-direction-label', this.formatBatteryDirection(battery));
        this.updateBatteryFill(battery.percentage || 0);

        this.updateElement('grid-voltage', Math.round(grid.voltage || 0));
        this.updateElement('grid-voltage-status', Math.round(grid.voltage || 0));
        this.updateElement('grid-frequency', (grid.frequency || 0).toFixed(1));
        this.updateElement('grid-frequency-status', (grid.frequency || 0).toFixed(1));
        const gridW = Math.round(grid.power || 0);
        this.updateElement('grid-power', gridW);
        this.updateElement('grid-power-status', gridW);
        const estBadge = document.getElementById('grid-estimated');
        if (estBadge) estBadge.style.display = (gridW > 0 && grid.estimated !== false) ? '' : 'none';

        this.updateElement('load-power', Math.round(load.active_power ?? load.power ?? 0));
        this.updateElement('load-power-status', Math.round(load.active_power ?? load.power ?? 0));
        this.updateElement('load-voltage', Math.round(load.voltage || 0));
        this.updateElement('load-voltage-status', Math.round(load.voltage || 0));
        this.updateElement('load-apparent', Math.round(load.apparent_power || 0));
        this.updateElement('load-pf', (load.power_factor || 0).toFixed(2));
        this.updateElement('load-percentage', Math.round(load.percentage || 0));
    }

    updateBatteryFill(percentage) {
        const fill = document.getElementById('battery-fill');
        if (!fill) return;
        const pct = Math.max(0, Math.min(100, percentage)) / 100;
        const maxHeight = 76;
        const top = 9;
        const height = maxHeight * pct;
        const y = top + (maxHeight - height);
        fill.setAttribute('y', y);
        fill.setAttribute('height', height);
        const color = percentage < 20 ? '#EF4444'
                    : percentage < 50 ? '#F59E0B'
                    : '#34D399';
        fill.setAttribute('fill', color);
    }

    formatBatteryDirection(battery) {
        const dir = battery.direction || 'idle';
        if (dir === 'charging') return 'Charging';
        if (dir === 'discharging') return 'Discharging';
        return 'Idle';
    }

    updateSystemInfo(system, metrics) {
        this.latestSystem = system || {};
        if (this.currentModal === 'inverter') this.rerenderCurrentModal();
        if (system.temperature != null) {
            this.updateElement('inverter-temp', system.temperature);
            this.updateElement('system-temp', system.temperature);
        }
        if (system.bus_voltage != null) {
            this.updateElement('bus-voltage', Math.round(system.bus_voltage));
        }
        this.renderModePill(system);
        this.renderChargeStage(system);
        this.renderGridPill(system, metrics);
        this.renderWarnings(system);
    }

    renderModePill(system) {
        const pill = document.getElementById('mode-pill');
        const dot = document.getElementById('mode-pill-dot');
        const label = document.getElementById('mode-pill-label');
        if (!pill || !label) return;

        const style = this.MODE_STYLE[system.mode] || this.MODE_STYLE.S;
        Object.values(this.MODE_STYLE).forEach((s) => {
            pill.classList.remove(s.bg, s.text);
            if (dot) dot.classList.remove(s.dot);
        });
        pill.classList.add(style.bg, style.text);
        if (dot) dot.classList.add(style.dot);
        label.textContent = system.mode_label || style.label;
        const isDerived = system.mode_source === 'derived';
        pill.classList.toggle('border-dashed', isDerived);
        pill.classList.toggle('border-solid', !isDerived);
        pill.title = isDerived
            ? 'Inverter mode derived from status flags (QMOD unavailable)'
            : 'Inverter mode reported by QMOD';
    }

    renderChargeStage(system) {
        const pill = document.getElementById('charge-stage-pill');
        const label = document.getElementById('charge-stage-label');
        if (!pill || !label) return;
        const stage = (system.charge_stage || 'idle');
        if (stage === 'idle') {
            pill.classList.add('hidden');
            return;
        }
        pill.classList.remove('hidden');
        const map = {
            bulk: 'Bulk Charging',
            absorption: 'Absorption',
            float: 'Float Charge',
        };
        label.textContent = map[stage] || stage;
    }

    renderGridPill(system, metrics) {
        const pill = document.getElementById('grid-pill');
        const label = document.getElementById('grid-pill-label');
        if (!pill || !label) return;
        const grid = (metrics && metrics.grid) || {};
        if (system.is_ac_charging_on) {
            pill.classList.remove('hidden');
            label.textContent = `Grid charging · ${Math.round(grid.power || 0)} W`;
        } else if (grid.in_use) {
            pill.classList.remove('hidden');
            label.textContent = `Grid in use · ~${Math.round(grid.power || 0)} W`;
        } else {
            pill.classList.add('hidden');
        }
    }

    renderWarnings(system) {
        const banner = document.getElementById('warnings-banner');
        const box = document.getElementById('warnings-banner-box');
        const icon = document.getElementById('warnings-banner-icon');
        const title = document.getElementById('warnings-banner-title');
        const list = document.getElementById('warnings-banner-list');
        if (!banner || !box || !title || !list) return;

        const warnings = (system.warnings || []);
        if (warnings.length === 0) {
            banner.classList.add('hidden');
            return;
        }

        banner.classList.remove('hidden');
        const hasFault = warnings.some((w) => w.severity === 'fault');
        box.className = 'rounded-lg border p-3 flex items-start gap-3 ' +
            (hasFault
                ? 'bg-red-500/15 border-red-400/40 text-red-100'
                : 'bg-amber-500/15 border-amber-400/40 text-amber-100');
        if (icon) icon.className = 'fas mt-1 ' +
            (hasFault ? 'fa-circle-exclamation text-red-300' : 'fa-triangle-exclamation text-amber-300');
        title.textContent = hasFault
            ? `${warnings.length} active ${warnings.length === 1 ? 'fault' : 'faults/warnings'}`
            : `${warnings.length} active warning${warnings.length === 1 ? '' : 's'}`;
        list.textContent = warnings.map((w) => w.label).join(' · ');
    }

    updateTiming(timing) {
        if (timing && timing.duration_ms != null) {
            this.updateElement('reading-duration', Math.round(timing.duration_ms));
        }
    }

    updateStatsPayload(data) {
        if (!data) return;
        if (data.config) this.renderConfig(data.config);
        if (data.summary) this.renderTodaySummary(data.summary);
        if (data.reading_stats) {
            this.updateElement('reading-total', data.reading_stats.total_readings || 0);
            this.updateElement('reading-errors', data.reading_stats.error_count || 0);
        }
        if (data.day && data.day.temperature_max != null) {
            this.updateElement('temp-max', Math.round(data.day.temperature_max));
        }
    }

    renderConfig(config) {
        this.latestConfig = config || {};
        if (this.currentModal) this.rerenderCurrentModal();
    }

    initializeComponentModals() {
        this.refreshExtras();
        this.loadSelectableCurrents();

        const refreshBtn = document.getElementById('extras-refresh');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.refreshExtras({ force: true }));
        }

        const modal = document.getElementById('component-modal');
        const card = document.getElementById('component-modal-card');
        if (!modal || !card) return;

        ['solar', 'grid', 'battery', 'load', 'inverter'].forEach((key) => {
            const el = document.getElementById(`${key}-component`);
            if (!el) return;
            el.addEventListener('click', (e) => {
                const t = e.target;
                if (t && t.classList && t.classList.contains('status-indicator')) return;
                this.openModal(key);
            });
        });

        modal.addEventListener('click', (e) => {
            if (e.target === modal) this.closeModal();
        });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') this.closeModal();
        });
    }

    openModal(component) {
        this.currentModal = component;
        this.rerenderCurrentModal();
        document.getElementById('component-modal').classList.remove('hidden');
        // Only talk to the inverter's USB if we don't already have config. Page-load
        // already ran refreshExtras() via initializeComponentModals, and write ops
        // return fresh QPIRI inline — so repeat sheet opens no longer need to re-query.
        if (this.needsConfig(component) && !this.hasConfig()) {
            this.refreshExtras();
        }
        // The battery panel's charge-current dropdowns need the selectable list.
        if (component === 'battery' && !this.selectableCurrents) {
            this.loadSelectableCurrents();
        }
    }

    async loadSelectableCurrents() {
        if (this.selectableCurrents) return this.selectableCurrents;
        try {
            const res = await fetch('/inverter/selectable-currents', { credentials: 'same-origin' });
            if (res.ok) this.selectableCurrents = await res.json();
        } catch (e) { /* ignore — dropdowns fall back to the current value only */ }
        // If the battery sheet is already open, refresh it so the options populate.
        if (this.currentModal === 'battery') this.rerenderCurrentModal();
        return this.selectableCurrents;
    }

    // ---- editable-parameter row builders (battery / inverter settings) ----------------------

    voltageRow(label, param, cur) {
        const now = (cur != null && cur !== '') ? `<span class="cur">now ${cur} V</span>` : '';
        const val = (cur != null && cur !== '') ? cur : '';
        return `
            <div class="param-row">
                <span class="k">${label}${now}</span>
                <input type="number" step="0.1" min="0" inputmode="decimal" data-param-input="${param}" value="${val}">
                <button class="apply" data-action="set-param" data-param="${param}">Set</button>
            </div>`;
    }

    currentRow(label, param, selKey, cur) {
        const now = (cur != null && cur !== '') ? `<span class="cur">now ${cur} A</span>` : '';
        return `
            <div class="param-row">
                <span class="k">${label}${now}</span>
                <select data-param-select="${param}" data-sel-key="${selKey}" data-current="${cur ?? ''}"></select>
                <button class="apply" data-action="set-param" data-param="${param}">Set</button>
            </div>`;
    }

    batteryTypeRow(curLabel) {
        const codeFor = { AGM: '0', Flooded: '1', User: '2', 'User-defined': '2' };
        const curCode = codeFor[curLabel] ?? '';
        const opts = [['0', 'AGM'], ['1', 'Flooded'], ['2', 'User-defined']]
            .map(([code, label]) => `<option value="${code}" ${code === curCode ? 'selected' : ''}>${label}</option>`)
            .join('');
        return `
            <div class="param-row">
                <span class="k">Battery Type</span>
                <select data-param-select="battery_type">${opts}</select>
                <button class="apply" data-action="set-param" data-param="battery_type">Set</button>
            </div>`;
    }

    needsConfig(component) {
        return component === 'battery' || component === 'load' || component === 'inverter';
    }

    hasConfig() {
        const c = this.latestConfig || {};
        return !!(c.output_priority || c.charger_priority || (c.rows && c.rows.length));
    }

    async refreshExtras({ force = false } = {}) {
        // Coalesce concurrent calls.
        if (this._extrasInFlight) return this._extrasInFlight;
        this._extrasInFlight = (async () => {
            this._setExtrasLoading(true);
            try {
                const [extrasRes, configRes] = await Promise.all([
                    fetch('/refresh-extras', { method: 'POST', headers: { 'X-CSRFToken': csrfToken() } }),
                    fetch('/config'),
                ]);
                const extras = await extrasRes.json();
                const meta = await configRes.json();
                this.passwordRequired = !!(meta && meta.password_required);
                if (extras && extras.config && Object.keys(extras.config).length > 0) {
                    this.renderConfig(extras.config);
                }
                if (extras && extras.mode) {
                    if (!this.latestSystem) this.latestSystem = {};
                    this.latestSystem.mode = extras.mode;
                    this.renderModePill(this.latestSystem);
                }
                if (extras && Array.isArray(extras.warnings)) {
                    if (!this.latestSystem) this.latestSystem = {};
                    this.latestSystem.warnings = extras.warnings;
                    this.latestSystem.has_fault = extras.warnings.some((w) => w.severity === 'fault');
                    this.renderWarnings(this.latestSystem);
                }
                if (this.currentModal === 'inverter') this.rerenderCurrentModal();
                return extras;
            } catch (err) {
                console.error('refresh-extras failed', err);
            } finally {
                this._setExtrasLoading(false);
                this._extrasInFlight = null;
            }
        })();
        return this._extrasInFlight;
    }

    _setExtrasLoading(loading) {
        const btn = document.getElementById('extras-refresh');
        const icon = document.getElementById('extras-refresh-icon');
        const label = document.getElementById('extras-refresh-label');
        if (!btn) return;
        btn.disabled = loading;
        btn.classList.toggle('opacity-60', loading);
        btn.classList.toggle('cursor-wait', loading);
        if (icon) icon.classList.toggle('fa-spin', loading);
        if (label) label.textContent = loading ? 'Reading inverter…' : 'Refresh status';
    }

    closeModal() {
        this.currentModal = null;
        this.setModalToast(null);
        document.getElementById('component-modal').classList.add('hidden');
    }

    /// Set (or clear, with text=null) the modal toast. Held on the instance so it survives the
    /// frequent live re-renders; auto-clears after `autoClearMs` (0 = sticky until replaced).
    setModalToast(cls, text = null, autoClearMs = 0) {
        if (this._modalToastTimer) { clearTimeout(this._modalToastTimer); this._modalToastTimer = null; }
        this.modalToast = (text == null) ? null : { cls, text };
        const el = document.getElementById('modal-toast');
        if (el) {
            el.className = this.modalToast ? `toast ${cls}` : '';
            el.textContent = this.modalToast ? text : '';
        }
        if (this.modalToast && autoClearMs > 0) {
            this._modalToastTimer = setTimeout(() => this.setModalToast(null), autoClearMs);
        }
    }

    rerenderCurrentModal() {
        const card = document.getElementById('component-modal-card');
        if (!card || !this.currentModal) return;
        // Live readings arrive ~every second and trigger this. Don't rebuild while the user is
        // editing a field in the sheet — it would discard their input and drop focus.
        const active = document.activeElement;
        if (active && card.contains(active) && /^(INPUT|SELECT|TEXTAREA)$/.test(active.tagName)) return;
        card.innerHTML = this.buildModalHTML(this.currentModal);
        this.attachModalHandlers();
        // Re-apply the sticky toast destroyed by the innerHTML rebuild.
        if (this.modalToast) {
            const el = document.getElementById('modal-toast');
            if (el) { el.className = `toast ${this.modalToast.cls}`; el.textContent = this.modalToast.text; }
        }
    }

    buildModalHTML(component) {
        const m = this.latestMetrics || {};
        const c = this.latestConfig || {};
        const close = `<button class="modal-close text-white/60 hover:text-white ml-auto" aria-label="Close"><i class="fas fa-times text-lg"></i></button>`;

        if (component === 'solar') {
            const s = m.solar || {};
            return `
                <div class="modal-head"><div class="icon-ring" style="background: rgba(252,211,77,0.15); color: #FCD34D"><i class="fas fa-solar-panel text-xl"></i></div>
                    <div><div class="text-white font-semibold">Solar (PV)</div><div class="text-white/50 text-xs">Live readings</div></div>${close}</div>
                <div class="modal-body">
                    <section><h3>Now</h3>
                        <div class="stat-grid">
                            <div class="stat-tile"><div class="k">Power</div><div class="v">${Math.round(s.power || 0)} W</div></div>
                            <div class="stat-tile"><div class="k">Voltage</div><div class="v">${(s.voltage || 0).toFixed(1)} V</div></div>
                            <div class="stat-tile"><div class="k">Current</div><div class="v">${(s.current || 0).toFixed(2)} A</div></div>
                            <div class="stat-tile"><div class="k">To Battery</div><div class="v">${(s.pv_to_battery_current || 0).toFixed(2)} A</div></div>
                        </div>
                    </section>
                    <section><h3>Notes</h3>
                        <div class="text-white/60 text-sm">PV settings on this inverter are read-only. Output / charger routing is controlled from the <b>Load</b> and <b>Battery</b> panels.</div>
                    </section>
                </div>`;
        }

        if (component === 'grid') {
            const g = m.grid || {};
            return `
                <div class="modal-head"><div class="icon-ring" style="background: rgba(96,165,250,0.15); color: #60A5FA"><i class="fas fa-plug text-xl"></i></div>
                    <div><div class="text-white font-semibold">Grid</div><div class="text-white/50 text-xs">Utility input</div></div>${close}</div>
                <div class="modal-body">
                    <section><h3>Now</h3>
                        <div class="stat-grid">
                            <div class="stat-tile"><div class="k">Voltage</div><div class="v">${Math.round(g.voltage || 0)} V</div></div>
                            <div class="stat-tile"><div class="k">Frequency</div><div class="v">${(g.frequency || 0).toFixed(1)} Hz</div></div>
                            <div class="stat-tile"><div class="k">Power</div><div class="v">${Math.round(g.power || 0)} W</div></div>
                            <div class="stat-tile"><div class="k">Status</div><div class="v">${g.in_use ? 'In use' : 'Idle / Backup'}</div></div>
                        </div>
                    </section>
                    <section><h3>Notes</h3>
                        <div class="text-white/60 text-sm">Grid-related write operations (input voltage range, AC charging current) aren't exposed yet. The readings above are live from the inverter.</div>
                    </section>
                </div>`;
        }

        if (component === 'load') {
            const l = m.load || {};
            const current = c.output_priority || '—';
            const freq = Math.round(Number(c.ac_output_frequency) || 0);
            const opts = [
                { key: 'SBU', name: 'SBU', desc: 'Solar → Battery → Grid' },
                { key: 'SOL', name: 'SOL', desc: 'Solar → Grid → Battery' },
                { key: 'UTI', name: 'UTI', desc: 'Grid first (battery / solar backup)' },
            ];
            const choices = opts.map((o) => `
                <button class="choice-btn ${current === o.key ? 'current' : ''}" data-action="set-output-priority" data-mode="${o.key}">
                    <div class="name">${o.name}${current === o.key ? '<i class="fas fa-check text-emerald-400 text-xs ml-1"></i>' : ''}</div>
                    <div class="desc">${o.desc}</div>
                </button>`).join('');
            return `
                <div class="modal-head"><div class="icon-ring" style="background: rgba(167,139,250,0.15); color: #A78BFA"><i class="fas fa-house text-xl"></i></div>
                    <div><div class="text-white font-semibold">Load (Output)</div><div class="text-white/50 text-xs">House consumption</div></div>${close}</div>
                <div class="modal-body">
                    <section><h3>Now</h3>
                        <div class="stat-grid">
                            <div class="stat-tile"><div class="k">Active</div><div class="v">${Math.round(l.active_power ?? l.power ?? 0)} W</div></div>
                            <div class="stat-tile"><div class="k">Apparent</div><div class="v">${Math.round(l.apparent_power || 0)} VA</div></div>
                            <div class="stat-tile"><div class="k">Voltage</div><div class="v">${Math.round(l.voltage || 0)} V</div></div>
                            <div class="stat-tile"><div class="k">Load %</div><div class="v">${Math.round(l.percentage || 0)}%</div></div>
                        </div>
                    </section>
                    <section><h3>Output Source Priority</h3>
                        <div class="text-white/60 text-xs mb-2">Where the load gets its power from. Current: <span class="text-white font-medium">${current}</span></div>
                        <div class="choice-grid">${choices}</div>
                    </section>
                    <section><h3>Output Frequency</h3>
                        <div class="text-white/60 text-xs mb-2">AC output frequency. Match your appliances / region.</div>
                        <div class="seg">
                            <button data-action="set-param" data-param="output_frequency" data-value="50" class="${freq === 50 ? 'current' : ''}">50 Hz</button>
                            <button data-action="set-param" data-param="output_frequency" data-value="60" class="${freq === 60 ? 'current' : ''}">60 Hz</button>
                        </div>
                    </section>
                    ${this.buildPasswordFieldHTML()}
                    <div id="modal-toast"></div>
                </div>`;
        }

        if (component === 'battery') {
            const b = m.battery || {};
            const current = c.charger_priority || '—';
            const opts = [
                { key: 'SOL_ONLY',  name: 'Only solar',       desc: 'Grid is never allowed to charge' },
                { key: 'SOL_FIRST', name: 'Solar first',      desc: 'Solar charges; grid tops up if needed' },
                { key: 'SOL_UTI',   name: 'Solar + Utility',  desc: 'Both charge simultaneously when available' },
                { key: 'UTI_SOL',   name: 'Utility + Solar',  desc: 'Grid and solar both allowed' },
            ];
            const choices = opts.map((o) => `
                <button class="choice-btn ${current === o.key ? 'current' : ''}" data-action="set-charger-priority" data-mode="${o.key}">
                    <div class="name">${o.name}${current === o.key ? '<i class="fas fa-check text-emerald-400 text-xs ml-1"></i>' : ''}</div>
                    <div class="desc">${o.desc}</div>
                </button>`).join('');
            const dir = b.direction || 'idle';
            return `
                <div class="modal-head"><div class="icon-ring" style="background: rgba(52,211,153,0.15); color: #34D399"><i class="fas fa-car-battery text-xl"></i></div>
                    <div><div class="text-white font-semibold">Battery</div><div class="text-white/50 text-xs">Storage</div></div>${close}</div>
                <div class="modal-body">
                    <section><h3>Now</h3>
                        <div class="stat-grid">
                            <div class="stat-tile"><div class="k">State of Charge</div><div class="v">${Math.round(b.percentage || 0)}%</div></div>
                            <div class="stat-tile"><div class="k">Voltage</div><div class="v">${(b.voltage || 0).toFixed(2)} V</div></div>
                            <div class="stat-tile"><div class="k">Current</div><div class="v">${Math.abs(b.current || 0).toFixed(2)} A</div></div>
                            <div class="stat-tile"><div class="k">Direction</div><div class="v">${dir.charAt(0).toUpperCase() + dir.slice(1)}</div></div>
                        </div>
                    </section>
                    <section><h3>Charger Source Priority</h3>
                        <div class="text-white/60 text-xs mb-2">What's allowed to charge the battery. Current: <span class="text-white font-medium">${current}</span></div>
                        <div class="choice-grid">${choices}</div>
                    </section>
                    <section><h3>Battery Settings</h3>
                        <div class="text-white/50 text-[11px] mb-2">
                            Each change is written to the inverter and read back.
                            Nominal system: <span class="text-white/70">${c.battery_nominal_voltage ?? '—'} V</span>
                        </div>
                        ${this.batteryTypeRow(c.battery_type)}
                        ${this.currentRow('Max Charge Current', 'max_charge_current', 'max_charging_current', c.max_charging_current)}
                        ${this.currentRow('Max AC Charge Current', 'max_ac_charge_current', 'max_ac_charging_current', c.max_ac_charging_current)}
                        ${this.voltageRow('Cut-off Voltage', 'cutoff_voltage', c.battery_under_voltage)}
                        ${this.voltageRow('Back to Grid (recharge)', 'back_to_grid_voltage', c.battery_recharge_voltage)}
                        ${this.voltageRow('Back to Battery (re-discharge)', 'back_to_battery_voltage', c.battery_redischarge_voltage)}
                        ${this.voltageRow('Bulk / Absorption Voltage', 'bulk_voltage', c.battery_bulk_charge_voltage)}
                        ${this.voltageRow('Float Voltage', 'float_voltage', c.battery_float_charge_voltage)}
                    </section>
                    ${this.buildPasswordFieldHTML()}
                    <div id="modal-toast"></div>
                </div>`;
        }

        if (component === 'inverter') {
            const sys = this.latestSystem || {};
            const rows = (c.rows || []);
            const rowsHTML = rows.length
                ? rows.map((r) => `<div class="info-row"><span class="k">${r.label}</span><span class="v">${r.value}${r.unit ? ' ' + r.unit : ''}</span></div>`).join('')
                : '<div class="text-white/50 text-sm">Loading…</div>';
            return `
                <div class="modal-head"><div class="icon-ring" style="background: rgba(251,191,36,0.15); color: #FBBF24"><i class="fas fa-microchip text-xl"></i></div>
                    <div><div class="text-white font-semibold">Inverter</div><div class="text-white/50 text-xs">System</div></div>${close}</div>
                <div class="modal-body">
                    <section><h3>Now</h3>
                        <div class="stat-grid">
                            <div class="stat-tile"><div class="k">Temperature</div><div class="v">${sys.temperature ?? '—'}°C</div></div>
                            <div class="stat-tile"><div class="k">Bus Voltage</div><div class="v">${sys.bus_voltage ? Math.round(sys.bus_voltage) : '—'} V</div></div>
                            <div class="stat-tile"><div class="k">Mode</div><div class="v">${sys.mode_label ?? sys.mode ?? '—'}</div></div>
                            <div class="stat-tile"><div class="k">Charge Stage</div><div class="v">${(sys.charge_stage || 'idle').replace(/^\w/, (ch) => ch.toUpperCase())}</div></div>
                        </div>
                    </section>
                    <section><h3>Full Configuration (QPIRI)</h3>
                        ${rowsHTML}
                    </section>
                </div>`;
        }

        return '';
    }

    buildPasswordFieldHTML() {
        // Authentication is handled at the session level — no per-action password needed.
        return '';
    }

    attachModalHandlers() {
        const card = document.getElementById('component-modal-card');
        if (!card) return;
        const closeBtn = card.querySelector('.modal-close');
        if (closeBtn) closeBtn.addEventListener('click', () => this.closeModal());

        card.querySelectorAll('[data-action]').forEach((btn) => {
            btn.addEventListener('click', () => this.handleConfigAction(btn));
        });

        // Fill charge-current dropdowns from the inverter's selectable values, preselecting the
        // current setting. Falls back to a single option (the current value) if the list isn't
        // loaded yet — loadSelectableCurrents() will re-render the sheet once it arrives.
        const sc = this.selectableCurrents || {};
        card.querySelectorAll('select[data-param-select][data-sel-key]').forEach((sel) => {
            const vals = sc[sel.dataset.selKey] || [];
            const cur = sel.dataset.current;
            if (!vals.length) {
                sel.innerHTML = `<option value="${cur || ''}">${cur ? cur + ' A' : '—'}</option>`;
                return;
            }
            sel.innerHTML = vals
                .map((a) => `<option value="${a}" ${String(a) === String(cur) ? 'selected' : ''}>${a} A</option>`)
                .join('');
        });
    }

    async handleConfigAction(btn) {
        const action = btn.dataset.action;
        if (action === 'set-param') return this.handleSetParam(btn);

        const mode = btn.dataset.mode;
        const endpoint = action === 'set-output-priority' ? '/set-output-priority'
                      : action === 'set-charger-priority' ? '/set-charger-priority'
                      : null;
        if (!endpoint) return;
        const label = btn.querySelector('.name').textContent.replace(/✓?$/, '').trim();
        if (!confirm(`Apply change: ${label}?`)) return;

        this.setModalToast('info', 'Sending…');

        try {
            const res = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
                body: JSON.stringify({ mode }),
            });
            const data = await res.json();
            if (!res.ok || data.error || data.success === false) {
                this.setModalToast('err', `Failed: ${data.error || res.statusText}`, 8000);
                return;
            }
            if (data.config) this.renderConfig(data.config);
            this.setModalToast('ok', `Applied: ${data.applied?.label || mode}`, 6000);
        } catch (err) {
            this.setModalToast('err', `Error: ${err.message}`, 8000);
        }
    }

    async handleSetParam(btn) {
        const param = btn.dataset.param;
        // The value comes from the field in this control's row (input/select), or a button's own
        // data-value (segmented controls like output frequency).
        const row = btn.closest('.param-row') || btn.closest('.seg');
        const field = row && row.querySelector('[data-param-input],[data-param-select]');
        const value = field ? field.value : btn.dataset.value;

        if (value === '' || value == null) {
            this.setModalToast('err', 'Enter a value first.', 5000);
            return;
        }
        const pretty = param.replace(/_/g, ' ');
        if (!confirm(`Apply ${pretty} = ${value}?\nThis writes the setting to the inverter.`)) return;
        this.setModalToast('info', 'Sending to inverter…');
        btn.disabled = true;

        try {
            const res = await fetch('/inverter/set-param', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
                body: JSON.stringify({ param, value }),
            });
            const data = await res.json();
            if (!res.ok || data.error || data.success === false) {
                this.setModalToast('err', `Failed: ${data.error || res.statusText}`, 8000);
                return;
            }
            // Re-render with the read-back config first; the sticky toast is re-applied after.
            if (data.config) this.renderConfig(data.config);
            const applied = data.applied || {};
            this.setModalToast('ok', `Applied: ${applied.label || pretty} → ${applied.value ?? value}`, 6000);
        } catch (err) {
            this.setModalToast('err', `Error: ${err.message}`, 8000);
        } finally {
            btn.disabled = false;
        }
    }

    renderTodaySummary(s) {
        if (!s) return;
        this.updateElement('today-date', s.date || '—');
        this.updateElement('today-solar', (s.solar_kwh || 0).toFixed(2));
        this.updateElement('today-grid', (s.grid_kwh || 0).toFixed(2));
        this.updateElement('today-load', (s.load_kwh || 0).toFixed(2));
        this.updateElement('today-charge', (s.battery_charge_kwh || 0).toFixed(2));
        this.updateElement('today-discharge', (s.battery_discharge_kwh || 0).toFixed(2));
        this.updateElement('today-selfsuff', Math.round((s.self_sufficiency || 0) * 100));
        this.updateElement('today-solarfrac', Math.round((s.solar_fraction || 0) * 100));
        // Instantaneous daily peaks (true *_max from the backend, not averaged buckets).
        this.updateElement('today-solar-peak', Math.round(s.solar_peak_w || 0));
        this.updateElement('today-grid-peak', Math.round(s.grid_peak_w || 0));
        this.updateElement('today-load-peak', Math.round(s.load_peak_w || 0));
        if (s.temperature_max != null) {
            this.updateElement('temp-max', Math.round(s.temperature_max));
        }
    }

    updateComponentStates(metrics) {
        const solar = metrics.solar || {};
        const battery = metrics.battery || {};
        const grid = metrics.grid || {};
        const load = metrics.load || {};

        const solarActive = (solar.power || 0) > 5;
        this.setComponentActive('solar', solarActive);
        this.setStatusIndicator('solar-status', solarActive);

        const gridActive = grid.in_use === true;
        this.setComponentActive('grid', gridActive);
        this.setStatusIndicator('grid-status', gridActive);

        const loadActive = (load.active_power ?? load.power ?? 0) > 5;
        this.setComponentActive('load', loadActive);
        this.setStatusIndicator('load-status', loadActive);

        const batteryActive = (battery.voltage || 0) > 20;
        this.setComponentActive('battery', batteryActive);
        this.setStatusIndicator('battery-status', batteryActive);

        this.setComponentActive('inverter', true);
        this.setStatusIndicator('inverter-status', true);
    }

    updateFlowAnimations(metrics) {
        const solar = metrics.solar || {};
        const battery = metrics.battery || {};
        const grid = metrics.grid || {};
        const load = metrics.load || {};

        if ((solar.power || 0) > 5) {
            this.activateFlow('solar', `${Math.round(solar.power)} W`);
        } else {
            this.deactivateFlow('solar');
        }

        const direction = battery.direction || 'idle';
        if (direction !== 'idle') {
            const w = Math.round(Math.abs(battery.power || 0));
            const text = direction === 'charging' ? `Charging ${w} W` : `Discharging ${w} W`;
            this.activateFlow('battery', text, direction);
        } else {
            this.deactivateFlow('battery');
        }

        if (grid.in_use) {
            const w = Math.round(grid.power || 0);
            this.activateFlow('grid', w > 0 ? `${w} W` : 'In use');
        } else {
            this.deactivateFlow('grid');
        }

        const loadW = Math.round(load.active_power ?? load.power ?? 0);
        if (loadW > 5) {
            this.activateFlow('load', `${loadW} W`);
        } else {
            this.deactivateFlow('load');
        }
    }

    activateFlow(component, text, direction = 'normal') {
        const line = document.getElementById(`${component}-line`);
        if (line) {
            line.style.strokeOpacity = '1';
            line.classList.add('animate-dash');
            if (component === 'battery' && direction === 'charging') {
                line.style.animationDirection = 'reverse';
            } else {
                line.style.animationDirection = 'normal';
            }
        }
        if (component === 'battery') {
            const motion = document.getElementById('battery-motion');
            if (motion) {
                motion.setAttribute('keyPoints', direction === 'charging' ? '1;0' : '0;1');
            }
        }
        const particle = document.getElementById(`${component}-particle`);
        if (particle) particle.style.opacity = '1';
        const label = document.getElementById(`${component}-label`);
        const flowElement = document.getElementById(`${component}-flow`);
        if (label && flowElement) {
            label.style.opacity = '1';
            flowElement.textContent = text;
        }
    }

    deactivateFlow(component) {
        const line = document.getElementById(`${component}-line`);
        if (line) {
            line.style.strokeOpacity = '0.4';
            line.classList.remove('animate-dash');
        }
        const particle = document.getElementById(`${component}-particle`);
        if (particle) particle.style.opacity = '0';
        const label = document.getElementById(`${component}-label`);
        if (label) label.style.opacity = '0';
    }

    setComponentActive(component, isActive) {
        const element = document.getElementById(`${component}-component`);
        if (element) element.classList.toggle('dim-component', !isActive);
    }

    setStatusIndicator(id, isActive) {
        const indicator = document.getElementById(id);
        if (!indicator) return;
        indicator.classList.toggle('status-active', isActive);
        indicator.classList.toggle('status-inactive', !isActive);
    }

    setAllComponentsInactive() {
        ['solar', 'grid', 'battery', 'load', 'inverter'].forEach((c) => {
            this.setComponentActive(c, false);
            this.setStatusIndicator(`${c}-status`, false);
            this.deactivateFlow(c);
        });
    }

    updateElement(id, value) {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    }

    updateConnectionStatus(status) {
        this.updateElement('connection-status', status);
    }

    updateLastUpdateTime() {
        if (this.lastUpdate) {
            this.updateElement('last-update', this.lastUpdate.toLocaleTimeString());
        }
    }

    startUpdateTimer() {
        setInterval(() => this.updateLastUpdateTime(), 1000);
    }
}

let dashboard;
document.addEventListener('DOMContentLoaded', () => {
    dashboard = new SolarFlowDashboard();
    window.dashboard = dashboard;
});
