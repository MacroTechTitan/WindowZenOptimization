const App = {
    currentPage: 'dashboard',
    refreshInterval: null,
    logInterval: null,
    breakTimerInterval: null,

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

        setInterval(() => this.checkBreak(), 60000);

        this.breakTimerInterval = setInterval(() => {
            const timerEl = document.getElementById('break-timer');
            if (timerEl && timerEl.dataset.seconds) {
                let secs = parseInt(timerEl.dataset.seconds);
                if (secs > 0) {
                    secs--;
                    timerEl.dataset.seconds = secs;
                    const mins = Math.floor(secs / 60);
                    const rem = secs % 60;
                    timerEl.textContent = `${mins}:${rem.toString().padStart(2, '0')}`;
                }
            }
        }, 1000);
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

        if (pageName === 'processes') {
            this.refreshProcesses();
            this.refreshStartupItems();
        }
        if (pageName === 'system') this.refreshSystemInfo();
        if (pageName === 'registry') this.refreshRegistry();
        if (pageName === 'scheduler') this.refreshScheduler();
        if (pageName === 'cleaner') this.refreshScanResults();
        if (pageName === 'settings') this.loadSettings();
        if (pageName === 'file-organizer') this.refreshFileOrganizer();
        if (pageName === 'cybersecurity') this.refreshSecurity();
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
        let html = `
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

        if (data.ram_details) {
            const ram = data.ram_details;
            html += `
                <div class="info-row" style="margin-top: 12px; border-top: 1px solid var(--border-color); padding-top: 12px;">
                    <span class="info-label" style="font-weight: bold; color: var(--accent-cyan);">RAM Details</span><span class="info-value"></span>
                </div>
                <div class="info-row"><span class="info-label">Installed</span><span class="info-value">${ram.installed_gb || 'N/A'} GB</span></div>
                <div class="info-row"><span class="info-label">Max Capacity</span><span class="info-value">${ram.max_capacity_gb || 'N/A'} GB</span></div>
                <div class="info-row"><span class="info-label">Slots Used</span><span class="info-value">${ram.slots_used || 'N/A'} / ${ram.slots_total || 'N/A'}</span></div>
                <div class="info-row"><span class="info-label">RAM Type</span><span class="info-value">${ram.ram_type || 'N/A'}</span></div>
            `;
        }

        if (data.motherboard) {
            const mb = data.motherboard;
            html += `
                <div class="info-row" style="margin-top: 12px; border-top: 1px solid var(--border-color); padding-top: 12px;">
                    <span class="info-label" style="font-weight: bold; color: var(--accent-cyan);">Motherboard</span><span class="info-value"></span>
                </div>
                <div class="info-row"><span class="info-label">Manufacturer</span><span class="info-value">${mb.manufacturer || 'N/A'}</span></div>
                <div class="info-row"><span class="info-label">Product</span><span class="info-value">${mb.product || 'N/A'}</span></div>
                <div class="info-row"><span class="info-label">Serial Number</span><span class="info-value">${mb.serial_number || 'N/A'}</span></div>
            `;
        }

        container.innerHTML = html;
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
                        <span class="name" style="grid-column: span 1;">${e.path}</span>
                        <span class="cpu">${e.type}</span>
                        <span class="mem" style="color: ${e.risk === 'medium' ? 'var(--accent-yellow)' : 'var(--accent-green)'};">${e.risk}</span>
                        <span class="cpu">${e.action || 'clean'}</span>
                        <span class="mem" style="color: ${e.status === 'fixed' ? 'var(--accent-green)' : 'var(--accent-yellow)'};">${e.status || 'pending'}</span>
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

    async fixRegistry() {
        try {
            await fetch('/api/registry/fix', { method: 'POST' });
            await this.refreshRegistry();
            this.showNotification('Registry issues fixed!');
        } catch(e) {
            this.showNotification('Failed to fix registry issues', 'error');
        }
    },

    async checkBreak() {
        try {
            const res = await fetch('/api/wellness/break-check');
            const data = await res.json();
            if (data.should_break) {
                const alertEl = document.getElementById('break-alert');
                if (alertEl) alertEl.style.display = 'flex';

                const timerEl = document.getElementById('break-timer');
                if (timerEl && data.seconds_remaining) {
                    timerEl.dataset.seconds = data.seconds_remaining;
                    const mins = Math.floor(data.seconds_remaining / 60);
                    const rem = data.seconds_remaining % 60;
                    timerEl.textContent = `${mins}:${rem.toString().padStart(2, '0')}`;
                }

                try {
                    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                    const oscillator = audioCtx.createOscillator();
                    const gainNode = audioCtx.createGain();
                    oscillator.connect(gainNode);
                    gainNode.connect(audioCtx.destination);
                    oscillator.type = 'sine';
                    oscillator.frequency.setValueAtTime(800, audioCtx.currentTime);
                    gainNode.gain.setValueAtTime(0.3, audioCtx.currentTime);
                    gainNode.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 1);
                    oscillator.start(audioCtx.currentTime);
                    oscillator.stop(audioCtx.currentTime + 1);
                } catch(audioErr) {}
            }
        } catch(e) {}
    },

    async dismissBreak() {
        try {
            await fetch('/api/wellness/dismiss-break', { method: 'POST' });
            const alertEl = document.getElementById('break-alert');
            if (alertEl) alertEl.style.display = 'none';
            const timerEl = document.getElementById('break-timer');
            if (timerEl) {
                timerEl.textContent = '0:00';
                timerEl.dataset.seconds = 0;
            }
        } catch(e) {}
    },

    async refreshStartupItems() {
        try {
            const res = await fetch('/api/startup-items');
            const data = await res.json();
            const container = document.getElementById('startup-items-list');
            if (!container) return;
            if (data.items && data.items.length > 0) {
                container.innerHTML = data.items.map(item => `
                    <div class="process-item">
                        <span class="name">${item.name}</span>
                        <span class="cpu" style="font-size: 11px;">${item.path || 'N/A'}</span>
                        <label class="toggle">
                            <input type="checkbox" ${item.enabled ? 'checked' : ''}
                                onchange="App.toggleStartupItem('${item.name.replace(/'/g, "\\'")}', '${item.hive || 'HKCU'}', this.checked)">
                            <span class="toggle-slider"></span>
                        </label>
                    </div>
                `).join('');
            } else {
                container.innerHTML = '<div class="info-row"><span class="info-label">No startup items found</span></div>';
            }
        } catch(e) {}
    },

    async toggleStartupItem(name, hive, enabled) {
        try {
            await fetch('/api/startup-items/toggle', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, hive, enabled })
            });
            this.showNotification(`Startup item "${name}" ${enabled ? 'enabled' : 'disabled'}`);
        } catch(e) {
            this.showNotification('Failed to toggle startup item', 'error');
        }
    },

    async rebootSystem() {
        if (!confirm('Are you sure you want to reboot the system? All unsaved work will be lost.')) return;
        try {
            await fetch('/api/system/reboot', { method: 'POST' });
            this.showNotification('System reboot initiated...');
        } catch(e) {
            this.showNotification('Failed to initiate reboot', 'error');
        }
    },

    async runDeepAnalysis() {
        const btn = document.getElementById('btn-deep-analysis');
        if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Analyzing...'; }
        try {
            await fetch('/api/system/deep-analysis', { method: 'POST' });
            const poll = setInterval(async () => {
                try {
                    const res = await fetch('/api/system/deep-analysis');
                    const data = await res.json();
                    if (data.status === 'complete') {
                        clearInterval(poll);
                        this.renderDeepAnalysis(data);
                        if (btn) { btn.disabled = false; btn.innerHTML = '&#x1F50E; Run Deep Analysis'; }
                    }
                } catch(e) {}
            }, 2000);
        } catch(e) {
            if (btn) { btn.disabled = false; btn.innerHTML = '&#x1F50E; Run Deep Analysis'; }
        }
    },

    renderDeepAnalysis(data) {
        const container = document.getElementById('deep-analysis-results');
        if (!container) return;
        const results = data.results || data;
        let html = `
            <div class="info-row"><span class="info-label">Total Files</span><span class="info-value">${results.total_files || 0}</span></div>
            <div class="info-row"><span class="info-label">Videos</span><span class="info-value">${results.videos || 0}</span></div>
            <div class="info-row"><span class="info-label">Images</span><span class="info-value">${results.images || 0}</span></div>
            <div class="info-row"><span class="info-label">Documents</span><span class="info-value">${results.documents || 0}</span></div>
            <div class="info-row"><span class="info-label">Audio</span><span class="info-value">${results.audio || 0}</span></div>
            <div class="info-row"><span class="info-label">Installed Software</span><span class="info-value">${results.installed_software ? results.installed_software.length || results.installed_software : 0}</span></div>
        `;

        if (results.event_log_paths && results.event_log_paths.length > 0) {
            html += `
                <div class="info-row" style="margin-top: 12px; border-top: 1px solid var(--border-color); padding-top: 12px;">
                    <span class="info-label" style="font-weight: bold; color: var(--accent-cyan);">Event Log Paths</span><span class="info-value"></span>
                </div>
            `;
            results.event_log_paths.forEach(path => {
                html += `<div class="info-row"><span class="info-label">&#x1F4C4;</span><span class="info-value" style="font-size: 11px;">${path}</span></div>`;
            });
        }

        container.innerHTML = html;
    },

    async scanFiles() {
        const btn = document.getElementById('btn-scan-files');
        if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Scanning...'; }
        try {
            await fetch('/api/file-organizer/scan', { method: 'POST' });
            const poll = setInterval(async () => {
                try {
                    const res = await fetch('/api/file-organizer/results');
                    const data = await res.json();
                    if (data.status === 'complete') {
                        clearInterval(poll);
                        this.renderFileOrganizerResults(data);
                        if (btn) { btn.disabled = false; btn.innerHTML = '&#x1F4C2; Scan Files'; }
                    }
                } catch(e) {}
            }, 2000);
        } catch(e) {
            if (btn) { btn.disabled = false; btn.innerHTML = '&#x1F4C2; Scan Files'; }
        }
    },

    async refreshFileOrganizer() {
        try {
            const res = await fetch('/api/file-organizer/results');
            const data = await res.json();
            if (data.status === 'complete') {
                this.renderFileOrganizerResults(data);
            }
        } catch(e) {}
    },

    renderFileOrganizerResults(data) {
        const container = document.getElementById('file-organizer-results');
        if (!container) return;

        const results = data.results || data;
        let html = '';

        const categories = [
            { key: 'zero_length_files', label: 'Zero-Length Files', icon: '&#x1F4C4;' },
            { key: 'duplicates', label: 'Duplicate Files', icon: '&#x1F4CB;' },
            { key: 'installers', label: 'Installer Files', icon: '&#x1F4E6;' }
        ];

        categories.forEach(cat => {
            const files = results[cat.key] || [];
            const totalSize = files.reduce((sum, f) => sum + (f.size || 0), 0);
            html += `
                <div class="file-category" style="margin-bottom: 16px;">
                    <div class="info-row" style="border-bottom: 1px solid var(--border-color); padding-bottom: 8px; margin-bottom: 8px;">
                        <span class="info-label" style="font-weight: bold; color: var(--accent-cyan);">
                            ${cat.icon} ${cat.label} (${files.length} files, ${this.formatBytes(totalSize)})
                        </span>
                        <span class="info-value">
                            <button class="btn btn-sm" onclick="App.toggleSelectAll('${cat.key}')" style="margin-right: 8px; padding: 4px 8px; font-size: 11px;">Select All</button>
                            <button class="btn btn-sm" onclick="App.deleteSelected('${cat.key}')" style="margin-right: 8px; padding: 4px 8px; font-size: 11px;">Delete Selected</button>
                            <button class="btn btn-sm btn-danger" onclick="App.deleteAllInCategory('${cat.key}')" style="padding: 4px 8px; font-size: 11px;">Delete All</button>
                        </span>
                    </div>
                    <div id="file-list-${cat.key}">
            `;
            files.forEach((f, idx) => {
                html += `
                    <div class="process-item" style="font-size: 11px;">
                        <input type="checkbox" class="file-check-${cat.key}" data-path="${f.path || f.name || ''}" style="margin-right: 8px;">
                        <span class="name" style="flex: 1;">${f.path || f.name || 'Unknown'}</span>
                        <span class="mem">${this.formatBytes(f.size || 0)}</span>
                    </div>
                `;
            });
            html += `</div></div>`;
        });

        container.innerHTML = html;
    },

    toggleSelectAll(category) {
        const checkboxes = document.querySelectorAll(`.file-check-${category}`);
        const allChecked = Array.from(checkboxes).every(cb => cb.checked);
        checkboxes.forEach(cb => cb.checked = !allChecked);
    },

    async deleteSelected(category) {
        const checkboxes = document.querySelectorAll(`.file-check-${category}:checked`);
        const paths = Array.from(checkboxes).map(cb => cb.dataset.path).filter(p => p);
        if (paths.length === 0) {
            this.showNotification('No files selected', 'error');
            return;
        }
        try {
            await fetch('/api/file-organizer/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ files: paths, category })
            });
            this.showNotification(`${paths.length} files deleted`);
            this.refreshFileOrganizer();
        } catch(e) {
            this.showNotification('Failed to delete files', 'error');
        }
    },

    async deleteAllInCategory(category) {
        const checkboxes = document.querySelectorAll(`.file-check-${category}`);
        checkboxes.forEach(cb => cb.checked = true);
        await this.deleteSelected(category);
    },

    async runSecurityScan() {
        const btn = document.getElementById('btn-security-scan');
        if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Scanning...'; }
        try {
            await fetch('/api/security/scan', { method: 'POST' });
            const poll = setInterval(async () => {
                try {
                    const res = await fetch('/api/security/scan');
                    const data = await res.json();
                    if (data.results || data.open_ports) {
                        clearInterval(poll);
                        this.renderSecurityResults(data.results || data);
                        if (btn) { btn.disabled = false; btn.innerHTML = '&#x1F6E1; Run Security Scan'; }
                    }
                } catch(e) {}
            }, 2000);
        } catch(e) {
            if (btn) { btn.disabled = false; btn.innerHTML = '&#x1F6E1; Run Security Scan'; }
        }
    },

    async refreshSecurity() {
        try {
            const res = await fetch('/api/security/scan');
            const data = await res.json();
            if (data.results || data.open_ports) {
                this.renderSecurityResults(data.results || data);
            }
        } catch(e) {}
    },

    renderSecurityResults(data) {
        const container = document.getElementById('security-results');
        if (!container) return;

        let html = '';

        if (data.public_ip) {
            html += `
                <div class="info-row" style="margin-bottom: 16px; padding: 12px; background: var(--card-bg); border-radius: 8px; border: 1px solid var(--accent-cyan);">
                    <span class="info-label" style="font-weight: bold; color: var(--accent-cyan);">&#x1F310; Public IP</span>
                    <span class="info-value" style="font-size: 16px; font-weight: bold;">${data.public_ip}</span>
                </div>
            `;
        }

        if (data.open_ports && data.open_ports.length > 0) {
            html += `
                <div style="margin-bottom: 16px;">
                    <div class="info-row" style="border-bottom: 1px solid var(--border-color); padding-bottom: 8px; margin-bottom: 8px;">
                        <span class="info-label" style="font-weight: bold; color: var(--accent-cyan);">&#x1F6AA; Open Ports</span>
                    </div>
                    <div class="process-item" style="font-weight: bold; font-size: 11px;">
                        <span class="pid">Port</span>
                        <span class="name">Service</span>
                        <span class="cpu">Protocol</span>
                        <span class="mem">Status</span>
                    </div>
            `;
            data.open_ports.forEach(port => {
                const statusColor = port.status === 'open' ? 'var(--accent-red)' : 'var(--accent-green)';
                html += `
                    <div class="process-item">
                        <span class="pid">${port.port || port.number || ''}</span>
                        <span class="name">${port.service || 'Unknown'}</span>
                        <span class="cpu">${port.protocol || 'TCP'}</span>
                        <span class="mem" style="color: ${statusColor}; font-weight: bold;">${port.status || 'open'}</span>
                    </div>
                `;
            });
            html += `</div>`;
        }

        if (data.active_connections && data.active_connections.length > 0) {
            html += `
                <div style="margin-bottom: 16px;">
                    <div class="info-row" style="border-bottom: 1px solid var(--border-color); padding-bottom: 8px; margin-bottom: 8px;">
                        <span class="info-label" style="font-weight: bold; color: var(--accent-cyan);">&#x1F517; Active Connections</span>
                    </div>
                    <div class="process-item" style="font-weight: bold; font-size: 11px;">
                        <span class="pid">Local</span>
                        <span class="name">Remote</span>
                        <span class="cpu">Status</span>
                        <span class="mem">PID</span>
                    </div>
            `;
            data.active_connections.forEach(conn => {
                html += `
                    <div class="process-item">
                        <span class="pid" style="font-size: 10px;">${conn.local_address || ''}</span>
                        <span class="name" style="font-size: 10px;">${conn.remote_address || ''}</span>
                        <span class="cpu">${conn.status || ''}</span>
                        <span class="mem">${conn.pid || ''}</span>
                    </div>
                `;
            });
            html += `</div>`;
        }

        if (data.vulnerabilities && data.vulnerabilities.length > 0) {
            html += `
                <div style="margin-bottom: 16px;">
                    <div class="info-row" style="border-bottom: 1px solid var(--border-color); padding-bottom: 8px; margin-bottom: 8px;">
                        <span class="info-label" style="font-weight: bold; color: var(--accent-red);">&#x26A0; Vulnerabilities</span>
                    </div>
            `;
            data.vulnerabilities.forEach(vuln => {
                const severity = vuln.severity || 'info';
                const severityColor = severity === 'high' ? 'var(--accent-red)' :
                                      severity === 'medium' ? 'var(--accent-yellow)' : 'var(--accent-green)';
                html += `
                    <div class="process-item">
                        <span class="name" style="flex: 1;">${vuln.description || vuln.name || ''}</span>
                        <span class="mem" style="color: ${severityColor}; font-weight: bold;">${severity.toUpperCase()}</span>
                    </div>
                `;
            });
            html += `</div>`;
        }

        container.innerHTML = html;
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
