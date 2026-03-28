const App = {
    currentPage: 'dashboard',
    refreshInterval: null,
    logInterval: null,
    breakTimerInterval: null,
    breakDismissedUntil: 0,
    networkFixPoller: null,

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
        const urlParams = new URLSearchParams(window.location.search);
        const hashPage = window.location.hash.replace('#', '');
        const startPage = window.__initialPage || urlParams.get('page') || hashPage || 'dashboard';
        this.showPage(startPage);

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
        if (pageName === 'speedup') {
            this.refreshStartupItems();
            this.refreshUndoLog();
        }
        if (pageName === 'system') this.refreshSystemInfo();
        if (pageName === 'registry') this.refreshRegistry();
        if (pageName === 'scheduler') this.refreshScheduler();
        if (pageName === 'cleaner') this.refreshScanResults();
        if (pageName === 'settings') this.loadSettings();
        if (pageName === 'file-organizer') {
            this.refreshFileOrganizer();
            this.refreshUndoLog();
        }
        if (pageName === 'cybersecurity') this.refreshSecurity();
        if (pageName === 'network') this.resetNetworkFixUI();
        if (pageName === 'dashboard') this.refreshHealthScore();
        if (pageName === 'apps' && this._appsData.length === 0) this.refreshApps();
        if (pageName === 'recommendations') this.refreshRecs();
        if (pageName === 'profiles') this.refreshProfiles();
        if (pageName === 'maintenance') { this.refreshMaintenance(); this.refreshMaintenanceHistory(); }
        if (pageName === 'debug-logs') this.refreshDebugLogs();
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
            this.renderTop5Processes(data.top_processes);
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

            if (ram.upgrade_recommendations) {
                const rec = ram.upgrade_recommendations;
                html += `
                    <div class="info-row" style="margin-top: 12px; border-top: 1px solid var(--border-color); padding-top: 12px;">
                        <span class="info-label" style="font-weight: bold; color: var(--accent-green);">&#x2B06; RAM Upgrade Guide</span>
                        <span class="info-value" style="color: ${rec.can_upgrade ? 'var(--accent-green)' : 'var(--text-muted)'};">${rec.can_upgrade ? 'Upgrade Available' : 'At Maximum'}</span>
                    </div>
                    <div class="info-row"><span class="info-label">Current Setup</span><span class="info-value">${rec.current_summary}</span></div>
                    <div class="info-row"><span class="info-label">Max Supported</span><span class="info-value">${rec.max_supported}</span></div>
                    <div class="info-row"><span class="info-label">Free Slots</span><span class="info-value">${rec.slots_free}</span></div>
                    <div class="info-row"><span class="info-label">Compatible Type</span><span class="info-value" style="color: var(--accent-cyan); font-weight: 600;">${rec.compatible_type}</span></div>
                `;

                if (rec.compatible_modules && rec.compatible_modules.length > 0) {
                    const mod = rec.compatible_modules[0];
                    html += `
                        <div class="info-row" style="margin-top: 8px; border-top: 1px dashed var(--border-color); padding-top: 8px;">
                            <span class="info-label" style="font-weight: bold; color: var(--accent-cyan);">Compatible Specs</span><span class="info-value"></span>
                        </div>
                        <div class="info-row"><span class="info-label">Supported Speeds</span><span class="info-value" style="font-size: 10px;">${mod.speeds.join(', ')}</span></div>
                        <div class="info-row"><span class="info-label">Form Factor</span><span class="info-value" style="font-size: 10px;">${mod.form_factor}</span></div>
                        <div class="info-row"><span class="info-label">Voltage</span><span class="info-value">${mod.voltage}</span></div>
                    `;
                }

                if (rec.suggestions && rec.suggestions.length > 0) {
                    html += `
                        <div class="info-row" style="margin-top: 8px; border-top: 1px dashed var(--border-color); padding-top: 8px;">
                            <span class="info-label" style="font-weight: bold; color: var(--accent-yellow);">&#x1F4A1; Upgrade Options</span><span class="info-value"></span>
                        </div>
                    `;
                    rec.suggestions.forEach((s, i) => {
                        html += `
                            <div style="background: var(--bg-primary); border: 1px solid var(--border-color); border-radius: 8px; padding: 10px 14px; margin: 6px 0;">
                                <div style="color: var(--accent-green); font-weight: 600; font-size: 12px; margin-bottom: 4px;">Option ${i + 1}: ${s.option}</div>
                                <div style="display: flex; justify-content: space-between; font-size: 11px;">
                                    <span style="color: var(--accent-cyan);">${s.result}</span>
                                    <span style="color: var(--text-muted);">${s.difficulty}</span>
                                </div>
                            </div>
                        `;
                    });
                }

                if (rec.notes && rec.notes.length > 0) {
                    html += `
                        <div class="info-row" style="margin-top: 8px; border-top: 1px dashed var(--border-color); padding-top: 8px;">
                            <span class="info-label" style="font-weight: bold; color: var(--text-muted);">&#x26A0; Important Notes</span><span class="info-value"></span>
                        </div>
                    `;
                    rec.notes.forEach(note => {
                        html += `<div style="padding: 4px 0; font-size: 11px; color: var(--text-muted); line-height: 1.5;">&#x2022; ${note}</div>`;
                    });
                }
            }
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

        const upgradePanel = document.getElementById('ram-upgrade-info');
        if (upgradePanel && data.ram_details && data.ram_details.upgrade_recommendations) {
            const rec = data.ram_details.upgrade_recommendations;
            let uhtml = '';

            uhtml += `<div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
                <span style="font-size: 20px;">${rec.can_upgrade ? '&#x2705;' : '&#x26D4;'}</span>
                <span style="font-weight: 700; color: ${rec.can_upgrade ? 'var(--accent-green)' : 'var(--text-muted)'}; font-size: 14px;">
                    ${rec.can_upgrade ? 'Upgrade Available' : 'Maximum RAM Reached'}
                </span>
            </div>`;

            uhtml += `<div class="info-row"><span class="info-label">Compatible RAM</span><span class="info-value" style="color: var(--accent-cyan); font-weight: 700;">${rec.compatible_type}</span></div>`;
            uhtml += `<div class="info-row"><span class="info-label">Free Slots</span><span class="info-value">${rec.slots_free}</span></div>`;
            uhtml += `<div class="info-row"><span class="info-label">Max Supported</span><span class="info-value">${rec.max_supported}</span></div>`;

            if (rec.compatible_modules && rec.compatible_modules.length > 0) {
                const mod = rec.compatible_modules[0];
                uhtml += `<div style="margin-top: 12px; padding-top: 10px; border-top: 1px dashed var(--border-color);">
                    <div style="font-weight: 600; color: var(--accent-cyan); font-size: 12px; margin-bottom: 8px;">What to Buy:</div>
                    <div class="info-row"><span class="info-label">Speeds</span><span class="info-value" style="font-size: 10px;">${mod.speeds.join(', ')}</span></div>
                    <div class="info-row"><span class="info-label">Form Factor</span><span class="info-value" style="font-size: 10px;">${mod.form_factor}</span></div>
                    <div class="info-row"><span class="info-label">Voltage</span><span class="info-value">${mod.voltage}</span></div>
                </div>`;
            }

            if (rec.suggestions && rec.suggestions.length > 0) {
                uhtml += `<div style="margin-top: 12px; padding-top: 10px; border-top: 1px dashed var(--border-color);">
                    <div style="font-weight: 600; color: var(--accent-yellow); font-size: 12px; margin-bottom: 8px;">Upgrade Options:</div>
                </div>`;
                rec.suggestions.forEach((s, i) => {
                    uhtml += `<div style="background: var(--bg-primary); border: 1px solid var(--border-color); border-radius: 8px; padding: 10px 14px; margin: 6px 0;">
                        <div style="color: var(--accent-green); font-weight: 600; font-size: 12px; margin-bottom: 4px;">Option ${i + 1}: ${s.option}</div>
                        <div style="display: flex; justify-content: space-between; font-size: 11px;">
                            <span style="color: var(--accent-cyan);">${s.result}</span>
                            <span style="color: var(--text-muted);">${s.difficulty}</span>
                        </div>
                    </div>`;
                });
            }

            if (rec.notes && rec.notes.length > 0) {
                uhtml += `<div style="margin-top: 12px; padding-top: 10px; border-top: 1px dashed var(--border-color);">
                    <div style="font-weight: 600; color: var(--text-muted); font-size: 11px; margin-bottom: 6px;">Important Notes:</div>
                </div>`;
                rec.notes.forEach(note => {
                    uhtml += `<div style="padding: 3px 0; font-size: 11px; color: var(--text-muted); line-height: 1.5;">&#x2022; ${note}</div>`;
                });
            }

            upgradePanel.innerHTML = uhtml;
        }
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

    _pendingUpdateUrl: null,

    async checkForUpdates() {
        const btn = document.getElementById('update-check-btn');
        const statusEl = document.getElementById('update-status-label');
        const outputEl = document.getElementById('update-output');
        const dlBtn = document.getElementById('update-download-btn');
        const localVerEl = document.getElementById('update-local-version');

        if (btn) { btn.disabled = true; btn.textContent = 'Checking...'; }
        if (dlBtn) dlBtn.style.display = 'none';
        if (outputEl) { outputEl.style.display = 'block'; outputEl.textContent = 'Contacting update server...\n'; }
        if (statusEl) { statusEl.textContent = 'Checking...'; statusEl.style.color = 'var(--accent-cyan)'; }

        try {
            const res = await fetch('/api/updates/check');
            const data = await res.json();

            if (localVerEl) localVerEl.textContent = `${data.local_version} (build ${data.local_build})`;

            let out = `Update Check Results\n${'='.repeat(40)}\n`;
            out += `Installed : v${data.local_version} (build ${data.local_build})\n`;
            out += `Available : v${data.remote_version} (build ${data.remote_build})\n`;
            out += `Released  : ${data.release_date || 'N/A'}\n`;
            if (data.note) out += `\nNote: ${data.note}\n`;

            if (data.update_available) {
                out += `\n✅ UPDATE AVAILABLE!\n\nWhat's new:\n`;
                (data.changelog || []).forEach(c => { out += `  • ${c}\n`; });
                if (statusEl) { statusEl.textContent = `Update available: v${data.remote_version}`; statusEl.style.color = 'var(--accent-green)'; }
                if (dlBtn) { dlBtn.style.display = 'inline-flex'; }
                this._pendingUpdateUrl = data.download_url;
            } else {
                out += `\n✅ You are up to date.\n`;
                if (statusEl) { statusEl.textContent = 'Up to date'; statusEl.style.color = 'var(--accent-green)'; }
            }

            if (outputEl) outputEl.textContent = out;
        } catch(e) {
            if (outputEl) outputEl.textContent = 'Error: Could not reach the update server. Check your internet connection.';
            if (statusEl) { statusEl.textContent = 'Check failed'; statusEl.style.color = 'var(--accent-red)'; }
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = '🔍 Check for Updates'; }
        }
    },

    async downloadUpdate() {
        const dlBtn = document.getElementById('update-download-btn');
        const outputEl = document.getElementById('update-output');

        if (!this._pendingUpdateUrl) {
            this.showNotification('No update URL available. Check for updates first.', 'error');
            return;
        }
        if (!confirm(`Download and install the update now?\n\nThe app will restart automatically after the update is applied.`)) return;

        if (dlBtn) { dlBtn.disabled = true; dlBtn.textContent = 'Downloading...'; }
        if (outputEl) { outputEl.style.display = 'block'; outputEl.textContent += '\n\nDownloading update...\n'; }

        try {
            const res = await fetch('/api/updates/apply', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ download_url: this._pendingUpdateUrl })
            });
            const data = await res.json();

            if (data.status === 'ok') {
                if (outputEl) outputEl.textContent += `✅ ${data.message}\nThe app will close and restart. Please wait...\n`;
                this.showNotification('Update applied! Restarting...', 'success');
            } else if (data.status === 'demo') {
                if (outputEl) outputEl.textContent += `ℹ️ DEMO MODE:\n${data.message}\n`;
                this.showNotification('Demo mode: update simulated', 'info');
                if (dlBtn) { dlBtn.disabled = false; dlBtn.textContent = '⬇ Download & Install Update'; }
            } else {
                if (outputEl) outputEl.textContent += `❌ Error: ${data.message}\n`;
                this.showNotification('Update failed: ' + data.message, 'error');
                if (dlBtn) { dlBtn.disabled = false; dlBtn.textContent = '⬇ Download & Install Update'; }
            }
        } catch(e) {
            if (outputEl) outputEl.textContent += '\n[ERROR] Failed to apply update.\n';
            this.showNotification('Update failed', 'error');
            if (dlBtn) { dlBtn.disabled = false; dlBtn.textContent = '⬇ Download & Install Update'; }
        }
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
        const bg = type === 'success' ? 'var(--accent-green)'
                 : type === 'info'    ? 'var(--accent-cyan)'
                 : type === 'warn'    ? 'var(--accent-yellow)'
                 :                      'var(--accent-red)';
        const color = (type === 'warn' || type === 'info') ? '#000' : 'white';
        notif.style.cssText = `
            position: fixed; top: 20px; right: 20px; z-index: 10000;
            padding: 12px 20px; border-radius: 8px;
            font-family: 'JetBrains Mono', monospace; font-size: 12px;
            background: ${bg}; color: ${color};
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            animation: fadeIn 0.3s ease; max-width: 360px;
        `;
        notif.textContent = message;
        document.body.appendChild(notif);
        setTimeout(() => notif.remove(), 3500);
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
        if (Date.now() < this.breakDismissedUntil) return;
        try {
            const res = await fetch('/api/wellness/break-check');
            const data = await res.json();
            if (data.should_break) {
                const alertEl = document.getElementById('break-alert');
                if (alertEl) alertEl.style.display = 'block';
            }
        } catch(e) {}
    },

    async dismissBreak() {
        await this.dismissBreakReminder();
    },

    async dismissBreakReminder() {
        try {
            await fetch('/api/wellness/dismiss-break', { method: 'POST' });
            this.breakDismissedUntil = Date.now() + (40 * 60 * 1000);
            const alertEl = document.getElementById('break-alert');
            if (alertEl) alertEl.style.display = 'none';
            const timerEl = document.getElementById('break-timer');
            const breakMins = 40;
            if (timerEl) { timerEl.dataset.seconds = breakMins * 60; timerEl.textContent = `${breakMins}:00`; }
        } catch(e) {}
    },

    async refreshStartupItems() {
        try {
            const res = await fetch('/api/startup-items');
            const data = await res.json();
            const items = Array.isArray(data) ? data : (data.items || []);
            const renderTo = (containerId, enhanced) => {
                const container = document.getElementById(containerId);
                if (!container) return;
                if (items.length > 0) {
                    container.innerHTML = items.map(item => {
                        const impact = item.impact || (item.hive === 'HKLM' ? 'Medium' : 'Low');
                        const impactColor = impact === 'High' ? 'var(--accent-red)' : impact === 'Medium' ? 'var(--accent-yellow)' : 'var(--accent-green)';
                        const cat = item.category || 'review';
                        const catLabel = { safe_to_disable:'✔ Safe to disable', review:'Review', system_related:'⚠ System/caution' }[cat] || cat;
                        const catColor = { safe_to_disable:'var(--accent-green)', review:'var(--accent-yellow)', system_related:'var(--accent-red)' }[cat] || 'var(--text-muted)';
                        const rec = item.recommendation || '';
                        if (enhanced) {
                            return `<div class="process-item" style="flex-wrap:wrap;gap:4px;" title="${rec}">
                                <span class="name">${item.name}</span>
                                <span class="cpu" style="font-size:10px;color:var(--text-muted);">${item.hive}</span>
                                <span class="mem" style="font-size:10px;">
                                    <span style="color:${impactColor};font-weight:600;">${impact}</span>
                                    &nbsp;<span style="color:${catColor};font-size:9px;padding:1px 5px;border:1px solid ${catColor};border-radius:3px;">${catLabel}</span>
                                </span>
                                <label class="toggle">
                                    <input type="checkbox" ${item.enabled ? 'checked' : ''}
                                        onchange="App.toggleStartupItem('${item.name.replace(/'/g, "\\'")}', '${item.hive || 'HKCU'}', this.checked, '${item.path?.replace(/'/g,"\\'")||''}')">
                                    <span class="toggle-slider"></span>
                                </label>
                            </div>`;
                        }
                        return `<div class="process-item">
                            <span class="name">${item.name}</span>
                            <span class="cpu" style="font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${item.path || 'N/A'}</span>
                            <label class="toggle">
                                <input type="checkbox" ${item.enabled ? 'checked' : ''}
                                    onchange="App.toggleStartupItem('${item.name.replace(/'/g, "\\'")}', '${item.hive || 'HKCU'}', this.checked, '${item.path?.replace(/'/g,"\\'")||''}')">
                                <span class="toggle-slider"></span>
                            </label>
                        </div>`;
                    }).join('');
                } else {
                    container.innerHTML = '<div class="info-row"><span class="info-label">No startup items found</span></div>';
                }
            };
            renderTo('startup-items-list', false);
            renderTo('speedup-startup-list', true);
        } catch(e) {}
    },

    async toggleStartupItem(name, hive, enabled, path) {
        try {
            await fetch('/api/startup-items/toggle', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, hive, enabled, path: path || '' })
            });
            this.showNotification(`Startup item "${name}" ${enabled ? 'enabled' : 'disabled'}`);
            this.refreshUndoLog();
        } catch(e) {
            this.showNotification('Failed to toggle startup item', 'error');
        }
    },

    async undoLastAction() {
        try {
            const res = await fetch('/api/undo', { method: 'POST' });
            const data = await res.json();
            if (data.status === 'ok') {
                this.showNotification(`Undo: ${data.message}`, 'success');
            } else if (data.status === 'nothing') {
                this.showNotification('Nothing to undo', 'info');
            } else {
                this.showNotification(`Undo: ${data.message}`, 'warn');
            }
            this.refreshUndoLog();
        } catch(e) {
            this.showNotification('Undo failed', 'error');
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
    },

    renderTop5Processes(processes) {
        const container = document.getElementById('top5-process-list');
        if (!container || !processes) return;
        const top5 = processes.slice(0, 5);
        if (top5.length === 0) {
            container.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: 8px; font-size: 11px;">No process data available</div>';
            return;
        }
        container.innerHTML = top5.map((p, i) => {
            const cpu = p.cpu_percent || p.cpu || 0;
            const mem = p.memory_percent || p.memory || 0;
            return `<div class="process-item">
                <span class="pid" style="color: var(--text-muted);">${i + 1}</span>
                <span class="name">${p.name || 'Unknown'}</span>
                <span class="cpu" style="color: ${cpu > 50 ? 'var(--accent-red)' : cpu > 20 ? 'var(--accent-yellow)' : 'var(--accent-green)'};">${cpu.toFixed(1)}%</span>
                <span class="mem" style="color: ${mem > 50 ? 'var(--accent-red)' : mem > 20 ? 'var(--accent-yellow)' : 'var(--accent-cyan)'};">${mem.toFixed(1)}%</span>
            </div>`;
        }).join('');
    },

    openTaskManager() {
        this.showNotification('On Windows, press Ctrl+Shift+Esc to open Task Manager, or run "taskmgr.exe"', 'info');
    },

    recommendRestart() {
        const msg = 'A system restart is recommended to apply pending updates, free memory, and refresh system services. Would you like to restart now?';
        if (confirm(msg)) {
            this.rebootSystem();
        } else {
            this.showNotification('Restart reminder noted. You can restart later from Settings.', 'info');
        }
    },

    async runNetworkFix(mode) {
        mode = mode || 'full';
        const labels = {
            winsock: 'Winsock Reset',
            dns: 'Flush DNS',
            full: 'Full Network Fix'
        };
        if (!confirm(`Run ${labels[mode] || 'Network Fix'}? This requires Administrator privileges on Windows.\n\nCommands to run:\n${mode === 'winsock' ? '• netsh winsock reset' : mode === 'dns' ? '• ipconfig /flushdns' : '• netsh winsock reset\n• netsh int ip reset\n• ipconfig /release\n• ipconfig /renew\n• ipconfig /flushdns'}`)) return;

        const btn = document.getElementById('fix-internet-btn');
        const outputEl = document.getElementById('network-fix-output');
        const rebootEl = document.getElementById('network-fix-reboot');

        if (btn) { btn.disabled = true; btn.textContent = 'Running...'; }
        if (rebootEl) rebootEl.style.display = 'none';
        if (outputEl) {
            outputEl.style.display = 'block';
            outputEl.textContent = `MTT Network Fix — ${labels[mode] || mode}\n${'='.repeat(50)}\nRunning commands...\n`;
        }

        try {
            const res = await fetch('/api/network-fix', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mode })
            });
            const data = await res.json();
            if (outputEl) {
                outputEl.textContent = `MTT Network Fix — ${labels[mode] || mode}\n${'='.repeat(50)}\n${data.output || 'No output returned.'}`;
                outputEl.scrollTop = outputEl.scrollHeight;
            }
            if (data.needs_reboot && rebootEl) {
                rebootEl.style.display = 'block';
            }
            this.showNotification('Network fix complete!', 'success');
        } catch(e) {
            if (outputEl) outputEl.textContent += '\n[ERROR] Failed to communicate with backend.';
            this.showNotification('Network fix failed', 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = '▶ Run Network Fix (Admin)'; }
        }
    },

    // ── New streaming network fix (Network page + Cleaner panel) ──────────────

    resetNetworkFixUI() {
        if (this.networkFixPoller) { clearInterval(this.networkFixPoller); this.networkFixPoller = null; }
        const stepsEl = document.getElementById('network-fix-steps');
        if (stepsEl) stepsEl.innerHTML = `<div style="text-align:center;color:var(--text-muted);padding:20px;font-family:'JetBrains Mono',monospace;font-size:12px;">
            Press <strong style="color:var(--accent-cyan);">Run Fix Network</strong> to begin. Each command runs in sequence and its output is shown below.
        </div>`;
        const termEl = document.getElementById('network-fix-terminal');
        if (termEl) termEl.style.display = 'none';
        const bodyEl = document.getElementById('network-fix-terminal-body');
        if (bodyEl) bodyEl.textContent = '';
        const rebootEl = document.getElementById('network-fix-reboot-network');
        if (rebootEl) rebootEl.style.display = 'none';
        const runBtn = document.getElementById('btn-network-fix-run');
        if (runBtn) { runBtn.disabled = false; runBtn.textContent = '▶ Run Fix Network'; runBtn.style.display = ''; }
        const resetBtn = document.getElementById('btn-network-fix-reset');
        if (resetBtn) resetBtn.style.display = 'none';
        // Also reset cleaner panel
        const cStepsEl = document.getElementById('cleaner-network-fix-steps');
        if (cStepsEl) cStepsEl.innerHTML = '';
        const cOutEl = document.getElementById('cleaner-network-fix-output');
        if (cOutEl) { cOutEl.style.display = 'none'; cOutEl.textContent = ''; }
        const cRebootEl = document.getElementById('cleaner-network-fix-reboot');
        if (cRebootEl) cRebootEl.style.display = 'none';
        // Update admin badge
        this._updateNetworkAdminBadge();
    },

    async _updateNetworkAdminBadge() {
        const badge = document.getElementById('network-admin-badge');
        if (!badge) return;
        try {
            const data = await fetch('/api/network-fix/progress').then(r => r.json());
            const plat = data.platform || 'Unknown';
            if (plat !== 'Windows') {
                badge.textContent = 'DEMO MODE';
                badge.style.background = 'rgba(156,163,175,0.15)';
                badge.style.color = 'var(--text-muted)';
            } else if (data.admin) {
                badge.textContent = '✔ RUNNING AS ADMIN';
                badge.style.background = 'rgba(16,185,129,0.2)';
                badge.style.color = 'var(--accent-green)';
            } else {
                badge.textContent = '⚠ NOT ADMIN — UAC will prompt';
                badge.style.background = 'rgba(245,158,11,0.15)';
                badge.style.color = 'var(--accent-yellow)';
            }
        } catch(e) { /* silent */ }
    },

    async startNetworkFix(context) {
        context = context || 'network';
        const runBtn = document.getElementById('btn-network-fix-run');
        const cleanerBtn = document.getElementById('btn-cleaner-network-fix');

        // Guard — reset first if a previous run is showing
        const currentStatus = await fetch('/api/network-fix/progress').then(r => r.json()).catch(() => ({status:'idle'}));
        if (currentStatus.status === 'running') {
            this.showNotification('Network fix is already running', 'info');
            return;
        }

        // Disable buttons
        if (runBtn) { runBtn.disabled = true; runBtn.textContent = '⏳ Running...'; }
        if (cleanerBtn) { cleanerBtn.disabled = true; cleanerBtn.textContent = '⏳ Running...'; }

        // Show terminal on Network page
        const termEl = document.getElementById('network-fix-terminal');
        if (termEl) termEl.style.display = 'block';
        const bodyEl = document.getElementById('network-fix-terminal-body');
        if (bodyEl) bodyEl.textContent = 'Starting Fix Network...\n';

        // Show cleaner output
        const cOutEl = document.getElementById('cleaner-network-fix-output');
        if (cOutEl) { cOutEl.style.display = 'block'; cOutEl.textContent = 'Starting Fix Network...\n'; }

        const badgeEl = document.getElementById('network-fix-status-badge');
        if (badgeEl) { badgeEl.textContent = 'RUNNING'; badgeEl.style.background = 'rgba(6,182,212,0.2)'; badgeEl.style.color = 'var(--accent-cyan)'; }

        // Start the fix
        await fetch('/api/network-fix/run', { method: 'POST' }).catch(() => {});

        // Poll for progress
        if (this.networkFixPoller) clearInterval(this.networkFixPoller);
        this.networkFixPoller = setInterval(() => this.pollNetworkFix(context), 600);
    },

    async pollNetworkFix(context) {
        try {
            const data = await fetch('/api/network-fix/progress').then(r => r.json());
            const steps = data.steps || [];

            this._renderNetworkSteps(steps, 'network-fix-steps');
            this._renderNetworkSteps(steps, 'cleaner-network-fix-steps');

            const termLines = this._buildNetworkTerminal(steps);
            const bodyEl = document.getElementById('network-fix-terminal-body');
            if (bodyEl) { bodyEl.textContent = termLines; bodyEl.scrollTop = bodyEl.scrollHeight; }
            const cOutEl = document.getElementById('cleaner-network-fix-output');
            if (cOutEl) { cOutEl.textContent = termLines; cOutEl.scrollTop = cOutEl.scrollHeight; }

            if (data.status === 'complete') {
                clearInterval(this.networkFixPoller);
                this.networkFixPoller = null;

                const badgeEl = document.getElementById('network-fix-status-badge');
                if (badgeEl) { badgeEl.textContent = 'COMPLETE'; badgeEl.style.background = 'rgba(16,185,129,0.2)'; badgeEl.style.color = 'var(--accent-green)'; }

                const runBtn = document.getElementById('btn-network-fix-run');
                if (runBtn) { runBtn.disabled = false; runBtn.textContent = '▶ Run Again'; }
                const resetBtn = document.getElementById('btn-network-fix-reset');
                if (resetBtn) resetBtn.style.display = '';
                const cleanerBtn = document.getElementById('btn-cleaner-network-fix');
                if (cleanerBtn) { cleanerBtn.disabled = false; cleanerBtn.textContent = '▶ Run Fix Network'; }

                if (data.needs_reboot) {
                    const rebootEl = document.getElementById('network-fix-reboot-network');
                    if (rebootEl) rebootEl.style.display = 'block';
                    const cRebootEl = document.getElementById('cleaner-network-fix-reboot');
                    if (cRebootEl) cRebootEl.style.display = 'block';
                }
                this.showNotification(data.needs_reboot ? 'Network fix complete — reboot required' : 'Network fix complete!', 'success');
            }
        } catch(e) {
            clearInterval(this.networkFixPoller);
            this.networkFixPoller = null;
        }
    },

    _renderNetworkSteps(steps, containerId) {
        const el = document.getElementById(containerId);
        if (!el) return;
        if (!steps || steps.length === 0) return;
        const statusColors = {
            pending: 'var(--text-muted)',
            running: 'var(--accent-cyan)',
            done:    'var(--accent-green)',
            error:   'var(--accent-red)',
        };
        const statusIcons = { pending: '⏳', running: '▶', done: '✅', error: '❌' };
        el.innerHTML = steps.map((s, i) => {
            const col = statusColors[s.status] || 'var(--text-muted)';
            const icon = statusIcons[s.status] || '⬜';
            const pulse = s.status === 'running' ? 'animation: pulse 1s infinite;' : '';
            return `<div style="display:flex;align-items:flex-start;gap:12px;padding:10px 14px;background:var(--bg-card);border:1px solid ${col}33;border-left:3px solid ${col};border-radius:8px;${pulse}">
                <span style="font-size:16px;flex-shrink:0;margin-top:1px;">${icon}</span>
                <div style="flex:1;min-width:0;">
                    <div style="display:flex;align-items:center;gap:10px;margin-bottom:2px;">
                        <span style="font-family:'JetBrains Mono',monospace;font-size:11px;font-weight:700;color:${col};">${s.label}</span>
                        <code style="font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-muted);background:var(--bg-primary);padding:1px 6px;border-radius:3px;">${s.cmd}</code>
                    </div>
                    <div style="font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-muted);">${s.description}</div>
                    ${s.output ? `<pre style="margin:6px 0 0;font-family:'JetBrains Mono',monospace;font-size:10px;color:${s.status==='error'?'var(--accent-red)':'var(--accent-green)'};white-space:pre-wrap;word-break:break-all;max-height:80px;overflow-y:auto;">${s.output}</pre>` : ''}
                </div>
                <span style="font-family:'JetBrains Mono',monospace;font-size:10px;color:${col};text-transform:uppercase;flex-shrink:0;">${s.status}</span>
            </div>`;
        }).join('');
    },

    _buildNetworkTerminal(steps) {
        if (!steps || steps.length === 0) return 'Waiting for commands...\n';
        let lines = ['MTT Fix Network — live output', '='.repeat(52), ''];
        steps.forEach(s => {
            if (s.status === 'pending') return;
            lines.push(`> ${s.cmd}  [${s.label}]`);
            if (s.status === 'running') {
                lines.push('  Running...');
            } else if (s.output) {
                s.output.split('\n').forEach(l => lines.push('  ' + l));
            }
            if (s.status === 'done') lines.push('  ✔ Done\n');
            if (s.status === 'error') lines.push('  ✖ Error — see output above\n');
        });
        return lines.join('\n');
    },

    openWindowsSetting(setting) {
        const deepLinks = {
            'visual_effects': 'SystemPropertiesPerformance.exe',
            'power': 'ms-settings:powersleep',
            'display': 'ms-settings:display',
            'nightlight': 'ms-settings:nightlight',
            'notifications': 'ms-settings:notifications',
        };
        const link = deepLinks[setting] || setting;
        this.showNotification(`On Windows, open: ${link}`, 'info');
    },

    async scanLargeFiles() {
        const threshold = parseInt(document.getElementById('large-files-threshold')?.value) || 100;
        const container = document.getElementById('large-files-results');
        if (container) container.innerHTML = '<div style="text-align: center; padding: 16px; color: var(--accent-cyan); font-family: \'JetBrains Mono\', monospace; font-size: 12px;">Scanning for large files...</div>';
        try {
            await fetch('/api/large-files/scan', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({threshold_mb: threshold})
            });
            setTimeout(() => this.refreshLargeFiles(), 2000);
        } catch(e) { this.showNotification('Large files scan failed', 'error'); }
    },

    async refreshLargeFiles() {
        try {
            const res = await fetch('/api/large-files/results');
            const data = await res.json();
            const container = document.getElementById('large-files-results');
            if (!container) return;
            if (data.status === 'scanning') {
                setTimeout(() => this.refreshLargeFiles(), 1000);
                return;
            }
            if (!data.files || data.files.length === 0) {
                container.innerHTML = '<div style="text-align: center; padding: 16px; color: var(--accent-green); font-family: \'JetBrains Mono\', monospace; font-size: 12px;">No large files found above threshold</div>';
                return;
            }
            let html = `<div style="margin-bottom: 8px; font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--text-muted);">Found ${data.files.length} files (${this.formatBytes(data.total_size)} total)</div>`;
            html += '<div class="process-list">';
            html += '<div class="process-item process-header"><span class="name">File</span><span class="cpu">Size</span><span class="mem">Location</span><span class="cpu">Actions</span></div>';
            data.files.forEach(f => {
                html += `<div class="process-item">
                    <span class="name" title="${f.path}">${f.name}</span>
                    <span class="cpu" style="color: var(--accent-yellow);">${f.size_fmt}</span>
                    <span class="mem" style="color: var(--text-muted);">${f.location}</span>
                    <span class="cpu">
                        <button class="btn" style="font-size:10px; padding:2px 6px;" onclick="App.deleteLargeFile('${f.path.replace(/\\/g, '\\\\').replace(/'/g, "\\'")}')">Del</button>
                        <button class="btn" style="font-size:10px; padding:2px 6px;" onclick="App.archiveLargeFile('${f.path.replace(/\\/g, '\\\\').replace(/'/g, "\\'")}')">Archive</button>
                    </span>
                </div>`;
            });
            html += '</div>';
            container.innerHTML = html;
        } catch(e) {}
    },

    async deleteLargeFile(path) {
        const dryRun = document.getElementById('large-files-dry-run')?.checked || false;
        if (!dryRun && !confirm(`Delete this file?\n${path}`)) return;
        try {
            await fetch('/api/large-files/delete', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({files: [path], dry_run: dryRun})
            });
            this.showNotification(dryRun ? '[DRY RUN] File would be deleted' : 'File deleted', 'success');
            this.refreshLargeFiles();
        } catch(e) { this.showNotification('Delete failed', 'error'); }
    },

    async archiveLargeFile(path) {
        const dryRun = document.getElementById('large-files-dry-run')?.checked || false;
        if (!dryRun && !confirm(`Archive this file to ~/Archive?\n${path}`)) return;
        try {
            await fetch('/api/large-files/archive', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({files: [path], dry_run: dryRun})
            });
            this.showNotification(dryRun ? '[DRY RUN] File would be archived' : 'File archived', 'success');
            this.refreshLargeFiles();
        } catch(e) { this.showNotification('Archive failed', 'error'); }
    },

    async previewOrganize(action) {
        const maxAgeDays = parseInt(document.getElementById('archive-days')?.value) || 30;
        try {
            const res = await fetch('/api/organize/preview', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({action: action, max_age_days: maxAgeDays})
            });
            const data = await res.json();
            const container = document.getElementById('organize-preview-results');
            const list = document.getElementById('organize-preview-list');
            if (!container || !list) return;
            if (data.actions.length === 0) {
                container.style.display = 'none';
                this.showNotification('No files match the selected rule', 'info');
                return;
            }
            container.style.display = 'block';
            this._organizeActions = data.actions;
            list.innerHTML = data.actions.map(a => `
                <div class="process-item">
                    <span class="name" title="${a.path}">${a.file}</span>
                    <span class="cpu" style="color: var(--accent-cyan);">${a.action}</span>
                    <span class="mem">${a.size_fmt}</span>
                    <span class="cpu" style="color: var(--text-muted);">${a.modified}</span>
                </div>
            `).join('');
        } catch(e) { this.showNotification('Preview failed', 'error'); }
    },

    async executeOrganize() {
        const dryRun = document.getElementById('organize-dry-run')?.checked || false;
        const actions = this._organizeActions || [];
        if (actions.length === 0) { this.showNotification('No actions to execute', 'info'); return; }
        if (!dryRun && !confirm(`Execute ${actions.length} file operations?`)) return;
        try {
            const res = await fetch('/api/organize/execute', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({actions: actions, dry_run: dryRun})
            });
            const data = await res.json();
            this.showNotification(dryRun ? `[DRY RUN] ${data.executed} actions previewed` : `${data.executed} files organized`, 'success');
            document.getElementById('organize-preview-results').style.display = 'none';
            this._organizeActions = [];
            this.refreshUndoLog();
        } catch(e) { this.showNotification('Execute failed', 'error'); }
    },

    async refreshUndoLog() {
        try {
            const res = await fetch('/api/undo-log');
            const log = await res.json();
            const targets = ['speedup-undo-log', 'organizer-undo-log'];
            targets.forEach(targetId => {
                const container = document.getElementById(targetId);
                if (!container) return;
                if (log.length === 0) {
                    container.innerHTML = '<div style="text-align: center; color: var(--text-muted); padding: 16px; font-size: 12px; font-family: \'JetBrains Mono\', monospace;">No actions recorded yet</div>';
                    return;
                }
                container.innerHTML = log.slice().reverse().map(entry => `
                    <div style="display: flex; justify-content: space-between; align-items: center; padding: 6px 0; border-bottom: 1px solid var(--border); font-family: 'JetBrains Mono', monospace; font-size: 11px;">
                        <span style="color: var(--text-muted); width: 140px;">${entry.timestamp}</span>
                        <span style="color: ${entry.type === 'delete' ? 'var(--accent-red)' : 'var(--accent-cyan)'}; width: 60px; text-transform: uppercase;">${entry.type}</span>
                        <span style="color: var(--text-secondary); flex: 1;">${entry.description}</span>
                    </div>
                `).join('');
            });
        } catch(e) {}
    },

    focusModeActive: false,
    pomodoroInterval: null,
    pomodoroPhase: 'work',
    pomodoroCycles: 0,

    toggleFocusMode() {
        this.focusModeActive = !this.focusModeActive;
        const btn = document.getElementById('btn-focus-start');
        if (this.focusModeActive) {
            if (btn) { btn.textContent = '\u23F9 Stop Focus Session'; btn.classList.remove('btn-primary'); btn.classList.add('btn-success'); }
            document.getElementById('focus-action-nightlight').textContent = '\u2705 Enable Night Light';
            document.getElementById('focus-action-brightness').textContent = '\u2705 Lower Brightness';
            document.getElementById('focus-action-notifications').textContent = '\u2705 Reduce Notifications';
            document.getElementById('focus-action-timer').textContent = '\u2705 Pomodoro Timer Active';
            this.pomodoroPhase = 'work';
            this.pomodoroCycles = 0;
            this.startPomodoro(25 * 60);
            this.showNotification('Focus Mode activated. Pomodoro timer started.', 'success');
            this.openWindowsSetting('nightlight');
        } else {
            if (btn) { btn.textContent = '\uD83C\uDFAF Start Focus Session'; btn.classList.add('btn-primary'); btn.classList.remove('btn-success'); }
            document.getElementById('focus-action-nightlight').textContent = '\u2B1C Enable Night Light';
            document.getElementById('focus-action-brightness').textContent = '\u2B1C Lower Brightness';
            document.getElementById('focus-action-notifications').textContent = '\u2B1C Reduce Notifications';
            document.getElementById('focus-action-timer').textContent = '\u2B1C Pomodoro Timer Active';
            if (this.pomodoroInterval) clearInterval(this.pomodoroInterval);
            document.getElementById('pomodoro-timer').textContent = '25:00';
            document.getElementById('pomodoro-phase').textContent = 'Work Phase';
            document.getElementById('pomodoro-cycles').textContent = 'Cycles: 0 / 4';
            this.showNotification('Focus Mode deactivated.', 'info');
        }
    },

    startPomodoro(seconds) {
        if (this.pomodoroInterval) clearInterval(this.pomodoroInterval);
        let remaining = seconds;
        const timerEl = document.getElementById('pomodoro-timer');
        const phaseEl = document.getElementById('pomodoro-phase');
        const cyclesEl = document.getElementById('pomodoro-cycles');
        this.pomodoroInterval = setInterval(() => {
            remaining--;
            if (timerEl) {
                const m = Math.floor(remaining / 60);
                const s = remaining % 60;
                timerEl.textContent = `${m}:${s.toString().padStart(2, '0')}`;
                timerEl.style.color = this.pomodoroPhase === 'work' ? 'var(--accent-green)' : 'var(--accent-cyan)';
            }
            if (remaining <= 0) {
                clearInterval(this.pomodoroInterval);
                if (this.pomodoroPhase === 'work') {
                    this.pomodoroCycles++;
                    if (cyclesEl) cyclesEl.textContent = `Cycles: ${this.pomodoroCycles} / 4`;
                    this.pomodoroPhase = 'break';
                    if (phaseEl) phaseEl.textContent = 'Break Phase';
                    this.showNotification('Work phase complete! Take a 5 minute break.', 'success');
                    try { new Audio('data:audio/wav;base64,UklGRl9vT19teleVtYWwAQBYAAAA...').play(); } catch(e) {}
                    this.startPomodoro(5 * 60);
                } else {
                    this.pomodoroPhase = 'work';
                    if (phaseEl) phaseEl.textContent = 'Work Phase';
                    this.showNotification('Break over! Starting next work session.', 'info');
                    if (this.pomodoroCycles < 4) {
                        this.startPomodoro(25 * 60);
                    } else {
                        if (timerEl) timerEl.textContent = 'Done!';
                        if (phaseEl) phaseEl.textContent = '4 cycles complete';
                        this.showNotification('All 4 Pomodoro cycles complete! Great work!', 'success');
                        this.focusModeActive = false;
                        const btn = document.getElementById('btn-focus-start');
                        if (btn) { btn.textContent = '\uD83C\uDFAF Start Focus Session'; btn.classList.add('btn-primary'); btn.classList.remove('btn-success'); }
                    }
                }
            }
        }, 1000);
    },

    async refreshProcesses() {
        try {
            const res = await fetch('/api/metrics');
            const data = await res.json();
            this.renderProcesses(data.top_processes);
        } catch(e) {}
    },

    // ══════════════════════════════════════════════════════════════
    // HEALTH SCORE
    // ══════════════════════════════════════════════════════════════

    async refreshHealthScore() {
        const valueEl = document.getElementById('health-score-value');
        const gradeEl = document.getElementById('health-score-grade');
        const ringEl  = document.getElementById('health-score-ring');
        const recsEl  = document.getElementById('health-recommendations');
        if (valueEl) valueEl.textContent = '…';
        try {
            const data = await fetch('/api/health-score').then(r => r.json());
            const colorMap = { green: 'var(--accent-green)', cyan: 'var(--accent-cyan)', yellow: 'var(--accent-yellow)', red: 'var(--accent-red)' };
            const col = colorMap[data.color] || 'var(--accent-green)';
            if (valueEl) { valueEl.textContent = data.score; valueEl.style.color = col; }
            if (gradeEl) gradeEl.textContent = data.grade.toUpperCase();
            if (ringEl)  { ringEl.style.borderColor = col; ringEl.style.background = col.replace('var(', 'rgba(').replace(')', ',0.08)') || `rgba(16,185,129,0.08)`; }
            if (recsEl) {
                const sevColor = { high: 'var(--accent-red)', medium: 'var(--accent-yellow)', low: 'var(--accent-green)' };
                recsEl.innerHTML = data.recommendations.map(r => `
                    <div style="display:flex;align-items:flex-start;gap:10px;padding:8px 12px;background:var(--bg-primary);border:1px solid var(--border);border-left:3px solid ${sevColor[r.severity]||'var(--border)'};border-radius:6px;cursor:pointer;" onclick="App.showPage('${r.page}')">
                        <span style="font-size:16px;flex-shrink:0;">${r.icon}</span>
                        <span style="font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--text-secondary);flex:1;">${r.text}</span>
                        <span style="font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--accent-cyan);flex-shrink:0;white-space:nowrap;">→ Go</span>
                    </div>`).join('');
            }
        } catch(e) {
            if (recsEl) recsEl.innerHTML = '<div style="font-family:\'JetBrains Mono\',monospace;font-size:12px;color:var(--text-muted);">Unable to compute health score.</div>';
        }
    },

    // ══════════════════════════════════════════════════════════════
    // APP & BLOAT MANAGER
    // ══════════════════════════════════════════════════════════════

    _appsData: [],
    _appsFilter: 'all',

    async refreshApps() {
        const listEl = document.getElementById('apps-list');
        const countEl = document.getElementById('apps-count');
        if (listEl) listEl.innerHTML = '<div style="text-align:center;color:var(--text-muted);padding:32px;font-family:\'JetBrains Mono\',monospace;font-size:12px;">Scanning registry for installed apps…</div>';
        try {
            this._appsData = await fetch('/api/apps/list').then(r => r.json());
            if (countEl) countEl.textContent = `${this._appsData.length} apps found`;
            this.renderApps();
            this._renderBloatPanel();
        } catch(e) {
            if (listEl) listEl.innerHTML = '<div style="text-align:center;color:var(--accent-red);padding:16px;font-family:\'JetBrains Mono\',monospace;font-size:12px;">Failed to load app list.</div>';
        }
    },

    setAppsFilter(filter) {
        this._appsFilter = filter;
        ['all','bloat','large'].forEach(f => {
            const btn = document.getElementById(`apps-filter-${f}`);
            if (btn) { btn.style.background = f === filter ? 'var(--accent-cyan)' : ''; btn.style.color = f === filter ? '#000' : ''; }
        });
        this.renderApps();
    },

    filterApps() {
        this.renderApps();
    },

    renderApps() {
        const listEl = document.getElementById('apps-list');
        const countEl = document.getElementById('apps-count');
        const query = (document.getElementById('apps-search')?.value || '').toLowerCase();
        const sortBy = document.getElementById('apps-sort')?.value || 'name';

        let apps = this._appsData.slice();
        if (this._appsFilter === 'bloat') apps = apps.filter(a => a.is_bloat);
        if (this._appsFilter === 'large') apps = apps.filter(a => (a.size_mb || 0) >= 500);
        if (query) apps = apps.filter(a => (a.name||'').toLowerCase().includes(query) || (a.publisher||'').toLowerCase().includes(query));

        if (sortBy === 'size') apps.sort((a,b) => (b.size_mb||0) - (a.size_mb||0));
        else if (sortBy === 'date') apps.sort((a,b) => (b.install_date||'').localeCompare(a.install_date||''));
        else if (sortBy === 'publisher') apps.sort((a,b) => (a.publisher||'').localeCompare(b.publisher||''));
        else apps.sort((a,b) => a.name.localeCompare(b.name));

        if (countEl) countEl.textContent = `${apps.length} apps`;
        if (!listEl) return;
        if (apps.length === 0) {
            listEl.innerHTML = '<div style="text-align:center;color:var(--text-muted);padding:24px;font-family:\'JetBrains Mono\',monospace;font-size:12px;">No apps match the current filter.</div>';
            return;
        }

        const tagColors = { likely_bloat:'var(--accent-red)', unknown:'var(--accent-yellow)', system:'var(--text-muted)', trusted:'var(--accent-green)', large_app:'var(--accent-cyan)', normal:'var(--border)' };
        const tagLabels = { likely_bloat:'⚠ BLOAT', unknown:'? UNKNOWN', system:'SYS', trusted:'✔ TRUSTED', large_app:'LARGE', normal:'' };

        listEl.innerHTML = apps.map(a => {
            const tag = a.tag || 'normal';
            const tc = tagColors[tag] || 'var(--border)';
            const tl = tagLabels[tag] || '';
            const sizeTxt = a.size_mb > 0 ? `${a.size_mb > 1000 ? (a.size_mb/1024).toFixed(1)+' GB' : a.size_mb+' MB'}` : '—';
            const hasUninstall = !!(a.uninstall_cmd);
            const hasFolder = !!(a.install_location);
            return `<div class="process-item" style="border-left: 3px solid ${tc}; padding-left: 10px;">
                <span class="name" title="${a.name}">${a.name}</span>
                <span style="flex:1.2;font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--text-muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${a.publisher || '—'}</span>
                <span class="cpu" style="color:var(--text-secondary);">${sizeTxt}</span>
                <span class="mem" style="color:var(--text-muted);font-size:10px;">${a.install_date || '—'}</span>
                <span class="cpu">${tl ? `<span style="font-family:'JetBrains Mono',monospace;font-size:9px;padding:2px 6px;border:1px solid ${tc};border-radius:3px;color:${tc};">${tl}</span>` : ''}</span>
                <span class="cpu" style="display:flex;gap:4px;">
                    ${hasUninstall ? `<button class="btn" style="padding:2px 8px;font-size:10px;" onclick="App.launchUninstall(${JSON.stringify(a.name)}, ${JSON.stringify(a.uninstall_cmd)})">Uninstall</button>` : '<span style="font-size:10px;color:var(--text-muted);">—</span>'}
                    ${hasFolder ? `<button class="btn" style="padding:2px 8px;font-size:10px;" onclick="App.openAppFolder(${JSON.stringify(a.install_location)})">&#x1F4C2;</button>` : ''}
                </span>
            </div>`;
        }).join('');
    },

    _renderBloatPanel() {
        const el = document.getElementById('apps-bloat-list');
        if (!el) return;
        const bloat = this._appsData.filter(a => a.is_bloat);
        if (bloat.length === 0) {
            el.innerHTML = '<div style="text-align:center;color:var(--accent-green);padding:16px;font-family:\'JetBrains Mono\',monospace;font-size:12px;">✔ No likely bloat detected.</div>';
            return;
        }
        el.innerHTML = bloat.map(a => `
            <div style="display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid var(--border);">
                <span style="font-size:18px;">⚠</span>
                <div style="flex:1;">
                    <div style="font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--accent-yellow);font-weight:600;">${a.name}</div>
                    <div style="font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-muted);">${a.publisher || 'Unknown publisher'}${a.size_mb ? ' · ' + a.size_mb + ' MB' : ''}</div>
                </div>
                ${a.uninstall_cmd ? `<button class="btn" style="padding:3px 10px;font-size:10px;border-color:var(--accent-red);color:var(--accent-red);" onclick="App.launchUninstall(${JSON.stringify(a.name)}, ${JSON.stringify(a.uninstall_cmd)})">Uninstall</button>` : '<span style="font-size:10px;color:var(--text-muted);">No uninstaller</span>'}
            </div>`).join('');
    },

    async launchUninstall(name, cmd) {
        if (!confirm(`Uninstall "${name}"?\n\nThis will run the official uninstaller. Windows UAC may prompt for confirmation.\n\nUninstall command: ${cmd}`)) return;
        try {
            const res = await fetch('/api/apps/uninstall', {
                method: 'POST', headers: {'Content-Type':'application/json'},
                body: JSON.stringify({name, uninstall_cmd: cmd})
            }).then(r => r.json());
            if (res.ok) {
                this.showNotification(res.msg || `Uninstaller launched for ${name}`, 'success');
            } else {
                this.showNotification(res.error || 'Failed to launch uninstaller', 'error');
            }
        } catch(e) {
            this.showNotification('Network error launching uninstaller', 'error');
        }
    },

    async openAppFolder(path) {
        try {
            const res = await fetch('/api/apps/open-folder', {
                method: 'POST', headers: {'Content-Type':'application/json'},
                body: JSON.stringify({path})
            }).then(r => r.json());
            if (!res.ok) this.showNotification(res.error || 'Folder not found', 'error');
        } catch(e) {}
    },

    exportApps() {
        window.location.href = '/api/apps/export';
    },

    // ══════════════════════════════════════════════════════════════
    // BROKEN SHORTCUTS
    // ══════════════════════════════════════════════════════════════

    async scanBrokenShortcuts() {
        const el = document.getElementById('broken-shortcuts-results');
        if (el) el.innerHTML = '<div style="text-align:center;color:var(--text-muted);padding:16px;font-family:\'JetBrains Mono\',monospace;font-size:12px;">Scanning shortcuts…</div>';
        try {
            const data = await fetch('/api/cleaner/broken-shortcuts').then(r => r.json());
            const items = data.items || [];
            if (!el) return;
            if (items.length === 0) {
                el.innerHTML = '<div style="text-align:center;color:var(--accent-green);padding:16px;font-family:\'JetBrains Mono\',monospace;font-size:12px;">✔ No broken shortcuts found.</div>';
                return;
            }
            const demoTag = data.demo ? '<span style="color:var(--accent-yellow);font-size:10px;"> [DEMO]</span>' : '';
            el.innerHTML = `<div style="margin-bottom:10px;font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--accent-yellow);">Found ${items.length} broken shortcut(s)${demoTag}</div>
            <div class="process-list">
                <div class="process-item process-header"><span class="name">Shortcut</span><span style="flex:2;font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--text-muted);">Missing Target</span><span class="cpu">Action</span></div>
                ${items.map(i => `<div class="process-item">
                    <span class="name" title="${i.path}"><input type="checkbox" class="broken-shortcut-cb" value="${i.path}" style="margin-right:6px;">${i.name}</span>
                    <span style="flex:2;font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--accent-red);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${i.target}">${i.target}</span>
                    <span class="cpu"><button class="btn" style="padding:2px 8px;font-size:10px;border-color:var(--accent-red);color:var(--accent-red);" onclick="App._deleteShortcut('${i.path.replace(/'/g,"\\'")}')">Delete</button></span>
                </div>`).join('')}
            </div>
            <div style="margin-top:12px;text-align:center;">
                <button class="btn" style="border-color:var(--accent-red);color:var(--accent-red);" onclick="App._deleteSelectedShortcuts()">Delete Selected</button>
            </div>`;
        } catch(e) {
            if (el) el.innerHTML = '<div style="color:var(--accent-red);font-family:\'JetBrains Mono\',monospace;font-size:12px;text-align:center;">Error scanning shortcuts.</div>';
        }
    },

    async _deleteShortcut(path) {
        if (!confirm(`Delete broken shortcut?\n${path}`)) return;
        const res = await fetch('/api/cleaner/delete-shortcuts', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({paths:[path]})
        }).then(r => r.json());
        this.showNotification(res.deleted?.length ? 'Shortcut deleted' : 'Delete failed', res.deleted?.length ? 'success' : 'error');
        this.scanBrokenShortcuts();
    },

    async _deleteSelectedShortcuts() {
        const cbs = document.querySelectorAll('.broken-shortcut-cb:checked');
        const paths = Array.from(cbs).map(c => c.value);
        if (!paths.length) { this.showNotification('No shortcuts selected', 'info'); return; }
        if (!confirm(`Delete ${paths.length} broken shortcut(s)?`)) return;
        const res = await fetch('/api/cleaner/delete-shortcuts', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({paths})
        }).then(r => r.json());
        this.showNotification(`Deleted ${res.deleted?.length || 0} shortcut(s)`, 'success');
        this.scanBrokenShortcuts();
    },

    // ══════════════════════════════════════════════════════════════
    // EMPTY FOLDERS
    // ══════════════════════════════════════════════════════════════

    async scanEmptyFolders() {
        const el = document.getElementById('empty-folders-results');
        if (el) el.innerHTML = '<div style="text-align:center;color:var(--text-muted);padding:16px;font-family:\'JetBrains Mono\',monospace;font-size:12px;">Scanning for empty folders…</div>';
        try {
            const data = await fetch('/api/cleaner/empty-folders').then(r => r.json());
            const items = data.items || [];
            if (!el) return;
            if (items.length === 0) {
                el.innerHTML = '<div style="text-align:center;color:var(--accent-green);padding:16px;font-family:\'JetBrains Mono\',monospace;font-size:12px;">✔ No empty folders found.</div>';
                return;
            }
            const demoTag = data.demo ? '<span style="color:var(--accent-yellow);font-size:10px;"> [DEMO]</span>' : '';
            el.innerHTML = `<div style="margin-bottom:10px;font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--accent-yellow);">Found ${items.length} empty folder(s)${demoTag}</div>
            <div class="process-list">
                <div class="process-item process-header"><span class="name">Folder Path</span><span class="cpu">Location</span><span class="cpu">Action</span></div>
                ${items.map(i => `<div class="process-item">
                    <span class="name"><input type="checkbox" class="empty-folder-cb" value="${i.path}" style="margin-right:6px;">${i.path.split(/[\\/]/).pop()}</span>
                    <span class="cpu" style="font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-muted);">${i.parent}</span>
                    <span class="cpu"><button class="btn" style="padding:2px 8px;font-size:10px;" onclick="App._deleteEmptyFolder('${i.path.replace(/'/g,"\\'")}')">Remove</button></span>
                </div>`).join('')}
            </div>
            <div style="margin-top:12px;text-align:center;">
                <button class="btn btn-primary" onclick="App._deleteSelectedEmptyFolders()">Remove Selected</button>
            </div>`;
        } catch(e) {
            if (el) el.innerHTML = '<div style="color:var(--accent-red);font-family:\'JetBrains Mono\',monospace;font-size:12px;text-align:center;">Error scanning folders.</div>';
        }
    },

    async _deleteEmptyFolder(path) {
        if (!confirm(`Remove empty folder?\n${path}`)) return;
        const res = await fetch('/api/cleaner/delete-empty-folders', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({paths:[path]})
        }).then(r => r.json());
        this.showNotification(res.deleted?.length ? 'Folder removed' : (res.errors?.[0]?.error || 'Remove failed'), res.deleted?.length ? 'success' : 'error');
        this.scanEmptyFolders();
    },

    async _deleteSelectedEmptyFolders() {
        const cbs = document.querySelectorAll('.empty-folder-cb:checked');
        const paths = Array.from(cbs).map(c => c.value);
        if (!paths.length) { this.showNotification('No folders selected', 'info'); return; }
        if (!confirm(`Remove ${paths.length} empty folder(s)? This cannot be undone.`)) return;
        const res = await fetch('/api/cleaner/delete-empty-folders', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({paths})
        }).then(r => r.json());
        this.showNotification(`Removed ${res.deleted?.length || 0} folder(s)`, 'success');
        this.scanEmptyFolders();
    },

    // ══════════════════════════════════════════════════════════════
    // FOLDER SIZE EXPLORER
    // ══════════════════════════════════════════════════════════════

    async scanFolderSizes() {
        const el = document.getElementById('folder-size-results');
        const path = document.getElementById('folder-size-path')?.value.trim() || '';
        if (el) el.innerHTML = '<div style="text-align:center;color:var(--text-muted);padding:16px;font-family:\'JetBrains Mono\',monospace;font-size:12px;">Computing folder sizes… this may take a moment.</div>';
        try {
            const data = await fetch('/api/folder-sizes/scan', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({path, depth:2})
            }).then(r => r.json());
            const folders = data.folders || [];
            if (!el) return;
            if (folders.length === 0) {
                el.innerHTML = '<div style="text-align:center;color:var(--text-muted);padding:16px;font-family:\'JetBrains Mono\',monospace;font-size:12px;">No folders found at that path.</div>';
                return;
            }
            const demoTag = data.demo ? ' <span style="color:var(--accent-yellow);font-size:10px;">[DEMO]</span>' : '';
            const maxSize = folders[0]?.size_bytes || 1;
            el.innerHTML = `<div style="margin-bottom:10px;font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--text-muted);">Showing ${folders.length} largest folders${demoTag}</div>
            ${folders.map(f => {
                const pct = Math.round((f.size_bytes / maxSize) * 100);
                const indent = f.depth > 1 ? `margin-left:${(f.depth-1)*16}px;` : '';
                return `<div style="${indent}margin-bottom:6px;">
                    <div style="display:flex;justify-content:space-between;font-family:'JetBrains Mono',monospace;font-size:11px;margin-bottom:3px;">
                        <span style="color:var(--text-secondary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:60%;" title="${f.path}">${f.depth > 1 ? '↳ ' : ''}${f.name}</span>
                        <span style="color:var(--accent-cyan);flex-shrink:0;margin-left:10px;">${f.size_human} <span style="color:var(--text-muted);font-size:10px;">(${f.file_count} files)</span></span>
                    </div>
                    <div style="background:var(--bg-primary);border-radius:3px;height:4px;overflow:hidden;">
                        <div style="height:100%;width:${pct}%;background:var(--accent-cyan);border-radius:3px;transition:width 0.3s;"></div>
                    </div>
                </div>`;
            }).join('')}`;
        } catch(e) {
            if (el) el.innerHTML = '<div style="color:var(--accent-red);font-family:\'JetBrains Mono\',monospace;font-size:12px;text-align:center;">Error computing folder sizes.</div>';
        }
    },

    // ══════════════════════════════════════════════════════════════
    // DESKTOP CLEANER WIZARD
    // ══════════════════════════════════════════════════════════════

    _desktopWizardData: null,

    async runDesktopWizard() {
        const resultsEl = document.getElementById('desktop-wizard-results');
        const actionsEl = document.getElementById('desktop-wizard-actions');
        const suggestEl = document.getElementById('desktop-wizard-suggestions');
        if (resultsEl) resultsEl.innerHTML = '<div style="text-align:center;color:var(--text-muted);padding:16px;font-family:\'JetBrains Mono\',monospace;font-size:12px;">Scanning Desktop…</div>';
        if (actionsEl) actionsEl.style.display = 'none';

        try {
            const data = await fetch('/api/organize/preview', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({action:'desktop_wizard', dry_run:true})
            }).then(r => r.json());
            this._desktopWizardData = data;
            const items = data.items || [];
            const demoTag = data.demo ? ' [DEMO]' : '';

            if (!resultsEl) return;
            if (items.length === 0) {
                resultsEl.innerHTML = '<div style="text-align:center;color:var(--accent-green);padding:16px;font-family:\'JetBrains Mono\',monospace;font-size:12px;">✔ Desktop is already well-organized!</div>';
                return;
            }

            const cats = {};
            items.forEach(i => { cats[i.category] = (cats[i.category] || []); cats[i.category].push(i); });

            resultsEl.innerHTML = `<div style="margin-bottom:10px;font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--text-muted);">Found ${items.length} files to organize${demoTag}</div>
            <div class="process-list">
                <div class="process-item process-header"><span class="name">File</span><span class="cpu">Category</span><span class="mem">Size</span><span class="cpu">Suggested Destination</span></div>
                ${items.slice(0,30).map(i => `<div class="process-item">
                    <span class="name" title="${i.src || i.path}">${(i.src || i.path || '').split(/[\\/]/).pop()}</span>
                    <span class="cpu" style="font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--accent-cyan);">${i.category || '—'}</span>
                    <span class="mem" style="font-size:10px;">${i.size_human || ''}</span>
                    <span class="cpu" style="font-size:10px;color:var(--text-muted);" title="${i.dst||''}">${(i.dst||'').split(/[\\/]/).pop() || '—'}</span>
                </div>`).join('')}
                ${items.length > 30 ? `<div style="text-align:center;padding:8px;font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--text-muted);">… and ${items.length-30} more files</div>` : ''}
            </div>`;

            if (actionsEl && suggestEl) {
                actionsEl.style.display = 'block';
                const summary = Object.entries(cats).map(([cat, arr]) => `<div style="display:flex;align-items:center;gap:10px;padding:6px 0;border-bottom:1px solid var(--border);">
                    <span style="font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--accent-cyan);font-weight:600;width:100px;">${cat}</span>
                    <span style="font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--text-secondary);">${arr.length} file(s) → moved to ${cat} folder</span>
                </div>`).join('');
                suggestEl.innerHTML = summary;
            }
        } catch(e) {
            if (resultsEl) resultsEl.innerHTML = '<div style="color:var(--accent-red);font-family:\'JetBrains Mono\',monospace;font-size:12px;text-align:center;">Error scanning Desktop.</div>';
        }
    },

    async executeDesktopWizard() {
        const dryRun = document.getElementById('desktop-wizard-dry-run')?.checked ?? true;
        if (!dryRun && !confirm('Move these files? This action is logged and can be undone via the Undo Log.')) return;
        try {
            const res = await fetch('/api/organize/execute', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({action:'desktop_wizard', dry_run:dryRun})
            }).then(r => r.json());
            const msg = dryRun ? `Dry run: ${res.moved||0} files would be moved.` : `Moved ${res.moved||0} files. Check Undo Log to revert.`;
            this.showNotification(msg, 'success');
            if (!dryRun) this.runDesktopWizard();
        } catch(e) {
            this.showNotification('Error executing Desktop Wizard', 'error');
        }
    },

    // ═══════════════════════════════════════════════════════════════════════
    // FEATURE 13: RECOMMENDATIONS ENGINE
    // ═══════════════════════════════════════════════════════════════════════
    _recsData: [],

    async refreshRecs() {
        try {
            const res = await fetch('/api/recommendations');
            const data = await res.json();
            this._recsData = data.recommendations || [];
            this._renderRecSummary(data);
            this._renderRecTop3(this._recsData);
            this._renderRecList(this._recsData);
            this._renderRecHistory();
            this._updateRecBadge(data.high || 0);
        } catch(e) {
            document.getElementById('rec-list').innerHTML = '<div style="text-align:center;color:var(--accent-red);padding:30px;">Failed to load recommendations</div>';
        }
    },

    _updateRecBadge(count) {
        const badge = document.getElementById('rec-badge');
        if (!badge) return;
        if (count > 0) { badge.style.display = 'inline'; badge.textContent = count; }
        else badge.style.display = 'none';
    },

    _renderRecSummary(data) {
        const el = document.getElementById('rec-summary-bar');
        if (!el) return;
        const items = [
            { label: 'Total', val: data.total || 0, color: 'var(--text-primary)' },
            { label: 'High Priority', val: data.high || 0, color: 'var(--accent-red)' },
            { label: 'Medium', val: data.medium || 0, color: 'var(--accent-yellow)' },
            { label: 'Low', val: data.low || 0, color: 'var(--accent-green)' },
        ];
        el.innerHTML = items.map(i => `
            <div style="display:flex;flex-direction:column;align-items:center;min-width:80px;">
                <div style="font-family:'JetBrains Mono',monospace;font-size:24px;font-weight:700;color:${i.color};">${i.val}</div>
                <div style="font-size:11px;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.5px;">${i.label}</div>
            </div>`).join('<div style="width:1px;background:var(--border);"></div>');
    },

    _renderRecTop3(recs) {
        const el = document.getElementById('rec-top3');
        if (!el) return;
        const top = recs.filter(r => r.priority === 'high').slice(0, 3);
        if (!top.length) { el.innerHTML = ''; return; }
        el.innerHTML = `
            <div style="background:rgba(239,68,68,0.06);border:1px solid rgba(239,68,68,0.2);border-radius:12px;padding:16px 20px;margin-bottom:4px;">
                <div style="font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--accent-red);text-transform:uppercase;letter-spacing:1px;margin-bottom:10px;">&#x26A1; Top Priority Actions</div>
                <div style="display:flex;flex-direction:column;gap:8px;">
                    ${top.map(r => `<div style="display:flex;align-items:center;justify-content:space-between;gap:12px;">
                        <span style="font-size:13px;font-weight:600;">${r.title}</span>
                        ${r.actionable && r.action ? `<button class="btn btn-outline" style="font-size:11px;padding:3px 10px;white-space:nowrap;" onclick="App.navigateToModule('${r.module}')">${r.action} →</button>` : ''}
                    </div>`).join('')}
                </div>
            </div>`;
    },

    filterRecs() {
        const cat = document.getElementById('rec-filter-cat')?.value || '';
        const pri = document.getElementById('rec-filter-pri')?.value || '';
        const filtered = this._recsData.filter(r =>
            (!cat || r.category === cat) && (!pri || r.priority === pri));
        this._renderRecList(filtered);
    },

    _renderRecList(recs) {
        const el = document.getElementById('rec-list');
        if (!el) return;
        if (!recs.length) {
            el.innerHTML = '<div class="panel" style="text-align:center;color:var(--accent-green);padding:40px;"><div style="font-size:36px;margin-bottom:12px;">✅</div><div style="font-size:15px;font-weight:600;">All clear! No recommendations right now.</div><div style="font-size:13px;color:var(--text-muted);margin-top:6px;">Your system looks healthy. Check back later.</div></div>';
            return;
        }
        const priColors = { high: 'var(--accent-red)', medium: 'var(--accent-yellow)', low: 'var(--accent-green)' };
        const catIcons = { Performance:'⚡', Storage:'💾', Startup:'🚀', Organization:'📁', Wellness:'💚', Maintenance:'🔧', Network:'🌐', Apps:'📦' };
        el.innerHTML = recs.map(r => {
            const pc = priColors[r.priority] || 'var(--text-muted)';
            const ic = catIcons[r.category] || '📋';
            return `<div class="panel" style="padding:16px 20px;border-left:3px solid ${pc};">
                <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:12px;flex-wrap:wrap;">
                    <div style="flex:1;min-width:200px;">
                        <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;flex-wrap:wrap;">
                            <span style="font-size:16px;">${ic}</span>
                            <span style="font-size:14px;font-weight:700;">${r.title}</span>
                            <span style="font-family:'JetBrains Mono',monospace;font-size:9px;padding:2px 8px;border:1px solid ${pc};color:${pc};border-radius:4px;text-transform:uppercase;">${r.priority}</span>
                            <span style="font-family:'JetBrains Mono',monospace;font-size:9px;padding:2px 8px;background:rgba(255,255,255,0.05);border-radius:4px;color:var(--text-muted);">${r.category}</span>
                        </div>
                        <div style="font-size:12px;color:var(--text-secondary);line-height:1.6;margin-bottom:8px;">${r.explanation}</div>
                        <div style="font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--text-muted);">Evidence: ${r.evidence}</div>
                    </div>
                    <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:flex-start;">
                        ${r.actionable && r.action ? `<button class="btn btn-primary" style="font-size:11px;padding:5px 12px;" onclick="App.navigateToModule('${r.module}')">${r.action}</button>` : ''}
                        <button class="btn btn-outline" style="font-size:11px;padding:5px 10px;" onclick="App.snoozeRec('${r.id}',24)" title="Snooze 24h">💤</button>
                        <button class="btn btn-outline" style="font-size:11px;padding:5px 10px;" onclick="App.dismissRec('${r.id}')" title="Dismiss">✕</button>
                    </div>
                </div>
            </div>`;
        }).join('');
    },

    async _renderRecHistory() {
        const el = document.getElementById('rec-history-list');
        if (!el) return;
        try {
            const res = await fetch('/api/recommendations/history');
            const data = await res.json();
            const history = data.history || [];
            if (!history.length) { el.innerHTML = '<div style="text-align:center;padding:20px;">No history yet</div>'; return; }
            el.innerHTML = history.slice(0, 20).map(h =>
                `<div style="padding:4px 0;border-bottom:1px solid rgba(255,255,255,0.05);">[${(h.timestamp||'').slice(0,16).replace('T',' ')}] ${h.action.replace('_',' ')} — <span style="color:var(--accent-cyan);">${h.id}</span></div>`
            ).join('');
        } catch(e) {}
    },

    async dismissRec(id) {
        await fetch('/api/recommendations/dismiss', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({id}) });
        this.showNotification('Recommendation dismissed', 'success');
        this.refreshRecs();
    },

    async snoozeRec(id, hours) {
        await fetch('/api/recommendations/snooze', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({id, hours}) });
        this.showNotification(`Snoozed for ${hours}h`, 'success');
        this.refreshRecs();
    },

    async resetDismissedRecs() {
        if (!confirm('Reset all dismissed recommendations? They will reappear.')) return;
        await fetch('/api/recommendations/reset-dismissed', { method:'POST' });
        this.showNotification('Dismissed recommendations reset', 'success');
        this.refreshRecs();
    },

    exportRecs() { window.location.href = '/api/recommendations/export'; },

    navigateToModule(module) { this.showPage(module); },

    // ═══════════════════════════════════════════════════════════════════════
    // FEATURE 14: PROFILES / PRESETS
    // ═══════════════════════════════════════════════════════════════════════
    _profilesData: { profiles: [], active: null },

    async refreshProfiles() {
        try {
            const res = await fetch('/api/profiles');
            const data = await res.json();
            this._profilesData = data;
            this._renderActiveProfileBar(data.active, data.profiles);
            this._renderProfilesGrid(data.profiles, data.active);
            this._renderProfileHistory(data.history || []);
        } catch(e) {}
    },

    _renderActiveProfileBar(activeId, profiles) {
        const el = document.getElementById('active-profile-bar');
        if (!el) return;
        if (!activeId) { el.innerHTML = '<div style="font-size:13px;color:var(--text-muted);">No profile active — click Apply on any profile below.</div>'; return; }
        const prof = profiles.find(p => p.id === activeId);
        if (!prof) return;
        el.innerHTML = `<div style="display:flex;align-items:center;gap:12px;background:rgba(16,185,129,0.08);border:1px solid rgba(16,185,129,0.25);border-radius:8px;padding:10px 16px;">
            <span style="font-size:22px;">${prof.icon}</span>
            <div>
                <div style="font-size:13px;font-weight:700;color:var(--accent-green);">Active: ${prof.name}</div>
                <div style="font-size:11px;color:var(--text-muted);">${prof.description}</div>
            </div>
            <span style="margin-left:auto;font-family:'JetBrains Mono',monospace;font-size:10px;padding:3px 10px;border:1px solid rgba(16,185,129,0.4);border-radius:6px;color:var(--accent-green);">ACTIVE</span>
        </div>`;
    },

    _renderProfilesGrid(profiles, activeId) {
        const builtinEl = document.getElementById('profiles-builtin-grid');
        const customEl = document.getElementById('profiles-custom-grid');
        if (!builtinEl || !customEl) return;
        const builtin = profiles.filter(p => p.builtin);
        const custom = profiles.filter(p => !p.builtin);
        const accents = { performance:'var(--accent-cyan)', work:'var(--accent-blue)', night_comfort:'var(--accent-purple)', battery_saver:'var(--accent-green)' };
        const renderCard = (p, allowDelete) => {
            const isActive = p.id === activeId;
            const accent = accents[p.id] || 'var(--accent-cyan)';
            return `<div style="background:var(--bg-card);border:1px solid ${isActive ? accent : 'var(--border)'};border-radius:12px;padding:20px;position:relative;overflow:hidden;transition:border-color 0.2s;">
                <div style="position:absolute;top:0;left:0;right:0;height:3px;background:${accent};"></div>
                <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;">
                    <span style="font-size:28px;">${p.icon}</span>
                    <div>
                        <div style="font-size:14px;font-weight:700;">${p.name}</div>
                        <div style="font-family:'JetBrains Mono',monospace;font-size:9px;color:${p.builtin ? 'var(--text-muted)' : accent};text-transform:uppercase;">${p.builtin ? 'Built-in' : 'Custom'}</div>
                    </div>
                    ${isActive ? `<span style="margin-left:auto;font-family:'JetBrains Mono',monospace;font-size:9px;padding:2px 8px;background:${accent};color:#000;border-radius:4px;">ACTIVE</span>` : ''}
                </div>
                <div style="font-size:12px;color:var(--text-secondary);line-height:1.6;margin-bottom:14px;">${p.description}</div>
                <div style="display:flex;gap:6px;flex-wrap:wrap;">
                    <button class="btn ${isActive ? 'btn-outline' : 'btn-primary'}" style="font-size:11px;padding:5px 14px;flex:1;" onclick="App.applyProfile('${p.id}')">${isActive ? '✓ Active' : '▶ Apply'}</button>
                    ${allowDelete ? `<button class="btn btn-outline" style="font-size:11px;padding:5px 10px;color:var(--accent-red);" onclick="App.deleteProfile('${p.id}')">✕</button>` : ''}
                </div>
            </div>`;
        };
        builtinEl.innerHTML = builtin.map(p => renderCard(p, false)).join('');
        if (!custom.length) {
            customEl.innerHTML = '<div style="color:var(--text-muted);font-size:13px;padding:20px;">No custom profiles yet. Click "+ New Profile" to create one.</div>';
        } else {
            customEl.innerHTML = custom.map(p => renderCard(p, true)).join('');
        }
    },

    _renderProfileHistory(history) {
        const el = document.getElementById('profile-history-list');
        if (!el) return;
        if (!history.length) { el.innerHTML = '<div style="text-align:center;padding:16px;color:var(--text-muted);">No profile changes recorded yet</div>'; return; }
        el.innerHTML = history.map(h =>
            `<div style="font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--text-muted);padding:3px 0;border-bottom:1px solid rgba(255,255,255,0.04);">[${(h.applied_at||'').slice(0,16).replace('T',' ')}] Applied: <span style="color:var(--accent-cyan);">${h.profile_name}</span></div>`
        ).join('');
    },

    async applyProfile(id) {
        try {
            const res = await fetch('/api/profiles/apply', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({id}) });
            const data = await res.json();
            if (data.status === 'ok') {
                this.showNotification(`Profile applied: ${data.profile.name}`, 'success');
                this.refreshProfiles();
            }
        } catch(e) { this.showNotification('Failed to apply profile', 'error'); }
    },

    async deleteProfile(id) {
        if (!confirm('Delete this custom profile?')) return;
        await fetch('/api/profiles/delete', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({id}) });
        this.showNotification('Profile deleted', 'success');
        this.refreshProfiles();
    },

    async restorePreviousProfile() {
        try {
            const res = await fetch('/api/profiles/restore-previous', { method:'POST' });
            const data = await res.json();
            if (data.status === 'ok') { this.showNotification(`Restored: ${data.profile.name}`, 'success'); this.refreshProfiles(); }
            else this.showNotification(data.message || 'No previous profile', 'info');
        } catch(e) {}
    },

    showNewProfileDialog() {
        const d = document.getElementById('profile-dialog');
        if (d) d.style.display = 'flex';
    },

    closeProfileDialog() {
        const d = document.getElementById('profile-dialog');
        if (d) d.style.display = 'none';
    },

    async saveNewProfile() {
        const name = document.getElementById('new-profile-name')?.value?.trim();
        if (!name) { this.showNotification('Profile name required', 'error'); return; }
        const settings = {
            refresh_interval_sec: parseInt(document.getElementById('new-profile-refresh')?.value || '5'),
            wellness_reminders: document.getElementById('new-profile-wellness')?.checked || false,
            low_resource_mode: document.getElementById('new-profile-lowres')?.checked || false,
        };
        try {
            await fetch('/api/profiles/save', { method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({ name, description: document.getElementById('new-profile-desc')?.value || '',
                    icon: document.getElementById('new-profile-icon')?.value || '⚙️', settings }) });
            this.showNotification(`Profile "${name}" saved`, 'success');
            this.closeProfileDialog();
            this.refreshProfiles();
        } catch(e) { this.showNotification('Failed to save profile', 'error'); }
    },

    // ═══════════════════════════════════════════════════════════════════════
    // FEATURE 15: SCHEDULED MAINTENANCE
    // ═══════════════════════════════════════════════════════════════════════
    _maintenanceTasks: [],

    async refreshMaintenance() {
        try {
            const res = await fetch('/api/maintenance/tasks');
            const data = await res.json();
            this._maintenanceTasks = data.tasks || [];
            this._renderMaintenanceTasks(this._maintenanceTasks);
        } catch(e) {}
    },

    async refreshMaintenanceHistory() {
        try {
            const res = await fetch('/api/maintenance/history');
            const data = await res.json();
            this._renderMaintenanceHistory(data.history || []);
        } catch(e) {}
    },

    _renderMaintenanceTasks(tasks) {
        const el = document.getElementById('maintenance-task-list');
        if (!el) return;
        if (!tasks.length) { el.innerHTML = '<div style="text-align:center;color:var(--text-muted);padding:30px;">No tasks configured</div>'; return; }
        const typeColors = { scan:'var(--accent-cyan)', reminder:'var(--accent-yellow)' };
        const scheduleLabel = t => {
            if (t.schedule === 'daily') return `Daily at ${t.time}`;
            if (t.schedule === 'weekly') return `Weekly (${t.day_of_week?.toUpperCase()}) at ${t.time}`;
            if (t.schedule === 'monthly') return `Monthly (day ${t.day_of_month||'?'}) at ${t.time}`;
            return t.schedule;
        };
        el.innerHTML = tasks.map((t, i) => {
            const tc = typeColors[t.type] || 'var(--text-muted)';
            return `<div style="display:flex;align-items:center;gap:12px;padding:12px 0;${i < tasks.length-1 ? 'border-bottom:1px solid rgba(255,255,255,0.05)' : ''};flex-wrap:wrap;">
                <label class="toggle" title="${t.enabled ? 'Enabled' : 'Disabled'}">
                    <input type="checkbox" ${t.enabled ? 'checked' : ''} onchange="App.toggleMaintenanceTask('${t.id}', this.checked)">
                    <span class="toggle-slider"></span>
                </label>
                <div style="flex:1;min-width:180px;">
                    <div style="font-size:13px;font-weight:600;margin-bottom:2px;">${t.name}</div>
                    <div style="font-size:11px;color:var(--text-secondary);">${t.description}</div>
                    <div style="display:flex;align-items:center;gap:8px;margin-top:4px;flex-wrap:wrap;">
                        <span style="font-family:'JetBrains Mono',monospace;font-size:9px;padding:2px 8px;border:1px solid ${tc};color:${tc};border-radius:4px;text-transform:uppercase;">${t.type}</span>
                        <span style="font-size:11px;color:var(--text-muted);">${scheduleLabel(t)}</span>
                        ${t.last_run ? `<span style="font-size:10px;color:var(--text-muted);">Last run: ${t.last_run.slice(0,10)}</span>` : ''}
                        ${t.run_count ? `<span style="font-size:10px;color:var(--text-muted);">(${t.run_count} runs)</span>` : ''}
                    </div>
                </div>
                <div style="display:flex;gap:6px;flex-shrink:0;">
                    <button class="btn btn-primary" style="font-size:11px;padding:4px 12px;" onclick="App.runMaintenanceTask('${t.id}', '${t.name}')">▶ Run Now</button>
                    ${!t.builtin ? `<button class="btn btn-outline" style="font-size:11px;padding:4px 8px;color:var(--accent-red);" onclick="App.deleteMaintenanceTask('${t.id}')">✕</button>` : ''}
                </div>
            </div>`;
        }).join('');
    },

    _renderMaintenanceHistory(history) {
        const el = document.getElementById('maintenance-history-list');
        if (!el) return;
        if (!history.length) { el.innerHTML = '<div style="text-align:center;color:var(--text-muted);padding:20px;font-size:12px;">No history yet — run a task to start logging.</div>'; return; }
        const statusColors = { ok:'var(--accent-green)', error:'var(--accent-red)' };
        el.innerHTML = history.map(h => {
            const sc = statusColors[h.status] || 'var(--text-muted)';
            const findings = h.findings ? Object.entries(h.findings).map(([k,v]) => `${k}: ${v}`).join(' • ') : '';
            return `<div style="background:rgba(255,255,255,0.02);border-radius:6px;padding:10px 12px;">
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;flex-wrap:wrap;">
                    <span style="font-size:12px;font-weight:600;">${h.task_name || h.task_id}</span>
                    <span style="font-family:'JetBrains Mono',monospace;font-size:9px;padding:1px 7px;border:1px solid ${sc};color:${sc};border-radius:4px;text-transform:uppercase;">${h.status}</span>
                    <span style="font-size:10px;color:var(--text-muted);margin-left:auto;">${(h.completed_at||'').slice(0,16).replace('T',' ')}</span>
                </div>
                ${findings ? `<div style="font-size:11px;color:var(--text-secondary);font-family:'JetBrains Mono',monospace;">${findings}</div>` : ''}
            </div>`;
        }).join('');
    },

    async toggleMaintenanceTask(id, enabled) {
        await fetch('/api/maintenance/tasks/toggle', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({id, enabled}) });
        this.showNotification(`Task ${enabled ? 'enabled' : 'disabled'}`, 'success');
    },

    async runMaintenanceTask(id, name) {
        this.showNotification(`Running: ${name}...`, 'info');
        try {
            const res = await fetch('/api/maintenance/tasks/run', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({id}) });
            const data = await res.json();
            if (data.status === 'ok') {
                const findings = data.findings ? Object.entries(data.findings).map(([k,v]) => `${k}: ${v}`).join(', ') : '';
                this.showNotification(`✓ ${name} complete. ${findings}`, 'success');
            } else { this.showNotification(`Error: ${data.error || 'Task failed'}`, 'error'); }
            this.refreshMaintenance();
            this.refreshMaintenanceHistory();
        } catch(e) { this.showNotification('Failed to run task', 'error'); }
    },

    async deleteMaintenanceTask(id) {
        if (!confirm('Delete this custom task?')) return;
        await fetch('/api/maintenance/tasks/delete', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({id}) });
        this.showNotification('Task deleted', 'success');
        this.refreshMaintenance();
    },

    showNewTaskDialog() {
        const d = document.getElementById('task-dialog');
        if (d) d.style.display = 'flex';
    },

    closeTaskDialog() {
        const d = document.getElementById('task-dialog');
        if (d) d.style.display = 'none';
    },

    async saveNewTask() {
        const name = document.getElementById('new-task-name')?.value?.trim();
        if (!name) { this.showNotification('Task name required', 'error'); return; }
        try {
            await fetch('/api/maintenance/tasks/save', { method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify({ name,
                    description: document.getElementById('new-task-desc')?.value || '',
                    type: document.getElementById('new-task-type')?.value || 'reminder',
                    schedule: document.getElementById('new-task-schedule')?.value || 'weekly',
                    day_of_week: document.getElementById('new-task-day')?.value || 'mon',
                    time: document.getElementById('new-task-time')?.value || '09:00',
                    enabled: true }) });
            this.showNotification(`Task "${name}" saved`, 'success');
            this.closeTaskDialog();
            this.refreshMaintenance();
        } catch(e) { this.showNotification('Failed to save task', 'error'); }
    },

    exportMaintenanceHistory() { window.location.href = '/api/maintenance/history/export'; },

    _debugLogs: [],
    _debugAutoRefreshInterval: null,

    async refreshDebugLogs() {
        const level = document.getElementById('debug-log-level')?.value || 'ALL';
        try {
            const res = await fetch(`/api/debug-logs?level=${level}`);
            const data = await res.json();
            this._debugLogs = data.logs || [];
            this._renderDebugLogs(this._debugLogs);
            this._renderDebugSummary(data.counts || {});
        } catch(e) {
            const t = document.getElementById('debug-log-terminal');
            if (t) t.innerHTML = '<span style="color:var(--accent-red);">Failed to load logs.</span>';
        }
    },

    _renderDebugLogs(logs) {
        const terminal = document.getElementById('debug-log-terminal');
        const countEl = document.getElementById('debug-log-count');
        if (!terminal) return;
        if (!logs || logs.length === 0) {
            terminal.innerHTML = '<span style="color:var(--text-muted);">No log entries found.</span>';
            if (countEl) countEl.textContent = '0 entries';
            return;
        }
        const colorMap = {
            SUCCESS: '#22c55e',
            INFO:    '#06b6d4',
            WARN:    '#f59e0b',
            ERROR:   '#ef4444',
        };
        terminal.innerHTML = logs.map(e => {
            const col = colorMap[e.level] || '#94a3b8';
            const lvl = (e.level || 'INFO').padEnd(7);
            return `<span style="color:#475569;">${e.time || '--:--:--'}</span>  <span style="color:${col};font-weight:600;">${lvl}</span>  <span style="color:#e2e8f0;">${this._escHtml(e.message || '')}</span>`;
        }).join('\n');
        if (countEl) countEl.textContent = `${logs.length} entries`;
        const badge = document.getElementById('debug-error-badge');
        if (badge) {
            const errCount = logs.filter(e => e.level === 'ERROR').length;
            if (errCount > 0) { badge.textContent = errCount; badge.style.display = 'inline-block'; }
            else { badge.style.display = 'none'; }
        }
    },

    _renderDebugSummary(counts) {
        const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val ?? '0'; };
        set('debug-count-success', counts.SUCCESS);
        set('debug-count-info',    counts.INFO);
        set('debug-count-warn',    counts.WARN);
        set('debug-count-error',   counts.ERROR);
    },

    filterDebugLogs() { this.refreshDebugLogs(); },

    async clearDebugLogs() {
        if (!confirm('Clear all debug logs? This cannot be undone.')) return;
        await fetch('/api/debug-logs/clear', { method: 'POST' });
        this.showNotification('Debug logs cleared', 'success');
        this.refreshDebugLogs();
    },

    toggleDebugAutoRefresh(enabled) {
        if (this._debugAutoRefreshInterval) {
            clearInterval(this._debugAutoRefreshInterval);
            this._debugAutoRefreshInterval = null;
        }
        if (enabled) {
            this._debugAutoRefreshInterval = setInterval(() => this.refreshDebugLogs(), 3000);
        }
    },

    _escHtml(str) {
        return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    },
};

document.addEventListener('DOMContentLoaded', () => App.init());
