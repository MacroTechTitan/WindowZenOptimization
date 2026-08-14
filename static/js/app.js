function escapeHtml(str) {
    return String(str ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#x27;');
}

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
        if (pageName === 'deepclean' && !this._deepcleanReport) this.deepcleanLoadTargets();
        if (pageName === 'largefiles' && !this._largefilesReport) this.largefilesLoadRoots();
        if (pageName === 'duplicates' && !this._duplicatesReport) this.duplicatesLoadRoots();
        if (pageName === 'internet' && !this._netDiag) this.netDiagnose();
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

            if (localVerEl) localVerEl.textContent = `v${data.current}`;

            let out = `Update Check Results\n${'='.repeat(40)}\n`;
            out += `Installed : v${data.current}\n`;
            out += `Latest    : v${data.latest}\n`;
            if (data.error) out += `\nNote: ${data.error}\n`;

            if (data.update_available) {
                out += `\n✅ UPDATE AVAILABLE — v${data.latest}\n\nDownload the new installer from the release page and run it to upgrade.\n`;
                if (statusEl) { statusEl.textContent = `Update available: v${data.latest}`; statusEl.style.color = 'var(--accent-green)'; }
                if (dlBtn) {
                    dlBtn.style.display = 'inline-flex';
                    dlBtn.textContent = '⬇ Download';
                }
                this._pendingUpdateUrl = data.url || '';
            } else {
                out += data.error ? `\n⚠ Could not confirm the latest version.\n` : `\n✅ You are up to date.\n`;
                if (statusEl) { statusEl.textContent = data.error ? 'Check failed' : 'Up to date'; statusEl.style.color = data.error ? 'var(--accent-red)' : 'var(--accent-green)'; }
                if (dlBtn) dlBtn.style.display = 'none';
            }

            if (outputEl) outputEl.textContent = out;
        } catch(e) {
            if (outputEl) outputEl.textContent = 'Error: Could not reach the update server. Check your internet connection.';
            if (statusEl) { statusEl.textContent = 'Check failed'; statusEl.style.color = 'var(--accent-red)'; }
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = '🔍 Check for Updates'; }
        }
    },

    downloadUpdate() {
        // The app never modifies itself — just open the GitHub release page so the
        // user can download and run the signed installer.
        if (!this._pendingUpdateUrl) {
            this.showNotification('No release page available. Check for updates first.', 'error');
            return;
        }
        window.open(this._pendingUpdateUrl, '_blank', 'noopener');
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
            if (data && data.ok === false) {
                const errHtml = `<div class="info-row"><span class="info-label" style="color:var(--accent-red);">${data.error || 'Could not read startup items.'}</span></div>`;
                ['startup-items-list', 'speedup-startup-list'].forEach(id => {
                    const c = document.getElementById(id);
                    if (c) c.innerHTML = errHtml;
                });
                return;
            }
            const items = Array.isArray(data) ? data : (data.items || []);

            const makeRow = (item, enhanced) => {
                const impact = item.impact || (item.hive === 'HKLM' ? 'Medium' : 'Low');
                const impactColor = impact === 'High' ? 'var(--accent-red)' : impact === 'Medium' ? 'var(--accent-yellow)' : 'var(--accent-green)';
                const cat = item.category || 'review';
                const catLabel = { safe_to_disable:'✔ Safe', review:'Review', system_related:'⚠ Caution' }[cat] || cat;
                const catColor = { safe_to_disable:'var(--accent-green)', review:'var(--accent-yellow)', system_related:'var(--accent-red)' }[cat] || 'var(--text-muted)';
                const rec = (item.recommendation || '').replace(/'/g, '&#39;');
                const nameSafe = item.name.replace(/'/g, "\\'");
                const pathSafe = (item.path || '').replace(/'/g, "\\'");
                const hiveSafe = (item.hive || 'HKCU');
                if (enhanced) {
                    return `<div class="process-item startup-enhanced" title="${rec}">
                        <span class="name">${item.name}</span>
                        <span class="cpu" style="font-size:10px;color:var(--text-muted);">${hiveSafe}</span>
                        <span class="mem" style="font-size:10px;">
                            <span style="color:${impactColor};font-weight:600;">${impact}</span>
                            <span style="color:${catColor};font-size:9px;padding:1px 5px;border:1px solid ${catColor};border-radius:3px;">${catLabel}</span>
                        </span>
                        <label class="toggle">
                            <input type="checkbox" ${item.enabled ? 'checked' : ''}
                                onchange="App.toggleStartupItem('${nameSafe}', '${hiveSafe}', this.checked, '${pathSafe}')">
                            <span class="toggle-slider"></span>
                        </label>
                    </div>`;
                }
                return `<div class="process-item">
                    <span class="name">${item.name}</span>
                    <span class="cpu" style="font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${item.path || 'N/A'}</span>
                    <label class="toggle">
                        <input type="checkbox" ${item.enabled ? 'checked' : ''}
                            onchange="App.toggleStartupItem('${nameSafe}', '${hiveSafe}', this.checked, '${pathSafe}')">
                        <span class="toggle-slider"></span>
                    </label>
                </div>`;
            };

            const simpleContainer = document.getElementById('startup-items-list');
            if (simpleContainer) {
                if (items.length === 0) {
                    simpleContainer.innerHTML = '<div class="info-row"><span class="info-label">No startup items found</span></div>';
                } else {
                    simpleContainer.innerHTML = items.map(item => makeRow(item, false)).join('');
                }
            }

            const speedupContainer = document.getElementById('speedup-startup-list');
            if (speedupContainer) {
                if (items.length === 0) {
                    speedupContainer.innerHTML = '<div class="info-row"><span class="info-label">No startup items found</span></div>';
                } else {
                    const sourceLabels = {
                        'HKCU': '🔵 HKCU — Current User (HKEY_CURRENT_USER\\...\\Run)',
                        'HKLM': '🔴 HKLM — All Users (HKEY_LOCAL_MACHINE\\...\\Run)',
                        'Startup': '📁 Startup Folder — Shell:Startup',
                    };
                    const groups = {};
                    items.forEach(item => {
                        const key = item.hive || 'HKCU';
                        if (!groups[key]) groups[key] = [];
                        groups[key].push(item);
                    });
                    const order = ['HKLM', 'HKCU', 'Startup'];
                    let html = '';
                    order.forEach(key => {
                        if (!groups[key] || groups[key].length === 0) return;
                        const label = sourceLabels[key] || key;
                        html += `<div style="padding:6px 0 4px; margin-top:8px; font-family:'JetBrains Mono',monospace; font-size:10px; color:var(--accent-cyan); letter-spacing:1px; border-bottom:1px solid var(--border);">${label}</div>`;
                        html += groups[key].map(item => makeRow(item, true)).join('');
                    });
                    Object.keys(groups).forEach(key => {
                        if (!order.includes(key)) {
                            html += `<div style="padding:6px 0 4px; margin-top:8px; font-family:'JetBrains Mono',monospace; font-size:10px; color:var(--accent-cyan); letter-spacing:1px; border-bottom:1px solid var(--border);">${key}</div>`;
                            html += groups[key].map(item => makeRow(item, true)).join('');
                        }
                    });
                    speedupContainer.innerHTML = html;
                }
            }
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

    async scanFiles(customFolder) {
        const btn = document.getElementById('btn-scan-files');
        if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Scanning...'; }
        try {
            await fetch('/api/file-organizer/scan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ custom_folder: customFolder || '' }),
            });
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

    async scanDuplicatesCustomFolder() {
        const folderInput = document.getElementById('dup-folder-path');
        const folderPath = folderInput ? folderInput.value.trim() : '';
        if (!folderPath) {
            this.showNotification('Enter a folder path to scan, or use Scan Files for defaults', 'info');
            return;
        }
        const listEl = document.getElementById('duplicates-list');
        if (listEl) listEl.innerHTML = '<div style="text-align:center;padding:16px;color:var(--accent-cyan);font-family:\'JetBrains Mono\',monospace;font-size:12px;">Scanning for duplicates...</div>';
        const panel = document.getElementById('duplicates-panel');
        if (panel) panel.hidden = false;
        try {
            await fetch('/api/file-organizer/scan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ custom_folder: folderPath }),
            });
            const poll = setInterval(async () => {
                try {
                    const res = await fetch('/api/file-organizer/results');
                    const data = await res.json();
                    if (data.status === 'complete') {
                        clearInterval(poll);
                        const dups = data.duplicates || [];
                        if (listEl) {
                            if (dups.length === 0) {
                                listEl.innerHTML = '<div style="text-align:center;color:var(--accent-green);padding:16px;font-family:\'JetBrains Mono\',monospace;font-size:12px;">No duplicate files found in this folder.</div>';
                            } else {
                                listEl.innerHTML = dups.map(f => `<div class="process-item" style="font-size:11px;">
                                    <input type="checkbox" class="file-check-duplicates" data-path="${f.path||''}" style="margin-right:8px;">
                                    <span class="name" style="flex:1;">${f.name}</span>
                                    <span class="mem" style="color:var(--text-muted);font-size:10px;">${f.size_fmt||''}</span>
                                </div>`).join('');
                            }
                        }
                        this.showNotification(`Found ${dups.length} duplicate file(s) in ${folderPath}`, dups.length ? 'warn' : 'success');
                    }
                } catch(e) {}
            }, 1500);
        } catch(e) { this.showNotification('Scan failed', 'error'); }
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
        const results = data.results || data;

        const summaryEl = document.getElementById('file-organizer-results');
        const zeroFiles = results.zero_length || results.zero_length_files || [];
        const dupFiles  = results.duplicates || [];
        const instFiles = results.installers || [];
        const lastScan  = results.last_scan || '';
        const total = zeroFiles.length + dupFiles.length + instFiles.length;

        if (summaryEl) {
            summaryEl.innerHTML = `<div style="font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--text-secondary);line-height:1.8;">
                <div style="display:flex;gap:20px;flex-wrap:wrap;">
                    <span>&#x1F4C4; Zero-length: <strong style="color:var(--accent-cyan);">${zeroFiles.length}</strong></span>
                    <span>&#x1F4CB; Duplicates: <strong style="color:${dupFiles.length>0?'var(--accent-yellow)':'var(--accent-cyan)'};">${dupFiles.length}</strong></span>
                    <span>&#x1F4E6; Installers: <strong style="color:var(--accent-cyan);">${instFiles.length}</strong></span>
                </div>
                ${lastScan ? `<div style="font-size:10px;color:var(--text-muted);margin-top:4px;">Last scan: ${lastScan}</div>` : ''}
                ${total === 0 ? '<div style="color:var(--accent-green);margin-top:8px;">&#x2705; No issues found — your files are clean!</div>' : ''}
            </div>`;
        }

        const renderPanel = (panelId, listId, cbClass, files, emptyMsg) => {
            const panel = document.getElementById(panelId);
            const listEl = document.getElementById(listId);
            if (!panel || !listEl) return;
            if (files.length > 0) {
                panel.hidden = false;
                listEl.innerHTML = files.map(f => `
                    <div class="process-item" style="font-size:11px;">
                        <input type="checkbox" class="${cbClass}" data-path="${f.path||f.name||''}" style="margin-right:8px;">
                        <span class="name" style="flex:1;" title="${f.path||''}">${f.name||f.path||'Unknown'}</span>
                        <span class="mem" style="color:var(--text-muted);">${this.formatBytes(f.size||0)}</span>
                        ${f.duplicate_of ? `<span style="font-size:9px;color:var(--accent-yellow);margin-left:8px;">dup of: ${f.duplicate_of.split(/[\\/]/).pop()}</span>` : ''}
                    </div>`).join('');
            } else {
                panel.hidden = true;
            }
        };
        renderPanel('zero-length-panel', 'zero-length-list', 'file-check-zero_length', zeroFiles, 'No zero-length files found');
        renderPanel('duplicates-panel', 'duplicates-list', 'file-check-duplicates', dupFiles, 'No duplicate files found');
        renderPanel('installers-panel', 'installers-list', 'file-check-installers', instFiles, 'No installer files found');
    },

    _cbClass(category) {
        const map = { 'zero-length': 'zero_length', 'zero_length_files': 'zero_length' };
        return `file-check-${map[category] || category}`;
    },

    toggleSelectAll(category) {
        const cls = this._cbClass(category);
        const checkboxes = document.querySelectorAll(`.${cls}`);
        const allChecked = Array.from(checkboxes).every(cb => cb.checked);
        checkboxes.forEach(cb => cb.checked = !allChecked);
    },

    async deleteSelected(category) {
        const cls = this._cbClass(category);
        const checkboxes = document.querySelectorAll(`.${cls}:checked`);
        const paths = Array.from(checkboxes).map(cb => cb.dataset.path).filter(p => p);
        if (paths.length === 0) {
            this.showNotification('No files selected', 'error');
            return;
        }
        if (!confirm(`Delete ${paths.length} file(s)? This cannot be undone.`)) return;
        try {
            await fetch('/api/file-organizer/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ files: paths, category })
            });
            this.showNotification(`${paths.length} file(s) deleted`);
            this.refreshFileOrganizer();
        } catch(e) {
            this.showNotification('Failed to delete files', 'error');
        }
    },

    async deleteAllInCategory(category) {
        const cls = this._cbClass(category);
        const checkboxes = document.querySelectorAll(`.${cls}`);
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

    selectNightLightPreset(preset) {
        const presets = {
            sunset: {
                label: '🌇 Sunset to Sunrise',
                info: 'In Night Light settings → Schedule: select "Sunset to sunrise". Windows will automatically turn on Night Light at sunset and off at sunrise based on your location.',
            },
            evening: {
                label: '🌙 Evening (9PM – 7AM)',
                info: 'In Night Light settings → Schedule: select "Set hours" → Turn on at 9:00 PM, Turn off at 7:00 AM. Adjust Color temperature slider to your preference (warmer = more blue-light reduction).',
            },
            always: {
                label: '🔴 Always On',
                info: 'To keep Night Light always on: toggle "Night light" to ON and do not enable a schedule. The setting stays active indefinitely until you manually toggle it off.',
            },
        };
        const chosen = presets[preset];
        if (!chosen) return;
        ['sunset','evening','always'].forEach(p => {
            const btn = document.getElementById(`nl-preset-${p}`);
            if (btn) btn.style.borderColor = '';
        });
        const activeBtn = document.getElementById(`nl-preset-${preset}`);
        if (activeBtn) activeBtn.style.borderColor = 'var(--accent-cyan)';
        const infoEl = document.getElementById('nl-preset-info');
        if (infoEl) {
            infoEl.innerHTML = `<strong>${chosen.label}</strong><br>${chosen.info}`;
            infoEl.style.display = 'block';
        }
        this.showNotification(`Preset selected: ${chosen.label} — Click "Open Settings" to apply`, 'info');
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
            const data = await fetch('/api/apps/list').then(r => r.json());
            if (data && data.ok === false) {
                this._appsData = [];
                if (countEl) countEl.textContent = '';
                if (listEl) listEl.innerHTML = `<div style="text-align:center;color:var(--accent-red);padding:16px;font-family:'JetBrains Mono',monospace;font-size:12px;">${data.error || 'Failed to load app list.'}</div>`;
                return;
            }
            this._appsData = Array.isArray(data) ? data : (data.apps || []);
            this._appsDemo = !!(data && data.demo);
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

        if (countEl) countEl.textContent = `${apps.length} apps${this._appsDemo ? ' (demo data)' : ''}`;
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
                    ${hasUninstall ? `<button class="btn uninstall-btn" style="padding:2px 8px;font-size:10px;" data-app-name="${encodeURIComponent(a.name)}" data-uninstall-cmd="${encodeURIComponent(a.uninstall_cmd)}">Uninstall</button>` : '<span style="font-size:10px;color:var(--text-muted);">—</span>'}
                    ${hasFolder ? `<button class="btn open-folder-btn" style="padding:2px 8px;font-size:10px;" data-install-location="${encodeURIComponent(a.install_location)}">&#x1F4C2;</button>` : ''}
                </span>
            </div>`;
        }).join('');
        this._ensureAppRowDelegation();
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
                ${a.uninstall_cmd ? `<button class="btn uninstall-btn" style="padding:3px 10px;font-size:10px;border-color:var(--accent-red);color:var(--accent-red);" data-app-name="${encodeURIComponent(a.name)}" data-uninstall-cmd="${encodeURIComponent(a.uninstall_cmd)}">Uninstall</button>` : '<span style="font-size:10px;color:var(--text-muted);">No uninstaller</span>'}
            </div>`).join('');
        this._ensureAppRowDelegation();
    },

    // One document-level delegated handler for the app-row buttons, attached once.
    // Values ride in data attributes (encodeURIComponent) because UninstallString
    // and install paths routinely contain quotes and backslashes that break an
    // inline onclick.
    _ensureAppRowDelegation() {
        if (this._appRowDelegationAttached) return;
        this._appRowDelegationAttached = true;
        document.addEventListener('click', (e) => {
            const uninstallBtn = e.target.closest('.uninstall-btn');
            if (uninstallBtn) {
                const name = decodeURIComponent(uninstallBtn.dataset.appName || '');
                const cmd = decodeURIComponent(uninstallBtn.dataset.uninstallCmd || '');
                App.launchUninstall(name, cmd);
                return;
            }
            const folderBtn = e.target.closest('.open-folder-btn');
            if (folderBtn) {
                App.openAppFolder(decodeURIComponent(folderBtn.dataset.installLocation || ''));
            }
        });
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
                // Let the user complete the uninstaller wizard, then confirm removal.
                setTimeout(() => {
                    if (confirm(`When you've finished uninstalling "${name}", click OK to verify it was removed.`)) {
                        this.verifyUninstall(name);
                    }
                }, 1500);
            } else {
                this.showNotification(res.error || 'Failed to launch uninstaller', 'error');
            }
        } catch(e) {
            this.showNotification('Network error launching uninstaller', 'error');
        }
    },

    async verifyUninstall(name) {
        try {
            const res = await fetch('/api/apps/verify-uninstall', {
                method: 'POST', headers: {'Content-Type':'application/json'},
                body: JSON.stringify({name})
            }).then(r => r.json());
            if (!res.ok) {
                this.showNotification(res.error || 'Could not verify removal', 'error');
                return;
            }
            if (res.still_present) {
                this.showNotification(`"${name}" is still installed — the uninstall may not have completed.`, 'warn');
            } else {
                this.showNotification(`"${name}" was removed successfully.`, 'success');
                this.refreshApps();
            }
        } catch(e) {
            this.showNotification('Could not verify removal', 'error');
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
                    <span style="font-size:28px;">${escapeHtml(p.icon)}</span>
                    <div>
                        <div style="font-size:14px;font-weight:700;">${escapeHtml(p.name)}</div>
                        <div style="font-family:'JetBrains Mono',monospace;font-size:9px;color:${p.builtin ? 'var(--text-muted)' : accent};text-transform:uppercase;">${p.builtin ? 'Built-in' : 'Custom'}</div>
                    </div>
                    ${isActive ? `<span style="margin-left:auto;font-family:'JetBrains Mono',monospace;font-size:9px;padding:2px 8px;background:${accent};color:#000;border-radius:4px;">ACTIVE</span>` : ''}
                </div>
                <div style="font-size:12px;color:var(--text-secondary);line-height:1.6;margin-bottom:14px;">${escapeHtml(p.description)}</div>
                <div style="display:flex;gap:6px;flex-wrap:wrap;">
                    <button class="btn ${isActive ? 'btn-outline' : 'btn-primary'}" style="font-size:11px;padding:5px 14px;flex:1;" onclick="App.applyProfile('${escapeHtml(p.id)}')">${isActive ? '✓ Active' : '▶ Apply'}</button>
                    ${allowDelete ? `<button class="btn btn-outline" style="font-size:11px;padding:5px 10px;color:var(--accent-red);" onclick="App.deleteProfile('${escapeHtml(p.id)}')">✕</button>` : ''}
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
            `<div style="font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--text-muted);padding:3px 0;border-bottom:1px solid rgba(255,255,255,0.04);">[${escapeHtml((h.applied_at||'').slice(0,16).replace('T',' '))}] Applied: <span style="color:var(--accent-cyan);">${escapeHtml(h.profile_name)}</span></div>`
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
        const esc = s => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
        const typeColors = { scan:'var(--accent-cyan)', reminder:'var(--accent-yellow)' };
        const scheduleLabel = t => {
            if (t.schedule === 'daily') return `Daily at ${esc(t.time)}`;
            if (t.schedule === 'weekly') return `Weekly (${esc(t.day_of_week?.toUpperCase())}) at ${esc(t.time)}`;
            if (t.schedule === 'monthly') return `Monthly (day ${esc(t.day_of_month||'?')}) at ${esc(t.time)}`;
            return esc(t.schedule);
        };
        el.innerHTML = tasks.map((t, i) => {
            const tc = typeColors[t.type] || 'var(--text-muted)';
            return `<div style="display:flex;align-items:center;gap:12px;padding:12px 0;${i < tasks.length-1 ? 'border-bottom:1px solid rgba(255,255,255,0.05)' : ''};flex-wrap:wrap;">
                <label class="toggle" title="${t.enabled ? 'Enabled' : 'Disabled'}">
                    <input type="checkbox" ${t.enabled ? 'checked' : ''} onchange="App.toggleMaintenanceTask('${esc(t.id)}', this.checked)">
                    <span class="toggle-slider"></span>
                </label>
                <div style="flex:1;min-width:180px;">
                    <div style="font-size:13px;font-weight:600;margin-bottom:2px;">${esc(t.name)}</div>
                    <div style="font-size:11px;color:var(--text-secondary);">${esc(t.description)}</div>
                    <div style="display:flex;align-items:center;gap:8px;margin-top:4px;flex-wrap:wrap;">
                        <span style="font-family:'JetBrains Mono',monospace;font-size:9px;padding:2px 8px;border:1px solid ${tc};color:${tc};border-radius:4px;text-transform:uppercase;">${esc(t.type)}</span>
                        <span style="font-size:11px;color:var(--text-muted);">${scheduleLabel(t)}</span>
                        ${t.last_run ? `<span style="font-size:10px;color:var(--text-muted);">Last run: ${esc(t.last_run.slice(0,10))}</span>` : ''}
                        ${t.run_count ? `<span style="font-size:10px;color:var(--text-muted);">(${esc(t.run_count)} runs)</span>` : ''}
                    </div>
                </div>
                <div style="display:flex;gap:6px;flex-shrink:0;">
                    <button class="btn btn-primary" style="font-size:11px;padding:4px 12px;" onclick="App.runMaintenanceTask('${esc(t.id)}', '${esc(t.name)}')">▶ Run Now</button>
                    ${!t.builtin ? `<button class="btn btn-outline" style="font-size:11px;padding:4px 8px;color:var(--accent-red);" onclick="App.deleteMaintenanceTask('${esc(t.id)}')">✕</button>` : ''}
                </div>
            </div>`;
        }).join('');
    },

    _renderMaintenanceHistory(history) {
        const el = document.getElementById('maintenance-history-list');
        if (!el) return;
        if (!history.length) { el.innerHTML = '<div style="text-align:center;color:var(--text-muted);padding:20px;font-size:12px;">No history yet — run a task to start logging.</div>'; return; }
        const esc = s => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
        const statusColors = { ok:'var(--accent-green)', error:'var(--accent-red)' };
        el.innerHTML = history.map(h => {
            const sc = statusColors[h.status] || 'var(--text-muted)';
            const findings = h.findings ? Object.entries(h.findings).map(([k,v]) => `${esc(k)}: ${esc(v)}`).join(' • ') : '';
            return `<div style="background:rgba(255,255,255,0.02);border-radius:6px;padding:10px 12px;">
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;flex-wrap:wrap;">
                    <span style="font-size:12px;font-weight:600;">${esc(h.task_name || h.task_id)}</span>
                    <span style="font-family:'JetBrains Mono',monospace;font-size:9px;padding:1px 7px;border:1px solid ${sc};color:${sc};border-radius:4px;text-transform:uppercase;">${esc(h.status)}</span>
                    <span style="font-size:10px;color:var(--text-muted);margin-left:auto;">${esc((h.completed_at||'').slice(0,16).replace('T',' '))}</span>
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
        terminal.textContent = '';
        const fragment = document.createDocumentFragment();
        logs.forEach((e, i) => {
            const col = colorMap[e.level] || '#94a3b8';
            if (i > 0) fragment.appendChild(document.createTextNode('\n'));
            const timeSpan = document.createElement('span');
            timeSpan.style.color = '#475569';
            timeSpan.textContent = e.time || '--:--:--';
            const lvlSpan = document.createElement('span');
            lvlSpan.style.color = col;
            lvlSpan.style.fontWeight = '600';
            lvlSpan.textContent = (e.level || 'INFO').padEnd(7);
            const msgSpan = document.createElement('span');
            msgSpan.style.color = '#e2e8f0';
            msgSpan.textContent = e.message || '';
            fragment.appendChild(timeSpan);
            fragment.appendChild(document.createTextNode('  '));
            fragment.appendChild(lvlSpan);
            fragment.appendChild(document.createTextNode('  '));
            fragment.appendChild(msgSpan);
        });
        terminal.appendChild(fragment);
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

    // ══════════════════════════════════════════════════════════
    // DEEP CLEAN (Sprint 3, Feature 1) — two-step: scan then apply
    // ══════════════════════════════════════════════════════════
    _deepcleanReport: null,
    _deepcleanPoller: null,

    _fmtBytes(b) {
        b = Number(b) || 0;
        const units = ['B','KB','MB','GB','TB'];
        let i = 0;
        while (b >= 1024 && i < units.length - 1) { b /= 1024; i++; }
        return `${b.toFixed(1)} ${units[i]}`;
    },

    _riskChip(risk) {
        const map = {
            safe:    ['var(--accent-green)',  'rgba(16,185,129,0.12)',  'SAFE'],
            caution: ['var(--accent-yellow)', 'rgba(245,158,11,0.12)',  'CAUTION'],
            high:    ['var(--accent-red)',    'rgba(239,68,68,0.12)',   'HIGH RISK'],
        };
        const [color, bg, label] = map[risk] || map.safe;
        return `<span style="font-family:'JetBrains Mono',monospace;font-size:9px;padding:2px 7px;border-radius:4px;background:${bg};color:${color};white-space:nowrap;">${label}</span>`;
    },

    // ══════════════════════════════════════════════════════════
    // INTERNET OPTIMIZER (Sprint 3, Feature 5)
    // ══════════════════════════════════════════════════════════
    _netDiag: null,

    _netShowOutput(title, steps, extra) {
        const el = document.getElementById('net-output');
        el.style.display = 'block';
        el.innerHTML = `
            <div class="terminal-window">
                <div class="terminal-header">
                    <div class="terminal-dots"><div class="terminal-dot red"></div><div class="terminal-dot yellow"></div><div class="terminal-dot green"></div></div>
                    <div class="terminal-title">${escapeHtml(title)}</div>
                </div>
                <div class="terminal-body" style="max-height:320px;overflow:auto;">
                    ${(steps || []).map(s => `
                        <div style="margin-bottom:10px;">
                            <div style="color:var(--accent-cyan);">&gt; ${escapeHtml(s.command)}</div>
                            <pre style="margin:4px 0 0;white-space:pre-wrap;color:${s.exit_code === 0 ? 'var(--text-secondary)' : 'var(--accent-yellow)'};font-size:11px;">${escapeHtml(s.output || '(no output)')}</pre>
                        </div>`).join('')}
                    ${extra ? `<div style="color:var(--accent-yellow);margin-top:8px;">${escapeHtml(extra)}</div>` : ''}
                </div>
            </div>`;
    },

    async netDiagnose() {
        const el = document.getElementById('net-diagnose');
        el.innerHTML = `<div style="color:var(--text-muted);font-family:'JetBrains Mono',monospace;font-size:12px;padding:12px;">Collecting diagnostics…</div>`;
        try {
            const d = await (await fetch('/api/network/diagnose')).json();
            this._netDiag = d;

            const dnsSel = document.getElementById('net-dns-adapter');
            const mtuSel = document.getElementById('net-mtu-adapter');
            if (dnsSel) dnsSel.innerHTML = (d.adapters || []).map(a => `<option value="${escapeHtml(a.name)}">${escapeHtml(a.name)}</option>`).join('');
            if (mtuSel) mtuSel.innerHTML = (d.mtu || []).map(m => `<option value="${escapeHtml(m.adapter)}">${escapeHtml(m.adapter)} (now ${m.mtu})</option>`).join('');
            const note = document.getElementById('net-advanced-note');
            if (note) note.textContent = d.advanced_note || '';

            el.innerHTML = `
                <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px;">
                    <div style="padding:12px;background:var(--bg-tertiary);border-radius:8px;">
                        <div style="font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-muted);margin-bottom:8px;">ADAPTERS</div>
                        ${(d.adapters || []).map(a => `<div style="font-size:11px;font-family:'JetBrains Mono',monospace;color:var(--text-secondary);">${escapeHtml(a.name)} — <span style="color:${a.state === 'Connected' ? 'var(--accent-green)' : 'var(--text-muted)'}">${escapeHtml(a.state)}</span></div>`).join('') || '<span style="color:var(--text-muted);font-size:11px;">none</span>'}
                    </div>
                    <div style="padding:12px;background:var(--bg-tertiary);border-radius:8px;">
                        <div style="font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-muted);margin-bottom:8px;">DNS PER ADAPTER</div>
                        ${(d.dns || []).map(x => `<div style="font-size:11px;font-family:'JetBrains Mono',monospace;color:var(--text-secondary);">${escapeHtml(x.adapter)}: ${escapeHtml((x.servers || []).join(', ') || 'none')} ${x.dhcp ? '<span style="color:var(--text-muted);">(DHCP)</span>' : '<span style="color:var(--accent-cyan);">(static)</span>'}</div>`).join('')}
                    </div>
                    <div style="padding:12px;background:var(--bg-tertiary);border-radius:8px;">
                        <div style="font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-muted);margin-bottom:8px;">MTU</div>
                        ${(d.mtu || []).map(x => `<div style="font-size:11px;font-family:'JetBrains Mono',monospace;color:var(--text-secondary);">${escapeHtml(x.adapter)}: ${x.mtu}</div>`).join('')}
                    </div>
                    <div style="padding:12px;background:var(--bg-tertiary);border-radius:8px;">
                        <div style="font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-muted);margin-bottom:8px;">WINSOCK LSP CATALOG — ${d.winsock?.count || 0} ENTRIES</div>
                        <div style="max-height:150px;overflow:auto;">
                        ${(d.winsock?.entries || []).map(e => `<div style="font-size:10px;font-family:'JetBrains Mono',monospace;color:var(--text-secondary);">${escapeHtml(e.name)}</div>`).join('')}
                        </div>
                        ${d.winsock?.truncated ? `<div style="font-size:10px;color:var(--text-muted);margin-top:6px;">…showing the first 60</div>` : ''}
                    </div>
                </div>`;
        } catch (e) {
            el.innerHTML = `<div style="color:var(--accent-red);font-size:12px;padding:12px;">Diagnostics failed.</div>`;
        }
    },

    async netQuickFix() {
        if (!confirm('Run Quick Fix?\n\n  • ipconfig /flushdns\n  • ipconfig /release\n  • ipconfig /renew\n\nYour connection drops briefly while the IP is renewed. No reboot needed.')) return;
        this._netShowOutput('QUICK FIX — running…', []);
        try {
            const d = await (await fetch('/api/network/quick-fix', { method: 'POST' })).json();
            this._netShowOutput('QUICK FIX', d.steps, d.message);
            this.showNotification('Quick fix complete', 'success');
            this.netDiagnose();
        } catch (e) { this.showNotification('Quick fix failed', 'error'); }
    },

    async netDeepReset() {
        const warning =
            '⚠ DEEP RESET — read this carefully\n\n' +
            'This runs:\n  • netsh winsock reset\n  • netsh int ip reset\n\n' +
            'What will happen:\n' +
            '  • Your network connection WILL DROP immediately\n' +
            '  • You MUST RESTART the computer afterwards\n' +
            '  • Winsock LSP entries added by VPN/AV software are removed\n' +
            '  • Administrator privileges are required\n\n' +
            'Save your work before continuing. Proceed?';
        if (!confirm(warning)) return;
        if (!confirm('Last check — the connection will drop and a restart is required.\n\nRun the deep reset now?')) return;
        this._netShowOutput('DEEP RESET — running…', []);
        try {
            const res = await fetch('/api/network/deep-reset', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ confirm: true })
            });
            const d = await res.json();
            if (d.status !== 'ok') { this.showNotification(d.message, 'error'); return; }
            this._netShowOutput('DEEP RESET', d.steps, d.message);
            alert('Deep reset complete.\n\nRESTART REQUIRED — networking will not behave normally until you restart the computer.');
            this.showNotification('Deep reset complete — reboot required', 'warning');
        } catch (e) { this.showNotification('Deep reset failed', 'error'); }
    },

    async netSetDns() {
        const adapter = document.getElementById('net-dns-adapter')?.value;
        const preset = document.getElementById('net-dns-preset')?.value;
        if (!adapter) { this.showNotification('Run Diagnose first to list adapters', 'warning'); return; }
        if (!confirm(`Set DNS on "${adapter}" to ${preset}?\n\nThe current setting is saved first so you can restore it.`)) return;
        try {
            const d = await (await fetch('/api/network/set-dns', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ adapter, preset })
            })).json();
            if (d.status !== 'ok') { this.showNotification(d.message, 'error'); return; }
            this._netShowOutput('SET DNS', d.steps, d.message);
            this.showNotification(`DNS on ${adapter} → ${(d.applied || []).join(', ')}`, 'success');
            this.netDiagnose();
        } catch (e) { this.showNotification('Could not set DNS', 'error'); }
    },

    async netRestoreDns() {
        const adapter = document.getElementById('net-dns-adapter')?.value;
        if (!adapter) return;
        try {
            const d = await (await fetch('/api/network/set-dns', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ adapter, restore: true })
            })).json();
            if (d.status !== 'ok') { this.showNotification(d.message, 'warning'); return; }
            this.showNotification(`DNS on ${adapter} restored`, 'success');
            this.netDiagnose();
        } catch (e) { this.showNotification('Could not restore DNS', 'error'); }
    },

    async netDnsBenchmark() {
        const el = document.getElementById('net-dns-benchmark');
        el.innerHTML = `<div style="color:var(--text-muted);font-family:'JetBrains Mono',monospace;font-size:12px;">Timing lookups against 1.1.1.1, 8.8.8.8, 9.9.9.9 and your current DNS…</div>`;
        try {
            const d = await (await fetch('/api/network/dns-benchmark')).json();
            if (d.error) { el.innerHTML = `<div style="color:var(--accent-red);font-size:12px;">${escapeHtml(d.error)}</div>`; return; }
            el.innerHTML = `
                <div style="border:1px solid var(--border-color);border-radius:8px;overflow:hidden;">
                    ${(d.results || []).map((r, i) => `
                        <div style="display:flex;gap:12px;align-items:center;padding:9px 12px;${i ? 'border-top:1px solid var(--border-color);' : ''}${i === 0 && r.avg_ms > 0 ? 'background:rgba(16,185,129,0.07);' : ''}">
                            <div style="width:22px;font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--text-muted);">${i + 1}</div>
                            <div style="flex:1;font-family:'JetBrains Mono',monospace;font-size:12px;">
                                ${escapeHtml(r.server)}
                                ${r.preset ? `<span style="font-size:9px;color:var(--text-muted);margin-left:6px;">${escapeHtml(r.preset)}</span>` : ''}
                                ${r.current ? `<span style="font-size:9px;padding:1px 6px;border-radius:3px;background:rgba(6,182,212,0.15);color:var(--accent-cyan);margin-left:6px;">CURRENT</span>` : ''}
                            </div>
                            <div style="font-family:'JetBrains Mono',monospace;font-size:12px;color:${r.avg_ms > 0 ? 'var(--accent-cyan)' : 'var(--accent-red)'};">
                                ${r.avg_ms > 0 ? r.avg_ms + ' ms' : 'no response'}
                            </div>
                            <div style="font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-muted);width:70px;text-align:right;">${r.ok}/${r.ok + r.failed} ok</div>
                        </div>`).join('')}
                </div>
                ${d.note ? `<div style="margin-top:10px;font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--text-secondary);line-height:1.7;">${escapeHtml(d.note)}</div>` : ''}`;
        } catch (e) {
            el.innerHTML = `<div style="color:var(--accent-red);font-size:12px;">Benchmark failed.</div>`;
        }
    },

    async netMtuProbe() {
        const el = document.getElementById('net-mtu-result');
        el.innerHTML = `<div style="color:var(--text-muted);font-family:'JetBrains Mono',monospace;font-size:12px;">Binary-searching the largest unfragmented packet…</div>`;
        try {
            const d = await (await fetch('/api/network/mtu-probe')).json();
            el.innerHTML = `
                <div style="padding:12px;background:var(--bg-tertiary);border-radius:8px;">
                    <div style="display:flex;gap:24px;flex-wrap:wrap;align-items:center;">
                        <div>
                            <div style="font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-muted);">OPTIMAL MTU</div>
                            <div style="font-size:22px;font-weight:600;color:var(--accent-cyan);">${d.optimal_mtu ?? '—'}</div>
                        </div>
                        <div>
                            <div style="font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-muted);">LARGEST PAYLOAD</div>
                            <div style="font-size:22px;font-weight:600;">${d.optimal_payload ?? '—'}</div>
                        </div>
                        <div style="flex:1;min-width:200px;font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--text-secondary);line-height:1.7;">${escapeHtml(d.note || '')}</div>
                    </div>
                </div>`;
            if (d.optimal_mtu) {
                const input = document.getElementById('net-mtu-value');
                if (input) input.value = d.optimal_mtu;
            }
        } catch (e) {
            el.innerHTML = `<div style="color:var(--accent-red);font-size:12px;">MTU probe failed.</div>`;
        }
    },

    async netSetMtu() {
        const adapter = document.getElementById('net-mtu-adapter')?.value;
        const mtu = parseInt(document.getElementById('net-mtu-value')?.value || '1500', 10);
        if (!adapter) { this.showNotification('Run Diagnose first to list adapters', 'warning'); return; }
        if (!confirm(`Set MTU on "${adapter}" to ${mtu}?\n\nThe change is persistent. The previous value is saved so you can restore it.\nAdministrator privileges are required.`)) return;
        try {
            const d = await (await fetch('/api/network/set-mtu', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ adapter, mtu })
            })).json();
            this.showNotification(d.message, d.status === 'ok' ? 'success' : 'error');
            this.netDiagnose();
        } catch (e) { this.showNotification('Could not set MTU', 'error'); }
    },

    async netRestoreMtu() {
        const adapter = document.getElementById('net-mtu-adapter')?.value;
        if (!adapter) return;
        try {
            const d = await (await fetch('/api/network/set-mtu', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ adapter, restore: true })
            })).json();
            this.showNotification(d.message || 'Restored', d.status === 'ok' ? 'success' : 'warning');
            this.netDiagnose();
        } catch (e) { this.showNotification('Could not restore MTU', 'error'); }
    },

    async netBrowserCache(action) {
        const browsers = Array.from(document.querySelectorAll('.net-browser:checked')).map(c => c.value);
        if (!browsers.length) { this.showNotification('Select at least one browser', 'warning'); return; }
        const el = document.getElementById('net-browser-result');

        if (action === 'clear') {
            if (!confirm(`Clear the cache for ${browsers.join(', ')}?\n\nOnly cache directories are removed — cookies, history, saved passwords and bookmarks are untouched.\nThey go to the Recycle Bin after a System Restore point is created.\n\nClose the browsers first.`)) return;
        }
        el.innerHTML = `<div style="color:var(--text-muted);font-family:'JetBrains Mono',monospace;font-size:12px;">Working…</div>`;

        const send = (extra) => fetch('/api/network/browser-cache', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ browsers, action, confirm: action === 'clear', ...extra })
        });

        try {
            let res = await send({});
            let d = await res.json();

            if (res.status === 409 && d.status === 'restore_point_failed') {
                if (!confirm(`A System Restore point could not be created:\n\n${d.message}\n\nNothing was cleared. Continue WITHOUT a restore point? Cache folders still go to the Recycle Bin.`)) {
                    el.innerHTML = '';
                    return;
                }
                res = await send({ proceed_without_restore_point: true });
                d = await res.json();
            }

            if (d.status !== 'ok') {
                el.innerHTML = `<div style="color:var(--accent-red);font-size:12px;">${escapeHtml(d.message || 'Failed')}</div>`;
                return;
            }

            if (d.action === 'scan') {
                el.innerHTML = `
                    <div style="border:1px solid var(--border-color);border-radius:8px;overflow:hidden;">
                        ${(d.browsers || []).map((b, i) => `
                            <div style="display:flex;gap:12px;align-items:center;padding:9px 12px;${i ? 'border-top:1px solid var(--border-color);' : ''}">
                                <div style="flex:1;font-size:12px;font-weight:600;">${escapeHtml(b.browser)}
                                    <span style="font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-muted);margin-left:8px;">${b.installed ? b.cache_dirs.length + ' cache dir(s)' : 'not installed'}</span>
                                </div>
                                <div style="font-family:'JetBrains Mono',monospace;font-size:13px;color:var(--accent-cyan);">${escapeHtml(b.bytes_fmt)}</div>
                            </div>`).join('')}
                        <div style="display:flex;gap:12px;padding:9px 12px;border-top:1px solid var(--border-color);background:var(--bg-tertiary);">
                            <div style="flex:1;font-size:12px;font-weight:600;">Total</div>
                            <div style="font-family:'JetBrains Mono',monospace;font-size:13px;color:var(--accent-cyan);">${escapeHtml(d.total_fmt)}</div>
                        </div>
                    </div>
                    <div style="margin-top:8px;font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-muted);">${escapeHtml(d.note || '')}</div>`;
            } else {
                el.innerHTML = `<div style="padding:12px;background:rgba(16,185,129,0.07);border:1px solid rgba(16,185,129,0.25);border-radius:8px;font-size:12px;color:var(--text-secondary);">
                    ✓ ${d.cleared} cache folder(s) cleared — ${escapeHtml(d.bytes_fmt)} reclaimed.<br>
                    <span style="font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-muted);">${escapeHtml(d.message || '')}</span>
                </div>`;
                this.showNotification(`Browser cache cleared — ${d.bytes_fmt}`, 'success');
                this.refreshLogs();
            }
        } catch (e) {
            el.innerHTML = `<div style="color:var(--accent-red);font-size:12px;">Request failed.</div>`;
        }
    },

    // ══════════════════════════════════════════════════════════
    // AI STORAGE REPORT (Sprint 3, Feature 4) — READ ONLY, no delete path
    // ══════════════════════════════════════════════════════════
    _aiStoragePoller: null,

    async aiStorageScan() {
        const btn = document.getElementById('btn-aistorage-scan');
        if (btn) { btn.disabled = true; btn.textContent = '⏳ Measuring…'; }
        document.getElementById('aistorage-list').innerHTML =
            `<div style="text-align:center;color:var(--text-muted);padding:24px;font-family:'JetBrains Mono',monospace;font-size:12px;">Measuring model caches… large model directories can take a minute.</div>`;
        try {
            await fetch('/api/ai-storage/scan', { method: 'POST' });
            if (this._aiStoragePoller) clearInterval(this._aiStoragePoller);
            this._aiStoragePoller = setInterval(async () => {
                const rep = await (await fetch('/api/ai-storage/report')).json();
                if (rep.status === 'scanning') return;
                clearInterval(this._aiStoragePoller);
                this._aiStoragePoller = null;
                if (btn) { btn.disabled = false; btn.innerHTML = '🔍 Build Report'; }
                this.renderAiStorage(rep);
            }, 1500);
        } catch (e) {
            this.showNotification('AI storage report failed to start', 'error');
            if (btn) { btn.disabled = false; btn.innerHTML = '🔍 Build Report'; }
        }
    },

    renderAiStorage(rep) {
        const tools = rep.tools || [];
        const detected = tools.filter(t => t.present);
        const missing = tools.filter(t => !t.present);

        const summary = document.getElementById('aistorage-summary');
        summary.style.display = 'block';
        summary.innerHTML = `
            <div style="display:flex;gap:24px;flex-wrap:wrap;align-items:center;padding:14px 16px;background:var(--bg-tertiary);border-radius:8px;">
                <div>
                    <div style="font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-muted);">TOTAL AI STORAGE</div>
                    <div style="font-size:24px;font-weight:600;color:var(--accent-cyan);">${escapeHtml(rep.total_fmt || '0 B')}</div>
                </div>
                <div>
                    <div style="font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-muted);">TOOLS DETECTED</div>
                    <div style="font-size:24px;font-weight:600;">${rep.detected || 0}</div>
                </div>
                <div>
                    <div style="font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-muted);">ORPHANED REVISIONS</div>
                    <div style="font-size:24px;font-weight:600;color:${(rep.stale_revisions || 0) > 0 ? 'var(--accent-yellow)' : 'var(--text-primary)'};">${rep.stale_revisions || 0}</div>
                </div>
                <div style="margin-left:auto;font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-muted);">
                    ${escapeHtml(rep.last_scan || '')}
                </div>
            </div>`;

        const toolHtml = detected.map(t => {
            const models = (t.models || []).slice(0, 25);
            const rows = models.map(m => `
                <div style="display:flex;gap:10px;align-items:center;padding:5px 12px 5px 26px;border-top:1px solid var(--border-color);">
                    <div style="flex:1;min-width:0;font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--text-secondary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
                        ${escapeHtml(m.name)}
                        ${m.kind === 'dataset' ? `<span style="font-size:9px;padding:1px 5px;border-radius:3px;background:rgba(156,163,175,0.15);color:var(--text-muted);margin-left:6px;">DATASET</span>` : ''}
                        ${m.orphaned_revisions > 0 ? `<span style="font-size:9px;padding:1px 5px;border-radius:3px;background:rgba(245,158,11,0.14);color:var(--accent-yellow);margin-left:6px;">${m.orphaned_revisions} ORPHANED REVISION${m.orphaned_revisions > 1 ? 'S' : ''}</span>` : ''}
                    </div>
                    <div style="font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--accent-cyan);white-space:nowrap;">${escapeHtml(m.bytes_fmt)}</div>
                </div>`).join('');
            return `
            <div style="border:1px solid var(--border-color);border-radius:8px;margin-bottom:10px;overflow:hidden;">
                <div style="display:flex;gap:12px;align-items:center;padding:10px 12px;background:var(--bg-tertiary);">
                    <div style="flex:1;min-width:0;">
                        <div style="font-size:13px;font-weight:600;">${escapeHtml(t.tool)}</div>
                        <div style="font-size:10px;color:var(--text-muted);font-family:'JetBrains Mono',monospace;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(t.path)}</div>
                    </div>
                    <div style="text-align:right;white-space:nowrap;">
                        <div style="font-family:'JetBrains Mono',monospace;font-size:15px;color:var(--accent-cyan);">${escapeHtml(t.bytes_fmt)}</div>
                        <div style="font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-muted);">${t.files} file(s)</div>
                    </div>
                </div>
                ${t.note ? `<div style="padding:7px 12px;font-size:10px;color:var(--text-muted);font-family:'JetBrains Mono',monospace;line-height:1.6;border-top:1px solid var(--border-color);">${escapeHtml(t.note)}</div>` : ''}
                ${rows}
                ${(t.models || []).length > 25 ? `<div style="padding:6px 12px 8px 26px;font-size:10px;color:var(--text-muted);font-family:'JetBrains Mono',monospace;">…and ${t.models.length - 25} more</div>` : ''}
            </div>`;
        }).join('');

        const missingHtml = missing.length ? `
            <div style="margin-top:14px;padding:12px;border:1px dashed var(--border-color);border-radius:8px;">
                <div style="font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-muted);margin-bottom:6px;">NOT DETECTED</div>
                ${missing.map(t => `<div style="font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--text-muted);">${escapeHtml(t.tool)} — ${escapeHtml(t.note)}</div>`).join('')}
            </div>` : '';

        document.getElementById('aistorage-list').innerHTML =
            (toolHtml || `<div style="text-align:center;color:var(--text-muted);padding:24px;">No AI tool caches detected on this machine.</div>`)
            + missingHtml;
    },

    // ══════════════════════════════════════════════════════════
    // SHARED FINDER UI — filename-first rows, custom roots, Review screen
    // Used by the duplicate, large-file and zero-length finders.
    // ══════════════════════════════════════════════════════════

    _pathParts(path) {
        const p = String(path || '');
        const i = Math.max(p.lastIndexOf('\\'), p.lastIndexOf('/'));
        return i < 0 ? { name: p, folder: '' } : { name: p.slice(i + 1), folder: p.slice(0, i) };
    },

    // Middle truncation: the head names the drive and the tail names the
    // deepest folder, so cutting the middle is the only cut that loses
    // neither. The filename is rendered separately and is never cut.
    _midTrunc(text, max) {
        const t = String(text || '');
        max = max || 72;
        if (t.length <= max) return t;
        const head = Math.ceil((max - 1) / 2);
        const tail = Math.floor((max - 1) / 2);
        return t.slice(0, head) + '…' + t.slice(t.length - tail);
    },

    // One row shape everywhere: filename first, in bold, never truncated;
    // the folder under it, truncated in the middle; full path on hover.
    _fileRowHtml(f, opts) {
        opts = opts || {};
        const parts = this._pathParts(f.path);
        const name = f.name || parts.name;
        const full = escapeHtml(f.path);
        return `
            <div style="flex:1;min-width:0;">
                <div style="font-size:12px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${full}">
                    ${escapeHtml(name)}${opts.chips || ''}
                </div>
                <div style="font-size:10px;color:var(--text-muted);font-family:'JetBrains Mono',monospace;margin-top:2px;white-space:nowrap;" title="${full}">
                    ${escapeHtml(this._midTrunc(parts.folder))}
                </div>
                ${opts.meta ? `<div style="font-size:10px;color:var(--text-muted);margin-top:2px;">${opts.meta}</div>` : ''}
            </div>`;
    },

    // ── Custom folder picker (shared by all three finders) ────
    // kind is 'duplicates' | 'largefiles' | 'zerolength'; the finder's root
    // checkboxes are .<kind>-root inside #<kind>-roots.
    async addCustomRoot(kind) {
        const input = document.getElementById(`${kind}-custom-path`);
        const status = document.getElementById(`${kind}-custom-status`);
        const say = (html, color) => {
            if (status) status.innerHTML = `<span style="color:${color};">${html}</span>`;
        };
        const path = (input?.value || '').trim();
        if (!path) { say('Type a folder path first.', 'var(--accent-yellow)'); return; }

        say('Checking…', 'var(--text-muted)');
        let data;
        try {
            const res = await fetch('/api/scan-roots/validate', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path })
            });
            data = await res.json();
        } catch (e) {
            say('Could not validate that folder.', 'var(--accent-red)');
            return;
        }
        if (!data.ok) { say(escapeHtml(data.message || 'Refused.'), 'var(--accent-red)'); return; }

        const list = document.getElementById(`${kind}-roots`);
        const existing = Array.from(list.querySelectorAll(`.${kind}-root`))
            .find(c => c.value.toLowerCase() === data.path.toLowerCase());
        if (existing) {
            existing.checked = true;
            say('Already in the list — ticked it.', 'var(--accent-cyan)');
            if (input) input.value = '';
            return;
        }
        const label = document.createElement('label');
        label.style.cssText = "font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--text-secondary);cursor:pointer;display:block;";
        label.innerHTML = `
            <input type="checkbox" class="${kind}-root" value="${escapeHtml(data.path)}" checked style="vertical-align:middle;">
            ${escapeHtml(data.label)}
            <span style="color:var(--text-muted);" title="${escapeHtml(data.path)}">${escapeHtml(this._midTrunc(data.path, 60))}</span>
            <span style="color:var(--accent-cyan);"> · custom</span>
            ${data.cloud_synced ? `<span style="color:var(--accent-yellow);"> ☁ cloud-synced — delete blocked</span>` : ''}`;
        const placeholder = list.querySelector('span');
        if (placeholder && !list.querySelector(`.${kind}-root`)) list.innerHTML = '';
        list.appendChild(label);
        if (input) input.value = '';
        say('Added and ticked.', 'var(--accent-green)');
    },

    // ══════════════════════════════════════════════════════════
    // DUPLICATE FINDER (Sprint 3, Feature 3) — file level, user picks copies
    // ══════════════════════════════════════════════════════════
    _duplicatesReport: null,
    _duplicatesPoller: null,

    async duplicatesLoadRoots() {
        try {
            const data = await (await fetch('/api/duplicates/roots')).json();
            document.getElementById('duplicates-roots').innerHTML =
                (data.roots || []).map(r => `
                    <label style="font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--text-secondary);cursor:pointer;display:block;">
                        <input type="checkbox" class="duplicates-root" value="${escapeHtml(r.path)}" ${r.default_on ? 'checked' : ''} style="vertical-align:middle;">
                        ${escapeHtml(r.label)} <span style="color:var(--text-muted);">${escapeHtml(r.path)}</span>
                        ${r.cloud_synced ? `<span style="color:var(--accent-yellow);"> ☁ cloud-synced — delete blocked</span>` : ''}
                    </label>`).join('') ||
                `<span style="color:var(--text-muted);font-size:12px;">No standard folders found.</span>`;
        } catch (e) { /* ignore */ }
    },

    async duplicatesScan() {
        const roots = Array.from(document.querySelectorAll('.duplicates-root:checked')).map(c => c.value);
        if (!roots.length) { this.showNotification('Select at least one folder to scan', 'warning'); return; }
        const btn = document.getElementById('btn-duplicates-scan');
        if (btn) { btn.disabled = true; btn.textContent = '⏳ Scanning…'; }
        document.getElementById('duplicates-list').innerHTML =
            `<div style="text-align:center;color:var(--text-muted);padding:24px;font-family:'JetBrains Mono',monospace;font-size:12px;">
                Pass 1 (size) → pass 2 (partial hash) → pass 3 (SHA-256)… this can take a while on large folders.
             </div>`;
        try {
            const d = await (await fetch('/api/duplicates/scan', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ roots })
            })).json();
            if (d.status === 'error') {
                this.showNotification(d.message, 'error');
                if (btn) { btn.disabled = false; btn.innerHTML = '🔍 Step 1 — Scan'; }
                return;
            }
            if (this._duplicatesPoller) clearInterval(this._duplicatesPoller);
            this._duplicatesPoller = setInterval(async () => {
                const rep = await (await fetch('/api/duplicates/report')).json();
                if (rep.status === 'scanning') return;
                clearInterval(this._duplicatesPoller);
                this._duplicatesPoller = null;
                if (btn) { btn.disabled = false; btn.innerHTML = '🔍 Step 1 — Scan'; }
                this._duplicatesReport = rep;
                this.renderDuplicates();
            }, 1500);
        } catch (e) {
            this.showNotification('Duplicate scan failed to start', 'error');
            if (btn) { btn.disabled = false; btn.innerHTML = '🔍 Step 1 — Scan'; }
        }
    },

    renderDuplicates() {
        const rep = this._duplicatesReport;
        if (!rep) return;
        const groups = rep.groups || [];
        const p = rep.passes || {};

        const summary = document.getElementById('duplicates-summary');
        summary.style.display = 'block';
        summary.innerHTML = `
            <div style="padding:14px 16px;background:var(--bg-tertiary);border-radius:8px;">
                <div style="display:flex;gap:24px;flex-wrap:wrap;align-items:center;">
                    <div>
                        <div style="font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-muted);">RECLAIMABLE</div>
                        <div style="font-size:22px;font-weight:600;color:var(--accent-cyan);">${escapeHtml(rep.reclaimable_fmt || '0 B')}</div>
                    </div>
                    <div>
                        <div style="font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-muted);">DUPLICATE GROUPS</div>
                        <div style="font-size:22px;font-weight:600;">${rep.group_count || 0}</div>
                    </div>
                    <div style="margin-left:auto;font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-muted);line-height:1.7;">
                        pass 1 size candidates: ${p.pass1_size_candidates || 0}<br>
                        pass 2 partial-hash collisions: ${p.pass2_partial_collisions || 0}<br>
                        pass 3 confirmed identical: ${p.pass3_confirmed_files || 0} (${rep.files_hashed || 0} hash ops)
                    </div>
                </div>
                ${rep.truncated ? `<div style="font-size:10px;color:var(--accent-yellow);margin-top:8px;font-family:'JetBrains Mono',monospace;">Showing the ${rep.shown} largest of ${rep.group_count} groups.</div>` : ''}
                ${(rep.skipped_roots || []).length ? `<div style="font-size:10px;color:var(--accent-yellow);margin-top:6px;font-family:'JetBrains Mono',monospace;">${rep.skipped_roots.length} root(s) skipped by safety rules.</div>` : ''}
            </div>`;

        const html = groups.map(g => `
            <div style="border:1px solid var(--border-color);border-radius:8px;margin-bottom:10px;overflow:hidden;">
                <div style="display:flex;gap:12px;align-items:center;padding:9px 12px;background:var(--bg-tertiary);">
                    <div style="flex:1;min-width:0;font-size:12px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
                        ${escapeHtml(g.copies[0].name)}
                        <span style="font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-muted);margin-left:8px;">${g.count} identical copies · ${escapeHtml(g.size_fmt)} each · sha256:${escapeHtml(g.hash)}</span>
                    </div>
                    <div style="font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--accent-yellow);white-space:nowrap;">${escapeHtml(g.wasted_fmt)} wasted</div>
                </div>
                ${g.copies.map(c => `
                    <div style="display:flex;gap:10px;align-items:center;padding:7px 12px;border-top:1px solid var(--border-color);">
                        <input type="checkbox" class="duplicates-file" data-group="${escapeHtml(g.hash)}" value="${escapeHtml(c.path)}" ${(c.cloud_synced || c.protected) ? 'disabled' : ''}>
                        ${this._fileRowHtml(c, {
                            meta: `modified ${escapeHtml(c.modified)}`
                                + (c.cloud_synced ? `<span style="color:var(--accent-red);"> · ☁ cloud-synced, delete blocked</span>` : '')
                                + (c.protected ? `<span style="color:var(--accent-red);"> · protected location</span>` : '')
                        })}
                    </div>`).join('')}
            </div>`).join('');

        document.getElementById('duplicates-list').innerHTML = html ||
            `<div style="text-align:center;color:var(--text-muted);padding:24px;">No duplicate files found in the selected folders.</div>`;
        const btn = document.getElementById('btn-duplicates-delete');
        if (btn) btn.disabled = groups.length === 0;
    },

    async duplicatesDelete(opts) {
        opts = opts || {};
        const boxes = Array.from(document.querySelectorAll('.duplicates-file:checked'));
        if (!boxes.length) { this.showNotification('Tick the copies you want to remove', 'warning'); return; }

        // Client-side mirror of the server rule: keep at least one copy per group.
        const perGroup = {};
        boxes.forEach(b => { perGroup[b.dataset.group] = (perGroup[b.dataset.group] || 0) + 1; });
        const wipe = (this._duplicatesReport.groups || [])
            .filter(g => perGroup[g.hash] && perGroup[g.hash] >= g.count);
        if (wipe.length) {
            alert(`That selection would delete every copy of ${wipe.length} file(s):\n\n` +
                  wipe.slice(0, 6).map(g => `  • ${g.copies[0].name}`).join('\n') +
                  `\n\nLeave at least one copy of each file.`);
            return;
        }

        const files = boxes.map(b => b.value);
        if (!opts.skipConfirm) {
            if (!confirm(`Remove ${files.length} duplicate copy(ies)?\n\nEvery file will still have at least one copy left.\nRemoved copies go to the Recycle Bin after a System Restore point is created.`)) return;
        }

        const btn = document.getElementById('btn-duplicates-delete');
        if (btn) { btn.disabled = true; btn.textContent = '⏳ Removing…'; }
        try {
            const res = await fetch('/api/duplicates/delete', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    confirm: true, files,
                    proceed_without_restore_point: !!opts.withoutRestorePoint,
                    allow_permanent: !!opts.allowPermanent
                })
            });
            const data = await res.json();
            if (btn) { btn.disabled = false; btn.innerHTML = '🗑 Step 2 — Review & Delete'; }

            if (res.status === 409 && data.status === 'restore_point_failed') {
                if (confirm(`A System Restore point could not be created:\n\n${data.message}\n\nNothing was deleted. Continue WITHOUT a restore point? Copies still go to the Recycle Bin.`)) {
                    this.duplicatesDelete({ withoutRestorePoint: true, skipConfirm: true });
                }
                return;
            }
            if (data.status !== 'ok') {
                this.showNotification(data.message || 'Removal refused', 'error');
                return;
            }
            if (data.message) this.showNotification(data.message, 'warning');
            this.showNotification(`${data.deleted} copy(ies) moved to the Recycle Bin — ${data.bytes_fmt} reclaimed`, 'success');
            this._duplicatesReport = await (await fetch('/api/duplicates/report')).json();
            this.renderDuplicates();
            this.refreshLogs();
        } catch (e) {
            this.showNotification('Removal failed', 'error');
            if (btn) { btn.disabled = false; btn.innerHTML = '🗑 Step 2 — Review & Delete'; }
        }
    },

    // ══════════════════════════════════════════════════════════
    // LARGE FILE FINDER (Sprint 3, Feature 2) — report, then per-file delete
    // ══════════════════════════════════════════════════════════
    _largefilesReport: null,
    _largefilesPoller: null,

    _catLabel(c) {
        return ({ video: 'Video', installer_archive: 'Installer/Archive',
                  disk_image: 'Disk image', model_file: 'Model file',
                  other: 'Other' })[c] || c;
    },

    async largefilesLoadRoots() {
        try {
            const res = await fetch('/api/largefiles/roots');
            const data = await res.json();
            const el = document.getElementById('largefiles-roots');
            el.innerHTML = (data.roots || []).map(r => `
                <label style="font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--text-secondary);cursor:pointer;display:block;">
                    <input type="checkbox" class="largefiles-root" value="${escapeHtml(r.path)}" ${r.default_on ? 'checked' : ''} style="vertical-align:middle;">
                    ${escapeHtml(r.label)}
                    <span style="color:var(--text-muted);">${escapeHtml(r.path)}</span>
                    ${r.cloud_synced ? `<span style="color:var(--accent-yellow);"> ☁ cloud-synced — delete blocked</span>` : ''}
                </label>`).join('') ||
                `<span style="color:var(--text-muted);font-size:12px;">No standard folders found.</span>`;
            const t = document.getElementById('largefiles-threshold');
            if (t && data.default_threshold_mb) t.value = data.default_threshold_mb;
        } catch (e) { /* ignore */ }
    },

    async largefilesScan() {
        const roots = Array.from(document.querySelectorAll('.largefiles-root:checked')).map(c => c.value);
        if (!roots.length) { this.showNotification('Select at least one folder to scan', 'warning'); return; }
        const threshold = parseInt(document.getElementById('largefiles-threshold')?.value || '500', 10);
        const btn = document.getElementById('btn-largefiles-scan');
        if (btn) { btn.disabled = true; btn.textContent = '⏳ Scanning…'; }
        document.getElementById('largefiles-list').innerHTML =
            `<div style="text-align:center;color:var(--text-muted);padding:24px;font-family:'JetBrains Mono',monospace;font-size:12px;">Scanning ${roots.length} folder(s)…</div>`;
        try {
            const res = await fetch('/api/largefiles/scan', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ roots, threshold_mb: threshold })
            });
            const d = await res.json();
            if (d.status === 'error') {
                this.showNotification(d.message, 'error');
                if (btn) { btn.disabled = false; btn.innerHTML = '🔍 Step 1 — Scan'; }
                return;
            }
            if (this._largefilesPoller) clearInterval(this._largefilesPoller);
            this._largefilesPoller = setInterval(async () => {
                const rep = await (await fetch('/api/largefiles/report')).json();
                if (rep.status === 'scanning') return;
                clearInterval(this._largefilesPoller);
                this._largefilesPoller = null;
                if (btn) { btn.disabled = false; btn.innerHTML = '🔍 Step 1 — Scan'; }
                this._largefilesReport = rep;
                this.renderLargefiles();
            }, 1200);
        } catch (e) {
            this.showNotification('Large file scan failed to start', 'error');
            if (btn) { btn.disabled = false; btn.innerHTML = '🔍 Step 1 — Scan'; }
        }
    },

    renderLargefiles() {
        const rep = this._largefilesReport;
        if (!rep) return;
        const filter = document.getElementById('largefiles-category')?.value || '';
        let files = rep.files || [];
        if (filter === '__old') files = files.filter(f => f.old_installer);
        else if (filter) files = files.filter(f => f.category === filter);

        const summary = document.getElementById('largefiles-summary');
        summary.style.display = 'block';
        const cats = Object.entries(rep.by_category || {})
            .sort((a, b) => b[1].bytes - a[1].bytes)
            .map(([c, v]) => `<span style="font-family:'JetBrains Mono',monospace;font-size:10px;padding:3px 8px;border-radius:4px;background:var(--bg-tertiary);margin-right:6px;">${escapeHtml(this._catLabel(c))}: ${escapeHtml(v.bytes_fmt)} (${v.count})</span>`)
            .join('');
        summary.innerHTML = `
            <div style="padding:14px 16px;background:var(--bg-tertiary);border-radius:8px;">
                <div style="display:flex;gap:20px;flex-wrap:wrap;align-items:center;margin-bottom:10px;">
                    <div>
                        <div style="font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-muted);">TOTAL</div>
                        <div style="font-size:22px;font-weight:600;color:var(--accent-cyan);">${escapeHtml(rep.total_fmt || '0 B')}</div>
                    </div>
                    <div>
                        <div style="font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-muted);">FILES &gt; ${rep.threshold_mb} MB</div>
                        <div style="font-size:22px;font-weight:600;">${rep.found || 0}</div>
                    </div>
                    <div>
                        <div style="font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-muted);">SUPERSEDED INSTALLERS</div>
                        <div style="font-size:22px;font-weight:600;color:var(--accent-yellow);">${rep.old_installers || 0}</div>
                    </div>
                </div>
                <div>${cats}</div>
                ${rep.truncated ? `<div style="font-size:10px;color:var(--accent-yellow);margin-top:8px;font-family:'JetBrains Mono',monospace;">Showing the largest ${rep.shown} of ${rep.found} matches.</div>` : ''}
                ${(rep.skipped_roots || []).length ? `<div style="font-size:10px;color:var(--accent-yellow);margin-top:6px;font-family:'JetBrains Mono',monospace;">${rep.skipped_roots.length} root(s) skipped by safety rules.</div>` : ''}
            </div>`;

        const rows = files.map(f => `
            <div style="display:flex;gap:12px;align-items:center;padding:9px 12px;border-bottom:1px solid var(--border-color);">
                <input type="checkbox" class="largefiles-file" value="${escapeHtml(f.path)}" ${f.cloud_synced ? 'disabled' : ''}>
                ${this._fileRowHtml(f, {
                    chips: (f.old_installer ? `<span style="font-family:'JetBrains Mono',monospace;font-size:9px;padding:2px 6px;border-radius:4px;background:rgba(245,158,11,0.14);color:var(--accent-yellow);margin-left:6px;">OLD INSTALLER → v${escapeHtml(f.superseded_by)}</span>` : '')
                         + (f.cloud_synced ? `<span style="font-family:'JetBrains Mono',monospace;font-size:9px;padding:2px 6px;border-radius:4px;background:rgba(239,68,68,0.14);color:var(--accent-red);margin-left:6px;">☁ CLOUD-SYNCED</span>` : ''),
                    meta: `${escapeHtml(this._catLabel(f.category))} · ${escapeHtml(f.modified)}`
                })}
                <div style="font-family:'JetBrains Mono',monospace;font-size:13px;color:var(--accent-cyan);white-space:nowrap;">${escapeHtml(f.size_fmt)}</div>
            </div>`).join('');

        document.getElementById('largefiles-list').innerHTML = rows ||
            `<div style="text-align:center;color:var(--text-muted);padding:24px;">No files matched.</div>`;
        const btn = document.getElementById('btn-largefiles-delete');
        if (btn) btn.disabled = files.length === 0;
    },

    async largefilesDelete(opts) {
        opts = opts || {};
        const files = Array.from(document.querySelectorAll('.largefiles-file:checked')).map(c => c.value);
        if (!files.length) { this.showNotification('Select the files you want to delete', 'warning'); return; }

        const rep = this._largefilesReport || { files: [] };
        const chosen = rep.files.filter(f => files.includes(f.path));
        const total = chosen.reduce((s, f) => s + f.size, 0);

        if (!opts.skipConfirm) {
            let msg = `Delete ${files.length} file(s), ${this._fmtBytes(total)}?\n\n`;
            msg += chosen.slice(0, 12).map(f => `  • ${f.name} — ${f.size_fmt}`).join('\n');
            if (chosen.length > 12) msg += `\n  … and ${chosen.length - 12} more`;
            msg += `\n\nThese go to the Recycle Bin (recoverable) after a System Restore point is created.`;
            if (!confirm(msg)) return;
        }

        const btn = document.getElementById('btn-largefiles-delete');
        if (btn) { btn.disabled = true; btn.textContent = '⏳ Deleting…'; }
        try {
            const res = await fetch('/api/largefiles/delete', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    confirm: true, files,
                    proceed_without_restore_point: !!opts.withoutRestorePoint,
                    allow_permanent: !!opts.allowPermanent
                })
            });
            const data = await res.json();
            if (btn) { btn.disabled = false; btn.innerHTML = '🗑 Step 2 — Review & Delete'; }

            if (res.status === 409 && data.status === 'restore_point_failed') {
                if (confirm(`A System Restore point could not be created:\n\n${data.message}\n\nNothing was deleted. Continue WITHOUT a restore point? Files still go to the Recycle Bin.`)) {
                    this.largefilesDelete({ withoutRestorePoint: true, skipConfirm: true });
                }
                return;
            }
            if (data.status !== 'ok') {
                this.showNotification(data.message || 'Deletion refused', 'error');
                return;
            }
            if (data.message) this.showNotification(data.message, 'warning');
            this.showNotification(`${data.deleted} file(s) moved to the Recycle Bin — ${data.bytes_fmt} reclaimed`, 'success');
            if ((data.blocked || []).length) {
                this.showNotification(`${data.blocked.length} file(s) skipped by safety rules`, 'warning');
            }
            const rep2 = await (await fetch('/api/largefiles/report')).json();
            this._largefilesReport = rep2;
            this.renderLargefiles();
            this.refreshLogs();
        } catch (e) {
            this.showNotification('Deletion failed', 'error');
            if (btn) { btn.disabled = false; btn.innerHTML = '🗑 Step 2 — Review & Delete'; }
        }
    },

    async deepcleanLoadTargets() {
        // Show the catalogue (labels, risk, defaults) before any scan runs so the
        // page is never empty. Sizes stay blank until Step 1 is pressed.
        try {
            const res = await fetch('/api/deepclean/targets');
            const data = await res.json();
            this.renderDeepcleanReport({
                targets: (data.targets || []).map(t => ({ ...t, bytes: 0, count: 0, note: '' })),
                total_fmt: '—', last_scan: 'not scanned yet', platform_supported: true
            });
            const applyBtn = document.getElementById('btn-deepclean-apply');
            if (applyBtn) applyBtn.disabled = true;   // Step 2 needs a report first
            this._deepcleanReport = null;
        } catch (e) { /* page still usable via Scan */ }
    },

    async deepcleanScan() {
        const btn = document.getElementById('btn-deepclean-scan');
        const includeDism = !!document.getElementById('deepclean-include-dism')?.checked;
        if (btn) { btn.disabled = true; btn.textContent = '⏳ Scanning…'; }
        document.getElementById('deepclean-results').style.display = 'none';
        document.getElementById('deepclean-targets').innerHTML =
            `<div style="text-align:center;color:var(--text-muted);padding:24px;font-family:'JetBrains Mono',monospace;font-size:12px;">
                Building report${includeDism ? ' (DISM analysis can take several minutes)' : ''}…
             </div>`;
        try {
            await fetch('/api/deepclean/scan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ include_dism: includeDism })
            });
            this._pollDeepcleanReport();
        } catch (e) {
            this.showNotification('Deep Clean scan failed to start', 'error');
            if (btn) { btn.disabled = false; btn.innerHTML = '🔍 Step 1 — Scan'; }
        }
    },

    _pollDeepcleanReport() {
        if (this._deepcleanPoller) clearInterval(this._deepcleanPoller);
        this._deepcleanPoller = setInterval(async () => {
            try {
                const res = await fetch('/api/deepclean/report');
                const data = await res.json();
                if (data.status === 'scanning') return;
                clearInterval(this._deepcleanPoller);
                this._deepcleanPoller = null;
                const btn = document.getElementById('btn-deepclean-scan');
                if (btn) { btn.disabled = false; btn.innerHTML = '🔍 Step 1 — Scan'; }
                if (data.status === 'error') {
                    this.showNotification('Deep Clean scan error: ' + (data.message || ''), 'error');
                    return;
                }
                this._deepcleanReport = data;
                this.renderDeepcleanReport(data);
            } catch (e) { /* keep polling */ }
        }, 1200);
    },

    renderDeepcleanReport(data) {
        const targets = data.targets || [];
        const summary = document.getElementById('deepclean-summary');
        summary.style.display = 'block';
        summary.innerHTML = `
            <div style="display:flex;gap:20px;flex-wrap:wrap;align-items:center;padding:14px 16px;background:var(--bg-tertiary);border-radius:8px;">
                <div>
                    <div style="font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-muted);">TOTAL RECLAIMABLE</div>
                    <div style="font-size:24px;font-weight:600;color:var(--accent-cyan);">${escapeHtml(data.total_fmt || '0 B')}</div>
                </div>
                <div>
                    <div style="font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-muted);">TARGETS</div>
                    <div style="font-size:24px;font-weight:600;">${targets.length}</div>
                </div>
                <div style="margin-left:auto;font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-muted);">
                    Scanned ${escapeHtml(data.last_scan || '—')}${data.platform_supported ? '' : ' — PREVIEW MODE (non-Windows)'}
                </div>
            </div>`;

        const rows = targets.map(t => {
            const disabled = t.report_only ? 'disabled' : '';
            const checked = (t.default_on && !t.report_only) ? 'checked' : '';
            return `
            <div style="display:flex;gap:12px;align-items:flex-start;padding:12px 14px;border-bottom:1px solid var(--border-color);">
                <input type="checkbox" class="deepclean-target" value="${escapeHtml(t.key)}" ${checked} ${disabled} style="margin-top:3px;">
                <div style="flex:1;min-width:0;">
                    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
                        <span style="font-weight:600;">${escapeHtml(t.label)}</span>
                        ${this._riskChip(t.risk)}
                        ${t.report_only ? `<span style="font-family:'JetBrains Mono',monospace;font-size:9px;padding:2px 7px;border-radius:4px;background:rgba(156,163,175,0.15);color:var(--text-muted);">REPORT ONLY</span>` : ''}
                        ${!t.default_on && !t.report_only ? `<span style="font-family:'JetBrains Mono',monospace;font-size:9px;padding:2px 7px;border-radius:4px;background:rgba(156,163,175,0.15);color:var(--text-muted);">OPT-IN</span>` : ''}
                    </div>
                    <div style="font-size:11px;color:var(--text-secondary);margin-top:4px;line-height:1.6;">${escapeHtml(t.description)}</div>
                    ${t.note ? `<div style="font-size:10px;color:var(--text-muted);margin-top:4px;font-family:'JetBrains Mono',monospace;">${escapeHtml(t.note)}</div>` : ''}
                </div>
                <div style="text-align:right;white-space:nowrap;">
                    <div style="font-family:'JetBrains Mono',monospace;font-size:14px;color:var(--accent-cyan);">${escapeHtml(this._fmtBytes(t.bytes))}</div>
                    <div style="font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-muted);">${t.count} item(s)</div>
                </div>
            </div>`;
        }).join('');

        document.getElementById('deepclean-targets').innerHTML = rows ||
            `<div style="text-align:center;color:var(--text-muted);padding:24px;">Nothing found.</div>`;
        const applyBtn = document.getElementById('btn-deepclean-apply');
        if (applyBtn) applyBtn.disabled = targets.length === 0;
    },

    async deepcleanReview(opts) {
        opts = opts || {};
        const keys = Array.from(document.querySelectorAll('.deepclean-target:checked')).map(c => c.value);
        if (!keys.length) { this.showNotification('Select at least one target to clean', 'warning'); return; }

        const report = this._deepcleanReport || { targets: [] };
        const chosen = report.targets.filter(t => keys.includes(t.key));
        const total = chosen.reduce((s, t) => s + (t.bytes || 0), 0);
        const highRisk = chosen.filter(t => t.risk === 'high');

        if (!opts.skipConfirm) {
            let msg = `Clean ${keys.length} target(s) and reclaim about ${this._fmtBytes(total)}?\n\n`;
            msg += chosen.map(t => `  • ${t.label} — ${this._fmtBytes(t.bytes)}`).join('\n');
            msg += `\n\nSafety:\n`;
            msg += `  • A System Restore point is created first\n`;
            msg += `  • Files go to the Recycle Bin (recoverable), not a permanent delete\n`;
            msg += `  • Windows, Program Files and cloud-sync folders are excluded\n`;
            if (highRisk.length) {
                msg += `\n⚠ HIGH RISK targets selected:\n`;
                msg += highRisk.map(t => `  • ${t.label}`).join('\n');
                msg += `\nThese changes cannot be reversed.\n`;
            }
            if (!confirm(msg)) return;
        }

        const btn = document.getElementById('btn-deepclean-apply');
        if (btn) { btn.disabled = true; btn.textContent = '⏳ Cleaning…'; }
        document.getElementById('deepclean-progress').style.display = 'block';
        document.getElementById('deepclean-progress').innerHTML =
            `<div style="font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--accent-cyan);">Creating restore point and cleaning…</div>`;

        try {
            const res = await fetch('/api/deepclean/apply', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    confirm: true,
                    targets: keys,
                    proceed_without_restore_point: !!opts.withoutRestorePoint,
                    allow_permanent: !!opts.allowPermanent
                })
            });
            const data = await res.json();
            if (data.status === 'error') {
                this.showNotification(data.message || 'Deep Clean rejected', 'error');
                if (btn) { btn.disabled = false; btn.innerHTML = '🧹 Step 2 — Review & Clean'; }
                return;
            }
            this._pollDeepcleanStatus();
        } catch (e) {
            this.showNotification('Deep Clean failed to start', 'error');
            if (btn) { btn.disabled = false; btn.innerHTML = '🧹 Step 2 — Review & Clean'; }
        }
    },

    _pollDeepcleanStatus() {
        if (this._deepcleanPoller) clearInterval(this._deepcleanPoller);
        this._deepcleanPoller = setInterval(async () => {
            try {
                const res = await fetch('/api/deepclean/status');
                const data = await res.json();
                const prog = document.getElementById('deepclean-progress');
                if (data.status === 'running') {
                    prog.innerHTML = `
                        <div style="font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--accent-cyan);margin-bottom:6px;">
                            ${escapeHtml(data.current || 'Working…')} — ${data.progress || 0}%
                        </div>
                        <div class="progress-bar"><div class="progress-fill" style="width:${data.progress || 0}%"></div></div>`;
                    return;
                }
                clearInterval(this._deepcleanPoller);
                this._deepcleanPoller = null;
                const btn = document.getElementById('btn-deepclean-apply');
                if (btn) { btn.disabled = false; btn.innerHTML = '🧹 Step 2 — Review & Clean'; }
                prog.style.display = 'none';

                if (data.status === 'blocked') {
                    this.renderDeepcleanBlocked(data);
                    return;
                }
                this.renderDeepcleanResults(data);
            } catch (e) { /* keep polling */ }
        }, 1500);
    },

    renderDeepcleanBlocked(data) {
        const el = document.getElementById('deepclean-results');
        el.style.display = 'block';
        el.innerHTML = `
            <div style="padding:16px;background:rgba(245,158,11,0.08);border:1px solid rgba(245,158,11,0.3);border-radius:8px;">
                <div style="font-weight:600;color:var(--accent-yellow);margin-bottom:8px;">⚠ Stopped — no restore point</div>
                <div style="font-size:12px;color:var(--text-secondary);line-height:1.7;margin-bottom:12px;">
                    ${escapeHtml(data.message || 'A System Restore point could not be created.')}
                </div>
                <div style="font-size:12px;color:var(--text-secondary);margin-bottom:12px;">
                    Nothing was deleted. You can continue without a restore point, but the cleanup
                    will not be revertible from System Restore. Files still go to the Recycle Bin.
                </div>
                <button class="btn btn-outline" onclick="App.deepcleanForceWithoutRestorePoint()">Continue without a restore point</button>
            </div>`;
        this.showNotification('Deep Clean stopped — restore point could not be created', 'warning');
    },

    deepcleanForceWithoutRestorePoint() {
        if (!confirm('Continue WITHOUT a System Restore point?\n\nThe cleanup will not be revertible via System Restore. Files will still go to the Recycle Bin where you can recover them individually.')) return;
        document.getElementById('deepclean-results').style.display = 'none';
        this.deepcleanReview({ withoutRestorePoint: true, skipConfirm: true });
    },

    renderDeepcleanResults(data) {
        const el = document.getElementById('deepclean-results');
        el.style.display = 'block';
        const results = data.results || [];
        const rp = data.restore_point || {};
        const rows = results.map(r => `
            <div style="display:flex;gap:12px;align-items:center;padding:10px 14px;border-bottom:1px solid var(--border-color);">
                <div style="flex:1;min-width:0;">
                    <div style="font-weight:600;font-size:12px;">${escapeHtml(r.label)}</div>
                    ${r.note ? `<div style="font-size:10px;color:var(--text-muted);margin-top:3px;font-family:'JetBrains Mono',monospace;">${escapeHtml(r.note)}</div>` : ''}
                    ${(r.blocked && r.blocked.length) ? `<div style="font-size:10px;color:var(--accent-yellow);margin-top:3px;">${r.blocked.length} item(s) skipped by safety rules</div>` : ''}
                    ${(r.errors && r.errors.length) ? `<div style="font-size:10px;color:var(--accent-red);margin-top:3px;">${escapeHtml(r.errors[0].error || '')}</div>` : ''}
                </div>
                <div style="text-align:right;white-space:nowrap;">
                    <div style="font-family:'JetBrains Mono',monospace;font-size:13px;color:var(--accent-green);">${escapeHtml(this._fmtBytes(r.bytes))}</div>
                    <div style="font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--text-muted);">${r.count || 0} item(s)</div>
                </div>
            </div>`).join('');

        el.innerHTML = `
            <div style="padding:14px 16px;background:rgba(16,185,129,0.07);border:1px solid rgba(16,185,129,0.25);border-radius:8px;margin-bottom:12px;">
                <div style="font-weight:600;color:var(--accent-green);">✓ Deep Clean complete — ${escapeHtml(data.bytes_freed_fmt || '0 B')} reclaimed</div>
                <div style="font-size:11px;color:var(--text-secondary);margin-top:6px;font-family:'JetBrains Mono',monospace;">
                    Restore point: ${rp.created ? 'created' : escapeHtml(rp.message || 'not created')}<br>
                    Removed files are in the Recycle Bin and can be restored.
                </div>
            </div>
            ${rows}`;
        this.showNotification(`Deep Clean complete — ${data.bytes_freed_fmt || '0 B'} reclaimed`, 'success');
        this.refreshLogs();
    },
};

document.addEventListener('DOMContentLoaded', () => App.init());
