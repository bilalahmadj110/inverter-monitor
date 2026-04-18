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

        this.initializeSocketEvents();
        this.initializeWarningBanner();
        this.initializePriorityPanel();
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
        const pill = document.getElementById('priority-pill-label');
        const current = document.getElementById('priority-current');
        const p = (config && config.output_priority) || '—';
        if (pill) pill.textContent = p;
        if (current) current.textContent = config && config.output_priority_raw ? `${p} (${config.output_priority_raw})` : p;
    }

    initializePriorityPanel() {
        const pill = document.getElementById('priority-pill');
        const panel = document.getElementById('priority-panel');
        const closeBtn = document.getElementById('priority-close');
        const status = document.getElementById('priority-status');
        const pwWrap = document.getElementById('priority-password-wrap');
        const pwInput = document.getElementById('priority-password');
        if (!pill || !panel) return;

        let passwordRequired = false;
        fetch('/config').then((r) => r.json()).then((data) => {
            passwordRequired = !!(data && data.password_required);
            pwWrap.classList.toggle('hidden', !passwordRequired);
            if (data && data.config) this.renderConfig(data.config);
        }).catch(() => {});

        pill.addEventListener('click', () => panel.classList.toggle('hidden'));
        closeBtn.addEventListener('click', () => panel.classList.add('hidden'));

        document.querySelectorAll('.priority-btn').forEach((btn) => {
            btn.addEventListener('click', async () => {
                const mode = btn.dataset.prio;
                const label = btn.querySelector('.font-semibold').textContent;
                if (!confirm(`Set output priority to ${label}? This changes how the inverter routes power.`)) return;
                status.textContent = 'Sending…';
                status.className = 'text-xs text-white/70';
                try {
                    const body = { mode };
                    if (passwordRequired) body.password = pwInput.value || '';
                    const res = await fetch('/set-output-priority', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(body),
                    });
                    const data = await res.json();
                    if (!res.ok || data.error) {
                        status.textContent = `Failed: ${data.error || res.statusText}`;
                        status.className = 'text-xs text-red-300';
                        return;
                    }
                    status.textContent = `Changed to ${data.applied.mode} · ${data.applied.label}`;
                    status.className = 'text-xs text-emerald-300';
                    if (data.config) this.renderConfig(data.config);
                } catch (err) {
                    status.textContent = `Error: ${err.message}`;
                    status.className = 'text-xs text-red-300';
                }
            });
        });
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
