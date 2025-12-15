"""
Analytics Module for MCP Reddit Server
Standardized analytics tracking following MCP Analytics Standardization Guide
"""

import os
import json
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path

# Configuration
ANALYTICS_DIR = os.environ.get("ANALYTICS_DIR", "/app/data")
ANALYTICS_FILE = os.path.join(ANALYTICS_DIR, "analytics.json")
SAVE_INTERVAL_SECONDS = 60
MAX_RECENT_CALLS = 100


class Analytics:
    """Thread-safe analytics tracking with persistence"""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._data: Dict[str, Any] = self._get_default_data()
        self._load()
        
    def _get_default_data(self) -> Dict[str, Any]:
        """Return default analytics structure"""
        return {
            "serverStartTime": datetime.utcnow().isoformat() + "Z",
            "totalRequests": 0,
            "totalToolCalls": 0,
            "requestsByMethod": {},
            "requestsByEndpoint": {},
            "toolCalls": {},
            "recentToolCalls": [],
            "clientsByIp": {},
            "clientsByUserAgent": {},
            "hourlyRequests": {},
        }
    
    def _ensure_dir(self) -> None:
        """Ensure analytics directory exists"""
        Path(ANALYTICS_DIR).mkdir(parents=True, exist_ok=True)
    
    def _load(self) -> None:
        """Load analytics from disk"""
        try:
            self._ensure_dir()
            if os.path.exists(ANALYTICS_FILE):
                with open(ANALYTICS_FILE, 'r') as f:
                    loaded = json.load(f)
                    # Merge with defaults to ensure all fields exist
                    self._data = {**self._get_default_data(), **loaded}
                    # Preserve original start time
                    if "serverStartTime" in loaded:
                        self._data["serverStartTime"] = loaded["serverStartTime"]
                print(f"📊 Loaded analytics from {ANALYTICS_FILE}")
                print(f"   Total requests: {self._data['totalRequests']}")
            else:
                print(f"📊 No existing analytics file, starting fresh")
                self._save()
        except Exception as e:
            print(f"⚠️ Failed to load analytics: {e}")
    
    def _save(self) -> None:
        """Save analytics to disk"""
        try:
            self._ensure_dir()
            with open(ANALYTICS_FILE, 'w') as f:
                json.dump(self._data, f, indent=2)
        except Exception as e:
            print(f"⚠️ Failed to save analytics: {e}")
    
    def save(self) -> None:
        """Public save method (thread-safe)"""
        with self._lock:
            self._save()
            print(f"💾 Saved analytics to {ANALYTICS_FILE}")
    
    def track_request(self, method: str, endpoint: str, client_ip: str, user_agent: str = "") -> None:
        """Track an HTTP request"""
        with self._lock:
            self._data["totalRequests"] += 1
            
            # Track by method
            self._data["requestsByMethod"][method] = \
                self._data["requestsByMethod"].get(method, 0) + 1
            
            # Track by endpoint (normalize path)
            normalized_endpoint = endpoint.split("?")[0]  # Remove query params
            self._data["requestsByEndpoint"][normalized_endpoint] = \
                self._data["requestsByEndpoint"].get(normalized_endpoint, 0) + 1
            
            # Track by client IP
            self._data["clientsByIp"][client_ip] = \
                self._data["clientsByIp"].get(client_ip, 0) + 1
            
            # Track by user agent (truncate to 50 chars)
            short_agent = (user_agent or "unknown")[:50]
            self._data["clientsByUserAgent"][short_agent] = \
                self._data["clientsByUserAgent"].get(short_agent, 0) + 1
            
            # Track hourly
            hour = datetime.utcnow().isoformat()[:13]  # YYYY-MM-DDTHH
            self._data["hourlyRequests"][hour] = \
                self._data["hourlyRequests"].get(hour, 0) + 1
    
    def track_tool_call(self, tool_name: str, client_ip: str, user_agent: str = "") -> None:
        """Track a tool call"""
        with self._lock:
            self._data["totalToolCalls"] += 1
            
            # Track by tool name
            self._data["toolCalls"][tool_name] = \
                self._data["toolCalls"].get(tool_name, 0) + 1
            
            # Add to recent tool calls
            tool_call = {
                "tool": tool_name,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "clientIp": client_ip,
                "userAgent": (user_agent or "unknown")[:50],
            }
            self._data["recentToolCalls"].insert(0, tool_call)
            
            # Keep only last MAX_RECENT_CALLS
            if len(self._data["recentToolCalls"]) > MAX_RECENT_CALLS:
                self._data["recentToolCalls"] = self._data["recentToolCalls"][:MAX_RECENT_CALLS]
    
    def get_uptime(self) -> str:
        """Calculate server uptime as human-readable string"""
        try:
            start = datetime.fromisoformat(self._data["serverStartTime"].replace("Z", "+00:00"))
            now = datetime.utcnow().replace(tzinfo=start.tzinfo)
            diff = now - start
            
            total_seconds = int(diff.total_seconds())
            days = total_seconds // 86400
            hours = (total_seconds % 86400) // 3600
            minutes = (total_seconds % 3600) // 60
            
            if days > 0:
                return f"{days}d {hours}h {minutes}m"
            elif hours > 0:
                return f"{hours}h {minutes}m"
            else:
                return f"{minutes}m"
        except:
            return "unknown"
    
    def get_data(self) -> Dict[str, Any]:
        """Get a copy of analytics data"""
        with self._lock:
            return dict(self._data)
    
    def get_summary(self) -> Dict[str, Any]:
        """Get analytics summary for API endpoint"""
        with self._lock:
            # Get last 24 hours of hourly data, sorted
            hourly = self._data.get("hourlyRequests", {})
            sorted_hours = sorted(hourly.items(), reverse=True)[:24]
            
            return {
                "server": "Reddit MCP Server",
                "version": "1.0.0",
                "uptime": self.get_uptime(),
                "serverStartTime": self._data["serverStartTime"],
                "totalRequests": self._data["totalRequests"],
                "totalToolCalls": self._data["totalToolCalls"],
                "breakdown": {
                    "byMethod": self._data["requestsByMethod"],
                    "byEndpoint": self._data["requestsByEndpoint"],
                    "byTool": self._data["toolCalls"],
                },
                "recentToolCalls": self._data["recentToolCalls"][:10],
                "hourlyRequests": dict(sorted_hours),
                "topClients": dict(sorted(
                    self._data["clientsByUserAgent"].items(),
                    key=lambda x: x[1],
                    reverse=True
                )[:10]),
            }
    
    def import_data(self, data: Dict[str, Any]) -> None:
        """Import analytics data from backup"""
        with self._lock:
            # Merge counters
            if "totalRequests" in data:
                self._data["totalRequests"] += data["totalRequests"]
            if "totalToolCalls" in data:
                self._data["totalToolCalls"] += data["totalToolCalls"]
            
            # Merge breakdown data
            if "breakdown" in data:
                breakdown = data["breakdown"]
                if "byMethod" in breakdown:
                    for method, count in breakdown["byMethod"].items():
                        self._data["requestsByMethod"][method] = \
                            self._data["requestsByMethod"].get(method, 0) + count
                if "byEndpoint" in breakdown:
                    for endpoint, count in breakdown["byEndpoint"].items():
                        self._data["requestsByEndpoint"][endpoint] = \
                            self._data["requestsByEndpoint"].get(endpoint, 0) + count
                if "byTool" in breakdown:
                    for tool, count in breakdown["byTool"].items():
                        self._data["toolCalls"][tool] = \
                            self._data["toolCalls"].get(tool, 0) + count
            
            # Save immediately
            self._save()


