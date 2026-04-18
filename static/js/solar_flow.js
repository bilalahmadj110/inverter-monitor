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

        this.initializeSocketEvents();
        this.initializeWarningBanner();
        this.initializeComponentModals();
        this.startUpdateTimer();
    }

    initializeSocketEvents() {
        this.socket.on('connect', () => {
            this.isConnected = true;
            this.updateConnectionStatus('Connected');
        });
        this.socket.on('disconnect', () => {
            this.isConnected = false;
            this.updateConnectionStatus('Disconnected');
            this.setAllComponentsInactive();
        });
        this.socket.on('inverter_update', (data) => {
            this.lastUpdate = new Date();
            this.updateSystem(data);
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
            this.setSystemStatus('Operating Normally', false);
        } else {
            const errorMsg = (data && data.error) || 'Inverter not connected';
            this.updateConnectionStatus('Inverter Offline');
            this.setAllComponentsInactive();
            this.setSystemStatus(errorMsg, true);
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
        this.loadConfig({ retries: 5 });

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
        if (this.needsConfig(component) && !this.hasConfig()) {
            this.loadConfig({ retries: 4 });
        }
    }

    needsConfig(component) {
        return component === 'battery' || component === 'load' || component === 'inverter';
    }

    hasConfig() {
        const c = this.latestConfig || {};
        return !!(c.output_priority || c.charger_priority || (c.rows && c.rows.length));
    }

    async loadConfig({ retries = 1, attempt = 0 } = {}) {
        try {
            const res = await fetch('/config');
            const data = await res.json();
            this.passwordRequired = !!(data && data.password_required);
            if (data && data.config && Object.keys(data.config).length > 0) {
                this.renderConfig(data.config);
                return true;
            }
        } catch (err) {
            // retry on next tick
        }
        if (attempt + 1 < retries) {
            const delay = Math.min(3000, 600 * Math.pow(1.6, attempt));
            setTimeout(() => this.loadConfig({ retries, attempt: attempt + 1 }), delay);
        }
        return false;
    }

    closeModal() {
        this.currentModal = null;
        document.getElementById('component-modal').classList.add('hidden');
    }

    rerenderCurrentModal() {
        const card = document.getElementById('component-modal-card');
        if (!card || !this.currentModal) return;
        card.innerHTML = this.buildModalHTML(this.currentModal);
        this.attachModalHandlers();
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
                    <section><h3>Battery Info</h3>
                        <div class="info-row"><span class="k">Type</span><span class="v">${c.battery_type ?? '—'}</span></div>
                        <div class="info-row"><span class="k">Max Charging Current</span><span class="v">${c.max_charging_current ?? '—'} A</span></div>
                        <div class="info-row"><span class="k">Max AC Charging Current</span><span class="v">${c.max_ac_charging_current ?? '—'} A</span></div>
                        <div class="info-row"><span class="k">Under Voltage</span><span class="v">${c.battery_under_voltage ?? '—'} V</span></div>
                        <div class="info-row"><span class="k">Bulk Charge</span><span class="v">${c.battery_bulk_charge_voltage ?? '—'} V</span></div>
                        <div class="info-row"><span class="k">Float Charge</span><span class="v">${c.battery_float_charge_voltage ?? '—'} V</span></div>
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
        if (!this.passwordRequired) return '';
        return `
            <section><h3>Admin Password</h3>
                <input type="password" id="modal-password" class="w-full px-3 py-2 rounded-lg bg-white/10 border border-white/20 text-white text-sm" placeholder="Required to apply changes">
            </section>`;
    }

    attachModalHandlers() {
        const card = document.getElementById('component-modal-card');
        if (!card) return;
        const closeBtn = card.querySelector('.modal-close');
        if (closeBtn) closeBtn.addEventListener('click', () => this.closeModal());

        card.querySelectorAll('[data-action]').forEach((btn) => {
            btn.addEventListener('click', () => this.handleConfigAction(btn));
        });
    }

    async handleConfigAction(btn) {
        const action = btn.dataset.action;
        const mode = btn.dataset.mode;
        const endpoint = action === 'set-output-priority' ? '/set-output-priority'
                      : action === 'set-charger-priority' ? '/set-charger-priority'
                      : null;
        if (!endpoint) return;
        const label = btn.querySelector('.name').textContent.replace(/✓?$/, '').trim();
        if (!confirm(`Apply change: ${label}?`)) return;

        const toast = document.getElementById('modal-toast');
        const password = (document.getElementById('modal-password') || {}).value || '';
        if (toast) { toast.className = 'toast info'; toast.textContent = 'Sending…'; }

        try {
            const res = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mode, password }),
            });
            const data = await res.json();
            if (!res.ok || data.error || data.success === false) {
                if (toast) { toast.className = 'toast err'; toast.textContent = `Failed: ${data.error || res.statusText}`; }
                return;
            }
            if (toast) { toast.className = 'toast ok'; toast.textContent = `Applied: ${data.applied?.label || mode}`; }
            if (data.config) this.renderConfig(data.config);
        } catch (err) {
            if (toast) { toast.className = 'toast err'; toast.textContent = `Error: ${err.message}`; }
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
        if (s.temperature_max != null) {
            this.updateElement('temp-max', Math.round(s.temperature_max));
        }
    }

    setSystemStatus(text, isError) {
        const statusEl = document.getElementById('system-status');
        const pill = document.getElementById('system-status-pill');
        if (statusEl) statusEl.textContent = text;
        if (pill) {
            pill.className = 'inline-flex items-center space-x-2 px-4 py-2 rounded-full ' +
                (isError ? 'bg-red-500/20 text-red-300' : 'bg-green-500/20 text-green-300');
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

    requestManualUpdate() {
        if (!this.isConnected) return;
        this.socket.emit('request_update');
        const refreshIcon = document.getElementById('refresh-icon');
        if (refreshIcon) {
            refreshIcon.classList.add('fa-spin');
            setTimeout(() => refreshIcon.classList.remove('fa-spin'), 1000);
        }
    }
}

let dashboard;
document.addEventListener('DOMContentLoaded', () => {
    dashboard = new SolarFlowDashboard();
    window.dashboard = dashboard;
});
