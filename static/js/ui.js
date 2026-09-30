/* Shared UI helpers: theme toggle (dark default, light on request), CSS-token palette for
 * charts, Chart.js defaults matching the theme, and a live clock in the top bar.
 * Loaded after Chart.js (where a page has charts) and before the page's own scripts. */
(function () {
    'use strict';
    const root = document.documentElement;
    const listeners = [];
    const KEY = 'im_theme';

    const cssVar = (name) => getComputedStyle(root).getPropertyValue(name).trim();
    const theme = () => (root.getAttribute('data-theme') === 'light' ? 'light' : 'dark');
    const palette = () => ({
        solar: cssVar('--solar'), grid: cssVar('--grid'), load: cssVar('--load'), battery: cssVar('--battery'),
        voltage: cssVar('--voltage'), text: cssVar('--text'), text2: cssVar('--text-2'), text3: cssVar('--text-3'),
        line: cssVar('--line'), lineStrong: cssVar('--line-strong'), surface: cssVar('--surface'),
        surface3: cssVar('--surface-3'), accent: cssVar('--accent'), danger: cssVar('--danger'),
    });
    const withAlpha = (hex, a) => {
        const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
        if (!m) return hex;
        const n = parseInt(m[1], 16);
        return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
    };
    const chartTheme = () => {
        const p = palette();
        return {
            tick: p.text2, grid: p.line, border: p.lineStrong,
            tooltip: { backgroundColor: p.surface3, titleColor: p.text, bodyColor: p.text, borderColor: p.lineStrong, borderWidth: 1, padding: 10, cornerRadius: 8 },
            legend: { color: p.text2, usePointStyle: true, boxWidth: 8, boxHeight: 8, padding: 14 },
        };
    };

    function applyChartDefaults() {
        if (!window.Chart) return;
        const p = palette();
        Chart.defaults.color = p.text2;
        Chart.defaults.borderColor = p.line;
        Chart.defaults.font.family = cssVar('--font-sans') || 'system-ui, sans-serif';
        Chart.defaults.font.size = 11;
        Chart.defaults.plugins.legend.labels.usePointStyle = true;
        Chart.defaults.plugins.legend.labels.boxWidth = 8;
        Chart.defaults.plugins.legend.labels.boxHeight = 8;
    }

    function refreshToggles() {
        document.querySelectorAll('[data-theme-toggle]').forEach((b) => {
            const light = theme() === 'light';
            b.setAttribute('aria-pressed', light ? 'true' : 'false');
            b.title = light ? 'Switch to dark theme' : 'Switch to light theme';
        });
    }

    function setTheme(next) {
        if (next === 'light') root.setAttribute('data-theme', 'light');
        else root.removeAttribute('data-theme');
        try { localStorage.setItem(KEY, next); } catch (_e) { /* private mode */ }
        applyChartDefaults();
        refreshToggles();
        listeners.forEach((fn) => { try { fn(theme(), palette()); } catch (e) { console.error('theme listener', e); } });
        window.dispatchEvent(new CustomEvent('themechange', { detail: theme() }));
    }

    function startClock() {
        const el = document.getElementById('topbar-clock');
        if (!el) return;
        const tick = () => { el.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }); };
        tick();
        setInterval(tick, 1000);
    }

    applyChartDefaults();
    document.addEventListener('DOMContentLoaded', () => {
        document.querySelectorAll('[data-theme-toggle]').forEach((b) => {
            b.addEventListener('click', () => setTheme(theme() === 'light' ? 'dark' : 'light'));
        });
        refreshToggles();
        startClock();
    });

    window.UI = { cssVar, palette, withAlpha, theme, setTheme, chartTheme, onTheme: (fn) => listeners.push(fn) };
})();
