"""Single-file dark-mode HTML/CSS/JS UI for Control Room."""

CONTROL_ROOM_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cloakroom Control Room</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
            background: #0a0a0a;
            color: #e0e0e0;
            line-height: 1.6;
        }

        .container {
            max-width: 1800px;
            margin: 0 auto;
            padding: 20px;
        }

        /* Header / Command Bar */
        .header {
            background: #1a1a1a;
            border: 1px solid #333;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 15px;
        }

        .status-badge {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 8px 16px;
            background: #0f4c3a;
            border: 1px solid #1a7a5a;
            border-radius: 4px;
            font-size: 14px;
            font-weight: 500;
        }

        .status-dot {
            width: 8px;
            height: 8px;
            background: #2ecc71;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }

        .metrics {
            display: flex;
            gap: 20px;
            flex-wrap: wrap;
        }

        .metric {
            display: flex;
            flex-direction: column;
            gap: 4px;
        }

        .metric-label {
            font-size: 11px;
            text-transform: uppercase;
            color: #888;
            font-weight: 600;
        }

        .metric-value {
            font-size: 18px;
            font-weight: 700;
            color: #fff;
        }

        .toggle {
            padding: 8px 16px;
            background: #2a2a2a;
            border: 1px solid #444;
            border-radius: 4px;
            color: #e0e0e0;
            cursor: pointer;
            font-size: 13px;
            transition: all 0.2s;
        }

        .toggle:hover {
            background: #333;
            border-color: #555;
        }

        .toggle.active {
            background: #3498db;
            border-color: #2980b9;
        }

        /* Main workspace */
        .workspace {
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 20px;
            margin-bottom: 20px;
        }

        @media (max-width: 1200px) {
            .workspace {
                grid-template-columns: 1fr;
            }
        }

        .panel {
            background: #1a1a1a;
            border: 1px solid #333;
            border-radius: 8px;
            overflow: hidden;
        }

        .panel-header {
            padding: 15px 20px;
            background: #222;
            border-bottom: 1px solid #333;
            font-weight: 600;
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .panel-content {
            padding: 20px;
            max-height: 600px;
            overflow-y: auto;
        }

        /* Live feed */
        .event-item {
            background: #252525;
            border: 1px solid #333;
            border-radius: 6px;
            padding: 15px;
            margin-bottom: 15px;
        }

        .event-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }

        .event-type {
            font-weight: 600;
            color: #3498db;
            font-size: 13px;
        }

        .event-time {
            font-size: 11px;
            color: #666;
        }

        .diff-container {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            margin-top: 10px;
        }

        .diff-pane {
            background: #1a1a1a;
            border: 1px solid #333;
            border-radius: 4px;
            padding: 10px;
            font-size: 12px;
            font-family: 'Courier New', monospace;
        }

        .diff-label {
            font-size: 10px;
            text-transform: uppercase;
            color: #888;
            margin-bottom: 5px;
            font-weight: 600;
        }

        .placeholder {
            background: #9b59b6;
            color: #fff;
            padding: 2px 6px;
            border-radius: 3px;
            font-weight: 600;
            font-size: 11px;
        }

        .badge {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 3px;
            font-size: 10px;
            font-weight: 600;
            margin-left: 8px;
        }

        .badge-success {
            background: #2ecc71;
            color: #fff;
        }

        .badge-warning {
            background: #f39c12;
            color: #fff;
        }

        .badge-danger {
            background: #e74c3c;
            color: #fff;
        }

        /* Approvals */
        .approval-card {
            background: #2a1a1a;
            border: 2px solid #d35400;
            border-radius: 6px;
            padding: 15px;
            margin-bottom: 15px;
        }

        .approval-tool {
            font-weight: 700;
            color: #e67e22;
            margin-bottom: 10px;
        }

        .risk-flags {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin: 10px 0;
        }

        .risk-flag {
            padding: 4px 10px;
            background: #c0392b;
            border-radius: 3px;
            font-size: 11px;
            font-weight: 600;
        }

        .approval-actions {
            display: flex;
            gap: 10px;
            margin-top: 15px;
        }

        .btn {
            padding: 10px 20px;
            border: none;
            border-radius: 4px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            font-size: 13px;
        }

        .btn-approve {
            background: #27ae60;
            color: #fff;
        }

        .btn-approve:hover {
            background: #229954;
        }

        .btn-deny {
            background: #c0392b;
            color: #fff;
        }

        .btn-deny:hover {
            background: #a93226;
        }

        .empty-state {
            text-align: center;
            padding: 40px 20px;
            color: #666;
        }

        /* Scrollbar styling */
        ::-webkit-scrollbar {
            width: 10px;
        }

        ::-webkit-scrollbar-track {
            background: #1a1a1a;
        }

        ::-webkit-scrollbar-thumb {
            background: #444;
            border-radius: 5px;
        }

        ::-webkit-scrollbar-thumb:hover {
            background: #555;
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Header / Command Bar -->
        <div class="header">
            <div class="status-badge">
                <div class="status-dot"></div>
                <span>127.0.0.1 Live</span>
            </div>
            
            <div class="metrics">
                <div class="metric">
                    <div class="metric-label">Catalog</div>
                    <div class="metric-value" id="catalog-metric">0 / 0</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Cloaked</div>
                    <div class="metric-value" id="cloaked-count">0</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Leaked</div>
                    <div class="metric-value" id="leak-count">0</div>
                </div>
            </div>

            <button class="toggle" id="reveal-toggle" onclick="toggleReveal()">
                🔒 Reveal Local Values
            </button>
        </div>

        <!-- Main workspace -->
        <div class="workspace">
            <!-- Live feed -->
            <div class="panel">
                <div class="panel-header">Live Feed</div>
                <div class="panel-content" id="live-feed">
                    <div class="empty-state">Waiting for events...</div>
                </div>
            </div>

            <!-- Pending approvals -->
            <div class="panel">
                <div class="panel-header">Pending Approvals</div>
                <div class="panel-content" id="approvals-panel">
                    <div class="empty-state">No pending approvals</div>
                </div>
            </div>
        </div>
    </div>

    <script>
        const TOKEN = '{{TOKEN}}';
        let revealEnabled = false;
        let eventCount = 0;
        let cloakedCount = 0;
        let leakCount = 0;

        function toggleReveal() {
            revealEnabled = !revealEnabled;
            const btn = document.getElementById('reveal-toggle');
            btn.classList.toggle('active', revealEnabled);
            btn.textContent = revealEnabled ? '🔓 Hide Local Values' : '🔒 Reveal Local Values';
        }

        function formatTimestamp(isoString) {
            const date = new Date(isoString);
            return date.toLocaleTimeString();
        }

        function renderEvent(event) {
            const cloudView = JSON.stringify(event.cloud_view, null, 2);
            const hasEntities = event.entities && event.entities.length > 0;
            const tripwireBadge = event.tripwire_passed 
                ? '<span class="badge badge-success">TRIPWIRE ✓</span>'
                : '<span class="badge badge-danger">TRIPWIRE ✗</span>';

            return `
                <div class="event-item">
                    <div class="event-header">
                        <div>
                            <span class="event-type">${event.event_type}</span>
                            ${event.tool_id ? `<span style="color: #888; font-size: 12px;"> → ${event.tool_id}</span>` : ''}
                            ${tripwireBadge}
                            ${event.latency_ms ? `<span class="badge badge-warning">${Math.round(event.latency_ms)}ms</span>` : ''}
                        </div>
                        <div class="event-time">${formatTimestamp(event.timestamp)}</div>
                    </div>
                    ${hasEntities ? `
                        <div style="margin: 10px 0; font-size: 11px;">
                            <strong>Entities:</strong>
                            ${event.entities.map(e => `<span class="placeholder">${e.placeholder}</span>`).join(' ')}
                        </div>
                    ` : ''}
                    <div class="diff-container">
                        <div class="diff-pane">
                            <div class="diff-label">Cloud Saw</div>
                            <pre style="margin: 0; white-space: pre-wrap; word-break: break-word;">${cloudView}</pre>
                        </div>
                        <div class="diff-pane">
                            <div class="diff-label">Laptop Saw</div>
                            <pre style="margin: 0; white-space: pre-wrap; word-break: break-word; ${revealEnabled ? '' : 'filter: blur(4px);'}">${cloudView}</pre>
                        </div>
                    </div>
                </div>
            `;
        }

        function updateMetrics() {
            document.getElementById('cloaked-count').textContent = cloakedCount;
            document.getElementById('leak-count').textContent = leakCount;
        }

        async function loadInitialState() {
            try {
                const response = await fetch(`/api/state?token=${TOKEN}`);
                const data = await response.json();
                
                // Update metrics if we have catalog info
                if (data.history.length > 0) {
                    const latestWithMetrics = data.history.reverse().find(e => e.catalog_metrics);
                    if (latestWithMetrics && latestWithMetrics.catalog_metrics) {
                        const m = latestWithMetrics.catalog_metrics;
                        document.getElementById('catalog-metric').textContent = 
                            `${m.exposed_tools} / ${m.total_tools}`;
                    }
                }

                // Load pending approvals
                updateApprovals(data.pending_approvals);
            } catch (err) {
                console.error('Failed to load initial state:', err);
            }
        }

        function updateApprovals(approvals) {
            const panel = document.getElementById('approvals-panel');
            if (!approvals || approvals.length === 0) {
                panel.innerHTML = '<div class="empty-state">No pending approvals</div>';
                return;
            }

            panel.innerHTML = approvals.map(approval => `
                <div class="approval-card">
                    <div class="approval-tool">${approval.tool_id}</div>
                    <div style="font-size: 12px; color: #888; margin-bottom: 10px;">
                        Effect: <strong style="color: #e67e22;">${approval.effect}</strong> | 
                        Hash: <code style="font-size: 10px;">${approval.payload_hash.slice(0, 12)}...</code>
                    </div>
                    ${approval.risk_flags && approval.risk_flags.length > 0 ? `
                        <div class="risk-flags">
                            ${approval.risk_flags.map(flag => `<div class="risk-flag">${flag}</div>`).join('')}
                        </div>
                    ` : ''}
                    <div class="approval-actions">
                        <button class="btn btn-approve" onclick="approveAction('${approval.approval_id}', '${approval.payload_hash}')">
                            ✓ Approve
                        </button>
                        <button class="btn btn-deny" onclick="denyAction('${approval.approval_id}', '${approval.payload_hash}')">
                            ✗ Deny
                        </button>
                    </div>
                </div>
            `).join('');
        }

        async function approveAction(approvalId, payloadHash) {
            try {
                const response = await fetch(`/api/approvals/${approvalId}/decision?token=${TOKEN}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ approved: true, payload_hash: payloadHash })
                });
                if (response.ok) {
                    await loadInitialState(); // Refresh
                }
            } catch (err) {
                console.error('Failed to approve:', err);
            }
        }

        async function denyAction(approvalId, payloadHash) {
            try {
                const response = await fetch(`/api/approvals/${approvalId}/decision?token=${TOKEN}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ approved: false, payload_hash: payloadHash })
                });
                if (response.ok) {
                    await loadInitialState(); // Refresh
                }
            } catch (err) {
                console.error('Failed to deny:', err);
            }
        }

        function connectEventStream() {
            const eventsUrl = `/api/events?token=${TOKEN}`;
            const eventSource = new EventSource(eventsUrl);

            eventSource.onmessage = (e) => {
                const event = JSON.parse(e.data);
                eventCount++;
                
                if (event.entities && event.entities.length > 0) {
                    cloakedCount += event.entities.length;
                }
                
                if (!event.tripwire_passed) {
                    leakCount++;
                }
                
                updateMetrics();

                // Add to live feed
                const feed = document.getElementById('live-feed');
                if (feed.querySelector('.empty-state')) {
                    feed.innerHTML = '';
                }
                feed.insertAdjacentHTML('afterbegin', renderEvent(event));

                // Keep only last 50 events
                while (feed.children.length > 50) {
                    feed.removeChild(feed.lastChild);
                }

                // Update catalog metrics if present
                if (event.catalog_metrics) {
                    const m = event.catalog_metrics;
                    document.getElementById('catalog-metric').textContent = 
                        `${m.exposed_tools} / ${m.total_tools}`;
                }
            };

            eventSource.onerror = () => {
                console.error('EventSource error, reconnecting in 5s...');
                eventSource.close();
                setTimeout(connectEventStream, 5000);
            };
        }

        // Initialize
        loadInitialState();
        connectEventStream();
    </script>
</body>
</html>
"""
