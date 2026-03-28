// Mock backend for Pragati Web UI Playwright tests
// Serves static files from parent directory and provides WebSocket API
//
// Usage: node mock_backend.js
// Listens on port 8888

const http = require('http');
const fs = require('fs');
const path = require('path');
const { WebSocketServer } = require('ws');

const PORT = parseInt(process.env.MOCK_PORT || '8889', 10);
const STATIC_ROOT = path.resolve(__dirname, '..');

// MIME types for static file serving
const MIME_TYPES = {
    '.html': 'text/html',
    '.css': 'text/css',
    '.js': 'application/javascript',
    '.json': 'application/json',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.svg': 'image/svg+xml',
    '.ico': 'image/x-icon',
};

// Test pattern data
const TEST_PATTERNS = [
    { name: 'letter_P', category: 'letter', estimated_duration: 30 },
    { name: 'circle', category: 'geometric', estimated_duration: 20 },
    { name: 'zigzag', category: 'field', estimated_duration: 45 },
    { name: 'letter_R', category: 'letter', estimated_duration: 35 },
];

// ── HTTP Server (static files) ─────────────────────────────────────

const server = http.createServer((req, res) => {
    // Strip query string
    let urlPath = req.url.split('?')[0];
    if (urlPath === '/') urlPath = '/index.html';

    const filePath = path.join(STATIC_ROOT, urlPath);

    // Security: prevent directory traversal
    if (!filePath.startsWith(STATIC_ROOT)) {
        res.writeHead(403);
        res.end('Forbidden');
        return;
    }

    fs.readFile(filePath, (err, data) => {
        if (err) {
            res.writeHead(404);
            res.end('Not Found');
            return;
        }
        const ext = path.extname(filePath);
        const mime = MIME_TYPES[ext] || 'application/octet-stream';
        res.writeHead(200, { 'Content-Type': mime });
        res.end(data);
    });
});

// ── WebSocket Server ───────────────────────────────────────────────

const wss = new WebSocketServer({ server, path: '/ws' });

wss.on('connection', (ws) => {
    // No auto-send on connect; client sends get_patterns first

    ws.on('close', () => {
        clearPatternTimers(ws);
        movingConnections.delete(ws);
    });

    ws.on('message', (raw) => {
        let msg;
        try {
            msg = JSON.parse(raw.toString());
        } catch (e) {
            return;
        }

        switch (msg.type) {
            case 'ping':
                send(ws, { type: 'pong' });
                break;

            case 'get_patterns':
                send(ws, { type: 'pattern_list', patterns: TEST_PATTERNS });
                break;

            case 'start_pattern':
                handleStartPattern(ws, msg);
                break;

            case 'stop_pattern':
                handleStopPattern(ws);
                break;

            case 'pause_pattern':
                // Cancel pending pattern timers to prevent overriding paused state
                clearPatternTimers(ws);
                send(ws, { type: 'ack', action: 'pause_pattern' });
                send(ws, {
                    type: 'pattern_status',
                    state: 'paused',
                    pattern_name: msg.name || 'unknown',
                    progress_percent: 50,
                    elapsed_time: 5.0,
                    current_segment: 3,
                    total_segments: 6,
                });
                break;

            case 'resume_pattern':
                send(ws, { type: 'ack', action: 'resume_pattern' });
                send(ws, {
                    type: 'pattern_status',
                    state: 'executing',
                    pattern_name: msg.name || 'unknown',
                    progress_percent: 50,
                    elapsed_time: 5.0,
                    current_segment: 3,
                    total_segments: 6,
                });
                // Schedule completion after resume
                {
                    const timers = [];
                    timers.push(setTimeout(() => {
                        send(ws, {
                            type: 'pattern_status',
                            state: 'completed',
                            pattern_name: msg.name || 'unknown',
                            progress_percent: 100,
                            elapsed_time: 10.0,
                            current_segment: 6,
                            total_segments: 6,
                        });
                        send(ws, { type: 'cmd_vel_owner', owner: 'browser' });
                        connectionTimers.delete(ws);
                    }, 1000));
                    connectionTimers.set(ws, timers);
                }
                break;

            case 'set_speed_scale': {
                const clamped = Math.min(2.0, Math.max(0.25, msg.value || 1.0));
                send(ws, { type: 'speed_scale_set', value: clamped });
                break;
            }

            case 'draw_path':
                handleDrawPath(ws, msg);
                break;

            case 'start_recording':
                send(ws, {
                    type: 'recording_status',
                    state: 'recording',
                    filename: 'test.ogv',
                    duration: 0,
                });
                break;

            case 'stop_recording':
                send(ws, {
                    type: 'recording_status',
                    state: 'stopped',
                    filename: 'test.ogv',
                    duration: 5,
                });
                setTimeout(() => {
                    send(ws, {
                        type: 'recording_verified',
                        success: true,
                        filename: 'test.ogv',
                        size_bytes: 12345,
                    });
                }, 100);
                break;

            case 'set_auto_record':
                send(ws, {
                    type: 'auto_record_status',
                    enabled: !!msg.enabled,
                });
                break;

            case 'teleport': {
                const validTargets = ['start', 'end', 'spawn', 'custom'];
                if (validTargets.includes(msg.target)) {
                    send(ws, { type: 'teleport_result', success: true, message: 'Teleport complete' });
                } else {
                    send(ws, { type: 'teleport_result', success: false, message: `Unknown target: ${msg.target}` });
                }
                break;
            }

            case 'precision_move': {
                const validActions = ['forward_1m', 'forward_5m', 'forward_10m', 'turn_left_90', 'turn_right_90'];
                if (!validActions.includes(msg.action)) {
                    send(ws, { type: 'precision_move_status', state: 'failed', progress_percent: 0, message: 'Unknown action' });
                    break;
                }

                // Cancel any existing timers and mark as moving
                clearPatternTimers(ws);
                movingConnections.add(ws);

                // Immediately take cmd_vel ownership
                send(ws, { type: 'cmd_vel_owner', owner: 'backend' });

                const timers = [];

                timers.push(setTimeout(() => {
                    send(ws, { type: 'precision_move_status', state: 'executing', progress_percent: 0 });
                }, 100));

                timers.push(setTimeout(() => {
                    send(ws, { type: 'precision_move_status', state: 'executing', progress_percent: 50 });
                }, 400));

                timers.push(setTimeout(() => {
                    send(ws, { type: 'precision_move_status', state: 'completed', progress_percent: 100 });
                    send(ws, { type: 'cmd_vel_owner', owner: 'browser' });
                    movingConnections.delete(ws);
                    connectionTimers.delete(ws);
                }, 800));

                connectionTimers.set(ws, timers);
                break;
            }

            case 'cancel_move':
                clearPatternTimers(ws);
                movingConnections.delete(ws);
                send(ws, { type: 'precision_move_status', state: 'cancelled', progress_percent: 0 });
                send(ws, { type: 'cmd_vel_owner', owner: 'browser' });
                send(ws, { type: 'ack', action: 'cancel_move' });
                break;

            default:
                break;
        }
    });
});

