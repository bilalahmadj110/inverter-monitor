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

    // ---- matrix tables -------------------------------------------------------------------
    // Give a filled .table the "matrix" look: every numeric <td class="num"> becomes a pill tinted
    // with its column's series colour (data-series on the <th>), darker the larger the value is
    // within that column; zeros and blanks stay quiet. opts.totals puts a bold row in <tfoot>
    // (one entry per column, null for blank); opts.footer = {left, right} writes the caption
    // under the table. Call it after filling <tbody>; re-calling re-renders totals and caption.
    // A <td> may carry data-v="<number>" when its text is not a plain number (durations).
    const parseNum = (text) => {
        const m = String(text).replace(/,/g, '').match(/-?\d+(\.\d+)?/);
        return m ? parseFloat(m[0]) : NaN;
    };
    function matrix(table, opts = {}) {
        if (!table) return;
        table.classList.add('matrix');
        const ths = Array.from(table.querySelectorAll('thead th'));
        const rows = Array.from(table.querySelectorAll('tbody tr')).filter((tr) => !tr.querySelector('td.empty'));
        const cols = ths.map(() => []);
        rows.forEach((tr) => Array.from(tr.children).forEach((td, i) => {
            if (!cols[i] || !td.classList.contains('num') || td.querySelector('.cell-pill, input, button')) return;
            const v = td.dataset.v != null ? parseFloat(td.dataset.v) : parseNum(td.textContent);
            cols[i].push({ td, v });
        }));
        cols.forEach((cells, i) => {
            const series = ths[i] && ths[i].dataset.series;
            const max = Math.max(0, ...cells.filter((c) => Number.isFinite(c.v)).map((c) => Math.abs(c.v)));
            cells.forEach(({ td, v }) => {
                if (series) td.dataset.series = series;
                const finite = Number.isFinite(v);
                const pill = document.createElement('span');
                pill.className = 'cell-pill' + (!finite ? ' na' : v === 0 ? ' zero' : '');
                pill.style.setProperty('--heat', (finite && max > 0 ? Math.abs(v) / max : 0).toFixed(3));
                while (td.firstChild) pill.appendChild(td.firstChild);
                td.appendChild(pill);
            });
        });
        let tfoot = table.querySelector('tfoot');
        if (opts.totals) {
            if (!tfoot) tfoot = table.createTFoot();
            tfoot.innerHTML = '<tr>' + ths.map((th, i) => {
                const val = opts.totals[i];
                return `<td${th.classList.contains('num') ? ' class="num"' : ''}>${val == null ? '' : val}</td>`;
            }).join('') + '</tr>';
        } else if (tfoot) {
            tfoot.remove();
        }
        const wrap = table.closest('.table-wrap') || table;
        let foot = wrap.nextElementSibling;
        if (!(foot && foot.classList.contains('table-foot'))) {
            if (!opts.footer) return;
            foot = document.createElement('div');
            foot.className = 'table-foot';
            wrap.insertAdjacentElement('afterend', foot);
        }
        if (opts.footer) foot.innerHTML = `<span>${opts.footer.left || ''}</span><span>${opts.footer.right || ''}</span>`;
        else foot.remove();
    }

    applyChartDefaults();
    document.addEventListener('DOMContentLoaded', () => {
        document.querySelectorAll('[data-theme-toggle]').forEach((b) => {
            b.addEventListener('click', () => setTheme(theme() === 'light' ? 'dark' : 'light'));
        });
        refreshToggles();
        startClock();
    });

    window.UI = { cssVar, palette, withAlpha, theme, setTheme, chartTheme, matrix, onTheme: (fn) => listeners.push(fn) };
})();