# Global analytics instance
analytics = Analytics()


def get_dashboard_html() -> str:
    """Generate the analytics dashboard HTML"""
    return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reddit MCP - Analytics Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #e0e0e0;
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        .header {
            text-align: center;
            margin-bottom: 30px;
            padding: 20px;
            background: rgba(255,255,255,0.05);
            border-radius: 15px;
            border: 1px solid rgba(255,255,255,0.1);
        }
        .header h1 { color: #ff6b35; font-size: 2em; margin-bottom: 10px; }
        .header .subtitle { color: #888; font-size: 0.9em; }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: rgba(255,255,255,0.05);
            border-radius: 15px;
            padding: 25px;
            text-align: center;
            border: 1px solid rgba(255,255,255,0.1);
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .stat-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
        }
        .stat-card .value {
            font-size: 2.5em;
            font-weight: bold;
            color: #ff6b35;
            margin-bottom: 5px;
        }
        .stat-card .label { color: #888; font-size: 0.9em; text-transform: uppercase; }
        .charts-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .chart-card {
            background: rgba(255,255,255,0.05);
            border-radius: 15px;
            padding: 20px;
            border: 1px solid rgba(255,255,255,0.1);
        }
        .chart-card h3 { color: #ff6b35; margin-bottom: 15px; font-size: 1.1em; }
        .chart-container { position: relative; height: 250px; }
        .recent-activity {
            background: rgba(255,255,255,0.05);
            border-radius: 15px;
            padding: 20px;
            border: 1px solid rgba(255,255,255,0.1);
        }
        .recent-activity h3 { color: #ff6b35; margin-bottom: 15px; }
        .activity-list { list-style: none; }
        .activity-item {
            padding: 12px 15px;
            background: rgba(255,255,255,0.03);
            border-radius: 8px;
            margin-bottom: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.9em;
        }
        .activity-item .tool { color: #4ecdc4; font-weight: 500; }
        .activity-item .time { color: #888; font-size: 0.85em; }
        .refresh-btn {
            position: fixed;
            bottom: 30px;
            right: 30px;
            background: #ff6b35;
            color: white;
            border: none;
            padding: 15px 25px;
            border-radius: 50px;
            cursor: pointer;
            font-size: 1em;
            box-shadow: 0 5px 20px rgba(255,107,53,0.4);
            transition: transform 0.2s;
        }
        .refresh-btn:hover { transform: scale(1.05); }
        .last-updated { text-align: center; color: #666; font-size: 0.8em; margin-top: 20px; }
        @media (max-width: 768px) {
            .charts-grid { grid-template-columns: 1fr; }
            .stat-card .value { font-size: 2em; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Reddit MCP Analytics</h1>
            <div class="subtitle">Real-time server metrics and usage statistics</div>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="value" id="uptime">--</div>
                <div class="label">Uptime</div>
            </div>
            <div class="stat-card">
                <div class="value" id="totalRequests">--</div>
                <div class="label">Total Requests</div>
            </div>
            <div class="stat-card">
                <div class="value" id="totalToolCalls">--</div>
                <div class="label">Tool Calls</div>
            </div>
            <div class="stat-card">
                <div class="value" id="avgPerHour">--</div>
                <div class="label">Avg Requests/Hour</div>
            </div>
        </div>
        
        <div class="charts-grid">
            <div class="chart-card">
                <h3>📈 Tool Usage</h3>
                <div class="chart-container">
                    <canvas id="toolsChart"></canvas>
                </div>
            </div>
            <div class="chart-card">
                <h3>⏰ Hourly Requests (Last 24h)</h3>
                <div class="chart-container">
                    <canvas id="hourlyChart"></canvas>
                </div>
            </div>
            <div class="chart-card">
                <h3>🔗 Requests by Endpoint</h3>
                <div class="chart-container">
                    <canvas id="endpointChart"></canvas>
                </div>
            </div>
            <div class="chart-card">
                <h3>👥 Top Clients</h3>
                <div class="chart-container">
                    <canvas id="clientsChart"></canvas>
                </div>
            </div>
        </div>
        
        <div class="recent-activity">
            <h3>🕐 Recent Tool Calls</h3>
            <ul class="activity-list" id="recentCalls"></ul>
        </div>
        
        <div class="last-updated">Last updated: <span id="lastUpdated">--</span></div>
    </div>
    
    <button class="refresh-btn" onclick="loadData()">🔄 Refresh</button>
    
    <script>
        let toolsChart, hourlyChart, endpointChart, clientsChart;
        const chartColors = ['#ff6b35', '#4ecdc4', '#45b7d1', '#96ceb4', '#ffeaa7', '#dfe6e9', '#fd79a8', '#a29bfe'];
        
        async function loadData() {
            try {
                const basePath = window.location.pathname.replace(/\\/analytics\\/dashboard\\/?$/, '');
                const res = await fetch(basePath + '/analytics');
                const data = await res.json();
                updateDashboard(data);
            } catch (error) {
                console.error('Failed to load analytics:', error);
            }
        }
        
        function updateDashboard(data) {
            // Update stats
            document.getElementById('uptime').textContent = data.uptime || '--';
            document.getElementById('totalRequests').textContent = (data.totalRequests || 0).toLocaleString();
            document.getElementById('totalToolCalls').textContent = (data.totalToolCalls || 0).toLocaleString();
            
            // Calculate avg per hour
            const hourlyData = Object.values(data.hourlyRequests || {});
            const avgPerHour = hourlyData.length > 0 
                ? Math.round(hourlyData.reduce((a, b) => a + b, 0) / hourlyData.length)
                : 0;
            document.getElementById('avgPerHour').textContent = avgPerHour.toLocaleString();
            
            // Update charts
            updateToolsChart(data.breakdown?.byTool || {});
            updateHourlyChart(data.hourlyRequests || {});
            updateEndpointChart(data.breakdown?.byEndpoint || {});
            updateClientsChart(data.topClients || {});
            
            // Update recent calls
            updateRecentCalls(data.recentToolCalls || []);
            
            // Update timestamp
            document.getElementById('lastUpdated').textContent = new Date().toLocaleString();
        }
        
        function updateToolsChart(toolData) {
            const ctx = document.getElementById('toolsChart').getContext('2d');
            const labels = Object.keys(toolData);
            const values = Object.values(toolData);
            
            if (toolsChart) toolsChart.destroy();
            toolsChart = new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: labels,
                    datasets: [{
                        data: values,
                        backgroundColor: chartColors.slice(0, labels.length),
                        borderWidth: 0
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { position: 'right', labels: { color: '#e0e0e0' } }
                    }
                }
            });
        }
        
        function updateHourlyChart(hourlyData) {
            const ctx = document.getElementById('hourlyChart').getContext('2d');
            const sorted = Object.entries(hourlyData).sort((a, b) => a[0].localeCompare(b[0])).slice(-24);
            const labels = sorted.map(([h]) => h.split('T')[1] + ':00');
            const values = sorted.map(([, v]) => v);
            
            if (hourlyChart) hourlyChart.destroy();
            hourlyChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [{
                        label: 'Requests',
                        data: values,
                        borderColor: '#ff6b35',
                        backgroundColor: 'rgba(255, 107, 53, 0.1)',
                        fill: true,
                        tension: 0.4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: { ticks: { color: '#888' }, grid: { color: 'rgba(255,255,255,0.05)' } },
                        y: { ticks: { color: '#888' }, grid: { color: 'rgba(255,255,255,0.05)' } }
                    },
                    plugins: { legend: { display: false } }
                }
            });
        }
        
        function updateEndpointChart(endpointData) {
            const ctx = document.getElementById('endpointChart').getContext('2d');
            const sorted = Object.entries(endpointData).sort((a, b) => b[1] - a[1]).slice(0, 6);
            const labels = sorted.map(([e]) => e);
            const values = sorted.map(([, v]) => v);
            
            if (endpointChart) endpointChart.destroy();
            endpointChart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [{
                        data: values,
                        backgroundColor: chartColors.slice(0, labels.length),
                        borderRadius: 5
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    indexAxis: 'y',
                    scales: {
                        x: { ticks: { color: '#888' }, grid: { color: 'rgba(255,255,255,0.05)' } },
                        y: { ticks: { color: '#888' }, grid: { display: false } }
                    },
                    plugins: { legend: { display: false } }
                }
            });
        }
        
        function updateClientsChart(clientData) {
            const ctx = document.getElementById('clientsChart').getContext('2d');
            const labels = Object.keys(clientData).map(c => c.substring(0, 20) + (c.length > 20 ? '...' : ''));
            const values = Object.values(clientData);
            
            if (clientsChart) clientsChart.destroy();
            clientsChart = new Chart(ctx, {
                type: 'pie',
                data: {
                    labels: labels,
                    datasets: [{
                        data: values,
                        backgroundColor: chartColors.slice(0, labels.length),
                        borderWidth: 0
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { position: 'right', labels: { color: '#e0e0e0' } }
                    }
                }
            });
        }
        
        function updateRecentCalls(calls) {
            const list = document.getElementById('recentCalls');
            if (calls.length === 0) {
                list.innerHTML = '<li class="activity-item"><span>No tool calls yet</span></li>';
                return;
            }
            list.innerHTML = calls.slice(0, 10).map(call => {
                const time = new Date(call.timestamp).toLocaleString();
                return `<li class="activity-item">
                    <span class="tool">${call.tool}</span>
                    <span class="time">${time}</span>
                </li>`;
            }).join('');
        }
        
        // Initial load and auto-refresh
        loadData();
        setInterval(loadData, 30000);
    </script>
</body>
</html>'''