// ── Message Handlers ───────────────────────────────────────────────

// Track active pattern execution timers per connection so pause/stop can cancel them
const connectionTimers = new Map();

// Track connections currently executing a precision move
const movingConnections = new Set();

function send(ws, obj) {
    if (ws.readyState === 1) { // WebSocket.OPEN
        ws.send(JSON.stringify(obj));
    }
}

function clearPatternTimers(ws) {
    const timers = connectionTimers.get(ws);
    if (timers) {
        timers.forEach(t => clearTimeout(t));
        connectionTimers.delete(ws);
    }
}

function handleStartPattern(ws, msg) {
    // Cancel any existing pattern timers
    clearPatternTimers(ws);

    // 1. Backend takes cmd_vel ownership
    send(ws, { type: 'cmd_vel_owner', owner: 'backend' });

    const patternName = msg.name || 'unknown';
    const timers = [];

    // 2. Progress updates at 0%, 50%, 100%
    timers.push(setTimeout(() => {
        send(ws, {
            type: 'pattern_status',
            state: 'executing',
            pattern_name: patternName,
            progress_percent: 0,
            elapsed_time: 0,
            current_segment: 0,
            total_segments: 6,
        });
    }, 100));

    timers.push(setTimeout(() => {
        send(ws, {
            type: 'pattern_status',
            state: 'executing',
            pattern_name: patternName,
            progress_percent: 50,
            elapsed_time: 5.0,
            current_segment: 3,
            total_segments: 6,
        });
    }, 600));

    timers.push(setTimeout(() => {
        send(ws, {
            type: 'pattern_status',
            state: 'executing',
            pattern_name: patternName,
            progress_percent: 100,
            elapsed_time: 10.0,
            current_segment: 6,
            total_segments: 6,
        });
    }, 1100));

    // 3. Completed + release cmd_vel
    timers.push(setTimeout(() => {
        send(ws, {
            type: 'pattern_status',
            state: 'completed',
            pattern_name: patternName,
            progress_percent: 100,
            elapsed_time: 10.0,
            current_segment: 6,
            total_segments: 6,
        });
        send(ws, { type: 'cmd_vel_owner', owner: 'browser' });
        connectionTimers.delete(ws);
    }, 1600));

    connectionTimers.set(ws, timers);
}

function handleStopPattern(ws) {
    // Cancel pending pattern timers
    clearPatternTimers(ws);

    send(ws, { type: 'ack', action: 'stop_pattern' });
    send(ws, { type: 'cmd_vel_owner', owner: 'browser' });
    send(ws, {
        type: 'pattern_status',
        state: 'stopped',
        pattern_name: '',
        progress_percent: 0,
        elapsed_time: 0,
        current_segment: 0,
        total_segments: 0,
    });
}

function handleDrawPath(ws, msg) {
    const totalSegments = (msg.points && msg.points.length) || 10;

    // 1. Backend takes cmd_vel ownership
    send(ws, { type: 'cmd_vel_owner', owner: 'backend' });

    // 2. Draw progress updates
    setTimeout(() => {
        send(ws, {
            type: 'draw_progress',
            completed_segments: Math.floor(totalSegments / 2),
            total_segments: totalSegments,
        });
    }, 200);

    setTimeout(() => {
        send(ws, {
            type: 'draw_progress',
            completed_segments: totalSegments,
            total_segments: totalSegments,
        });
    }, 400);

    // 3. Completion + release
    setTimeout(() => {
        send(ws, {
            type: 'pattern_status',
            state: 'completed',
            pattern_name: 'drawn_path',
            progress_percent: 100,
            elapsed_time: 5.0,
            current_segment: totalSegments,
            total_segments: totalSegments,
        });
        send(ws, { type: 'cmd_vel_owner', owner: 'browser' });
    }, 600);
}

// ── Start ──────────────────────────────────────────────────────────

server.listen(PORT, () => {
    console.log(`Mock backend ready on port ${PORT}`);
});
