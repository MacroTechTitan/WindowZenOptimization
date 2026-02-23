const App = {
    currentPage: 'dashboard',
    refreshInterval: null,
    logInterval: null,
    
    init() {
        this.bindNavigation();
        this.startClock();
        this.refreshMetrics();
        this.refreshLogs();
        this.refreshScanResults();
        this.refreshActivity();
        this.loadSettings();
        this.refreshInterval = setInterval(() => this.refreshMetrics(), 3000);
        this.logInterval = setInterval(() => this.refreshLogs(), 2000);
        setInterval(() => this.refreshScanResults(), 5000);
        setInterval(() => this.refreshCleanStatus(), 2000);
        setInterval(() => this.refreshActivity(), 10000);
        this.showPage('dashboard');
    },

    bindNavigation() {
        document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', () => {
                const page = item.dataset.page;
                if (page) this.showPage(page);
            });
        });
    },

    showPage(pageName) {
        this.currentPage = pageName;
        document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
        document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
        
        const page = document.getElementById(`page-${pageName}`);
        if (page) page.classList.add('active');
        
        const nav = document.querySelector(`.nav-item[data-page="${pageName}"]`);
        if (nav) nav.classList.add('active');

        if (pageName === 'processes') this.refreshProcesses();
        if (pageName === 'system') this.refreshSystemInfo();
        if (pageName === 'registry') this.refreshRegistry();
        if (pageName === 'scheduler') this.refreshScheduler();
        if (pageName === 'cleaner') this.refreshScanResults();
        if (pageName === 'settings') this.loadSettings();
    },

    startClock() {
        const update = () => {
            const now = new Date();
            const el = document.getElementById('system-time');
            if (el) el.textContent = now.toLocaleTimeString('en-US', { hour12: false });
        };
        update();
        setInterval(update, 1000);
    },

    async refreshMetrics() {
        try {
            const res = await fetch('/api/metrics');
            const data = await res.json();
            this.updateMetricCards(data);
            if (this.currentPage === 'processes') this.renderProcesses(data.top_processes);
            if (this.currentPage === 'system') this.renderSystemInfo(data);
        } catch (e) {
            console.error('Metrics fetch error:', e);
        }
    },

    updateMetricCards(data) {
        const setVal = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.textContent = val;
        };
        const setWidth = (id, pct) => {
            const el = document.getElementById(id);
            if (el) el.style.width = pct + '%';
        };

        setVal('cpu-value', data.cpu.percent.toFixed(1) + '%');
        setVal('cpu-sub', `${data.cpu.cores}C/${data.cpu.threads}T @ ${data.cpu.freq.toFixed(0)} MHz`);
        setWidth('cpu-bar', data.cpu.percent);

        setVal('mem-value', data.memory.percent.toFixed(1) + '%');
        setVal('mem-sub', `${data.memory.used_fmt} / ${data.memory.total_fmt}`);
        setWidth('mem-bar', data.memory.percent);

        setVal('disk-value', data.disk.percent.toFixed(1) + '%');
        setVal('disk-sub', `${data.disk.free_fmt} free`);
        setWidth('disk-bar', data.disk.percent);

        setVal('uptime-value', data.system.uptime);

        const cpuBar = document.getElementById('cpu-bar');
        if (cpuBar) {
            cpuBar.className = 'progress-bar';
            if (data.cpu.percent > 80) cpuBar.classList.add('red');
            else if (data.cpu.percent > 50) cpuBar.classList.add('purple');
            else cpuBar.classList.add('blue');
        }

        const memBar = document.getElementById('mem-bar');
        if (memBar) {
            memBar.className = 'progress-bar';
            if (data.memory.percent > 80) memBar.classList.add('red');
            else if (data.memory.percent > 60) memBar.classList.add('purple');
            else memBar.classList.add('green');
        }
    },

    async refreshLogs() {
        try {
            const res = await fetch('/api/logs');
            const logs = await res.json();
            const container = document.getElementById('terminal-logs');
            if (container) {
                container.innerHTML = logs.map(log => `
                    <div class="log-line">
                        <span class="log-time">${log.time}</span>
                        <span class="log-level ${log.level}">${log.level}</span>
                        <span class="log-message">${log.message}</span>
                    </div>
                `).join('');
                container.scrollTop = container.scrollHeight;
            }
            const cleanerLog = document.getElementById('terminal-logs-cleaner');
            if (cleanerLog) {
                cleanerLog.innerHTML = logs.map(log => `
                    <div class="log-line">
                        <span class="log-time">${log.time}</span>
                        <span class="log-level ${log.level}">${log.level}</span>
                        <span class="log-message">${log.message}</span>
                    </div>
                `).join('');
                cleanerLog.scrollTop = cleanerLog.scrollHeight;
            }
        } catch (e) {
            console.error('Log fetch error:', e);
        }
    },

    async refreshScanResults() {
        try {
            const res = await fetch('/api/scan-results');
            const data = await res.json();
            this.renderScanSummary(data);
            this.renderCleanerCategories(data);
        } catch (e) {}
    },

    renderScanSummary(data) {
        const setVal = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.textContent = val;
        };
        setVal('scan-total', data.total_size_fmt || '0 B');
        setVal('scan-total-files', data.total_files || 0);
        setVal('last-scan-time', data.last_scan || 'Never');
        setVal('scan-registry', data.registry_issues || 0);

        const cats = data.categories || {};
        let tempCount = 0, tempSize = 0, browserSize = 0, junkCount = 0;
        if (cats.system_temp) { tempCount += cats.system_temp.count; tempSize += cats.system_temp.size; }
        if (cats.user_temp) { tempCount += cats.user_temp.count; tempSize += cats.user_temp.size; }
        if (cats.browser_cache) { browserSize = cats.browser_cache.size; }
        for (const [k, v] of Object.entries(cats)) {
            if (!['system_temp','user_temp','browser_cache'].includes(k)) {
                junkCount += v.count;
            }
        }
        setVal('scan-temp-count', tempCount);
        setVal('scan-chrome', this.formatBytes(browserSize));
        setVal('scan-junk', junkCount);
    },

    renderCleanerCategories(data) {
        const container = document.getElementById('cleaner-categories');
        if (!container) return;

        const setVal = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.textContent = val;
        };
        setVal('cleaner-total', data.total_size_fmt || '0 B');
        setVal('cleaner-total-files', data.total_files || 0);
        setVal('cleaner-last-scan', data.last_scan || 'Never');

        const cats = data.categories || {};
        if (Object.keys(cats).length === 0) return;

        const icons = {
            system_temp: '&#x1F4C4;', user_temp: '&#x1F4C2;', browser_cache: '&#x1F310;',
            recycle_bin: '&#x1F5D1;', thumbnails: '&#x1F5BC;', downloaded_program_files: '&#x1F4E5;',
            directx_shader_cache: '&#x1F3AE;', error_reports: '&#x26A0;', delivery_optimization: '&#x1F4E6;',
            defender_temp: '&#x1F6E1;', old_logs: '&#x1F4DD;', windows_update: '&#x1F504;',
            windows_old: '&#x1F4BE;',
        };

        container.innerHTML = Object.entries(cats).map(([key, cat]) => {
            const icon = icons[key] || '&#x1F4C1;';
            const safeClass = cat.safe_level === 'caution' ? 'caution' : 'safe';
            const sizeColor = cat.size > 100_000_000 ? 'var(--accent-yellow)' :
                              cat.size > 1_000_000 ? 'var(--accent-cyan)' : 'var(--text-secondary)';
            return `
                <div class="clean-category-item ${safeClass}">
                    <div class="clean-cat-icon">${icon}</div>
                    <div class="clean-cat-info">
                        <div class="clean-cat-label">${cat.label}</div>
                        <div class="clean-cat-desc">${cat.description}</div>
                    </div>
                    <div class="clean-cat-stats">
                        <div class="clean-cat-size" style="color: ${sizeColor}">${cat.size_fmt}</div>
                        <div class="clean-cat-count">${cat.count} files</div>
                    </div>
                    <div class="clean-cat-badge ${safeClass}">
                        ${cat.safe_level === 'caution' ? 'CAUTION' : 'SAFE'}
                    </div>
                    <label class="toggle">
                        <input type="checkbox" class="setting-toggle" data-key="${cat.setting}"
                            ${cat.enabled ? 'checked' : ''} onchange="App.toggleCleanTarget('${cat.setting}', this.checked)">
                        <span class="toggle-slider"></span>
                    </label>
                </div>
            `;
        }).join('');
    },

    async toggleCleanTarget(key, enabled) {
        try {
            const payload = {};
            payload[key] = enabled;
            await fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
        } catch(e) {}
    },

    async refreshCleanStatus() {
        try {
            const res = await fetch('/api/clean-status');
            const data = await res.json();
            const bar = document.getElementById('clean-progress-bar');
            const text = document.getElementById('clean-status-text');
            if (bar) bar.style.width = data.progress + '%';
            if (text) {
                if (data.is_running) {
                    text.textContent = `${data.current_task} (${data.progress}%)`;
                } else if (data.progress === 100) {
                    text.textContent = `Complete - ${this.formatBytes(data.space_freed)} freed`;
                }
            }
        } catch(e) {}
    },

    async refreshActivity() {
        try {
            const res = await fetch('/api/activity');
            const data = await res.json();
            this.renderWellness(data);
        } catch(e) {}
    },

    renderWellness(data) {
        const scoreEl = document.getElementById('wellness-score');
        if (scoreEl) {
            scoreEl.textContent = data.wellness_score;
            scoreEl.className = 'wellness-score';
            if (data.wellness_score >= 70) scoreEl.classList.add('good');
            else if (data.wellness_score >= 40) scoreEl.classList.add('ok');
            else scoreEl.classList.add('bad');
        }
        const setVal = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.textContent = val;
        };
        setVal('active-minutes', data.active_minutes);
        setVal('idle-minutes', data.idle_minutes);
        setVal('break-count', data.break_count);

        const gauge = document.getElementById('wellness-gauge');
        if (gauge) {
            const circumference = 2 * Math.PI * 65;
            const offset = circumference - (data.wellness_score / 100) * circumference;
            gauge.style.strokeDasharray = circumference;
            gauge.style.strokeDashoffset = offset;
            if (data.wellness_score >= 70) gauge.style.stroke = 'var(--accent-green)';
            else if (data.wellness_score >= 40) gauge.style.stroke = 'var(--accent-yellow)';
            else gauge.style.stroke = 'var(--accent-red)';
        }
    },

    async refreshProcesses() {
        try {
            const res = await fetch('/api/metrics');
            const data = await res.json();
            this.renderProcesses(data.top_processes);
        } catch (e) {}
    },

    renderProcesses(processes) {
        const container = document.getElementById('process-list');
        if (!container) return;
        container.innerHTML = processes.map(p => `
            <div class="process-item">
                <span class="pid">${p.pid}</span>
                <span class="name">${p.name}</span>
                <span class="cpu">${(p.cpu_percent || 0).toFixed(1)}%</span>
                <span class="mem">${(p.memory_percent || 0).toFixed(1)}%</span>
            </div>
        `).join('');
    },

    renderSystemInfo(data) {
        const container = document.getElementById('system-details');
        if (!container) return;
        container.innerHTML = `
            <div class="info-row"><span class="info-label">Platform</span><span class="info-value">${data.system.platform}</span></div>
            <div class="info-row"><span class="info-label">Release</span><span class="info-value">${data.system.release}</span></div>
            <div class="info-row"><span class="info-label">Machine</span><span class="info-value">${data.system.machine}</span></div>
            <div class="info-row"><span class="info-label">Processor</span><span class="info-value">${data.system.processor}</span></div>
            <div class="info-row"><span class="info-label">Boot Time</span><span class="info-value">${data.system.boot_time}</span></div>
            <div class="info-row"><span class="info-label">Uptime</span><span class="info-value">${data.system.uptime}</span></div>
            <div class="info-row"><span class="info-label">CPU Cores</span><span class="info-value">${data.cpu.cores} Physical / ${data.cpu.threads} Logical</span></div>
            <div class="info-row"><span class="info-label">CPU Frequency</span><span class="info-value">${data.cpu.freq.toFixed(0)} MHz</span></div>
            <div class="info-row"><span class="info-label">Total Memory</span><span class="info-value">${data.memory.total_fmt}</span></div>
            <div class="info-row"><span class="info-label">Total Disk</span><span class="info-value">${data.disk.total_fmt}</span></div>
            <div class="info-row"><span class="info-label">Network Sent</span><span class="info-value">${data.network.bytes_sent}</span></div>
            <div class="info-row"><span class="info-label">Network Received</span><span class="info-value">${data.network.bytes_recv}</span></div>
        `;
    },

    async startScan() {
        const btn = document.getElementById('btn-scan');
        if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Scanning...'; }
        try {
            await fetch('/api/scan', { method: 'POST' });
            const poll = setInterval(() => {
                this.refreshScanResults();
                this.refreshLogs();
            }, 1500);
            setTimeout(() => {
                clearInterval(poll);
                this.refreshScanResults();
                this.refreshLogs();
                if (btn) { btn.disabled = false; btn.innerHTML = '&#x1F50D; Scan System'; }
            }, 8000);
        } catch(e) {
            if (btn) { btn.disabled = false; btn.innerHTML = '&#x1F50D; Scan System'; }
        }
    },

    async startClean() {
        const btn = document.getElementById('btn-clean');
        if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Cleaning...'; }
        try {
            await fetch('/api/clean', { method: 'POST' });
            const check = setInterval(() => {
                this.refreshCleanStatus();
                this.refreshLogs();
            }, 1000);
            setTimeout(() => {
                clearInterval(check);
                this.refreshScanResults();
                this.refreshCleanStatus();
                if (btn) { btn.disabled = false; btn.innerHTML = '&#x1F9F9; Clean Now'; }
            }, 15000);
        } catch(e) {
            if (btn) { btn.disabled = false; btn.innerHTML = '&#x1F9F9; Clean Now'; }
        }
    },

    async loadSettings() {
        try {
            const res = await fetch('/api/settings');
            const data = await res.json();
            document.querySelectorAll('.setting-toggle').forEach(toggle => {
                const key = toggle.dataset.key;
                if (key && data[key] !== undefined) {
                    toggle.checked = data[key];
                }
            });
        } catch(e) {}
    },

    async saveSettings() {
        const formData = {};
        document.querySelectorAll('#page-settings .setting-toggle').forEach(toggle => {
            formData[toggle.dataset.key] = toggle.checked;
        });
        try {
            await fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(formData)
            });
            this.showNotification('Settings saved successfully');
        } catch(e) {
            this.showNotification('Failed to save settings', 'error');
        }
    },

    showNotification(message, type = 'success') {
        const notif = document.createElement('div');
        notif.style.cssText = `
            position: fixed; top: 20px; right: 20px; z-index: 10000;
            padding: 12px 20px; border-radius: 8px;
            font-family: 'JetBrains Mono', monospace; font-size: 12px;
            background: ${type === 'success' ? 'var(--accent-green)' : 'var(--accent-red)'};
            color: white; box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            animation: fadeIn 0.3s ease;
        `;
        notif.textContent = message;
        document.body.appendChild(notif);
        setTimeout(() => notif.remove(), 3000);
    },

    formatBytes(bytes) {
        if (!bytes || bytes === 0) return '0 B';
        const units = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(1024));
        return (bytes / Math.pow(1024, i)).toFixed(1) + ' ' + units[i];
    },

    takeBreak() {
        this.showNotification('Break logged! Stand up and stretch.');
    },

    async refreshRegistry() {
        try {
            const res = await fetch('/api/registry');
            const data = await res.json();
            const setVal = (id, val) => {
                const el = document.getElementById(id);
                if (el) el.textContent = val;
            };
            setVal('reg-orphaned', data.orphaned_keys);
            setVal('reg-invalid', data.invalid_paths);
            setVal('reg-startup', data.startup_items);
            setVal('reg-issues', data.issues_found);

            const list = document.getElementById('registry-entries');
            if (list && data.entries && data.entries.length > 0) {
                list.innerHTML = data.entries.map(e => `
                    <div class="process-item">
                        <span class="name" style="grid-column: span 2;">${e.path}</span>
                        <span class="cpu">${e.type}</span>
                        <span class="mem" style="color: ${e.risk === 'medium' ? 'var(--accent-yellow)' : 'var(--accent-green)'};">${e.risk}</span>
                    </div>
                `).join('');
            }
        } catch(e) {}
    },

    async scanRegistry() {
        const btn = event.target;
        if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Scanning...'; }
        try {
            await fetch('/api/registry/scan', { method: 'POST' });
            setTimeout(() => {
                this.refreshRegistry();
                this.refreshLogs();
                if (btn) { btn.disabled = false; btn.innerHTML = '&#x1F50D; Scan Registry'; }
            }, 3000);
        } catch(e) {
            if (btn) { btn.disabled = false; btn.innerHTML = '&#x1F50D; Scan Registry'; }
        }
    },

    async refreshScheduler() {
        try {
            const res = await fetch('/api/scheduler');
            const data = await res.json();
            const container = document.getElementById('scheduler-jobs');
            if (container && data.jobs) {
                container.innerHTML = data.jobs.map(job => `
                    <div class="info-row">
                        <span class="info-label">${job.id}</span>
                        <span class="info-value">${job.next_run || 'N/A'}</span>
                    </div>
                `).join('');
            }
            const status = document.getElementById('scheduler-status');
            if (status) {
                status.textContent = data.running ? 'Active' : 'Inactive';
                status.style.color = data.running ? 'var(--accent-green)' : 'var(--accent-red)';
            }
        } catch(e) {}
    }
};

document.addEventListener('DOMContentLoaded', () => App.init());
