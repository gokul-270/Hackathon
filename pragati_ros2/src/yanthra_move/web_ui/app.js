// ============================================
// Pragati Arm Simulation — Web UI Application
// ============================================
// Communication: rosbridge (WebSocket) → ROS2 topics
// Same protocol as vehicle_control web_ui

(function () {
    'use strict';

    // ── Constants ──
    const RECONNECT_MS = 3000;
    const PUBLISH_RATE_MS = 200;  // 5 Hz joint command rate

    // ── State ──
    let ros = null;
    let connected = false;
    let reconnectTimer = null;

    // Publishers
    let j3Pub = null, j4Pub = null, j5Pub = null;
    let startSwitchPub = null;
    let armCmdPub = null;

    // Subscribers
    let jointStateSub = null;
    let armResponseSub = null;

    // Publish timer for joint sliders
    let jointPublishTimer = null;
    let pendingJointUpdate = false;

    // ── DOM Elements ──
    const rosbridgeUrl  = document.getElementById('rosbridge-url');
    const connectBtn    = document.getElementById('connect-btn');
    const statusDot     = document.getElementById('status-dot');
    const statusText    = document.getElementById('status-text');

    // Joint sliders & inputs
    const j3Slider = document.getElementById('j3-slider');
    const j3Input  = document.getElementById('j3-input');
    const j4Slider = document.getElementById('j4-slider');
    const j4Input  = document.getElementById('j4-input');
    const j5Slider = document.getElementById('j5-slider');
    const j5Input  = document.getElementById('j5-input');

    // Cotton inputs
    const camX = document.getElementById('cam-x');
    const camY = document.getElementById('cam-y');
    const camZ = document.getElementById('cam-z');
    const l4Pos = document.getElementById('l4-pos');

    // Compensation toggles
    const enableJ4Compensation = document.getElementById('enable-j4-compensation');
    const enablePhiCompensation = document.getElementById('enable-phi-compensation');

    // Buttons
    const homeBtn          = document.getElementById('home-btn');
    const placeCottonBtn   = document.getElementById('place-cotton-btn');
    const removeCottonBtn  = document.getElementById('remove-cotton-btn');
    const computeBtn       = document.getElementById('compute-btn');
    const writeCentroidBtn = document.getElementById('write-centroid-btn');
    const pickCottonBtn    = document.getElementById('pick-cotton-btn');
    const triggerBtn       = document.getElementById('trigger-btn');

    // Telemetry displays
    const jointStatesDiv  = document.getElementById('joint-states');
    const logEntries      = document.getElementById('log-entries');
    const cottonWorldDiv  = document.getElementById('cotton-world-pos');

    // Computed approach cells
    const compArmX  = document.getElementById('comp-arm-x');
    const compArmY  = document.getElementById('comp-arm-y');
    const compArmZ  = document.getElementById('comp-arm-z');
    const compR     = document.getElementById('comp-r');
    const compTheta = document.getElementById('comp-theta');
    const compPhi   = document.getElementById('comp-phi');
    const compJ3    = document.getElementById('comp-j3');
    const compJ4    = document.getElementById('comp-j4');
    const compJ5    = document.getElementById('comp-j5');
    const compReach = document.getElementById('comp-reach');

    // ── Initialize URL ──
    const host = window.location.hostname || 'localhost';
    rosbridgeUrl.value = 'ws://' + host + ':9090';

    // ════════════════════════════════════════════
    // Connection
    // ════════════════════════════════════════════

    function setStatus(state) {
        statusDot.className = 'dot ' + state;
        statusText.textContent = state.charAt(0).toUpperCase() + state.slice(1);
        connected = (state === 'connected');
    }

    function connect() {
        disconnect();
        const url = rosbridgeUrl.value.trim();
        if (!url) return;

        setStatus('reconnecting');
        ros = new ROSLIB.Ros({
            url: url,
            // Increase timeout and keepalive for stability
            transportOptions: {
                maxTimeout: 60000,  // 60 seconds before timeout
            },
            groovyCompatibility: false
        });

        ros.on('connection', function () {
            setStatus('connected');
            clearTimeout(reconnectTimer);
            setupPublishers();
            setupSubscribers();
            startJointPublishing();
            addLog('Connected to ' + url, 'success');
        });

        ros.on('error', function (error) {
            console.warn('ROS connection error:', error);
            setStatus('disconnected');
        });

        ros.on('close', function () {
            setStatus('disconnected');
            stopJointPublishing();
            // Only auto-reconnect if we were previously connected
            if (ros) {
                addLog('Connection lost, reconnecting...', 'warning');
                reconnectTimer = setTimeout(connect, RECONNECT_MS);
            }
        });

        try {
            ros.connect(url);
        } catch (e) {
            console.error('Failed to connect:', e);
            setStatus('disconnected');
            addLog('Connection failed: ' + e.message, 'error');
        }
    }

    function disconnect() {
        clearTimeout(reconnectTimer);
        stopJointPublishing();
        
        // Unsubscribe from topics before closing
        if (jointStateSub) {
            try { jointStateSub.unsubscribe(); } catch (e) {}
            jointStateSub = null;
        }
        if (armResponseSub) {
            try { armResponseSub.unsubscribe(); } catch (e) {}
            armResponseSub = null;
        }
        
        // Close ROS connection
        if (ros) { 
            try { ros.close(); } catch (e) {} 
            ros = null; 
        }
    }

    // ════════════════════════════════════════════
    // Publishers
    // ════════════════════════════════════════════

    function setupPublishers() {
        // QoS settings to match Gazebo bridge expectations (VOLATILE durability, RELIABLE reliability)
        const jointCmdQoS = {
            qos: {
                durability: 0,  // VOLATILE
                reliability: 1, // RELIABLE
                history: 1,     // KEEP_LAST
                depth: 1
            }
        };

        // Publish to _ui topics which are filtered by arm_sim_bridge before going to Gazebo
        // This ensures physical joint limits are enforced
        j3Pub = new ROSLIB.Topic({ 
            ros: ros, 
            name: '/joint3_ui', 
            messageType: 'std_msgs/msg/Float64',
            ...jointCmdQoS
        });
        j4Pub = new ROSLIB.Topic({ 
            ros: ros, 
            name: '/joint4_ui', 
            messageType: 'std_msgs/msg/Float64',
            ...jointCmdQoS
        });
        j5Pub = new ROSLIB.Topic({ 
            ros: ros, 
            name: '/joint5_ui', 
            messageType: 'std_msgs/msg/Float64',
            ...jointCmdQoS
        });
        startSwitchPub = new ROSLIB.Topic({ 
            ros: ros, 
            name: '/start_switch/command', 
            messageType: 'std_msgs/msg/Bool',
            ...jointCmdQoS
        });
        armCmdPub = new ROSLIB.Topic({ 
            ros: ros, 
            name: '/arm_sim/command', 
            messageType: 'std_msgs/msg/String',
            ...jointCmdQoS
        });
    }

    // ════════════════════════════════════════════
    // Subscribers
    // ════════════════════════════════════════════

    function setupSubscribers() {
        // Joint states - throttled to reduce load
        jointStateSub = new ROSLIB.Topic({
            ros: ros, 
            name: '/joint_states',
            messageType: 'sensor_msgs/msg/JointState',
            throttle_rate: 200,  // 200ms = 5Hz (sufficient for UI updates)
            queue_length: 1,      // Only keep latest message
            queue_size: 1
        });
        jointStateSub.subscribe(renderJointStates);

        // Bridge responses
        armResponseSub = new ROSLIB.Topic({
            ros: ros, 
            name: '/arm_sim/response',
            messageType: 'std_msgs/msg/String',
            throttle_rate: 100,   // Increased from 50ms to reduce load
            queue_length: 1,
            queue_size: 1
        });
        armResponseSub.subscribe(handleBridgeResponse);
    }

    // ════════════════════════════════════════════
    // Joint Direct Control
    // ════════════════════════════════════════════

    function publishJoints() {
        if (!connected || !pendingJointUpdate) return;
        pendingJointUpdate = false;

        const j3 = parseFloat(j3Input.value) || 0;
        const j4 = parseFloat(j4Input.value) || 0;
        const j5 = parseFloat(j5Input.value) || 0;

        j3Pub.publish(new ROSLIB.Message({ data: j3 }));
        j4Pub.publish(new ROSLIB.Message({ data: j4 }));
        j5Pub.publish(new ROSLIB.Message({ data: j5 }));
    }

    function startJointPublishing() {
        stopJointPublishing();
        jointPublishTimer = setInterval(publishJoints, PUBLISH_RATE_MS);
    }

    function stopJointPublishing() {
        if (jointPublishTimer) { clearInterval(jointPublishTimer); jointPublishTimer = null; }
    }

    function syncSliderToInput(slider, input) {
        input.value = parseFloat(slider.value).toFixed(3);
        pendingJointUpdate = true;
    }

    function syncInputToSlider(input, slider) {
        const v = parseFloat(input.value);
        if (!isNaN(v)) {
            slider.value = v;
            pendingJointUpdate = true;
        }
    }

    // Bidirectional sync for each joint
    j3Slider.addEventListener('input', function () { syncSliderToInput(j3Slider, j3Input); });
    j3Input.addEventListener('change', function () { syncInputToSlider(j3Input, j3Slider); });
    j4Slider.addEventListener('input', function () { syncSliderToInput(j4Slider, j4Input); });
    j4Input.addEventListener('change', function () { syncInputToSlider(j4Input, j4Slider); });
    j5Slider.addEventListener('input', function () { syncSliderToInput(j5Slider, j5Input); });
    j5Input.addEventListener('change', function () { syncInputToSlider(j5Input, j5Slider); });

    // Home all joints
    homeBtn.addEventListener('click', function () {
        j3Slider.value = 0; j3Input.value = '0.000';
        j4Slider.value = 0; j4Input.value = '0.000';
        j5Slider.value = 0; j5Input.value = '0.000';
        pendingJointUpdate = true;
        addLog('Homing all joints to 0', 'info');
    });

    // ════════════════════════════════════════════
    // Bridge Commands (via /arm_sim/command topic)
    // ════════════════════════════════════════════

    function sendBridgeCommand(cmd) {
        if (!connected || !armCmdPub) {
            addLog('Not connected!', 'error');
            return;
        }
        armCmdPub.publish(new ROSLIB.Message({ data: JSON.stringify(cmd) }));
    }

    // Place Cotton
    placeCottonBtn.addEventListener('click', function () {
        const cmd = {
            action: 'spawn_cotton',
            cam_x: parseFloat(camX.value),
            cam_y: parseFloat(camY.value),
            cam_z: parseFloat(camZ.value),
            l4_pos: parseFloat(l4Pos.value),
            enable_j4_compensation: enableJ4Compensation.checked,
            enable_phi_compensation: enablePhiCompensation.checked
        };
        addLog('Placing cotton... cam(' + cmd.cam_x + ', ' + cmd.cam_y + ', ' + cmd.cam_z + ') L4=' + cmd.l4_pos, 'info');
        sendBridgeCommand(cmd);
    });

    // Remove Cotton
    removeCottonBtn.addEventListener('click', function () {
        sendBridgeCommand({ action: 'remove_cotton' });
        addLog('Removing cotton...', 'info');
        cottonWorldDiv.innerHTML = '<span class="telem-value stale">No cotton placed</span>';
    });

    // Compute Approach
    computeBtn.addEventListener('click', function () {
        const cmd = {
            action: 'compute_approach',
            cam_x: parseFloat(camX.value),
            cam_y: parseFloat(camY.value),
            cam_z: parseFloat(camZ.value),
            enable_j4_compensation: enableJ4Compensation.checked,
            enable_phi_compensation: enablePhiCompensation.checked
        };
        addLog('Computing approach...', 'info');
        sendBridgeCommand(cmd);
    });

    // Write Centroid
    writeCentroidBtn.addEventListener('click', function () {
        const cmd = {
            action: 'write_centroid',
            cam_x: parseFloat(camX.value),
            cam_y: parseFloat(camY.value),
            cam_z: parseFloat(camZ.value)
        };
        addLog('Writing centroid.txt...', 'info');
        sendBridgeCommand(cmd);
    });

    // Pick Cotton (move arm to the cotton)
    pickCottonBtn.addEventListener('click', function () {
        const cmd = {
            action: 'pick_cotton',
            cam_x: parseFloat(camX.value),
            cam_y: parseFloat(camY.value),
            cam_z: parseFloat(camZ.value)
        };
        pickCottonBtn.disabled = true;
        pickCottonBtn.textContent = '🦾 Picking...';
        addLog('🤚 Picking cotton — arm moving...', 'info');
        sendBridgeCommand(cmd);
    });

    // Trigger Start Switch
    triggerBtn.addEventListener('click', function () {
        if (!connected || !startSwitchPub) {
            addLog('Not connected!', 'error');
            return;
        }
        // Auto-write centroid.txt with current UI camera coords before triggering
        // This ensures the file exists when yanthra_move reads it
        var writeCentroidCmd = {
            action: 'write_centroid',
            cam_x: parseFloat(camX.value),
            cam_y: parseFloat(camY.value),
            cam_z: parseFloat(camZ.value)
        };
        sendBridgeCommand(writeCentroidCmd);
        addLog('📝 Auto-writing centroid.txt before start...', 'info');

        // Small delay to let the bridge write the file before yanthra_move reads it
        setTimeout(function () {
            startSwitchPub.publish(new ROSLIB.Message({ data: true }));
            addLog('▶️ Triggered /start_switch/command = true', 'success');
        }, 300);
    });

    // ════════════════════════════════════════════
    // Bridge Response Handler
    // ════════════════════════════════════════════

    function handleBridgeResponse(msg) {
        let data;
        try { data = JSON.parse(msg.data); } catch (e) { return; }

        const action = data.action || '';
        const ok = data.success;
        const message = data.message || '';

        addLog(message, ok ? 'success' : 'error');

        if (action === 'spawn_cotton' && ok) {
            cottonWorldDiv.innerHTML =
                '<div style="color:#66bb6a">✅ Cotton placed</div>' +
                '<div>X: ' + data.world_x + '</div>' +
                '<div>Y: ' + data.world_y + '</div>' +
                '<div>Z: ' + data.world_z + '</div>' +
                '<div style="color:#607d8b;font-size:10px;margin-top:4px">cam(' +
                data.cam_x + ', ' + data.cam_y + ', ' + data.cam_z + ') L4=' + data.l4_pos + '</div>';
        }

        if (action === 'compute_approach' && ok) {
            compArmX.textContent  = data.arm_x + ' m';
            compArmY.textContent  = data.arm_y + ' m';
            compArmZ.textContent  = data.arm_z + ' m';
            compR.textContent     = data.r + ' m';
            compTheta.textContent = data.theta + ' m';
            compPhi.textContent   = data.phi_deg + '° (' + data.phi_rad + ' rad)';
            compJ3.textContent    = data.j3_cmd + ' rot' + (data.j3_ok ? ' ✅' : ' ❌');
            compJ4.textContent    = data.j4_cmd + ' m'   + (data.j4_ok ? ' ✅' : ' ❌');
            compJ5.textContent    = data.j5_cmd + ' m'   + (data.j5_ok ? ' ✅' : ' ❌');
            compReach.textContent = data.reachable ? '✅ Reachable' : '❌ NOT reachable';
            compReach.className   = data.reachable ? 'reach-ok' : 'reach-bad';

            // Color individual joint cells
            compJ3.className = data.j3_ok ? 'reach-ok' : 'reach-bad';
            compJ4.className = data.j4_ok ? 'reach-ok' : 'reach-bad';
            compJ5.className = data.j5_ok ? 'reach-ok' : 'reach-bad';
        }

        if (action === 'pick_cotton') {
            // Re-enable the pick button
            pickCottonBtn.disabled = false;
            pickCottonBtn.textContent = '🤚 Pick Cotton';
            // Update computed values display with arm frame and joints (for both success and failure)
            if (data.j3_cmd !== undefined) {
                console.log('[pick_cotton] Updating UI with:', data);
                if (data.arm_x !== undefined) {
                    compArmX.textContent  = data.arm_x + ' m';
                    compArmY.textContent  = data.arm_y + ' m';
                    compArmZ.textContent  = data.arm_z + ' m';
                }
                compR.textContent     = data.r + ' m';
                compTheta.textContent = data.theta + ' m';
                compPhi.textContent   = data.phi_deg + '°';
                compJ3.textContent    = data.j3_cmd + ' rad';
                compJ4.textContent    = data.j4_cmd + ' m';
                compJ5.textContent    = data.j5_cmd + ' m';
                // Update reachability status
                if (ok) {
                    compReach.textContent = '✅ Picked';
                    compReach.className   = 'reach-ok';
                } else {
                    compReach.textContent = data.reachable ? '✅ Reachable' : '❌ NOT reachable';
                    compReach.className   = data.reachable ? 'reach-ok' : 'reach-bad';
                }
            }
        }
    }

    // ════════════════════════════════════════════
    // Joint States Rendering
    // ════════════════════════════════════════════

    function renderJointStates(msg) {
        let html = '<div class="js-row" style="font-weight:600;color:#90a4ae">' +
                   '<span class="js-name">Joint</span>' +
                   '<span class="js-pos">Position</span>' +
                   '<span class="js-vel">Velocity</span></div>';

        for (let i = 0; i < msg.name.length; i++) {
            const name = msg.name[i];
            const pos = msg.position && msg.position[i] !== undefined
                ? msg.position[i].toFixed(4)
                : '—';
            const vel = msg.velocity && msg.velocity[i] !== undefined
                ? msg.velocity[i].toFixed(3)
                : '—';

            html += '<div class="js-row">' +
                '<span class="js-name">' + name + '</span>' +
                '<span class="js-pos">' + pos + '</span>' +
                '<span class="js-vel">' + vel + '</span></div>';
        }
        jointStatesDiv.innerHTML = html;
    }

    // ════════════════════════════════════════════
    // Status Log
    // ════════════════════════════════════════════

    function addLog(text, type) {
        type = type || 'info';
        const ts = new Date().toLocaleTimeString();
        const entry = document.createElement('div');
        entry.className = 'log-entry ' + type;
        entry.textContent = '[' + ts + '] ' + text;

        logEntries.insertBefore(entry, logEntries.firstChild);

        // Keep max 50 entries
        while (logEntries.children.length > 50) {
            logEntries.removeChild(logEntries.lastChild);
        }
    }

    // ════════════════════════════════════════════
    // Camera View Presets
    // ════════════════════════════════════════════

    document.querySelectorAll('.cam-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var view = btn.dataset.view;
            if (!view) return;

            // Visual active state
            document.querySelectorAll('.cam-btn').forEach(function (b) { b.classList.remove('active'); });
            btn.classList.add('active');

            // Send to bridge
            sendBridgeCommand({ action: 'set_camera_view', view: view });
            addLog('📷 Camera → ' + view, 'info');
        });
    });

    // ════════════════════════════════════════════
    // Event Listeners
    // ════════════════════════════════════════════

    connectBtn.addEventListener('click', connect);
    rosbridgeUrl.addEventListener('keydown', function (e) { if (e.key === 'Enter') connect(); });

    // ════════════════════════════════════════════
    // Init
    // ════════════════════════════════════════════

    setStatus('disconnected');
    addLog('Arm Simulation UI loaded', 'info');
    connect();  // Auto-connect on load

})();
