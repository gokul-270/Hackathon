// ============================================
// Pragati Robot Web UI — Application Logic
// ============================================

(function () {
    'use strict';

    // ---- Speed Mode Presets ----
    const SPEED_MODES = {
        slow:   { maxLinear: 0.2, maxAngular: 0.3 },
        medium: { maxLinear: 0.5, maxAngular: 0.8 },
        fast:   { maxLinear: 1.0, maxAngular: 1.5 },
    };

    const DEAD_ZONE = 0.05;          // 5% of joystick radius
    const PUBLISH_RATE_MS = 100;      // 10 Hz cmd_vel publishing
    const RECONNECT_INTERVAL_MS = 3000;
    const BACKEND_RECONNECT_MS = 3000;

    // ---- State ----
    let ros = null;
    let cmdVelPublisher = null;
    let publishInterval = null;
    let reconnectTimer = null;
    let currentSpeedMode = 'slow';
    let estopActive = false;
    let joystickManager = null;
    let joystickSuppressed = false;  // true when backend owns cmd_vel

    // Backend WebSocket
    let backendWs = null;
    let backendReconnectTimer = null;
    let selectedPattern = null;
    let executionState = 'idle'; // idle, executing, paused

    // Drawing state
    let drawingPoints = [];
    let isDrawing = false;
    let drawCompletedSegments = 0;
    let drawTotalSegments = 0;

    // Precision move state
    let precisionMoveActive = false;

    // Sensor stale timers
    let sensorTimers = {};

    // Sensor enable/disable state and topic references
    let sensorEnabled = { imu: true, gps: true, odom: true, camera: true, rtk: true };
    let sensorTopics = {};  // populated in setupSubscriptions()

    // Odometry trail state
    let odomTrail = [];
    const ODOM_TRAIL_MAX = 2000;
    const ODOM_TRAIL_MIN_DIST = 0.05;

    // Current joystick output (before speed scaling)
    let joyNormX = 0;  // -1 to 1, forward positive
    let joyNormZ = 0;  // -1 to 1, left-turn positive

    // ---- DOM Elements ----
    const statusDot = document.getElementById('status-dot');
    const statusText = document.getElementById('status-text');
    const backendDot = document.getElementById('backend-dot');
    const backendText = document.getElementById('backend-text');
    const rosbridgeUrlInput = document.getElementById('rosbridge-url');
    const connectBtn = document.getElementById('connect-btn');
    const estopBtn = document.getElementById('estop-btn');
    const cmdLinearX = document.getElementById('cmd-linear-x');
    const cmdAngularZ = document.getElementById('cmd-angular-z');

    // Telemetry elements
    const telemSteerFront = document.getElementById('steer-front');
    const telemSteerLeft = document.getElementById('steer-left');
    const telemSteerRight = document.getElementById('steer-right');
    const telemVelFront = document.getElementById('vel-front');
    const telemVelLeft = document.getElementById('vel-left');
    const telemVelRight = document.getElementById('vel-right');
    const jointStatesContainer = document.getElementById('joint-states-container');

    // Pattern panel elements
    const execStartBtn = document.getElementById('exec-start-btn');
    const execStopBtn = document.getElementById('exec-stop-btn');
    const execPauseBtn = document.getElementById('exec-pause-btn');
    const speedScaleSlider = document.getElementById('speed-scale-slider');
    const speedScaleValue = document.getElementById('speed-scale-value');
    const execStatusText = document.getElementById('exec-status-text');
    const execProgressFill = document.getElementById('exec-progress-fill');
    const execPatternName = document.getElementById('exec-pattern-name');
    const execElapsed = document.getElementById('exec-elapsed');
    const execSegments = document.getElementById('exec-segments');

    // Recording elements
    const recordBtn = document.getElementById('record-btn');
    const autoRecordCheckbox = document.getElementById('auto-record-checkbox');
    const recIndicator = document.getElementById('rec-indicator');
    const recStatusText = document.getElementById('rec-status-text');

    // Drawing elements
    const drawCanvas = document.getElementById('draw-canvas');
    const drawCtx = drawCanvas.getContext('2d');
    const drawExecuteBtn = document.getElementById('draw-execute-btn');
    const drawClearBtn = document.getElementById('draw-clear-btn');

    // Robot Control elements
    const teleportCustomToggle = document.getElementById('teleport-custom-toggle');
    const teleportCustomInputs = document.getElementById('teleport-custom-inputs');
    const teleportGoBtn = document.getElementById('teleport-go-btn');
    const teleportXInput = document.getElementById('teleport-x');
    const teleportYInput = document.getElementById('teleport-y');
    const teleportYawInput = document.getElementById('teleport-yaw');
    const teleportError = document.getElementById('teleport-error');
    const teleportStatus = document.getElementById('teleport-status');
    const precisionProgressFill = document.getElementById('precision-progress-fill');
    const precisionProgressText = document.getElementById('precision-progress-text');
    const precisionCancelBtn = document.getElementById('precision-cancel-btn');

    // Sensor elements
    const sensorPanel = document.getElementById('sensor-panel');
    const cameraFeed = document.getElementById('camera-feed');
    const cameraFeedWrapper = document.getElementById('camera-feed-wrapper');
    const cameraFullscreenBtn = document.getElementById('camera-fullscreen-btn');
    const odomTrailCanvas = document.getElementById('odom-trail-canvas');
    const odomTrailClearBtn = document.getElementById('odom-trail-clear');

    // Detection feed toggle elements
    const feedToggleRaw = document.getElementById('feed-toggle-raw');
    const feedToggleDetection = document.getElementById('feed-toggle-detection');
    const detectionStatsOverlay = document.getElementById('detection-stats-overlay');
    const detCottonCount = document.getElementById('det-cotton-count');
    const detNotPickableCount = document.getElementById('det-not-pickable-count');
    const detTotalCount = document.getElementById('det-total-count');
    const detProcessingTime = document.getElementById('det-processing-time');

    // ---- Initialize Default URL ----
    function getDefaultUrl() {
        const host = window.location.hostname || 'localhost';
        return 'ws://' + host + ':9090';
    }
    rosbridgeUrlInput.value = getDefaultUrl();

    // ========================================
    // ROS Connection
    // ========================================

    function setConnectionStatus(status) {
        statusDot.className = 'dot ' + status;
        statusText.textContent = status.charAt(0).toUpperCase() + status.slice(1);

        // Mark telemetry stale on disconnect
        if (status === 'disconnected' || status === 'reconnecting') {
            document.querySelectorAll('.telem-value').forEach(function (el) {
                el.classList.add('stale');
            });
        } else {
            document.querySelectorAll('.telem-value').forEach(function (el) {
                el.classList.remove('stale');
            });
        }
    }

    function connect() {
        // Clean up existing connection
        disconnect();

        const url = rosbridgeUrlInput.value.trim();
        if (!url) return;

        setConnectionStatus('reconnecting');

        ros = new ROSLIB.Ros();

        ros.on('connection', function () {
            setConnectionStatus('connected');
            clearReconnectTimer();
            setupPublisher();
            setupSubscriptions();
            startPublishing();
        });

        ros.on('error', function () {
            setConnectionStatus('disconnected');
        });

        ros.on('close', function () {
            setConnectionStatus('disconnected');
            stopPublishing();
            scheduleReconnect();
        });

        ros.connect(url);
    }

    function disconnect() {
        clearReconnectTimer();
        stopPublishing();
        if (ros) {
            try { ros.close(); } catch (e) { /* ignore */ }
            ros = null;
        }
        cmdVelPublisher = null;
    }

    function scheduleReconnect() {
        clearReconnectTimer();
        reconnectTimer = setTimeout(function () {
            setConnectionStatus('reconnecting');
            connect();
        }, RECONNECT_INTERVAL_MS);
    }

    function clearReconnectTimer() {
        if (reconnectTimer) {
            clearTimeout(reconnectTimer);
            reconnectTimer = null;
        }
    }

    // ========================================
    // cmd_vel Publisher
    // ========================================

    function setupPublisher() {
        cmdVelPublisher = new ROSLIB.Topic({
            ros: ros,
            name: '/cmd_vel',
            messageType: 'geometry_msgs/msg/Twist',
        });
    }

    function getScaledVelocity() {
        if (estopActive || joystickSuppressed) {
            return { linear: 0, angular: 0 };
        }
        const mode = SPEED_MODES[currentSpeedMode];
        return {
            linear:  joyNormX * mode.maxLinear,
            angular: joyNormZ * mode.maxAngular,
        };
    }

    function publishCmdVel() {
        if (!cmdVelPublisher || joystickSuppressed) return;

        const vel = getScaledVelocity();
        const msg = new ROSLIB.Message({
            linear:  { x: vel.linear,  y: 0, z: 0 },
            angular: { x: 0, y: 0, z: vel.angular },
        });
        cmdVelPublisher.publish(msg);

        // Update commanded velocity display
        cmdLinearX.textContent = vel.linear.toFixed(2);
        cmdAngularZ.textContent = vel.angular.toFixed(2);
    }

    function startPublishing() {
        if (joystickSuppressed) return;
        stopPublishing();
        publishInterval = setInterval(publishCmdVel, PUBLISH_RATE_MS);
    }

    function stopPublishing() {
        if (publishInterval) {
            clearInterval(publishInterval);
            publishInterval = null;
        }
    }

    // ========================================
    // Joystick Suppression (cmd_vel ownership)
    // ========================================

    function suppressJoystick() {
        joystickSuppressed = true;
        stopPublishing();
        var zone = document.getElementById('joystick-zone');
        if (zone) zone.classList.add('suppressed');
        joyNormX = 0;
        joyNormZ = 0;
        cmdLinearX.textContent = '0.00';
        cmdAngularZ.textContent = '0.00';
    }

    function unsuppressJoystick() {
        joystickSuppressed = false;
        var zone = document.getElementById('joystick-zone');
        if (zone) zone.classList.remove('suppressed');
        if (ros && cmdVelPublisher) {
            startPublishing();
        }
    }

    // ========================================
    // Backend WebSocket Connection
    // ========================================

    function connectBackend() {
        if (backendWs) {
            try { backendWs.close(); } catch (e) { /* ignore */ }
        }

        const host = window.location.hostname || 'localhost';
        const port = window.location.port || '8888';
        const url = 'ws://' + host + ':' + port + '/ws';

        backendWs = new WebSocket(url);

        backendWs.onopen = function () {
            backendDot.className = 'dot connected';
            backendText.textContent = 'Backend';
            clearBackendReconnect();
            // Request pattern list
            backendSend({ type: 'get_patterns' });
            // Sync auto-record state
            backendSend({ type: 'set_auto_record', enabled: autoRecordCheckbox.checked });
        };

        backendWs.onclose = function () {
            backendDot.className = 'dot disconnected';
            backendText.textContent = 'Backend';
            scheduleBackendReconnect();
        };

        backendWs.onerror = function () {
            backendDot.className = 'dot disconnected';
        };

        backendWs.onmessage = function (event) {
            try {
                var msg = JSON.parse(event.data);
                handleBackendMessage(msg);
            } catch (e) {
                console.error('Backend message parse error:', e);
            }
        };
    }

    function backendSend(obj) {
        if (backendWs && backendWs.readyState === WebSocket.OPEN) {
            backendWs.send(JSON.stringify(obj));
        }
    }

    function scheduleBackendReconnect() {
        clearBackendReconnect();
        backendReconnectTimer = setTimeout(connectBackend, BACKEND_RECONNECT_MS);
    }

    function clearBackendReconnect() {
        if (backendReconnectTimer) {
            clearTimeout(backendReconnectTimer);
            backendReconnectTimer = null;
        }
    }

    // ========================================
    // Backend Message Handler
    // ========================================

    function handleBackendMessage(msg) {
        switch (msg.type) {
            case 'pong':
                break;

            case 'pattern_list':
                renderPatternButtons(msg.patterns);
                break;

            case 'cmd_vel_owner':
                if (msg.owner === 'backend') {
                    suppressJoystick();
                } else {
                    unsuppressJoystick();
                }
                break;

            case 'pattern_status':
                updateExecutionStatus(msg);
                break;

            case 'draw_progress':
                updateDrawProgress(msg);
                break;

            case 'recording_status':
                updateRecordingStatus(msg);
                break;

            case 'recording_verified':
                handleRecordingVerified(msg);
                break;

            case 'speed_scale_set':
                speedScaleSlider.value = msg.value;
                speedScaleValue.textContent = msg.value.toFixed(2) + 'x';
                break;

            case 'auto_record_status':
                autoRecordCheckbox.checked = msg.enabled;
                break;

            case 'error':
                console.warn('Backend error:', msg.message);
                execStatusText.textContent = 'Error: ' + msg.message;
                break;

            case 'teleport_result':
                handleTeleportResult(msg);
                break;

            case 'precision_move_status':
                handlePrecisionMoveStatus(msg);
                break;

            case 'ekf_status':
                handleEkfStatus(msg);
                break;

            case 'fusion_toggled':
                handleFusionToggled(msg);
                break;

            case 'ekf_config_updated':
                console.log('EKF config updated:', msg.config);
                break;

            case 'ekf_reset':
                console.log('EKF reset at:', msg.x, msg.y, msg.theta);
                break;

            case 'pattern_trail':
                renderPatternTrail(msg);
                break;

            case 'detection_stats':
                handleDetectionStats(msg);
                break;

            default:
                break;
        }
    }

    // ========================================
    // Pattern Selection & Rendering
    // ========================================

    function renderPatternButtons(patterns) {
        var letterContainer = document.getElementById('letter-patterns');
        var geoContainer = document.getElementById('geometric-patterns');
        var fieldContainer = document.getElementById('field-patterns');

        letterContainer.innerHTML = '';
        geoContainer.innerHTML = '';
        fieldContainer.innerHTML = '';

        // PRAGATI letter names for prominent styling
        var pragatiNames = ['letter_P', 'letter_R', 'letter_A', 'letter_G', 'letter_T', 'letter_I'];

        patterns.forEach(function (p) {
            var btn = document.createElement('button');
            btn.className = 'pattern-btn';
            btn.textContent = p.name.replace('letter_', '').replace('_', ' ');
            btn.dataset.pattern = p.name;
            btn.title = p.name + ' (~' + p.estimated_duration.toFixed(0) + 's)';

            if (pragatiNames.indexOf(p.name) >= 0) {
                btn.classList.add('pragati');
            }

            btn.addEventListener('click', function () {
                selectPattern(p.name);
            });

            if (p.category === 'letter') {
                letterContainer.appendChild(btn);
            } else if (p.category === 'geometric') {
                geoContainer.appendChild(btn);
            } else {
                fieldContainer.appendChild(btn);
            }
        });
    }

    function selectPattern(name) {
        selectedPattern = name;
        // Update button highlighting
        document.querySelectorAll('.pattern-btn').forEach(function (btn) {
            btn.classList.toggle('selected', btn.dataset.pattern === name);
        });
        // Enable start button if idle
        if (executionState === 'idle') {
            execStartBtn.disabled = false;
        }
    }

    // ========================================
    // Execution Controls
    // ========================================

    function updateExecutionControls() {
        switch (executionState) {
            case 'idle':
                execStartBtn.disabled = !selectedPattern;
                execStopBtn.disabled = true;
                execPauseBtn.disabled = true;
                execPauseBtn.textContent = 'Pause';
                break;
            case 'executing':
                execStartBtn.disabled = true;
                execStopBtn.disabled = false;
                execPauseBtn.disabled = false;
                execPauseBtn.textContent = 'Pause';
                break;
            case 'paused':
                execStartBtn.disabled = true;
                execStopBtn.disabled = false;
                execPauseBtn.disabled = false;
                execPauseBtn.textContent = 'Resume';
                break;
        }
    }

    function updateExecutionStatus(msg) {
        executionState = msg.state === 'completed' || msg.state === 'stopped' ? 'idle' : msg.state;
        updateExecutionControls();

        var stateLabel = msg.state.charAt(0).toUpperCase() + msg.state.slice(1);
        execStatusText.textContent = stateLabel;

        var pct = msg.progress_percent || 0;
        execProgressFill.style.width = pct + '%';

        if (msg.pattern_name) {
            execPatternName.textContent = msg.pattern_name;
        }
        if (msg.elapsed_time !== undefined) {
            execElapsed.textContent = msg.elapsed_time.toFixed(1) + 's';
        }
        if (msg.total_segments) {
            execSegments.textContent = (msg.current_segment || 0) + '/' + msg.total_segments;
        }

        if (msg.state === 'completed' || msg.state === 'stopped') {
            // Reset after brief display
            setTimeout(function () {
                if (executionState === 'idle') {
                    execProgressFill.style.width = '0%';
                }
            }, 3000);
        }
    }

    execStartBtn.addEventListener('click', function () {
        if (!selectedPattern) return;
        backendSend({ type: 'start_pattern', name: selectedPattern });
        executionState = 'executing';
        updateExecutionControls();
        execStatusText.textContent = 'Starting...';
    });

    execStopBtn.addEventListener('click', function () {
        backendSend({ type: 'stop_pattern' });
        executionState = 'idle';
        updateExecutionControls();
        execStatusText.textContent = 'Stopping...';
    });

    execPauseBtn.addEventListener('click', function () {
        if (executionState === 'executing') {
            backendSend({ type: 'pause_pattern' });
            executionState = 'paused';
        } else if (executionState === 'paused') {
            backendSend({ type: 'resume_pattern' });
            executionState = 'executing';
        }
        updateExecutionControls();
    });

    // Speed scale slider
    speedScaleSlider.addEventListener('input', function () {
        var val = parseFloat(speedScaleSlider.value);
        speedScaleValue.textContent = val.toFixed(2) + 'x';
        backendSend({ type: 'set_speed_scale', value: val });
    });

    // ========================================
    // Recording Controls
    // ========================================

    let isRecording = false;

    recordBtn.addEventListener('click', function () {
        if (isRecording) {
            backendSend({ type: 'stop_recording' });
        } else {
            backendSend({ type: 'start_recording', name: selectedPattern || 'recording' });
        }
    });

    autoRecordCheckbox.addEventListener('change', function () {
        backendSend({ type: 'set_auto_record', enabled: autoRecordCheckbox.checked });
    });

    function updateRecordingStatus(msg) {
        if (msg.state === 'recording') {
            isRecording = true;
            recordBtn.className = 'rec-recording';
            recordBtn.textContent = 'Stop Rec';
            recIndicator.className = 'rec-active';
            var duration = msg.duration ? msg.duration.toFixed(0) + 's' : '';
            var filename = msg.filename || '';
            recStatusText.textContent = filename + (duration ? ' ' + duration : '');
        } else {
            isRecording = false;
            recordBtn.className = 'rec-idle';
            recordBtn.textContent = 'Record';
            recIndicator.className = 'rec-hidden';
            recStatusText.textContent = msg.filename ? 'Saved: ' + msg.filename : '';
        }
    }

    function handleRecordingVerified(msg) {
        if (msg.success) {
            var sizeKB = (msg.size_bytes / 1024).toFixed(0);
            recStatusText.textContent = msg.filename + ' (' + sizeKB + ' KB)';
        } else {
            recStatusText.textContent = 'Recording failed: ' + (msg.error || 'unknown');
        }
    }

    // ========================================
    // Teleport Controls
    // ========================================

    function handleTeleportResult(msg) {
        teleportStatus.textContent = msg.success ? msg.message || 'Teleport complete' : 'Failed: ' + (msg.message || 'unknown');
        teleportStatus.style.color = msg.success ? '#00e676' : '#ff5252';
        // Re-enable buttons
        document.querySelectorAll('.teleport-btn').forEach(function (btn) { btn.disabled = false; });
        if (teleportGoBtn) teleportGoBtn.disabled = false;
        setTimeout(function () {
            teleportStatus.textContent = '';
            teleportStatus.style.color = '';
        }, 3000);
    }

    // Teleport preset button clicks
    document.querySelectorAll('.teleport-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            if (estopActive) return;
            document.querySelectorAll('.teleport-btn').forEach(function (b) { b.disabled = true; });
            teleportStatus.textContent = 'Teleporting...';
            teleportStatus.style.color = '#ffab00';
            backendSend({ type: 'teleport', target: btn.dataset.target });
        });
    });

    // Custom teleport toggle
    if (teleportCustomToggle) {
        teleportCustomToggle.addEventListener('click', function () {
            teleportCustomInputs.classList.toggle('hidden');
            teleportCustomToggle.textContent = teleportCustomInputs.classList.contains('hidden') ? 'Custom...' : 'Hide';
        });
    }

    // Custom teleport Go button
    if (teleportGoBtn) {
        teleportGoBtn.addEventListener('click', function () {
            if (estopActive) return;
            var x = parseFloat(teleportXInput.value);
            var y = parseFloat(teleportYInput.value);
            var yawDeg = parseFloat(teleportYawInput.value);
            if (isNaN(x) || isNaN(y) || isNaN(yawDeg)) {
                teleportError.textContent = 'Invalid coordinates';
                return;
            }
            teleportError.textContent = '';
            var yawRad = yawDeg * Math.PI / 180;
            teleportGoBtn.disabled = true;
            document.querySelectorAll('.teleport-btn').forEach(function (b) { b.disabled = true; });
            teleportStatus.textContent = 'Teleporting...';
            teleportStatus.style.color = '#ffab00';
            backendSend({ type: 'teleport', target: 'custom', x: x, y: y, yaw: yawRad });
        });
    }

    // ========================================
    // Precision Movement Controls
    // ========================================

    function handlePrecisionMoveStatus(msg) {
        if (msg.state === 'executing') {
            precisionMoveActive = true;
            precisionProgressFill.style.width = msg.progress_percent + '%';
            precisionProgressText.textContent = Math.round(msg.progress_percent) + '%';
            precisionCancelBtn.classList.remove('hidden');
            // Disable precision buttons during move
            document.querySelectorAll('.precision-btn').forEach(function (b) { b.disabled = true; });
        } else {
            precisionMoveActive = false;
            precisionCancelBtn.classList.add('hidden');
            document.querySelectorAll('.precision-btn').forEach(function (b) { b.disabled = false; });
            if (msg.state === 'completed') {
                precisionProgressFill.style.width = '100%';
                precisionProgressText.textContent = 'Done';
            } else if (msg.state === 'cancelled') {
                precisionProgressText.textContent = 'Cancelled';
            } else if (msg.state === 'failed') {
                precisionProgressText.textContent = 'Failed';
            }
            setTimeout(function () {
                precisionProgressFill.style.width = '0%';
                precisionProgressText.textContent = '';
            }, 3000);
        }
        updateRobotControlDisableState();
    }

    // Precision movement button clicks
    document.querySelectorAll('.precision-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            if (estopActive || precisionMoveActive) return;
            backendSend({ type: 'precision_move', action: btn.dataset.action });
            precisionProgressText.textContent = 'Starting...';
        });
    });

    // Cancel precision move
    if (precisionCancelBtn) {
        precisionCancelBtn.addEventListener('click', function () {
            backendSend({ type: 'cancel_move' });
        });
    }

    // Disable state management for robot control buttons
    function updateRobotControlDisableState() {
        var disabled = estopActive || executionState !== 'idle';
        document.querySelectorAll('.teleport-btn').forEach(function (b) {
            b.disabled = disabled;
        });
        if (teleportGoBtn) teleportGoBtn.disabled = disabled;
        document.querySelectorAll('.precision-btn').forEach(function (b) {
            b.disabled = disabled || precisionMoveActive;
        });
    }

    // ========================================
    // Drawing Canvas
    // ========================================

    // Field extents (meters)
    const FIELD_X_MIN = -10, FIELD_X_MAX = 10;
    const FIELD_Y_MIN = -5, FIELD_Y_MAX = 5;

    function canvasToWorld(cx, cy) {
        var rect = drawCanvas.getBoundingClientRect();
        var scaleX = (FIELD_X_MAX - FIELD_X_MIN) / rect.width;
        var scaleY = (FIELD_Y_MAX - FIELD_Y_MIN) / rect.height;
        return {
            x: FIELD_X_MIN + cx * scaleX,
            y: FIELD_Y_MAX - cy * scaleY,  // canvas Y is inverted
        };
    }

    function worldToCanvas(wx, wy) {
        var rect = drawCanvas.getBoundingClientRect();
        var scaleX = rect.width / (FIELD_X_MAX - FIELD_X_MIN);
        var scaleY = rect.height / (FIELD_Y_MAX - FIELD_Y_MIN);
        return {
            x: (wx - FIELD_X_MIN) * scaleX,
            y: (FIELD_Y_MAX - wy) * scaleY,
        };
    }

    function drawGrid() {
        var rect = drawCanvas.getBoundingClientRect();
        drawCanvas.width = rect.width;
        drawCanvas.height = rect.height;

        drawCtx.clearRect(0, 0, drawCanvas.width, drawCanvas.height);

        // Grid lines
        drawCtx.strokeStyle = '#1a3050';
        drawCtx.lineWidth = 0.5;

        // Vertical grid lines (every 2m in X)
        for (var wx = FIELD_X_MIN; wx <= FIELD_X_MAX; wx += 2) {
            var cp = worldToCanvas(wx, 0);
            drawCtx.beginPath();
            drawCtx.moveTo(cp.x, 0);
            drawCtx.lineTo(cp.x, drawCanvas.height);
            drawCtx.stroke();
        }
        // Horizontal grid lines (every 2m in Y)
        for (var wy = FIELD_Y_MIN; wy <= FIELD_Y_MAX; wy += 2) {
            var cp2 = worldToCanvas(0, wy);
            drawCtx.beginPath();
            drawCtx.moveTo(0, cp2.y);
            drawCtx.lineTo(drawCanvas.width, cp2.y);
            drawCtx.stroke();
        }

        // Axis lines
        drawCtx.strokeStyle = '#2a4060';
        drawCtx.lineWidth = 1;
        var origin = worldToCanvas(0, 0);
        drawCtx.beginPath();
        drawCtx.moveTo(origin.x, 0);
        drawCtx.lineTo(origin.x, drawCanvas.height);
        drawCtx.stroke();
        drawCtx.beginPath();
        drawCtx.moveTo(0, origin.y);
        drawCtx.lineTo(drawCanvas.width, origin.y);
        drawCtx.stroke();
    }

    function drawPath(points, color, startIdx, endIdx) {
        if (points.length < 2) return;
        var start = startIdx || 0;
        var end = endIdx !== undefined ? endIdx : points.length;
        if (end - start < 2) return;

        drawCtx.strokeStyle = color;
        drawCtx.lineWidth = 2;
        drawCtx.lineCap = 'round';
        drawCtx.lineJoin = 'round';
        drawCtx.beginPath();

        var first = worldToCanvas(points[start].x, points[start].y);
        drawCtx.moveTo(first.x, first.y);

        for (var i = start + 1; i < end; i++) {
            var cp = worldToCanvas(points[i].x, points[i].y);
            drawCtx.lineTo(cp.x, cp.y);
        }
        drawCtx.stroke();
    }

    function redrawCanvas() {
        drawGrid();
        if (drawingPoints.length >= 2) {
            // Draw traversed portion in green
            if (drawCompletedSegments > 0 && drawTotalSegments > 0) {
                var traversedEnd = Math.min(
                    Math.ceil(drawingPoints.length * drawCompletedSegments / drawTotalSegments),
                    drawingPoints.length
                );
                drawPath(drawingPoints, '#00e676', 0, traversedEnd);
                drawPath(drawingPoints, '#00bcd4', traversedEnd - 1);
            } else {
                drawPath(drawingPoints, '#00bcd4');
            }
        }
    }

    function getCanvasPos(e) {
        var rect = drawCanvas.getBoundingClientRect();
        var x, y;
        if (e.touches) {
            x = e.touches[0].clientX - rect.left;
            y = e.touches[0].clientY - rect.top;
        } else {
            x = e.clientX - rect.left;
            y = e.clientY - rect.top;
        }
        return canvasToWorld(x, y);
    }

    drawCanvas.addEventListener('mousedown', function (e) {
        isDrawing = true;
        drawingPoints = [];
        drawCompletedSegments = 0;
        drawTotalSegments = 0;
        var pt = getCanvasPos(e);
        drawingPoints.push(pt);
    });

    drawCanvas.addEventListener('mousemove', function (e) {
        if (!isDrawing) return;
        var pt = getCanvasPos(e);
        drawingPoints.push(pt);
        redrawCanvas();
    });

    drawCanvas.addEventListener('mouseup', function () {
        isDrawing = false;
        drawExecuteBtn.disabled = drawingPoints.length < 2;
    });

    drawCanvas.addEventListener('mouseleave', function () {
        if (isDrawing) {
            isDrawing = false;
            drawExecuteBtn.disabled = drawingPoints.length < 2;
        }
    });

    // Touch support
    drawCanvas.addEventListener('touchstart', function (e) {
        e.preventDefault();
        isDrawing = true;
        drawingPoints = [];
        drawCompletedSegments = 0;
        drawTotalSegments = 0;
        var pt = getCanvasPos(e);
        drawingPoints.push(pt);
    });

    drawCanvas.addEventListener('touchmove', function (e) {
        e.preventDefault();
        if (!isDrawing) return;
        var pt = getCanvasPos(e);
        drawingPoints.push(pt);
        redrawCanvas();
    });

    drawCanvas.addEventListener('touchend', function (e) {
        e.preventDefault();
        isDrawing = false;
        drawExecuteBtn.disabled = drawingPoints.length < 2;
    });

    drawExecuteBtn.addEventListener('click', function () {
        if (drawingPoints.length < 2) return;
        backendSend({ type: 'draw_path', points: drawingPoints });
        drawExecuteBtn.disabled = true;
        execStatusText.textContent = 'Executing drawing...';
    });

    drawClearBtn.addEventListener('click', function () {
        drawingPoints = [];
        drawCompletedSegments = 0;
        drawTotalSegments = 0;
        drawExecuteBtn.disabled = true;
        redrawCanvas();
    });

    function updateDrawProgress(msg) {
        drawCompletedSegments = msg.completed_segments;
        drawTotalSegments = msg.total_segments;
        redrawCanvas();
    }

    // ========================================
    // Telemetry Subscriptions
    // ========================================

    function subscribeFloat64(topicName, element, formatter) {
        var topic = new ROSLIB.Topic({
            ros: ros,
            name: topicName,
            messageType: 'std_msgs/msg/Float64',
            throttle_rate: 100,  // 10 Hz max
        });
        topic.subscribe(function (msg) {
            element.textContent = formatter(msg.data);
            element.classList.remove('stale');
        });
    }

    function radToDeg(rad) {
        return (rad * 180 / Math.PI).toFixed(1);
    }

    function fmtRadPerSec(val) {
        return val.toFixed(2);
    }

    // ========================================
    // Quaternion to Euler conversion
    // ========================================

    function quaternionToEuler(q) {
        // Roll (x-axis rotation)
        var sinr_cosp = 2.0 * (q.w * q.x + q.y * q.z);
        var cosr_cosp = 1.0 - 2.0 * (q.x * q.x + q.y * q.y);
        var roll = Math.atan2(sinr_cosp, cosr_cosp);

        // Pitch (y-axis rotation)
        var sinp = 2.0 * (q.w * q.y - q.z * q.x);
        var pitch;
        if (Math.abs(sinp) >= 1) {
            pitch = Math.sign(sinp) * Math.PI / 2;
        } else {
            pitch = Math.asin(sinp);
        }

        // Yaw (z-axis rotation)
        var siny_cosp = 2.0 * (q.w * q.z + q.x * q.y);
        var cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z);
        var yaw = Math.atan2(siny_cosp, cosy_cosp);

        return { roll: roll, pitch: pitch, yaw: yaw };
    }

    // ========================================
    // Sensor Stale Detection
    // ========================================

    function markSensorFresh(sensorId) {
        // Clear stale class from elements
        var panelId = sensorId + '-panel';
        var panel = document.getElementById(panelId);
        if (panel) {
            panel.querySelectorAll('.sensor-value').forEach(function (el) {
                el.classList.remove('stale');
            });
        }
        // Reset timer
        if (sensorTimers[sensorId]) {
            clearTimeout(sensorTimers[sensorId]);
        }
        sensorTimers[sensorId] = setTimeout(function () {
            if (panel) {
                panel.querySelectorAll('.sensor-value').forEach(function (el) {
                    el.classList.add('stale');
                });
            }
        }, 3000);
    }

    // ========================================
    // Camera MJPEG Stream (from backend)
    // ========================================

    let cameraStreamActive = false;
    let currentFeedMode = 'raw';  // 'raw' or 'detection'

    function startCameraStream() {
        if (cameraStreamActive) return;
        var backendBase = getBackendBaseUrl();
        if (!backendBase) return;
        var endpoint = currentFeedMode === 'detection'
            ? '/camera/detection_stream'
            : '/camera/stream';
        cameraFeed.src = backendBase + endpoint;
        cameraStreamActive = true;
        cameraFeed.onload = function() {
            if (cameraFeedWrapper) cameraFeedWrapper.classList.add('streaming');
        };
        cameraFeed.onerror = function() {
            cameraStreamActive = false;
            if (cameraFeedWrapper) cameraFeedWrapper.classList.remove('streaming');
            // Retry after a short delay
            setTimeout(startCameraStream, 3000);
        };
    }

    function stopCameraStream() {
        cameraStreamActive = false;
        cameraFeed.src = '';
        if (cameraFeedWrapper) cameraFeedWrapper.classList.remove('streaming');
    }

    function switchFeedMode(mode) {
        if (mode === currentFeedMode && cameraStreamActive) return;
        currentFeedMode = mode;
        // Update toggle button states
        if (feedToggleRaw) feedToggleRaw.classList.toggle('active', mode === 'raw');
        if (feedToggleDetection) feedToggleDetection.classList.toggle('active', mode === 'detection');
        // Show/hide detection stats overlay
        if (detectionStatsOverlay) {
            detectionStatsOverlay.style.display = mode === 'detection' ? 'block' : 'none';
        }
        // Restart stream with new endpoint
        stopCameraStream();
        startCameraStream();
    }

    // Feed toggle button handlers
    if (feedToggleRaw) {
        feedToggleRaw.addEventListener('click', function() { switchFeedMode('raw'); });
    }
    if (feedToggleDetection) {
        feedToggleDetection.addEventListener('click', function() { switchFeedMode('detection'); });
    }

    // Fullscreen toggle
    if (cameraFullscreenBtn) {
        cameraFullscreenBtn.addEventListener('click', function() {
            if (cameraFeedWrapper) {
                cameraFeedWrapper.classList.toggle('fullscreen');
            }
        });
        // Escape key exits fullscreen
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && cameraFeedWrapper && cameraFeedWrapper.classList.contains('fullscreen')) {
                cameraFeedWrapper.classList.remove('fullscreen');
            }
        });
    }

    /** Derive the backend HTTP base URL from the page location */
    function getBackendBaseUrl() {
        var host = window.location.hostname || 'localhost';
        var port = window.location.port || '8888';
        var protocol = window.location.protocol === 'https:' ? 'https:' : 'http:';
        return protocol + '//' + host + ':' + port;
    }

    // ========================================
    // Odometry Trail Mini-Map
    // ========================================

    function updateOdomTrail(x, y, heading) {
        // Only add point if moved enough from last
        if (odomTrail.length > 0) {
            var last = odomTrail[odomTrail.length - 1];
            var dist = Math.hypot(x - last.x, y - last.y);
            if (dist < ODOM_TRAIL_MIN_DIST) {
                // Update heading for current position indicator
                if (odomTrail.length > 0) {
                    odomTrail[odomTrail.length - 1].heading = heading;
                }
                renderOdomTrail();
                return;
            }
        }
        odomTrail.push({ x: x, y: y, heading: heading });
        if (odomTrail.length > ODOM_TRAIL_MAX) {
            odomTrail.shift();
        }
        renderOdomTrail();
    }

    function renderOdomTrail() {
        if (!odomTrailCanvas) return;
        var ctx = odomTrailCanvas.getContext('2d');
        var w = odomTrailCanvas.width;
        var h = odomTrailCanvas.height;
        ctx.clearRect(0, 0, w, h);

        if (odomTrail.length === 0) return;

        // Compute bounding box
        var minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
        odomTrail.forEach(function (p) {
            if (p.x < minX) minX = p.x;
            if (p.x > maxX) maxX = p.x;
            if (p.y < minY) minY = p.y;
            if (p.y > maxY) maxY = p.y;
        });

        // Add padding
        var padding = 2.0; // meters
        minX -= padding;
        maxX += padding;
        minY -= padding;
        maxY += padding;

        // Ensure minimum range
        var rangeX = maxX - minX;
        var rangeY = maxY - minY;
        if (rangeX < 4) { var cx = (minX + maxX) / 2; minX = cx - 2; maxX = cx + 2; rangeX = 4; }
        if (rangeY < 4) { var cy = (minY + maxY) / 2; minY = cy - 2; maxY = cy + 2; rangeY = 4; }

        // Maintain aspect ratio
        var scaleX = (w - 20) / rangeX;
        var scaleY = (h - 20) / rangeY;
        var scale = Math.min(scaleX, scaleY);

        function toPixel(wx, wy) {
            return {
                px: 10 + (wx - minX) * scale,
                py: h - 10 - (wy - minY) * scale  // flip Y
            };
        }

        // Draw grid lines at 1m intervals
        ctx.strokeStyle = '#1a3050';
        ctx.lineWidth = 0.5;
        ctx.font = '9px monospace';
        ctx.fillStyle = '#556677';

        var gridStart = Math.floor(minX);
        var gridEnd = Math.ceil(maxX);
        for (var gx = gridStart; gx <= gridEnd; gx++) {
            var p1 = toPixel(gx, minY);
            var p2 = toPixel(gx, maxY);
            ctx.beginPath();
            ctx.moveTo(p1.px, p1.py);
            ctx.lineTo(p2.px, p2.py);
            ctx.stroke();
            if (gx % 2 === 0) {
                ctx.fillText(gx + '', p1.px + 1, p1.py - 2);
            }
        }
        gridStart = Math.floor(minY);
        gridEnd = Math.ceil(maxY);
        for (var gy = gridStart; gy <= gridEnd; gy++) {
            var p1 = toPixel(minX, gy);
            var p2 = toPixel(maxX, gy);
            ctx.beginPath();
            ctx.moveTo(p1.px, p1.py);
            ctx.lineTo(p2.px, p2.py);
            ctx.stroke();
            if (gy % 2 === 0) {
                ctx.fillText(gy + '', p1.px + 1, p1.py - 2);
            }
        }

        // Draw trail with opacity gradient
        if (odomTrail.length >= 2) {
            for (var i = 1; i < odomTrail.length; i++) {
                var alpha = 0.2 + 0.8 * (i / odomTrail.length);
                ctx.strokeStyle = 'rgba(79, 195, 247, ' + alpha.toFixed(2) + ')';
                ctx.lineWidth = 2;
                var from = toPixel(odomTrail[i - 1].x, odomTrail[i - 1].y);
                var to = toPixel(odomTrail[i].x, odomTrail[i].y);
                ctx.beginPath();
                ctx.moveTo(from.px, from.py);
                ctx.lineTo(to.px, to.py);
                ctx.stroke();
            }
        }

        // Draw current position indicator
        var current = odomTrail[odomTrail.length - 1];
        var cp = toPixel(current.x, current.y);

        // Circle
        ctx.fillStyle = '#4fc3f7';
        ctx.beginPath();
        ctx.arc(cp.px, cp.py, 5, 0, 2 * Math.PI);
        ctx.fill();

        // Heading arrow
        if (current.heading !== undefined) {
            var arrowLen = 12;
            // In canvas: heading 0 = +X = right, but Y is flipped
            var ax = cp.px + arrowLen * Math.cos(current.heading);
            var ay = cp.py - arrowLen * Math.sin(current.heading);
            ctx.strokeStyle = '#00e676';
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.moveTo(cp.px, cp.py);
            ctx.lineTo(ax, ay);
            ctx.stroke();
            // Arrowhead
            var angle = Math.atan2(-(ay - cp.py), ax - cp.px);
            ctx.beginPath();
            ctx.moveTo(ax, ay);
            ctx.lineTo(ax - 6 * Math.cos(angle - 0.4), ay + 6 * Math.sin(angle - 0.4));
            ctx.moveTo(ax, ay);
            ctx.lineTo(ax - 6 * Math.cos(angle + 0.4), ay + 6 * Math.sin(angle + 0.4));
            ctx.stroke();
        }
    }

    // Clear trail button
    if (odomTrailClearBtn) {
        odomTrailClearBtn.addEventListener('click', function () {
            odomTrail = [];
            renderOdomTrail();
        });
    }

    // Pattern panel collapsible toggle
    var patternPanelToggle = document.getElementById('pattern-panel-toggle');
    var patternPanel = document.getElementById('pattern-panel');
    if (patternPanelToggle && patternPanel) {
        patternPanelToggle.addEventListener('click', function () {
            patternPanel.classList.toggle('collapsed');
        });
    }

    // Sensor enable/disable toggles
    document.querySelectorAll('.sensor-toggle input').forEach(function (toggle) {
        toggle.addEventListener('change', function () {
            var sensor = toggle.dataset.sensor;
            sensorEnabled[sensor] = toggle.checked;
            var panel = document.getElementById(sensor + '-panel');
            if (panel) {
                if (toggle.checked) {
                    panel.classList.remove('sensor-disabled');
                } else {
                    panel.classList.add('sensor-disabled');
                    // Reset values to '--' when disabled
                    panel.querySelectorAll('.sensor-value').forEach(function (el) {
                        el.textContent = '--';
                        el.classList.remove('stale');
                    });
                    // Clear stale timer
                    if (sensorTimers[sensor]) {
                        clearTimeout(sensorTimers[sensor]);
                        delete sensorTimers[sensor];
                    }
                }
            }
        });
    });

    // ---- EKF Fusion Toggle ----
    var ekfFusionToggle = document.getElementById('ekf-fusion-toggle');
    if (ekfFusionToggle) {
        ekfFusionToggle.addEventListener('change', function () {
            backendSend({ type: 'toggle_fusion', enabled: ekfFusionToggle.checked });
        });
    }

    // ---- EKF Tuning Sliders — live value display ----
    document.querySelectorAll('#ekf-panel .slider-row input[type="range"]').forEach(function (slider) {
        var valueSpan = slider.parentElement.querySelector('span');
        if (valueSpan) {
            slider.addEventListener('input', function () {
                valueSpan.textContent = parseFloat(slider.value).toFixed(3);
            });
        }
    });

    // ---- EKF Apply Tuning Button ----
    var ekfApplyBtn = document.getElementById('ekf-apply-tuning');
    if (ekfApplyBtn) {
        ekfApplyBtn.addEventListener('click', function () {
            var config = {};
            var alphaEl = document.getElementById('ekf-alpha-imu');
            var qPosEl = document.getElementById('ekf-q-pos');
            var qThetaEl = document.getElementById('ekf-q-theta');
            var rOdomEl = document.getElementById('ekf-r-odom');
            var gpsFloorEl = document.getElementById('ekf-gps-floor');
            var cteKpEl = document.getElementById('ekf-cte-kp');

            if (alphaEl) config.alpha_imu = parseFloat(alphaEl.value);
            if (qPosEl) config.q_pos = parseFloat(qPosEl.value);
            if (qThetaEl) config.q_theta = parseFloat(qThetaEl.value);
            if (rOdomEl) config.r_odom_pos = parseFloat(rOdomEl.value);
            if (gpsFloorEl) config.r_gps_floor = parseFloat(gpsFloorEl.value);
            if (cteKpEl) config.cte_kp = parseFloat(cteKpEl.value);

            backendSend({ type: 'update_ekf_config', config: config });
            console.log('EKF tuning applied:', config);
        });
    }

    // ---- EKF Reset Button ----
    var ekfResetBtn = document.getElementById('ekf-reset-btn');
    if (ekfResetBtn) {
        ekfResetBtn.addEventListener('click', function () {
            backendSend({ type: 'reset_ekf' });
        });
    }

    function setupSubscriptions() {
        // Steering angles (display in degrees)
        subscribeFloat64('/steering/front', telemSteerFront, radToDeg);
        subscribeFloat64('/steering/left', telemSteerLeft, radToDeg);
        subscribeFloat64('/steering/right', telemSteerRight, radToDeg);

        // Wheel velocities (display in rad/s)
        subscribeFloat64('/wheel/front/velocity', telemVelFront, fmtRadPerSec);
        subscribeFloat64('/wheel/left/velocity', telemVelLeft, fmtRadPerSec);
        subscribeFloat64('/wheel/right/velocity', telemVelRight, fmtRadPerSec);

        // Joint states
        var jointStateTopic = new ROSLIB.Topic({
            ros: ros,
            name: '/joint_states',
            messageType: 'sensor_msgs/msg/JointState',
            throttle_rate: 200,  // 5 Hz max
        });
        jointStateTopic.subscribe(function (msg) {
            renderJointStates(msg);
        });

        // ---- Sensor Dashboard Subscriptions ----

        // IMU subscription
        var imuTopic = new ROSLIB.Topic({
            ros: ros,
            name: '/imu',
            messageType: 'sensor_msgs/msg/Imu',
            throttle_rate: 200,
        });
        sensorTopics.imu = imuTopic;
        // Dead-zone threshold for gyro (filters physics jitter when static)
        var GYRO_DEADZONE = 0.005;  // rad/s
        function dz(v) { return Math.abs(v) < GYRO_DEADZONE ? 0 : v; }

        imuTopic.subscribe(function (msg) {
            if (!sensorEnabled.imu) return;
            var euler = quaternionToEuler(msg.orientation);
            document.getElementById('imu-roll').textContent = (euler.roll * 180 / Math.PI).toFixed(1);
            document.getElementById('imu-pitch').textContent = (euler.pitch * 180 / Math.PI).toFixed(1);
            document.getElementById('imu-yaw').textContent = (euler.yaw * 180 / Math.PI).toFixed(1);

            // Gyro with dead-zone to suppress static jitter
            document.getElementById('imu-gyro-x').textContent = dz(msg.angular_velocity.x).toFixed(3);
            document.getElementById('imu-gyro-y').textContent = dz(msg.angular_velocity.y).toFixed(3);
            document.getElementById('imu-gyro-z').textContent = dz(msg.angular_velocity.z).toFixed(3);

            // Gravity-compensated acceleration:
            // A static accelerometer reads +g along the up-axis.
            // Compute gravity contribution in sensor frame: R^T * (0,0,+g)
            // then subtract to get pure dynamic acceleration.
            var q = msg.orientation;
            var g = 9.81;
            var gx =  2.0 * (q.x * q.z + q.w * q.y) * g;
            var gy =  2.0 * (q.y * q.z - q.w * q.x) * g;
            var gz = (1.0 - 2.0 * (q.x * q.x + q.y * q.y)) * g;
            document.getElementById('imu-accel-x').textContent = (msg.linear_acceleration.x - gx).toFixed(2);
            document.getElementById('imu-accel-y').textContent = (msg.linear_acceleration.y - gy).toFixed(2);
            document.getElementById('imu-accel-z').textContent = (msg.linear_acceleration.z - gz).toFixed(2);
            markSensorFresh('imu');
        });

        // NavSat (GPS) subscription
        var navsatTopic = new ROSLIB.Topic({
            ros: ros,
            name: '/navsat',
            messageType: 'sensor_msgs/msg/NavSatFix',
            throttle_rate: 1000,
        });
        sensorTopics.gps = navsatTopic;
        navsatTopic.subscribe(function (msg) {
            if (!sensorEnabled.gps) return;
            document.getElementById('gps-lat').textContent = msg.latitude.toFixed(7);
            document.getElementById('gps-lon').textContent = msg.longitude.toFixed(7);
            document.getElementById('gps-alt').textContent = msg.altitude.toFixed(2);
            markSensorFresh('gps');
        });

        // Odometry subscription
        var odomTopic = new ROSLIB.Topic({
            ros: ros,
            name: '/odom',
            messageType: 'nav_msgs/msg/Odometry',
            throttle_rate: 200,
        });
        sensorTopics.odom = odomTopic;
        // Kinematic-center offset from base-v1 (right rear wheel):
        // 0.65 m forward, 0.90 m kinematic-Y (maps to world -Y at θ=0)
        var KC_FWD = 0.65, KC_LAT = 0.90;

        odomTopic.subscribe(function (msg) {
            if (!sensorEnabled.odom) return;
            var pos = msg.pose.pose.position;
            var euler = quaternionToEuler(msg.pose.pose.orientation);
            // Transform from base-v1 to kinematic center
            var theta = euler.yaw;
            var cosT = Math.cos(theta), sinT = Math.sin(theta);
            var kinX = pos.x + KC_FWD * cosT + KC_LAT * sinT;
            var kinY = pos.y + KC_FWD * sinT - KC_LAT * cosT;
            document.getElementById('odom-x').textContent = kinX.toFixed(2);
            document.getElementById('odom-y').textContent = kinY.toFixed(2);
            document.getElementById('odom-heading').textContent = (euler.yaw * 180 / Math.PI).toFixed(1);
            document.getElementById('odom-lin-vel').textContent = msg.twist.twist.linear.x.toFixed(2);
            document.getElementById('odom-ang-vel').textContent = msg.twist.twist.angular.z.toFixed(3);
            markSensorFresh('odom');

            // Update odometry trail with kinematic center position
            updateOdomTrail(kinX, kinY, euler.yaw);
        });

        // Camera — start MJPEG stream from backend (no rosbridge needed)
        startCameraStream();

        // RTK GPS Fix subscription (corrected position)
        var rtkFixTopic = new ROSLIB.Topic({
            ros: ros,
            name: '/gps/fix',
            messageType: 'sensor_msgs/msg/NavSatFix',
            throttle_rate: 200,
        });
        sensorTopics.rtk = rtkFixTopic;
        rtkFixTopic.subscribe(function (msg) {
            if (!sensorEnabled.rtk) return;
            document.getElementById('rtk-lat').textContent = msg.latitude.toFixed(8);
            document.getElementById('rtk-lon').textContent = msg.longitude.toFixed(8);
            document.getElementById('rtk-alt').textContent = msg.altitude.toFixed(2);
            markSensorFresh('rtk');
        });

        // RTK Status subscription (JSON diagnostics)
        var rtkStatusTopic = new ROSLIB.Topic({
            ros: ros,
            name: '/rtk/status',
            messageType: 'std_msgs/msg/String',
            throttle_rate: 200,
        });
        rtkStatusTopic.subscribe(function (msg) {
            if (!sensorEnabled.rtk) return;
            try {
                var s = JSON.parse(msg.data);
                updateRtkDashboard(s);
            } catch (e) {
                console.warn('RTK status parse error:', e);
            }
        });
    }

    // ========================================
    // RTK Dashboard Update
    // ========================================

    function updateRtkDashboard(s) {
        // Fix badge
        var badge = document.getElementById('rtk-fix-badge');
        badge.textContent = s.fix_state;
        badge.className = 'rtk-fix-badge rtk-state-' + s.fix_state.toLowerCase().replace('_', '-');

        // Satellite count
        document.getElementById('rtk-sats').textContent = '\u{1F6F0}\uFE0F ' + s.satellites;

        // Convergence progress
        var pct = s.convergence_pct || 0;
        document.getElementById('rtk-convergence-fill').style.width = pct + '%';
        document.getElementById('rtk-convergence-pct').textContent = pct.toFixed(0) + '%';

        // Colour the progress bar based on state
        var fill = document.getElementById('rtk-convergence-fill');
        if (s.fix_state === 'RTK_FIXED') {
            fill.className = 'rtk-progress-fill rtk-fill-fixed';
        } else if (s.fix_state === 'FLOAT') {
            fill.className = 'rtk-progress-fill rtk-fill-float';
        } else if (s.fix_state === 'DGPS') {
            fill.className = 'rtk-progress-fill rtk-fill-dgps';
        } else {
            fill.className = 'rtk-progress-fill rtk-fill-searching';
        }

        // Precision
        document.getElementById('rtk-h-acc').textContent = s.horizontal_accuracy_m.toFixed(4);
        document.getElementById('rtk-v-acc').textContent = s.vertical_accuracy_m.toFixed(4);

        // Baseline
        document.getElementById('rtk-baseline-len').textContent = s.baseline_m.toFixed(3);
        document.getElementById('rtk-baseline-az').textContent = s.baseline_azimuth_deg.toFixed(1);
        document.getElementById('rtk-baseline-e').textContent = s.baseline_east_m.toFixed(3);
        document.getElementById('rtk-baseline-n').textContent = s.baseline_north_m.toFixed(3);
        document.getElementById('rtk-baseline-u').textContent = s.baseline_up_m.toFixed(3);

        // Corrections
        document.getElementById('rtk-corr-e').textContent = s.correction_east_m.toFixed(4);
        document.getElementById('rtk-corr-n').textContent = s.correction_north_m.toFixed(4);
        document.getElementById('rtk-corr-u').textContent = s.correction_up_m.toFixed(4);

        // Base station
        document.getElementById('rtk-base-lat').textContent = s.base_lat.toFixed(6);
        document.getElementById('rtk-base-lon').textContent = s.base_lon.toFixed(6);
        document.getElementById('rtk-epoch').textContent = s.epoch;

        // Dropout warning
        if (s.in_dropout) {
            badge.classList.add('rtk-dropout');
        } else {
            badge.classList.remove('rtk-dropout');
        }

        markSensorFresh('rtk');
    }

    // ========================================
    // EKF / Sensor Fusion Dashboard
    // ========================================

    function handleEkfStatus(msg) {
        // Mode badge
        var badge = document.getElementById('ekf-mode-badge');
        if (badge) {
            var mode = msg.mode || 'DISABLED';
            badge.textContent = mode;
            badge.className = 'ekf-mode-badge';
            if (!msg.fusion_enabled) {
                badge.classList.add('disabled');
            } else if (mode === 'ODOM+IMU+GPS') {
                badge.classList.add('full-fusion');
            } else if (mode === 'ODOM+IMU') {
                badge.classList.add('odom-imu');
            } else {
                badge.classList.add('odom-only');
            }
        }

        // Sources
        var srcEl = document.getElementById('ekf-sources');
        if (srcEl) {
            var parts = [];
            if (msg.odom_updates) parts.push('Odom:' + msg.odom_updates);
            if (msg.gps_updates) parts.push('GPS:' + msg.gps_updates);
            if (msg.predictions) parts.push('Pred:' + msg.predictions);
            srcEl.textContent = parts.join(' | ');
        }

        // Fused position
        setEkfValue('ekf-fused-x', msg.fused_x);
        setEkfValue('ekf-fused-y', msg.fused_y);
        setEkfValueDeg('ekf-fused-heading', msg.fused_theta);

        // Drift correction
        setEkfValue('ekf-drift-x', msg.drift_x, true);
        setEkfValue('ekf-drift-y', msg.drift_y, true);
        setEkfValueDeg('ekf-drift-theta', msg.drift_theta, true);

        // GPS local
        setEkfValue('ekf-gps-x', msg.gps_local_x);
        setEkfValue('ekf-gps-y', msg.gps_local_y);

        // Uncertainty (square root of covariance diagonal = std dev)
        var sx = msg.cov_diag ? Math.sqrt(msg.cov_diag[0]) : null;
        var sy = msg.cov_diag ? Math.sqrt(msg.cov_diag[1]) : null;
        var st = msg.cov_diag ? Math.sqrt(msg.cov_diag[2]) : null;
        setEkfValue('ekf-sigma-x', sx);
        setEkfValue('ekf-sigma-y', sy);
        setEkfValueDeg('ekf-sigma-theta', st);

        // Heading divergence warning
        var warnEl = document.getElementById('ekf-heading-warn');
        if (warnEl) {
            if (msg.heading_diverged) {
                warnEl.style.display = 'block';
            } else {
                warnEl.style.display = 'none';
            }
        }

        // Sync the fusion toggle checkbox
        var fusionChk = document.getElementById('ekf-fusion-toggle');
        if (fusionChk && msg.fusion_enabled !== undefined) {
            fusionChk.checked = msg.fusion_enabled;
        }
    }

    function setEkfValue(id, val, signed) {
        var el = document.getElementById(id);
        if (!el) return;
        if (val === null || val === undefined) {
            el.textContent = '--';
        } else {
            el.textContent = (signed && val >= 0 ? '+' : '') + val.toFixed(4);
        }
    }

    function setEkfValueDeg(id, valRad, signed) {
        var el = document.getElementById(id);
        if (!el) return;
        if (valRad === null || valRad === undefined) {
            el.textContent = '--';
        } else {
            var deg = valRad * 180.0 / Math.PI;
            el.textContent = (signed && deg >= 0 ? '+' : '') + deg.toFixed(2) + '\u00B0';
        }
    }

    function handleFusionToggled(msg) {
        var fusionChk = document.getElementById('ekf-fusion-toggle');
        if (fusionChk) fusionChk.checked = msg.enabled;
        console.log('Fusion toggled:', msg.enabled);
    }

    // ========================================
    // Pattern Trail Visualization (Planned vs Actual)
    // ========================================

    function renderPatternTrail(msg) {
        var canvas = document.getElementById('pattern-trail-canvas');
        var info = document.getElementById('pattern-trail-info');
        if (!canvas) return;

        var ctx = canvas.getContext('2d');
        var W = canvas.width;
        var H = canvas.height;

        var planned = msg.planned || [];
        var actual = msg.actual || [];

        if (planned.length < 2 && actual.length < 2) {
            if (info) info.textContent = 'No trail data yet';
            return;
        }

        // Find bounding box of all points
        var allPts = planned.concat(actual);
        var minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
        for (var i = 0; i < allPts.length; i++) {
            if (allPts[i].x < minX) minX = allPts[i].x;
            if (allPts[i].x > maxX) maxX = allPts[i].x;
            if (allPts[i].y < minY) minY = allPts[i].y;
            if (allPts[i].y > maxY) maxY = allPts[i].y;
        }

        // Add padding
        var pad = 0.5;
        minX -= pad; maxX += pad; minY -= pad; maxY += pad;
        var rangeX = maxX - minX || 1;
        var rangeY = maxY - minY || 1;

        // Uniform scale (preserve aspect ratio)
        var margin = 20;
        var scaleX = (W - 2 * margin) / rangeX;
        var scaleY = (H - 2 * margin) / rangeY;
        var scale = Math.min(scaleX, scaleY);

        // Center offset
        var cx = margin + ((W - 2 * margin) - rangeX * scale) / 2;
        var cy = margin + ((H - 2 * margin) - rangeY * scale) / 2;

        function toScreen(pt) {
            return {
                sx: cx + (pt.x - minX) * scale,
                sy: H - (cy + (pt.y - minY) * scale)  // flip Y for screen
            };
        }

        // Clear
        ctx.clearRect(0, 0, W, H);

        // Grid
        ctx.strokeStyle = '#1a2a4a';
        ctx.lineWidth = 0.5;
        var gridStep = 1.0;  // 1m grid
        if (rangeX > 10 || rangeY > 10) gridStep = 2.0;
        for (var gx = Math.ceil(minX / gridStep) * gridStep; gx <= maxX; gx += gridStep) {
            var sp = toScreen({x: gx, y: minY});
            var ep = toScreen({x: gx, y: maxY});
            ctx.beginPath(); ctx.moveTo(sp.sx, sp.sy); ctx.lineTo(ep.sx, ep.sy); ctx.stroke();
        }
        for (var gy = Math.ceil(minY / gridStep) * gridStep; gy <= maxY; gy += gridStep) {
            var sp2 = toScreen({x: minX, y: gy});
            var ep2 = toScreen({x: maxX, y: gy});
            ctx.beginPath(); ctx.moveTo(sp2.sx, sp2.sy); ctx.lineTo(ep2.sx, ep2.sy); ctx.stroke();
        }

        // Draw planned path (cyan, dashed)
        if (planned.length >= 2) {
            ctx.strokeStyle = '#4fc3f7';
            ctx.lineWidth = 2;
            ctx.setLineDash([6, 4]);
            ctx.beginPath();
            var p0 = toScreen(planned[0]);
            ctx.moveTo(p0.sx, p0.sy);
            for (var j = 1; j < planned.length; j++) {
                var pj = toScreen(planned[j]);
                ctx.lineTo(pj.sx, pj.sy);
            }
            ctx.stroke();
            ctx.setLineDash([]);

            // Start marker
            ctx.fillStyle = '#4fc3f7';
            ctx.beginPath(); ctx.arc(p0.sx, p0.sy, 4, 0, Math.PI * 2); ctx.fill();
        }

        // Draw actual trail (green, solid)
        if (actual.length >= 2) {
            ctx.strokeStyle = '#66ff99';
            ctx.lineWidth = 2;
            ctx.beginPath();
            var a0 = toScreen(actual[0]);
            ctx.moveTo(a0.sx, a0.sy);
            for (var k = 1; k < actual.length; k++) {
                var ak = toScreen(actual[k]);
                ctx.lineTo(ak.sx, ak.sy);
            }
            ctx.stroke();

            // End marker
            var aLast = toScreen(actual[actual.length - 1]);
            ctx.fillStyle = '#66ff99';
            ctx.beginPath(); ctx.arc(aLast.sx, aLast.sy, 4, 0, Math.PI * 2); ctx.fill();
        }

        // Compute max deviation
        var maxDev = 0;
        for (var m = 0; m < actual.length && m < planned.length; m++) {
            var d = Math.hypot(actual[m].x - planned[Math.min(m, planned.length - 1)].x,
                               actual[m].y - planned[Math.min(m, planned.length - 1)].y);
            if (d > maxDev) maxDev = d;
        }

        if (info) {
            info.textContent = msg.name + ' — ' + msg.state +
                '  |  Planned: ' + planned.length + ' pts' +
                '  |  Actual: ' + actual.length + ' pts' +
                '  |  Max dev: ' + maxDev.toFixed(3) + 'm';
        }
    }

    function renderJointStates(msg) {
        var html = '<div class="joint-row joint-header">' +
            '<span class="joint-name">Joint</span>' +
            '<span class="joint-pos">Position</span>' +
            '<span class="joint-vel">Velocity</span>' +
            '</div>';

        for (var i = 0; i < msg.name.length; i++) {
            var name = msg.name[i];
            var pos = msg.position && msg.position[i] !== undefined
                ? (msg.position[i] * 180 / Math.PI).toFixed(1) + '\u00B0'
                : '--';
            var vel = msg.velocity && msg.velocity[i] !== undefined
                ? msg.velocity[i].toFixed(2)
                : '--';

            html += '<div class="joint-row">' +
                '<span class="joint-name">' + name + '</span>' +
                '<span class="joint-pos">' + pos + '</span>' +
                '<span class="joint-vel">' + vel + '</span>' +
                '</div>';
        }
        jointStatesContainer.innerHTML = html;
    }

    // ========================================
    // Joystick
    // ========================================

    function initJoystick() {
        var zone = document.getElementById('joystick-zone');

        joystickManager = nipplejs.create({
            zone: zone,
            mode: 'static',
            position: { left: '50%', top: '50%' },
            color: '#4fc3f7',
            size: 200,
            restOpacity: 0.7,
        });

        joystickManager.on('move', function (evt, data) {
            if (estopActive || joystickSuppressed) return;

            var maxDist = 100;
            var normDist = Math.min(data.distance / maxDist, 1.0);

            if (normDist < DEAD_ZONE) {
                joyNormX = 0;
                joyNormZ = 0;
                return;
            }

            var scaledDist = (normDist - DEAD_ZONE) / (1.0 - DEAD_ZONE);
            var angle = data.angle.radian;
            joyNormX =  scaledDist * Math.sin(angle);
            joyNormZ = -scaledDist * Math.cos(angle);
        });

        joystickManager.on('end', function () {
            joyNormX = 0;
            joyNormZ = 0;
        });
    }

    // ========================================
    // E-Stop
    // ========================================

    function toggleEstop() {
        estopActive = !estopActive;

        if (estopActive) {
            estopBtn.className = 'estop-active';
            estopBtn.textContent = 'E-STOP';
            joyNormX = 0;
            joyNormZ = 0;
            publishCmdVel();
            // If backend is executing, send stop
            if (executionState !== 'idle') {
                backendSend({ type: 'stop_pattern' });
            }
            // Also cancel any precision move
            if (precisionMoveActive) {
                backendSend({ type: 'cancel_move' });
            }
            updateRobotControlDisableState();
        } else {
            estopBtn.className = 'estop-inactive';
            estopBtn.textContent = 'E-STOP';
            updateRobotControlDisableState();
        }
    }

    // ========================================
    // Speed Mode
    // ========================================

    function setSpeedMode(mode) {
        currentSpeedMode = mode;
        document.querySelectorAll('.speed-btn').forEach(function (btn) {
            btn.classList.toggle('active', btn.dataset.mode === mode);
        });
    }

    // ========================================
    // Event Listeners
    // ========================================

    connectBtn.addEventListener('click', connect);
    rosbridgeUrlInput.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') connect();
    });

    estopBtn.addEventListener('click', toggleEstop);

    document.querySelectorAll('.speed-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            setSpeedMode(btn.dataset.mode);
        });
    });

    // ========================================
    // Cotton Detection Stats Handler
    // ========================================

    function handleDetectionStats(msg) {
        if (detCottonCount) detCottonCount.textContent = msg.cotton_count || 0;
        if (detNotPickableCount) detNotPickableCount.textContent = msg.not_pickable_count || 0;
        if (detTotalCount) detTotalCount.textContent = msg.total_count || 0;
        if (detProcessingTime) detProcessingTime.textContent = msg.processing_time_ms != null ? msg.processing_time_ms : '--';
        // Auto-enable detection toggle indicator when stream is active
        if (msg.stream_active && feedToggleDetection) {
            feedToggleDetection.classList.add('available');
        }
    }

    // ========================================
    // Initialization
    // ========================================

    initJoystick();
    setConnectionStatus('disconnected');
    updateExecutionControls();

    // Initialize drawing canvas
    // Use ResizeObserver to redraw grid when canvas size changes
    if (typeof ResizeObserver !== 'undefined') {
        new ResizeObserver(function () { redrawCanvas(); }).observe(drawCanvas);
    }
    // Initial grid draw
    setTimeout(function () { redrawCanvas(); }, 100);

    // Auto-connect
    connect();
    connectBackend();

    // Start camera MJPEG stream (independent of rosbridge)
    startCameraStream();

})();
