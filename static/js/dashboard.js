class InverterDashboard {
    constructor() {
        this.socket = io();
        this.lastUpdate = null;
        this.isConnected = false;
        this.currentStatsPeriod = 'day';
        this.statsData = { day: {}, month: {}, year: {} };
        
        // Pagination state
        this.currentPage = 1;
        this.pageSize = 25;
        this.totalPages = 1;
        this.totalRecords = 0;
        
        this.initializeSocketEvents();
        this.initializeStatsEvents();
        this.initializeTableEvents();
        this.startUpdateTimer();
        this.loadRawData();
    }

    initializeSocketEvents() {
        this.socket.on('connect', () => {
            console.log('Connected to server');
            this.isConnected = true;
            this.updateConnectionStatus('Connected', true);
        });

        this.socket.on('disconnect', () => {
            console.log('Disconnected from server');
            this.isConnected = false;
            this.updateConnectionStatus('Disconnected', false);
        });

        this.socket.on('inverter_update', (data) => {
            this.lastUpdate = new Date();
            this.updateDashboard(data);
        });

        this.socket.on('stats_update', (data) => {
            this.statsData = data;
            this.updateStatsDisplay();
        });

        this.socket.on('connect_error', (error) => {
            console.error('Connection error:', error);
            this.updateConnectionStatus('Connection Error', false);
        });
    }

    initializeStatsEvents() {
        document.querySelectorAll('.stats-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                const period = tab.getAttribute('data-period');
                this.setStatsPeriod(period);
            });
        });
    }

    initializeTableEvents() {
        // Page size change handler
        document.getElementById('page-size-select').addEventListener('change', (e) => {
            this.pageSize = parseInt(e.target.value);
            this.currentPage = 1;
            this.loadRawData();
        });
    }

    setStatsPeriod(period) {
        document.querySelectorAll('.stats-tab').forEach(tab => {
            tab.classList.toggle('active', tab.getAttribute('data-period') === period);
        });
        this.currentStatsPeriod = period;
        this.updateStatsDisplay();
    }

    async loadRawData() {
        try {
            const response = await fetch(`/raw-data?page=${this.currentPage}&page_size=${this.pageSize}`);
            const result = await response.json();
            
            if (result.error) {
                console.error('Error loading raw data:', result.error);
                return;
            }
            
            this.totalPages = result.total_pages;
            this.totalRecords = result.total_count;
            
            this.updateTable(result.data);
            this.updatePagination();
            
        } catch (error) {
            console.error('Error fetching raw data:', error);
        }
    }

    updateDashboard(data) {
        if (data.success) {
            this.updateMetrics(data.metrics);
            this.updateStatusIndicators(data.metrics);
            this.updateConnectionStatus('Online', true);
            
            if (data.system && data.system.temperature) {
                this.updateElement('temp', data.system.temperature, 0);
            }
        } else {
            this.updateConnectionStatus(`Error: ${data.error}`, false);
            this.setAllStatusInactive();
        }
        this.updateLastUpdateTime();
    }

    updateMetrics(metrics) {
        // Solar metrics
        this.updateElement('solar-voltage', metrics.solar.voltage, 1);
        this.updateElement('solar-current', metrics.solar.current, 1);
        this.updateElement('solar-power', metrics.solar.power, 0);

        // Battery metrics
        this.updateElement('battery-voltage', metrics.battery.voltage, 1);
        this.updateElement('battery-current', metrics.battery.current, 1);
        this.updateElement('battery-percentage', metrics.battery.percentage, 0);

        // Grid metrics
        this.updateElement('grid-voltage', metrics.grid.voltage, 1);
        this.updateElement('grid-frequency', metrics.grid.frequency, 1);
        this.updateElement('grid-power', metrics.grid.power, 0);

        // Load metrics
        this.updateElement('load-voltage', metrics.load.voltage, 1);
        this.updateElement('load-power', metrics.load.power, 0);
        this.updateElement('load-percentage', metrics.load.percentage, 0);
    }

    updateStatusIndicators(metrics) {
        this.setStatusIndicator('solar-status', metrics.solar.power > 0);
        this.setStatusIndicator('grid-status', metrics.grid.voltage > 200);
        this.setStatusIndicator('load-status', metrics.load.power > 0);
        
        // Battery status with charging/discharging indication
        const batteryStatus = document.getElementById('battery-status');
        if (batteryStatus) {
            const current = metrics.battery.current;
            if (current > 0.1) {
                batteryStatus.classList.add('active');
                batteryStatus.style.background = 'var(--success-color)';
            } else if (current < -0.1) {
                batteryStatus.classList.add('active');
                batteryStatus.style.background = 'var(--warning-color)';
            } else {
                batteryStatus.classList.remove('active');
            }
        }
        
        // System status
        this.setStatusIndicator('system-status', true);
    }

    updateStatsDisplay() {
        if (!this.statsData || !this.statsData[this.currentStatsPeriod]) {
            return;
        }

        const data = this.statsData[this.currentStatsPeriod];
        
        const formatEnergy = (wh, decimals = 3) => {
            return (parseFloat(wh || 0) / 1000).toFixed(decimals);
        };
        
        // Update Solar stats
        this.updateElement('solar-peak', data.solar_max || 0, 0);
        this.updateElement('solar-avg', data.solar_avg || 0, 1);
        this.updateElement('solar-energy', formatEnergy(data.solar_energy, 3));
        
        // Update Grid stats
        this.updateElement('grid-peak', data.grid_max || 0, 0);
        this.updateElement('grid-avg', data.grid_avg || 0, 1);
        this.updateElement('grid-energy', formatEnergy(data.grid_energy, 3));
        
        // Update Load stats
        this.updateElement('load-peak', data.load_max || 0, 0);
        this.updateElement('load-avg', data.load_avg || 0, 1);
        this.updateElement('load-energy', formatEnergy(data.load_energy, 3));
        
        // Update Battery stats
        this.updateElement('battery-charge', formatEnergy(data.battery_charge_energy, 3));
        this.updateElement('battery-discharge', formatEnergy(data.battery_discharge_energy, 3));
        
        const netEnergyWh = (data.battery_charge_energy || 0) - (data.battery_discharge_energy || 0);
        this.updateElement('battery-net', formatEnergy(netEnergyWh, 3));
        
        // Update reading stats
        if (this.statsData.reading_stats) {
            this.updateReadingStats(this.statsData.reading_stats);
        }
    }

    updateReadingStats(stats) {
        const avgDuration = stats.avg_duration || 0;
        this.updateElement('avg-duration', `${(avgDuration * 1000).toFixed(0)}ms`, 0);
        this.updateElement('total-readings', stats.total_readings || 0, 0);
    }

    updateElement(id, value, decimals = 1) {
        const element = document.getElementById(id);
        if (element) {
            let formattedValue;
            if (typeof value === 'number') {
                formattedValue = decimals > 0 ? value.toFixed(decimals) : Math.round(value);
            } else {
                formattedValue = value;
            }
            
            element.textContent = formattedValue;
            element.classList.add('updated');
            setTimeout(() => element.classList.remove('updated'), 600);
        }
    }

    setStatusIndicator(id, isActive) {
        const indicator = document.getElementById(id);
        if (indicator) {
            indicator.classList.toggle('active', isActive);
        }
    }

    setAllStatusInactive() {
        document.querySelectorAll('.status-indicator').forEach(indicator => {
            indicator.classList.remove('active');
        });
    }

    updateConnectionStatus(message, isConnected) {
        const statusText = document.getElementById('status-text');
        const connectionIcon = document.getElementById('connection-icon');
        
        if (statusText) {
            statusText.textContent = message;
        }
        
        if (connectionIcon) {
            if (isConnected) {
                connectionIcon.className = 'fas fa-wifi';
                connectionIcon.style.color = 'var(--success-color)';
            } else {
                connectionIcon.className = 'fas fa-wifi-slash';
                connectionIcon.style.color = 'var(--danger-color)';
            }
        }
    }

    updateLastUpdateTime() {
        const lastUpdateElement = document.getElementById('last-update');
        if (lastUpdateElement && this.lastUpdate) {
            lastUpdateElement.textContent = this.lastUpdate.toLocaleTimeString();
        }
    }

    startUpdateTimer() {
        setInterval(() => {
            this.updateLastUpdateTime();
        }, 1000);
    }

    requestManualUpdate() {
        if (this.isConnected) {
            this.socket.emit('request_update');
            this.socket.emit('request_stats');
            
            const refreshIcon = document.getElementById('refresh-icon');
            if (refreshIcon) {
                refreshIcon.classList.add('fa-spin');
                setTimeout(() => refreshIcon.classList.remove('fa-spin'), 1000);
            }
        }
    }

    updateTable(data) {
        const tbody = document.getElementById('data-table-body');
        
        if (data.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-center">No data available</td></tr>';
            return;
        }
        
        tbody.innerHTML = data.map(row => `
            <tr>
                <td>${row.timestamp_formatted}</td>
                <td class="${this.getStatusClass(row.solar_power, 'solar')}">${row.solar_power}</td>
                <td class="${this.getStatusClass(row.grid_voltage, 'grid')}">${row.grid_voltage}</td>
                <td class="${this.getStatusClass(row.battery_percentage, 'battery')}">${row.battery_percentage}%</td>
                <td class="${this.getStatusClass(row.load_power, 'load')}">${row.load_power}</td>
                <td class="${this.getStatusClass(row.temperature, 'temp')}">${row.temperature}</td>
                <td>${row.duration_ms}ms</td>
            </tr>
        `).join('');
    }

    getStatusClass(value, type) {
        switch (type) {
            case 'solar':
                return value > 100 ? 'status-good' : value > 0 ? 'status-warning' : 'status-error';
            case 'grid':
                return value > 200 && value < 250 ? 'status-good' : 'status-warning';
            case 'battery':
                return value > 50 ? 'status-good' : value > 20 ? 'status-warning' : 'status-error';
            case 'load':
                return value > 0 ? 'status-good' : 'status-error';
            case 'temp':
                return value < 50 ? 'status-good' : value < 60 ? 'status-warning' : 'status-error';
            default:
                return '';
        }
    }

    updatePagination() {
        // Update pagination info
        const start = (this.currentPage - 1) * this.pageSize + 1;
        const end = Math.min(this.currentPage * this.pageSize, this.totalRecords);
        document.getElementById('pagination-info').textContent = 
            `Showing ${start} to ${end} of ${this.totalRecords} entries`;
        
        // Update button states
        document.getElementById('first-page-btn').disabled = this.currentPage === 1;
        document.getElementById('prev-page-btn').disabled = this.currentPage === 1;
        document.getElementById('next-page-btn').disabled = this.currentPage === this.totalPages;
        document.getElementById('last-page-btn').disabled = this.currentPage === this.totalPages;
        
        // Generate page numbers
        this.generatePageNumbers();
    }

    generatePageNumbers() {
        const pageNumbersContainer = document.getElementById('page-numbers');
        const maxVisiblePages = 5;
        let pages = [];
        
        if (this.totalPages <= maxVisiblePages) {
            // Show all pages
            for (let i = 1; i <= this.totalPages; i++) {
                pages.push(i);
            }
        } else {
            // Show smart pagination
            if (this.currentPage <= 3) {
                pages = [1, 2, 3, 4, '...', this.totalPages];
            } else if (this.currentPage >= this.totalPages - 2) {
                pages = [1, '...', this.totalPages - 3, this.totalPages - 2, this.totalPages - 1, this.totalPages];
            } else {
                pages = [1, '...', this.currentPage - 1, this.currentPage, this.currentPage + 1, '...', this.totalPages];
            }
        }
        
        pageNumbersContainer.innerHTML = pages.map(page => {
            if (page === '...') {
                return '<span class="page-number ellipsis">...</span>';
            }
            return `<button class="page-number ${page === this.currentPage ? 'active' : ''}" 
                     onclick="dashboard.goToPage(${page})">${page}</button>`;
        }).join('');
    }

    goToPage(page) {
        if (page === 'last') {
            this.currentPage = this.totalPages;
        } else {
            this.currentPage = parseInt(page);
        }
        this.loadRawData();
    }

    nextPage() {
        if (this.currentPage < this.totalPages) {
            this.currentPage++;
            this.loadRawData();
        }
    }

    previousPage() {
        if (this.currentPage > 1) {
            this.currentPage--;
            this.loadRawData();
        }
    }

    async exportData() {
        try {
            const response = await fetch('/export-data');
            const blob = await response.blob();
            
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'inverter_data.csv';
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
        } catch (error) {
            console.error('Error exporting data:', error);
        }
    }
}

// Initialize dashboard
let dashboard;
document.addEventListener('DOMContentLoaded', () => {
    dashboard = new InverterDashboard();
});
