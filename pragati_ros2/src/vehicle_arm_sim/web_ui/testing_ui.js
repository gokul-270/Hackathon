/* =============================================================================
   Pragati Testing UI — Application Logic
   =============================================================================
   Uses ROSLIB.js (via rosbridge WebSocket) for real-time vehicle and arm
   control.  Backend HTTP is used only for spawn and E-STOP.
   ============================================================================= */

(function () {
    'use strict';

    // =========================================================================
    // Constants
    // =========================================================================
    var SPEED_MODES = {
        slow:   { maxLinear: 0.2, maxAngular: 0.3 },
        medium: { maxLinear: 0.5, maxAngular: 0.8 },
        fast:   { maxLinear: 1.0, maxAngular: 1.5 },
    };
    var DEAD_ZONE     = 0.05;    // 5 % of joystick radius
    var CMD_VEL_HZ    = 10;      // publish rate
    var STATUS_POLL_MS = 3000;   // backend status poll
    var RECONNECT_MS   = 3000;   // rosbridge reconnect interval

    // Arm cosine test — joint limits
    var J3_MIN = -0.9;   // rad (tilt lower limit)
    var J3_MAX =  0.0;   // rad
    var J5_MIN =  0.0;   // m (extend lower limit)
    var J5_MAX =  0.45;  // m (extend upper limit)

    // Arm topic configs: { j3Topic, j4Topic, j5Topic }
    var ARM_CONFIGS = {
        arm1: { j3: '/joint3_cmd',          j4: '/joint4_cmd',          j5: '/joint5_cmd'          },
        arm2: { j3: '/joint3_copy_cmd',     j4: '/joint4_copy_cmd',     j5: '/joint5_copy_cmd'     },
        arm3: { j3: '/arm_joint3_copy1_cmd', j4: '/arm_joint4_copy1_cmd', j5: '/arm_joint5_copy1_cmd' },
    };

    // Test sequence state
    var testRunning  = false;
    var testAborted  = false;

    // Custom sequence state
    var seqRunning = false;
    var seqAborted = false;

    // Cotton position sequence state
    var camSeqRunning = false;
    var camSeqAborted = false;
    var tfReady       = false;
    var tfMatrix      = null;   // 4×4 camera_link → arm_yanthra_link transform

    // Cotton sequence — named constants
    var CAM_SEQ_TF_FRAME_FIXED  = 'camera_link';
    var CAM_SEQ_TF_FRAME_ARM    = 'arm_yanthra_link';
    var CAM_SEQ_J5_OFFSET       = 0.320;   // m — simulation pick-path offset
    var CAM_SEQ_J3_MIN          = -0.9;    // rad
    var CAM_SEQ_J3_MAX          =  0.0;    // rad
    var CAM_SEQ_J4_MIN          = -0.250;  // m
    var CAM_SEQ_J4_MAX          =  0.350;  // m
    var CAM_SEQ_J5_MIN          =  0.0;    // m
    var CAM_SEQ_J5_MAX          =  0.450;  // m

    // Phi compensation constants
    var PHI_ZONE1_MAX_DEG = 50.5;
    var PHI_ZONE2_MAX_DEG = 60.0;
    var PHI_ZONE1_OFFSET  = 0.014;
    var PHI_ZONE2_OFFSET  = 0.0;
    var PHI_ZONE3_OFFSET  = -0.014;
    var PHI_L5_SCALE      = 0.5;
    var PHI_JOINT5_MAX    = 0.450;

    // Running row counter for cam sequence rows
    var camSeqRowCounter = 0;

    // =========================================================================
    // State
    // =========================================================================
    var ros               = null;
    var cmdVelTopic       = null;
    var publishTimer      = null;
    var reconnectTimer    = null;
    var joyManager        = null;
    var rosbridgeConnected = false;
    var currentSpeed      = 'slow';
    var estopActive       = false;

    // Joystick output (normalised −1..+1)
    var joyLinear  = 0;   // forward = +1
    var joyAngular = 0;   // left = +1 (ROS convention)

    // Keyboard drive state
    var keysDown = {};

    // Arm joint ROSLIB topics (created on connect)
    var armTopics = {};

    // =========================================================================
    // DOM References
    // =========================================================================
    var rosDot         = document.getElementById('ros-dot');
    var gzDot          = document.getElementById('gz-dot');
    var kinDot         = document.getElementById('kin-dot');
    var rosbridgeInput = document.getElementById('rosbridge-url');
    var btnConnect     = document.getElementById('btn-connect');
    var btnEstop       = document.getElementById('btn-estop');
    var btnSpawn       = document.getElementById('btn-spawn');
    var btnRespawn     = document.getElementById('btn-respawn');
    var urdfSelect     = document.getElementById('urdf-select');
    var spawnStatus    = document.getElementById('spawn-status');
    var cmdLinearEl    = document.getElementById('cmd-linear');
    var cmdAngularEl   = document.getElementById('cmd-angular');
    var logArea        = document.getElementById('log-area');

    // =========================================================================
    // Logging
    // =========================================================================
    function log(msg, cls) {
        var ts = new Date().toLocaleTimeString();
        var div = document.createElement('div');
        div.textContent = ts + '  ' + msg;
        if (cls) div.className = 'log-' + cls;
        logArea.appendChild(div);
        logArea.scrollTop = logArea.scrollHeight;
        // Keep last 200 lines
        while (logArea.children.length > 200) {
            logArea.removeChild(logArea.firstChild);
        }
    }

    // =========================================================================
    // Rosbridge Connection
    // =========================================================================
    function getDefaultUrl() {
        var host = window.location.hostname || 'localhost';
        return 'ws://' + host + ':9090';
    }

    function connect() {
        var url = rosbridgeInput.value.trim() || getDefaultUrl();
        rosbridgeInput.value = url;

        if (ros) { disconnect(); }

        log('Connecting to ' + url + '...');
        ros = new ROSLIB.Ros({ url: url });

        ros.on('connection', function () {
            rosbridgeConnected = true;
            setRosDot('green');
            log('Connected to rosbridge', 'success');
            setupTopics();
            startPublishing();
        });

        ros.on('error', function (err) {
            log('rosbridge error: ' + (err.message || err), 'error');
            setRosDot('red');
        });

        ros.on('close', function () {
            rosbridgeConnected = false;
            setRosDot('red');
            log('rosbridge disconnected', 'warn');
            stopPublishing();
            scheduleReconnect();
        });
    }

    function disconnect() {
        stopPublishing();
        if (ros) {
            try { ros.close(); } catch (e) { /* ignore */ }
            ros = null;
        }
        rosbridgeConnected = false;
        setRosDot('red');
    }

    function scheduleReconnect() {
        clearTimeout(reconnectTimer);
        reconnectTimer = setTimeout(function () {
            if (!rosbridgeConnected) { connect(); }
        }, RECONNECT_MS);
    }

    function setRosDot(cls) {
        rosDot.className = 'dot ' + cls;
    }

    // =========================================================================
    // ROS2 Topics Setup
    // =========================================================================
    function setupTopics() {
        // ---- cmd_vel publisher ----
        cmdVelTopic = new ROSLIB.Topic({
            ros: ros,
            name: '/cmd_vel',
            messageType: 'geometry_msgs/msg/Twist',
        });

        // ---- Arm joint publishers ----
        var armTopicNames = [
            '/joint3_cmd', '/joint4_cmd', '/joint5_cmd',
            '/joint3_copy_cmd', '/joint4_copy_cmd', '/joint5_copy_cmd',
            '/arm_joint3_copy1_cmd', '/arm_joint4_copy1_cmd', '/arm_joint5_copy1_cmd',
        ];
        armTopicNames.forEach(function (name) {
            armTopics[name] = new ROSLIB.Topic({
                ros: ros,
                name: name,
                messageType: 'std_msgs/msg/Float64',
            });
        });

        // ---- Subscribe: /joint_states ----
        var jointStateSub = new ROSLIB.Topic({
            ros: ros,
            name: '/joint_states',
            messageType: 'sensor_msgs/msg/JointState',
        });
        jointStateSub.subscribe(onJointStates);

        // ---- Subscribe: /odom ----
        var odomSub = new ROSLIB.Topic({
            ros: ros,
            name: '/odom',
            messageType: 'nav_msgs/msg/Odometry',
        });
        odomSub.subscribe(onOdom);

        log('ROS2 topics set up (' + (2 + armTopicNames.length) + ' publishers, 2 subscribers)');

        // Set up TF subscriber for cotton sequence
        setupTfSubscriber();
    }

    // =========================================================================
    // cmd_vel Publishing (10 Hz)
    // =========================================================================
    function startPublishing() {
        stopPublishing();
        publishTimer = setInterval(publishCmdVel, 1000 / CMD_VEL_HZ);
    }

    function stopPublishing() {
        if (publishTimer) {
            clearInterval(publishTimer);
            publishTimer = null;
        }
    }

    function publishCmdVel() {
        if (!cmdVelTopic || !rosbridgeConnected) return;

        var lin = 0;
        var ang = 0;

        if (!estopActive) {
            var mode = SPEED_MODES[currentSpeed];
            // Combine joystick + keyboard
            var kbLin = 0;
            var kbAng = 0;
            if (keysDown['ArrowUp'] || keysDown['w'])    kbLin += 1;
            if (keysDown['ArrowDown'] || keysDown['s'])  kbLin -= 1;
            if (keysDown['ArrowLeft'] || keysDown['a'])  kbAng += 1;
            if (keysDown['ArrowRight'] || keysDown['d']) kbAng -= 1;

            // Use joystick if active, else keyboard
            var useLin = Math.abs(joyLinear)  > 0.01 ? joyLinear  : kbLin;
            var useAng = Math.abs(joyAngular) > 0.01 ? joyAngular : kbAng;

            lin = useLin * mode.maxLinear;
            ang = useAng * mode.maxAngular;
        }

        var msg = new ROSLIB.Message({
            linear:  { x: lin, y: 0, z: 0 },
            angular: { x: 0,   y: 0, z: ang },
        });
        cmdVelTopic.publish(msg);

        // Update display
        cmdLinearEl.textContent  = lin.toFixed(2);
        cmdAngularEl.textContent = ang.toFixed(2);
    }

    // =========================================================================
    // Arm Joint Publishing (via sliders)
    // =========================================================================
    function setupArmSliders() {
        var sliders = document.querySelectorAll('.joint-slider');
        sliders.forEach(function (slider) {
            var topicName = slider.getAttribute('data-topic');
            var valEl = document.getElementById('val-' + slider.id.replace('slider-', ''));

            // Debounced publish
            var debounce = null;
            slider.addEventListener('input', function () {
                var val = parseFloat(slider.value);
                if (valEl) valEl.textContent = val.toFixed(3);

                clearTimeout(debounce);
                debounce = setTimeout(function () {
                    publishArmJoint(topicName, val);
                }, 50);
            });
        });

        // Reset buttons
        document.querySelectorAll('[data-reset-arm]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var arm = btn.getAttribute('data-reset-arm');
                resetArm(arm);
            });
        });
    }

    function publishArmJoint(topicName, value) {
        if (!rosbridgeConnected || estopActive) {
            console.warn('[ARM] Blocked: connected=' + rosbridgeConnected + ' estop=' + estopActive);
            return;
        }
        var topic = armTopics[topicName];
        if (!topic) {
            console.error('[ARM] No publisher for topic: ' + topicName);
            return;
        }
        console.log('[ARM] Publishing ' + value.toFixed(3) + ' to ' + topicName);
        topic.publish(new ROSLIB.Message({ data: value }));
    }

    function resetArm(arm) {
        var suffix = (arm === 'arm2') ? '_copy' : (arm === 'arm3') ? '_copy1' : '';
        var joints = ['joint3', 'joint4', 'joint5'];
        joints.forEach(function (j) {
            var sliderId = 'slider-' + j + suffix;
            var slider = document.getElementById(sliderId);
            if (!slider) return;
            // Reset to 0 (or min if 0 is out of range)
            var min = parseFloat(slider.min);
            var max = parseFloat(slider.max);
            var resetVal = (min <= 0 && max >= 0) ? 0 : min;
            slider.value = resetVal;
            slider.dispatchEvent(new Event('input'));
        });
        log('Reset ' + arm + ' to zero');
    }

    // =========================================================================
    // Joint State Callback
    // =========================================================================
    // Mapping from URDF joint names to telemetry display IDs
    var JOINT_DISPLAY_MAP = {
        // Vehicle steering
        'base-plate-front_Revolute-14': { id: 'telem-steer-front', deg: true },
        'base-plate-right_Revolute-18': { id: 'telem-steer-left', deg: true },
        'base-plate-left_Revolute-20':  { id: 'telem-steer-right', deg: true },
        // Vehicle wheels
        'axial-front_Revolute-10': { id: 'telem-wheel-front', suffix: ' rad/s' },
        'axial-right_Revolute-19': { id: 'telem-wheel-left', suffix: ' rad/s' },
        'axial-left_Revolute-21':  { id: 'telem-wheel-right', suffix: ' rad/s' },
        // Arm 1
        'arm_joint3': { id: 'telem-arm_joint3', suffix: ' rad' },
        'arm_joint4': { id: 'telem-arm_joint4', suffix: ' m' },
        'arm_joint5': { id: 'telem-arm_joint5', suffix: ' m' },
        // Arm 2
        'arm_joint3_copy': { id: 'telem-arm_joint3_copy', suffix: ' rad' },
        'arm_joint4_copy': { id: 'telem-arm_joint4_copy', suffix: ' m' },
        'arm_joint5_copy': { id: 'telem-arm_joint5_copy', suffix: ' m' },
        // Arm 3
        'arm_joint3_copy1': { id: 'telem-arm_joint3_copy1', suffix: ' rad' },
        'arm_joint4_copy1': { id: 'telem-arm_joint4_copy1', suffix: ' m' },
        'arm_joint5_copy1': { id: 'telem-arm_joint5_copy1', suffix: ' m' },
    };

    function onJointStates(msg) {
        if (!msg.name || !msg.position) return;
        for (var i = 0; i < msg.name.length; i++) {
            var info = JOINT_DISPLAY_MAP[msg.name[i]];
            if (!info) continue;
            var el = document.getElementById(info.id);
            if (!el) continue;
            var val = msg.position[i];
            if (info.deg) {
                el.textContent = (val * 180 / Math.PI).toFixed(1) + '°';
            } else {
                el.textContent = val.toFixed(3) + (info.suffix || '');
            }
        }
    }

    // =========================================================================
    // Odometry Callback
    // =========================================================================
    function onOdom(msg) {
        var pos = msg.pose.pose.position;
        var q = msg.pose.pose.orientation;
        var vx = msg.twist.twist.linear.x;
        var wz = msg.twist.twist.angular.z;

        // Yaw from quaternion
        var siny = 2 * (q.w * q.z + q.x * q.y);
        var cosy = 1 - 2 * (q.y * q.y + q.z * q.z);
        var yaw = Math.atan2(siny, cosy);

        setTelem('telem-odom-x', pos.x.toFixed(2) + ' m');
        setTelem('telem-odom-y', pos.y.toFixed(2) + ' m');
        setTelem('telem-odom-theta', (yaw * 180 / Math.PI).toFixed(1) + '°');
        setTelem('telem-odom-speed', Math.sqrt(vx * vx).toFixed(2) + ' m/s');
    }

    function setTelem(id, text) {
        var el = document.getElementById(id);
        if (el) el.textContent = text;
    }

    // =========================================================================
    // Joystick (nipplejs)
    // =========================================================================
    function setupJoystick() {
        var zone = document.getElementById('joystick-zone');
        joyManager = nipplejs.create({
            zone: zone,
            mode: 'static',
            position: { left: '50%', top: '50%' },
            color: '#4fc3f7',
            size: 120,
            restOpacity: 0.7,
        });

        joyManager.on('move', function (evt, data) {
            if (estopActive) return;
            var force = Math.min(data.force, 1.0);
            if (force < DEAD_ZONE) {
                joyLinear = 0;
                joyAngular = 0;
                return;
            }
            // nipplejs angle: 0=right, 90=up, 180=left, 270=down (radians)
            var angle = data.angle.radian;
            joyLinear  = Math.sin(angle) * force;     // up = forward
            joyAngular = -Math.cos(angle) * force;    // right = turn right (neg in ROS)
            // Invert angular for correct ROS convention: push right = negative angular.z = turn right
            // Actually -cos already gives us: right(0°)→-1, left(180°)→+1. Perfect.
        });

        joyManager.on('end', function () {
            joyLinear = 0;
            joyAngular = 0;
        });
    }

    // =========================================================================
    // Keyboard Drive
    // =========================================================================
    function setupKeyboard() {
        document.addEventListener('keydown', function (e) {
            // Don't capture if typing in an input
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;

            keysDown[e.key] = true;

            if (e.key === ' ' || e.key === 'Escape') {
                e.preventDefault();
                toggleEstop();
            }
        });

        document.addEventListener('keyup', function (e) {
            delete keysDown[e.key];
        });
    }

    // =========================================================================
    // E-STOP
    // =========================================================================
    function toggleEstop() {
        estopActive = !estopActive;

        if (estopActive) {
            btnEstop.classList.add('active');
            // Zero joystick
            joyLinear = 0;
            joyAngular = 0;
            // Immediately publish zero via rosbridge
            if (cmdVelTopic && rosbridgeConnected) {
                cmdVelTopic.publish(new ROSLIB.Message({
                    linear:  { x: 0, y: 0, z: 0 },
                    angular: { x: 0, y: 0, z: 0 },
                }));
            }
            // Also notify backend (rclpy fallback — works even if rosbridge dies)
            fetch('/api/estop', { method: 'POST' })
                .then(function (r) { return r.json(); })
                .then(function (d) { log('E-STOP backend: ' + d.message, 'warn'); })
                .catch(function () { log('E-STOP backend unreachable', 'error'); });

            log('E-STOP ACTIVATED', 'error');
        } else {
            btnEstop.classList.remove('active');
            log('E-STOP released', 'warn');
        }
    }

    // =========================================================================
    // Speed Mode
    // =========================================================================
    function setupSpeedModes() {
        document.querySelectorAll('.speed-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                document.querySelectorAll('.speed-btn').forEach(function (b) {
                    b.classList.remove('active');
                });
                btn.classList.add('active');
                currentSpeed = btn.getAttribute('data-mode');
                log('Speed: ' + currentSpeed);
            });
        });
    }

    // =========================================================================
    // Spawn
    // =========================================================================
    function loadUrdfList() {
        fetch('/api/urdf/list')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                urdfSelect.innerHTML = '';
                if (!data.files || data.files.length === 0) {
                    urdfSelect.innerHTML = '<option value="">No URDF files found</option>';
                    return;
                }
                data.files.forEach(function (f) {
                    var opt = document.createElement('option');
                    opt.value = f.path;
                    opt.textContent = f.name;
                    urdfSelect.appendChild(opt);
                });
            })
            .catch(function () {
                urdfSelect.innerHTML = '<option value="">Failed to load</option>';
            });
    }

    function doSpawn(urdfFile) {
        spawnStatus.textContent = 'Spawning...';
        spawnStatus.className = 'status-msg';
        btnSpawn.disabled = true;
        btnRespawn.disabled = true;

        var body = {};
        if (urdfFile) body.urdf_file = urdfFile;

        fetch('/api/spawn', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        })
        .then(function (r) { return r.json(); })
        .then(function (d) {
            if (d.status === 'ok') {
                spawnStatus.textContent = d.message;
                spawnStatus.className = 'status-msg ok';
                log('Spawn OK: ' + d.message, 'success');
            } else {
                spawnStatus.textContent = d.message || 'Spawn failed';
                spawnStatus.className = 'status-msg err';
                log('Spawn error: ' + d.message, 'error');
            }
        })
        .catch(function (e) {
            spawnStatus.textContent = 'Network error';
            spawnStatus.className = 'status-msg err';
            log('Spawn fetch error: ' + e, 'error');
        })
        .finally(function () {
            btnSpawn.disabled = false;
            btnRespawn.disabled = false;
        });
    }

    // =========================================================================
    // Status Polling
    // =========================================================================
    function pollStatus() {
        fetch('/api/status')
            .then(function (r) { return r.json(); })
            .then(function (d) {
                gzDot.className  = 'dot ' + (d.gazebo_running ? 'green' : 'red');
                kinDot.className = 'dot ' + (d.kinematics_running ? 'green' : 'red');
            })
            .catch(function () {
                gzDot.className  = 'dot red';
                kinDot.className = 'dot red';
            });
    }

    // =========================================================================
    // Arm Cosine Test Sequence
    // =========================================================================
    function setupArmTest() {
        var btnRun  = document.getElementById('btn-run-test');
        var btnStop = document.getElementById('btn-stop-test');
        var btnHome = document.getElementById('btn-home-all');

        btnRun.addEventListener('click', runCosineTest);
        btnStop.addEventListener('click', function () {
            testAborted = true;
            log('Arm test ABORTED by user', 'warning');
        });
        btnHome.addEventListener('click', homeAllArms);
    }

    function getSelectedArms() {
        var arms = [];
        if (document.getElementById('test-arm1').checked) arms.push('arm1');
        if (document.getElementById('test-arm2').checked) arms.push('arm2');
        if (document.getElementById('test-arm3').checked) arms.push('arm3');
        return arms;
    }

    function homeAllArms() {
        var arms = ['arm1', 'arm2', 'arm3'];
        arms.forEach(function (arm) {
            var cfg = ARM_CONFIGS[arm];
            publishArmJoint(cfg.j3, 0);
            publishArmJoint(cfg.j4, 0);
            publishArmJoint(cfg.j5, 0);
        });
        // Also reset sliders
        resetArm('arm1');
        resetArm('arm2');
        resetArm('arm3');
        log('All arms homed (J3=0, J4=0, J5=0)');
    }

    function updateSliderUI(arm, j3Val, j4Val, j5Val) {
        // Map arm name to slider suffix
        var suffix = (arm === 'arm2') ? '_copy' : (arm === 'arm3') ? '_copy1' : '';
        var pairs = [
            { id: 'slider-joint3' + suffix, val: j3Val },
            { id: 'slider-joint4' + suffix, val: j4Val },
            { id: 'slider-joint5' + suffix, val: j5Val },
        ];
        pairs.forEach(function (p) {
            var sl = document.getElementById(p.id);
            if (sl) {
                sl.value = p.val;
                var valEl = document.getElementById('val-' + sl.id.replace('slider-', ''));
                if (valEl) valEl.textContent = p.val.toFixed(3);
            }
        });
    }

    function sleep(ms) {
        return new Promise(function (resolve) { setTimeout(resolve, ms); });
    }

    function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

    async function runCosineTest() {
        if (testRunning) return;
        if (!rosbridgeConnected) {
            log('Cannot run test — rosbridge not connected', 'error');
            return;
        }

        // Read config
        var adj      = parseFloat(document.getElementById('test-adj').value) || 0.25;
        var stepDeg  = parseFloat(document.getElementById('test-step').value) || 15;
        var maxTheta = parseFloat(document.getElementById('test-max-theta').value) || 75;
        var holdSec  = parseFloat(document.getElementById('test-hold').value) || 5;
        var arms     = getSelectedArms();

        if (arms.length === 0) {
            log('No arms selected for test', 'warning');
            return;
        }

        // Build step list — no clamping, raw cosine relation
        // J3 = -θ, J5 = adj / cos(θ)
        var steps = [];
        for (var deg = 0; deg <= maxTheta; deg += stepDeg) {
            var rad = deg * Math.PI / 180;
            var j3Cmd = -rad;
            var cosVal = Math.cos(rad);
            var j5Calc = (Math.abs(cosVal) > 0.01) ? (adj / cosVal) : adj;
            var j5Cmd  = j5Calc;
            steps.push({
                deg: deg,
                rad: rad,
                j3Cmd: j3Cmd,
                j5Calc: j5Calc,
                j5Cmd: j5Cmd,
            });
        }

        // Populate table
        var tbody = document.getElementById('test-table-body');
        tbody.innerHTML = '';
        steps.forEach(function (s, i) {
            var tr = document.createElement('tr');
            tr.id = 'test-row-' + i;
            tr.innerHTML =
                '<td>' + s.deg + '°</td>' +
                '<td>' + s.j3Cmd.toFixed(3) + '</td>' +
                '<td>' + s.j5Calc.toFixed(3) + '</td>' +
                '<td>' + s.j5Cmd.toFixed(3) + '</td>' +
                '<td class="step-status" id="step-status-' + i + '">⏳</td>';
            tbody.appendChild(tr);
        });

        // UI state
        testRunning = true;
        testAborted = false;
        document.getElementById('btn-run-test').disabled = true;
        document.getElementById('btn-stop-test').disabled = false;
        var progressDiv  = document.getElementById('test-progress');
        var progressFill = document.getElementById('test-progress-fill');
        var progressLabel = document.getElementById('test-progress-label');
        progressDiv.style.display = 'block';

        log('=== Arm Cosine Test START === (adj=' + adj + 'm, step=' + stepDeg + '°, hold=' + holdSec + 's, arms: ' + arms.join(',') + ')');

        // First, home all selected arms (publish 3x for reliable delivery)
        log('Homing selected arms...');
        for (var h = 0; h < 3; h++) {
            arms.forEach(function (arm) {
                var cfg = ARM_CONFIGS[arm];
                publishArmJoint(cfg.j3, 0);
                publishArmJoint(cfg.j4, 0);
                publishArmJoint(cfg.j5, 0);
            });
            if (h < 2) await sleep(500);
        }
        arms.forEach(function (arm) { updateSliderUI(arm, 0, 0, 0); });
        await sleep(2000);
        log('Initial home reached.');

        // Execute steps
        for (var i = 0; i < steps.length; i++) {
            if (testAborted || estopActive) {
                markStepStatus(i, '🛑 Aborted');
                break;
            }

            var s = steps[i];
            var pct = ((i + 1) / steps.length * 100).toFixed(0);
            progressFill.style.width = pct + '%';
            progressLabel.textContent = 'Step ' + (i + 1) + '/' + steps.length + ' — θ=' + s.deg + '°';

            // Highlight current row
            var row = document.getElementById('test-row-' + i);
            if (row) row.classList.add('active-step');

            markStepStatus(i, '▶ Running');
            log('Step ' + (i + 1) + ': θ=' + s.deg + '° → J3=' + s.j3Cmd.toFixed(3) + ' rad, J5=' + s.j5Cmd.toFixed(3) + ' m');

            // Send commands to all selected arms simultaneously
            arms.forEach(function (arm) {
                var cfg = ARM_CONFIGS[arm];
                publishArmJoint(cfg.j3, s.j3Cmd);
                publishArmJoint(cfg.j4, 0);      // J4 stays at homing
                publishArmJoint(cfg.j5, s.j5Cmd);
                updateSliderUI(arm, s.j3Cmd, 0, s.j5Cmd);
            });

            // Hold position
            await sleep(holdSec * 1000);

            if (testAborted || estopActive) {
                if (row) row.classList.remove('active-step');
                markStepStatus(i, '🛑 Aborted');
                break;
            }

            // Return to homing after each step — publish multiple times to ensure delivery
            log('  → Returning to home...');
            for (var h = 0; h < 3; h++) {
                arms.forEach(function (arm) {
                    var cfg = ARM_CONFIGS[arm];
                    publishArmJoint(cfg.j3, 0);
                    publishArmJoint(cfg.j4, 0);
                    publishArmJoint(cfg.j5, 0);
                });
                if (h < 2) await sleep(500);
            }
            arms.forEach(function (arm) {
                updateSliderUI(arm, 0, 0, 0);
            });
            await sleep(2000);
            log('  → Home reached.');

            if (row) row.classList.remove('active-step');

            if (testAborted || estopActive) {
                markStepStatus(i, '🛑 Aborted');
                break;
            }
            markStepStatus(i, '✅ Done');
        }

        // Final home (publish 3x for reliable delivery)
        if (!testAborted && !estopActive) {
            log('Final home — publishing...');
            for (var h = 0; h < 3; h++) {
                arms.forEach(function (arm) {
                    var cfg = ARM_CONFIGS[arm];
                    publishArmJoint(cfg.j3, 0);
                    publishArmJoint(cfg.j4, 0);
                    publishArmJoint(cfg.j5, 0);
                });
                if (h < 2) await sleep(500);
            }
            arms.forEach(function (arm) { updateSliderUI(arm, 0, 0, 0); });
            await sleep(2000);
            log('Final home position confirmed.');
        }

        // Done
        progressFill.style.width = '100%';
        progressLabel.textContent = testAborted ? 'Test aborted' : 'Test complete ✅';
        log('=== Arm Cosine Test ' + (testAborted ? 'ABORTED' : 'COMPLETE') + ' ===');

        testRunning = false;
        document.getElementById('btn-run-test').disabled = false;
        document.getElementById('btn-stop-test').disabled = true;
    }

    function markStepStatus(idx, text) {
        var el = document.getElementById('step-status-' + idx);
        if (el) el.textContent = text;
    }

    // =========================================================================
    // Custom Joint Sequence
    // =========================================================================

    // Joint limits mirror JOINT_LIMITS in testing_backend.py
    var SEQ_JOINT_LIMITS = {
        j3: { min: -0.9,  max: 0.0  },   // rad (tilt)
        j4: { min: -0.25, max: 0.35 },   // m   (lateral)
        j5: { min:  0.0,  max: 0.45 },   // m   (extend)
    };

    // Running row counter — increments each time a row is added, never resets,
    // giving each row a unique id for reliable DOM look-up.
    var seqRowCounter = 0;

    function seqAddRow(j3, j4, j5, hold) {
        j3   = (j3   !== undefined) ? j3   : 0;
        j4   = (j4   !== undefined) ? j4   : 0;
        j5   = (j5   !== undefined) ? j5   : 0;
        hold = (hold !== undefined) ? hold : 2.0;

        var tbody = document.getElementById('seq-table-body');
        var rowIdx = ++seqRowCounter;
        var tr = document.createElement('tr');
        tr.id = 'seq-row-' + rowIdx;

        tr.innerHTML =
            '<td class="seq-row-num">' + (tbody.children.length + 1) + '</td>' +
            '<td class="seq-cell-j3"><input type="number" class="seq-cell-input" data-joint="j3"' +
                ' value="' + j3.toFixed(3) + '" step="0.01"></td>' +
            '<td class="seq-cell-j4"><input type="number" class="seq-cell-input" data-joint="j4"' +
                ' value="' + j4.toFixed(3) + '" step="0.005"></td>' +
            '<td class="seq-cell-j5"><input type="number" class="seq-cell-input" data-joint="j5"' +
                ' value="' + j5.toFixed(3) + '" step="0.005"></td>' +
            '<td><input type="number" class="seq-cell-input" data-joint="hold"' +
                ' value="' + hold.toFixed(1) + '" step="0.1" min="0.1"></td>' +
            '<td class="seq-step-status" id="seq-step-status-' + rowIdx + '">—</td>' +
            '<td><button class="seq-del-btn" title="Delete row">✕</button></td>';

        // Wire delete button
        tr.querySelector('.seq-del-btn').addEventListener('click', function () {
            tr.parentNode.removeChild(tr);
            seqRenumberRows();
        });

        tbody.appendChild(tr);
        seqValidateRow(tr);
    }

    function seqRenumberRows() {
        var rows = document.querySelectorAll('#seq-table-body tr');
        rows.forEach(function (tr, i) {
            var numCell = tr.querySelector('.seq-row-num');
            if (numCell) numCell.textContent = i + 1;
        });
    }

    function seqValidateRow(tr) {
        var warnings = [];
        var inputs = tr.querySelectorAll('input[data-joint]');
        inputs.forEach(function (input) {
            var joint = input.getAttribute('data-joint');
            if (joint === 'hold') return;   // no limit on hold duration
            var limits = SEQ_JOINT_LIMITS[joint];
            if (!limits) return;
            var val = parseFloat(input.value);
            var td = input.parentNode;
            if (isNaN(val) || val < limits.min || val > limits.max) {
                td.classList.add('warn-cell');
                input.title = joint.toUpperCase() + ' valid range: [' + limits.min + ', ' + limits.max + ']';
                warnings.push(joint.toUpperCase() + ' out of range: ' + val +
                              ' (valid: [' + limits.min + ', ' + limits.max + '])');
            } else {
                td.classList.remove('warn-cell');
                input.title = '';
            }
        });
        return warnings;
    }

    function seqReadRows() {
        var rows = document.querySelectorAll('#seq-table-body tr');
        var result = [];
        rows.forEach(function (tr) {
            var j3   = parseFloat(tr.querySelector('[data-joint="j3"]').value)   || 0;
            var j4   = parseFloat(tr.querySelector('[data-joint="j4"]').value)   || 0;
            var j5   = parseFloat(tr.querySelector('[data-joint="j5"]').value)   || 0;
            var hold = parseFloat(tr.querySelector('[data-joint="hold"]').value) || 2.0;
            result.push({ j3: j3, j4: j4, j5: j5, hold: hold, trId: tr.id });
        });
        return result;
    }

    function setupCustomSequence() {
        document.getElementById('seq-btn-add-row').addEventListener('click', function () {
            seqAddRow();
        });

        document.getElementById('seq-btn-start').addEventListener('click', runCustomSequence);

        document.getElementById('seq-btn-stop').addEventListener('click', function () {
            seqAborted = true;
            log('Custom sequence ABORTED by user', 'warn');
        });

        document.getElementById('seq-loop').addEventListener('change', function () {
            document.getElementById('seq-repeat-count').disabled = this.checked;
        });

        // Live validation on any table input change
        document.getElementById('seq-table-body').addEventListener('input', function (e) {
            var input = e.target;
            if (!input.classList.contains('seq-cell-input')) return;
            var tr = input.closest('tr');
            if (tr) seqValidateRow(tr);
        });
    }

    async function runCustomSequence() {
        if (seqRunning) return;

        if (estopActive) {
            log('Cannot run sequence — E-STOP is active', 'error');
            return;
        }
        if (!rosbridgeConnected) {
            log('Cannot run sequence — rosbridge not connected', 'error');
            return;
        }

        var rows = seqReadRows();
        if (rows.length === 0) {
            log('Cannot run sequence — table is empty', 'error');
            return;
        }

        var armKey     = document.getElementById('seq-arm-select').value;  // 'arm1'/'arm2'/'arm3'
        var cfg        = ARM_CONFIGS[armKey];
        var loopMode   = document.getElementById('seq-loop').checked;
        var repeatCount = loopMode ? Infinity : (parseInt(document.getElementById('seq-repeat-count').value, 10) || 1);

        // UI: running state
        seqRunning = true;
        seqAborted = false;
        document.getElementById('seq-btn-start').disabled = true;
        document.getElementById('seq-btn-stop').disabled  = false;
        var progressDiv   = document.getElementById('seq-progress');
        var progressFill  = document.getElementById('seq-progress-fill');
        var progressLabel = document.getElementById('seq-progress-label');
        progressDiv.style.display = 'block';
        progressFill.style.width  = '0%';

        log('=== Custom Sequence START === (arm=' + armKey + ', rows=' + rows.length +
            ', repeat=' + (loopMode ? '∞' : repeatCount) + ')');

        // Auto-home selected arm before first step (same pattern as runCosineTest)
        log('Homing selected arm before sequence...');
        for (var h = 0; h < 3; h++) {
            publishArmJoint(cfg.j3, 0);
            publishArmJoint(cfg.j4, 0);
            publishArmJoint(cfg.j5, 0);
            if (h < 2) await sleep(500);
        }
        updateSliderUI(armKey, 0, 0, 0);
        await sleep(2000);
        log('Home reached. Starting sequence...');

        var pass = 0;
        var totalSteps = loopMode ? rows.length : repeatCount * rows.length;
        var stepsDone  = 0;

        outerLoop: while (pass < repeatCount) {
            pass++;
            for (var i = 0; i < rows.length; i++) {
                if (seqAborted || estopActive) {
                    var abortedTrId = rows[i].trId;
                    var abortedTr = document.getElementById(abortedTrId);
                    seqMarkStatus(abortedTrId, '🛑 Aborted');
                    if (abortedTr) abortedTr.classList.remove('active-step');
                    log('Sequence halted — ' + (estopActive ? 'E-STOP ACTIVATED' : 'user aborted'));
                    break outerLoop;
                }

                var row = rows[i];
                var tr  = document.getElementById(row.trId);

                if (tr) tr.classList.add('active-step');
                seqMarkStatus(row.trId, '▶ Running');

                if (!loopMode) {
                    var pct = (++stepsDone / totalSteps * 100).toFixed(0);
                    progressFill.style.width = pct + '%';
                } else {
                    // In loop mode: show progress within the current pass
                    var loopPct = ((i + 1) / rows.length * 100).toFixed(0);
                    progressFill.style.width = loopPct + '%';
                }
                progressLabel.textContent = 'Step ' + (i + 1) + '/' + rows.length +
                    (loopMode ? ' (loop pass ' + pass + ')' : ' — pass ' + pass + '/' + repeatCount) +
                    ' — hold ' + row.hold + 's';

                log('Step ' + (i + 1) + ': J3=' + row.j3.toFixed(3) +
                    ' J4=' + row.j4.toFixed(3) + ' J5=' + row.j5.toFixed(3) +
                    ' hold=' + row.hold + 's');

                publishArmJoint(cfg.j3, row.j3);
                publishArmJoint(cfg.j4, row.j4);
                publishArmJoint(cfg.j5, row.j5);
                updateSliderUI(armKey, row.j3, row.j4, row.j5);

                await sleep(row.hold * 1000);

                if (seqAborted || estopActive) {
                    if (tr) tr.classList.remove('active-step');
                    seqMarkStatus(row.trId, '🛑 Aborted');
                    log('Sequence halted — ' + (estopActive ? 'E-STOP ACTIVATED' : 'user aborted'));
                    break outerLoop;
                }

                if (tr) tr.classList.remove('active-step');
                seqMarkStatus(row.trId, '✅ Done');
            }
        }

        // Final state
        progressFill.style.width = '100%';
        if (!seqAborted && !estopActive) {
            progressLabel.textContent = 'Sequence complete ✅';
            log('=== Custom Sequence COMPLETE ===');
        } else {
            progressLabel.textContent = 'Sequence aborted';
            log('=== Custom Sequence ABORTED ===');
        }

        seqRunning = false;
        document.getElementById('seq-btn-start').disabled = false;
        document.getElementById('seq-btn-stop').disabled  = true;
    }

    function seqMarkStatus(trId, text) {
        // Status cell id is derived from row id: 'seq-row-N' -> 'seq-step-status-N'
        var match = trId && trId.match(/seq-row-(\d+)/);
        if (match) {
            var el = document.getElementById('seq-step-status-' + match[1]);
            if (el) el.textContent = text;
        }
    }

    // =========================================================================
    // Cotton Position Sequence — cam-coord → joint conversion
    // =========================================================================

    /**
     * camToJoint(tf4x4, cam_x, cam_y, cam_z)
     *
     * Converts a camera-frame point to arm joint commands using polar decomposition.
     *
     * @param {object} tf4x4  - Object with method apply(x,y,z) → {x,y,z} in arm frame
     * @param {number} cam_x
     * @param {number} cam_y
     * @param {number} cam_z
     * @returns {{ valid: boolean, j3?: number, j4?: number, j5?: number }}
     */
    function camToJoint(tf4x4, cam_x, cam_y, cam_z) {
        var arm = tf4x4.apply(cam_x, cam_y, cam_z);
        var ax = arm.x, ay = arm.y, az = arm.z;

        var r  = Math.sqrt(ax * ax + az * az);
        var j3 = (r > 1e-9) ? Math.asin(az / r) : 0.0;
        var j4 = ay;
        var j5 = r - CAM_SEQ_J5_OFFSET;

        if (j3 < CAM_SEQ_J3_MIN || j3 > CAM_SEQ_J3_MAX ||
            j4 < CAM_SEQ_J4_MIN || j4 > CAM_SEQ_J4_MAX ||
            j5 < CAM_SEQ_J5_MIN || j5 > CAM_SEQ_J5_MAX) {
            return { valid: false };
        }
        return { valid: true, j3: j3, j4: j4, j5: j5 };
    }

    /**
     * Phi-compensation: adjust j3 based on phi zone and j5 extension.
     * Zones: phi_deg <= 50.5 → +offset, 50.5..60 → 0, > 60 → −offset.
     */
    function phiCompensation(j3, j5) {
        var phiDeg = Math.abs(j3 * 180.0 / Math.PI);
        var baseOffset;
        if (phiDeg <= PHI_ZONE1_MAX_DEG) {
            baseOffset = PHI_ZONE1_OFFSET;
        } else if (phiDeg <= PHI_ZONE2_MAX_DEG) {
            baseOffset = PHI_ZONE2_OFFSET;
        } else {
            baseOffset = PHI_ZONE3_OFFSET;
        }
        var l5Norm = Math.max(0.0, j5) / PHI_JOINT5_MAX;
        var l5Scale = 1.0 + PHI_L5_SCALE * l5Norm;
        var compRot = baseOffset * l5Scale;
        var compRad = compRot * 2.0 * Math.PI;
        return j3 + compRad;
    }

    /**
     * Build a 4×4 apply() adapter from a ROSLIB transform message.
     * The transform carries translation + quaternion rotation.
     * We only need R·v (the rotation part) for the arm-frame decomposition.
     */
    function makeTfAdapter(tMsg) {
        // tMsg.transform: { translation: {x,y,z}, rotation: {x,y,z,w} }
        var t = tMsg.transform.translation;
        var q = tMsg.transform.rotation;
        // Quaternion → rotation matrix
        var qx = q.x, qy = q.y, qz = q.z, qw = q.w;
        // Row 0
        var r00 = 1 - 2*(qy*qy + qz*qz);
        var r01 = 2*(qx*qy - qw*qz);
        var r02 = 2*(qx*qz + qw*qy);
        // Row 1
        var r10 = 2*(qx*qy + qw*qz);
        var r11 = 1 - 2*(qx*qx + qz*qz);
        var r12 = 2*(qy*qz - qw*qx);
        // Row 2
        var r20 = 2*(qx*qz - qw*qy);
        var r21 = 2*(qy*qz + qw*qx);
        var r22 = 1 - 2*(qx*qx + qy*qy);
        return {
            apply: function (x, y, z) {
                return {
                    x: r00*x + r01*y + r02*z + t.x,
                    y: r10*x + r11*y + r12*z + t.y,
                    z: r20*x + r21*y + r22*z + t.z,
                };
            }
        };
    }

    function setupTfSubscriber() {
        if (!ros) return;
        var tfStaticSub = new ROSLIB.Topic({
            ros: ros,
            name: '/tf_static',
            messageType: 'tf2_msgs/msg/TFMessage',
        });
        tfStaticSub.subscribe(function (msg) {
            if (!msg.transforms) return;
            for (var i = 0; i < msg.transforms.length; i++) {
                var t = msg.transforms[i];
                if (t.child_frame_id === CAM_SEQ_TF_FRAME_ARM &&
                    t.header.frame_id === CAM_SEQ_TF_FRAME_FIXED) {
                    tfMatrix = makeTfAdapter(t);
                    if (!tfReady) {
                        tfReady = true;
                        log('TF ready: ' + CAM_SEQ_TF_FRAME_FIXED + ' → ' + CAM_SEQ_TF_FRAME_ARM, 'success');
                        updateCamSeqTfStatus(true);
                    }
                    break;
                }
            }
        });
    }

    // Pre-computed camera_link -> arm_yanthra_link transform.
    // Based on URDF: camera_joint parent=arm_yanthra_link, child=camera_link
    // origin xyz=(0.016845, 0.100461, -0.077129) rpy=(1.5708, 0.785398, 0)
    // We compute the INVERSE of this transform for camToJoint.
    function initCameraToArmTransform() {
        var tx = 0.016845, ty = 0.100461, tz = -0.077129;
        var roll = 1.5708, pitch = 0.785398, yaw = 0.0;

        var cr = Math.cos(roll), sr = Math.sin(roll);
        var cp = Math.cos(pitch), sp = Math.sin(pitch);
        var cy = Math.cos(yaw), sy = Math.sin(yaw);

        // Forward rotation (yanthra -> camera)
        var r00 = cy*cp, r01 = cy*sp*sr - sy*cr, r02 = cy*sp*cr + sy*sr;
        var r10 = sy*cp, r11 = sy*sp*sr + cy*cr, r12 = sy*sp*cr - cy*sr;
        var r20 = -sp,   r21 = cp*sr,             r22 = cp*cr;

        // Inverse: R^T and -R^T * t
        var inv_tx = -(r00*tx + r10*ty + r20*tz);
        var inv_ty = -(r01*tx + r11*ty + r21*tz);
        var inv_tz = -(r02*tx + r12*ty + r22*tz);

        tfMatrix = {
            apply: function(x, y, z) {
                return {
                    x: r00*x + r10*y + r20*z + inv_tx,
                    y: r01*x + r11*y + r21*z + inv_ty,
                    z: r02*x + r12*y + r22*z + inv_tz,
                };
            }
        };
        tfReady = true;
    }

    function updateCamSeqTfStatus(ready) {
        var el = document.getElementById('cam-seq-tf-status');
        if (!el) return;
        el.textContent = ready ? 'TF ready' : 'TF not ready';
        el.className   = ready ? 'cam-seq-tf-ready' : 'cam-seq-tf-not-ready';
    }

    // =========================================================================
    // Cotton Position Sequence — UI handlers
    // =========================================================================

    function camSeqAddRow(cam_x, cam_y, cam_z) {
        cam_x = (cam_x !== undefined) ? cam_x : 0;
        cam_y = (cam_y !== undefined) ? cam_y : 0;
        cam_z = (cam_z !== undefined) ? cam_z : 0;

        var tbody   = document.getElementById('cam-seq-table-body');
        var rowIdx  = ++camSeqRowCounter;
        var tr      = document.createElement('tr');
        tr.id       = 'cam-seq-row-' + rowIdx;
        tr.className = 'cam-seq-row';

        tr.innerHTML =
            '<td class="cam-seq-row-num">' + (tbody.children.length + 1) + '</td>' +
            '<td><input type="number" class="cam-seq-input" data-col="cam_x"' +
                ' value="' + cam_x.toFixed(3) + '" step="0.01"></td>' +
            '<td><input type="number" class="cam-seq-input" data-col="cam_y"' +
                ' value="' + cam_y.toFixed(3) + '" step="0.01"></td>' +
            '<td><input type="number" class="cam-seq-input" data-col="cam_z"' +
                ' value="' + cam_z.toFixed(3) + '" step="0.01"></td>' +
            '<td class="cam-seq-joints" id="cam-seq-joints-' + rowIdx + '">—</td>' +
            '<td class="cam-seq-marker-name" id="cam-seq-marker-' + rowIdx + '">—</td>' +
            '<td id="cam-seq-status-' + rowIdx + '">—</td>' +
            '<td><button class="cam-seq-remove-btn" title="Remove row">✕</button></td>';

        tr.querySelector('.cam-seq-remove-btn').addEventListener('click', function () {
            tr.parentNode.removeChild(tr);
            camSeqRenumber();
        });

        tr.querySelectorAll('.cam-seq-input').forEach(function (inp) {
            inp.addEventListener('input', function () {
                camSeqValidateRow(tr);
            });
        });

        tbody.appendChild(tr);
        camSeqValidateRow(tr);
    }

    function camSeqRenumber() {
        document.querySelectorAll('#cam-seq-table-body tr').forEach(function (tr, i) {
            var numCell = tr.querySelector('.cam-seq-row-num');
            if (numCell) numCell.textContent = i + 1;
        });
    }

    function camSeqValidateRow(tr) {
        var cam_x = parseFloat(tr.querySelector('[data-col="cam_x"]').value) || 0;
        var cam_y = parseFloat(tr.querySelector('[data-col="cam_y"]').value) || 0;
        var cam_z = parseFloat(tr.querySelector('[data-col="cam_z"]').value) || 0;

        var rowIdx = tr.id.replace('cam-seq-row-', '');
        var jointsCell = document.getElementById('cam-seq-joints-' + rowIdx);

        if (!tfReady || !tfMatrix) {
            tr.classList.remove('row-error');
            if (jointsCell) jointsCell.textContent = '—';
            return null;
        }

        var result = camToJoint(tfMatrix, cam_x, cam_y, cam_z);
        if (!result.valid) {
            tr.classList.add('row-error');
            if (jointsCell) jointsCell.textContent = 'OUT OF RANGE';
        } else {
            tr.classList.remove('row-error');
            if (jointsCell) {
                jointsCell.textContent =
                    'J3=' + result.j3.toFixed(3) +
                    ' J4=' + result.j4.toFixed(3) +
                    ' J5=' + result.j5.toFixed(3);
            }
        }
        return result;
    }

    // =========================================================================
    // Cotton Placement (ported from yanthra_move)
    // =========================================================================

    function setupCottonPlacement() {
        var spawnBtn     = document.getElementById('cotton-spawn-btn');
        var removeBtn    = document.getElementById('cotton-remove-btn');
        var computeBtn   = document.getElementById('cotton-compute-btn');
        var pickBtn      = document.getElementById('cotton-pick-btn');
        var removeAllBtn = document.getElementById('cotton-remove-all-btn');
        var pickAllBtn   = document.getElementById('cotton-pick-all-btn');

        if (spawnBtn)     spawnBtn.addEventListener('click', cottonSpawn);
        if (removeBtn)    removeBtn.addEventListener('click', cottonRemove);
        if (computeBtn)   computeBtn.addEventListener('click', cottonCompute);
        if (pickBtn)      pickBtn.addEventListener('click', cottonPick);
        if (removeAllBtn) removeAllBtn.addEventListener('click', cottonRemoveAll);
        if (pickAllBtn)   pickAllBtn.addEventListener('click', cottonPickAll);
    }

    function getCottonParams() {
        return {
            cam_x: parseFloat(document.getElementById('cotton-cam-x').value) || 0,
            cam_y: parseFloat(document.getElementById('cotton-cam-y').value) || 0,
            cam_z: parseFloat(document.getElementById('cotton-cam-z').value) || 0,
            arm:   document.getElementById('cotton-arm-select').value || 'arm1',
            j4_pos: parseFloat(document.getElementById('cotton-j4-pos').value) || 0,
            enable_j4_compensation: document.getElementById('cotton-j4-comp').checked,
            enable_phi_compensation: document.getElementById('cotton-phi-comp').checked,
        };
    }

    function cottonSpawn() {
        var params = getCottonParams();
        log('Spawning cotton at cam(' + params.cam_x + ', ' + params.cam_y + ', ' + params.cam_z + ')...');
        fetch('/api/cotton/spawn', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                cam_x: params.cam_x, cam_y: params.cam_y, cam_z: params.cam_z,
                arm: params.arm, j4_pos: params.j4_pos,
            }),
        })
        .then(function (r) {
            return r.json().then(function (d) { return { ok: r.ok, status: r.status, data: d }; });
        })
        .then(function (resp) {
            if (!resp.ok) {
                var reason = resp.data.detail || 'Unknown error';
                log('Cotton spawn failed: ' + reason, 'error');
                return;
            }
            var d = resp.data;
            log('Cotton spawned at world(' + d.world_x.toFixed(3) + ', ' +
                d.world_y.toFixed(3) + ', ' + d.world_z.toFixed(3) + ')', 'success');
            refreshCottonTable();
        })
        .catch(function (e) { log('Cotton spawn error: ' + e, 'error'); });
    }

    function cottonRemove() {
        fetch('/api/cotton/remove', { method: 'POST' })
        .then(function (r) { return r.json(); })
        .then(function () {
            log('Cotton removed', 'success');
            refreshCottonTable();
        })
        .catch(function (e) { log('Cotton remove error: ' + e, 'error'); });
    }

    function refreshCottonTable() {
        fetch('/api/cotton/list')
        .then(function (r) { return r.json(); })
        .then(function (d) {
            var container = document.getElementById('cotton-table-container');
            var tbody = document.getElementById('cotton-table-body');
            if (!container || !tbody) return;

            tbody.innerHTML = '';
            var cottons = d.cottons || [];

            if (cottons.length === 0) {
                container.style.display = 'none';
                return;
            }

            container.style.display = 'block';
            cottons.forEach(function (c) {
                var jv = c.joint_values || {};
                var j3 = jv.j3 != null ? jv.j3.toFixed(3) : '—';
                var j4 = jv.j4 != null ? jv.j4.toFixed(3) : '—';
                var j5 = jv.j5 != null ? jv.j5.toFixed(3) : '—';
                var tr = document.createElement('tr');
                tr.innerHTML =
                    '<td>' + c.name + '</td>' +
                    '<td>' + c.cam_x.toFixed(3) + '</td>' +
                    '<td>' + c.cam_y.toFixed(3) + '</td>' +
                    '<td>' + c.cam_z.toFixed(3) + '</td>' +
                    '<td>' + j3 + '</td>' +
                    '<td>' + j4 + '</td>' +
                    '<td>' + j5 + '</td>' +
                    '<td class="status-' + c.status + '">' + c.status + '</td>';
                tbody.appendChild(tr);
            });
        })
        .catch(function () { /* ignore refresh errors */ });
    }

    function cottonRemoveAll() {
        fetch('/api/cotton/remove-all', { method: 'POST' })
        .then(function (r) {
            return r.json().then(function (d) { return { ok: r.ok, data: d }; });
        })
        .then(function (resp) {
            if (!resp.ok) {
                log('Remove all failed: ' + resp.data.detail, 'error');
                return;
            }
            log('Removed ' + resp.data.removed + ' cotton(s)', 'success');
            refreshCottonTable();
        })
        .catch(function (e) { log('Remove all error: ' + e, 'error'); });
    }

    function cottonPickAll() {
        var params = getCottonParams();
        var pickAllBtn = document.getElementById('cotton-pick-all-btn');
        var removeAllBtn = document.getElementById('cotton-remove-all-btn');
        var statusDiv = document.getElementById('cotton-pick-status');
        var statusText = document.getElementById('cotton-pick-status-text');

        if (pickAllBtn) pickAllBtn.disabled = true;
        if (removeAllBtn) removeAllBtn.disabled = true;
        statusDiv.style.display = 'block';
        statusDiv.className = 'pick-status picking';
        statusText.textContent = 'Picking all...';

        log('Starting pick-all sequence on ' + params.arm + '...');
        fetch('/api/cotton/pick-all', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                arm: params.arm,
                enable_phi_compensation: params.enable_phi_compensation,
            }),
        })
        .then(function (r) {
            return r.json().then(function (d) { return { ok: r.ok, data: d }; });
        })
        .then(function (resp) {
            if (!resp.ok) {
                log('Pick-all error: ' + resp.data.detail, 'error');
                if (pickAllBtn) pickAllBtn.disabled = false;
                if (removeAllBtn) removeAllBtn.disabled = false;
                statusDiv.className = 'pick-status';
                statusText.textContent = 'Error';
                return;
            }
            if (resp.data.status === 'nothing_to_pick') {
                log('No cottons to pick', 'warn');
                if (pickAllBtn) pickAllBtn.disabled = false;
                if (removeAllBtn) removeAllBtn.disabled = false;
                statusDiv.style.display = 'none';
                return;
            }
            log('Pick-all started: ' + resp.data.total + ' cotton(s)', 'success');
            pollPickAllStatus(pickAllBtn, removeAllBtn, statusDiv, statusText);
        })
        .catch(function (e) {
            log('Pick-all error: ' + e, 'error');
            if (pickAllBtn) pickAllBtn.disabled = false;
            if (removeAllBtn) removeAllBtn.disabled = false;
            statusDiv.className = 'pick-status';
            statusText.textContent = 'Error';
        });
    }

    var _pickAllPollInterval = null;

    function pollPickAllStatus(pickAllBtn, removeAllBtn, statusDiv, statusText) {
        if (_pickAllPollInterval) {
            clearInterval(_pickAllPollInterval);
            _pickAllPollInterval = null;
        }
        _pickAllPollInterval = setInterval(function () {
            fetch('/api/cotton/pick/status')
            .then(function (r) { return r.json(); })
            .then(function (d) {
                if (d.progress) {
                    statusText.textContent = 'Picking ' + d.progress.current +
                        '/' + d.progress.total + ' (' + (d.current || '') + ')';
                }
                if (!d.in_progress) {
                    clearInterval(_pickAllPollInterval);
                    _pickAllPollInterval = null;
                    if (pickAllBtn) pickAllBtn.disabled = false;
                    if (removeAllBtn) removeAllBtn.disabled = false;
                    statusDiv.className = 'pick-status done';
                    statusText.textContent = 'Done';
                    log('Pick-all sequence complete', 'success');
                    refreshCottonTable();
                    setTimeout(function () { statusDiv.style.display = 'none'; }, 3000);
                }
            })
            .catch(function () { /* ignore poll errors */ });
        }, 500);
    }

    function cottonCompute() {
        var params = getCottonParams();
        fetch('/api/cotton/compute', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                cam_x: params.cam_x, cam_y: params.cam_y, cam_z: params.cam_z,
                arm: params.arm, j4_pos: params.j4_pos,
                enable_phi_compensation: params.enable_phi_compensation,
            }),
        })
        .then(function (r) { return r.json(); })
        .then(function (d) {
            var panel = document.getElementById('cotton-compute-results');
            panel.style.display = 'block';
            document.getElementById('cotton-arm-xyz').textContent =
                '(' + d.arm_x.toFixed(4) + ', ' + d.arm_y.toFixed(4) + ', ' + d.arm_z.toFixed(4) + ')';
            document.getElementById('cotton-r').textContent = d.r.toFixed(4) + ' m';
            document.getElementById('cotton-theta').textContent = d.theta.toFixed(4) + ' m';
            document.getElementById('cotton-phi').textContent =
                d.phi.toFixed(4) + ' rad (' + (d.phi * 180 / Math.PI).toFixed(1) + ' deg)';
            document.getElementById('cotton-j3').textContent = d.j3.toFixed(4) + ' rad';
            document.getElementById('cotton-j4').textContent = d.j4.toFixed(4) + ' m';
            document.getElementById('cotton-j5').textContent = d.j5.toFixed(4) + ' m';
            document.getElementById('cotton-reachable').textContent = d.reachable ? 'YES' : 'NO';
            document.getElementById('cotton-reachable').style.color = d.reachable ? '#5cb85c' : '#d9534f';
            log('Compute approach: r=' + d.r.toFixed(3) + ' reachable=' + d.reachable,
                d.reachable ? 'success' : 'warn');
        })
        .catch(function (e) { log('Compute error: ' + e, 'error'); });
    }

    function cottonPick() {
        var params = getCottonParams();
        var pickBtn = document.getElementById('cotton-pick-btn');
        var statusDiv = document.getElementById('cotton-pick-status');
        var statusText = document.getElementById('cotton-pick-status-text');

        pickBtn.disabled = true;
        statusDiv.style.display = 'block';
        statusDiv.className = 'pick-status picking';
        statusText.textContent = 'Picking...';

        log('Starting pick sequence on ' + params.arm + '...');
        fetch('/api/cotton/pick', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                arm: params.arm,
                enable_j4_compensation: params.enable_j4_compensation,
                enable_phi_compensation: params.enable_phi_compensation,
            }),
        })
        .then(function (r) {
            if (!r.ok) { throw new Error('HTTP ' + r.status); }
            return r.json();
        })
        .then(function (d) {
            log('Pick started: J3=' + d.j3.toFixed(3) + ' J4=' + d.j4.toFixed(3) +
                ' J5=' + d.j5.toFixed(3), 'success');
            pollPickStatus(pickBtn, statusDiv, statusText);
        })
        .catch(function (e) {
            log('Pick error: ' + e, 'error');
            pickBtn.disabled = false;
            statusDiv.className = 'pick-status';
            statusText.textContent = 'Error';
        });
    }

    var _pickPollInterval = null;

    function pollPickStatus(pickBtn, statusDiv, statusText) {
        // Clear any existing poll to prevent stacking (D2)
        if (_pickPollInterval) {
            clearInterval(_pickPollInterval);
            _pickPollInterval = null;
        }
        _pickPollInterval = setInterval(function () {
            fetch('/api/cotton/pick/status')
            .then(function (r) { return r.json(); })
            .then(function (d) {
                if (!d.in_progress) {
                    clearInterval(_pickPollInterval);
                    _pickPollInterval = null;
                    pickBtn.disabled = false;
                    statusDiv.className = 'pick-status done';
                    statusText.textContent = 'Done';
                    log('Pick sequence complete', 'success');
                    setTimeout(function () { statusDiv.style.display = 'none'; }, 3000);
                }
            })
            .catch(function () { /* ignore poll errors */ });
        }, 500);
    }

    // =========================================================================
    // Cotton Position Sequence
    // =========================================================================

    function setupCottonSequence() {
        document.getElementById('cam-seq-add-btn').addEventListener('click', function () {
            camSeqAddRow();
        });

        document.getElementById('cam-seq-run-btn').addEventListener('click', runCottonSequence);

        document.getElementById('cam-seq-stop-btn').addEventListener('click', function () {
            camSeqAborted = true;
            log('Cotton sequence ABORTED by user', 'warn');
        });

        document.getElementById('cam-seq-place-btn').addEventListener('click', placeAllCamMarkers);
        document.getElementById('cam-seq-clear-btn').addEventListener('click', clearCamMarkers);

        // Live re-validation on input change
        document.getElementById('cam-seq-table-body').addEventListener('input', function (e) {
            var inp = e.target;
            if (!inp.classList.contains('cam-seq-input')) return;
            var tr = inp.closest('tr');
            if (tr) camSeqValidateRow(tr);
        });

        updateCamSeqTfStatus(false);
    }

    function placeAllCamMarkers() {
        var rows = document.querySelectorAll('#cam-seq-table-body tr.cam-seq-row');
        if (rows.length === 0) {
            log('No positions to place markers for', 'warn');
            return;
        }
        rows.forEach(function (tr) {
            var cam_x = parseFloat(tr.querySelector('[data-col="cam_x"]').value) || 0;
            var cam_y = parseFloat(tr.querySelector('[data-col="cam_y"]').value) || 0;
            var cam_z = parseFloat(tr.querySelector('[data-col="cam_z"]').value) || 0;
            var rowIdx = tr.id.replace('cam-seq-row-', '');
            var markerCell = document.getElementById('cam-seq-marker-' + rowIdx);

            fetch('/api/cam_markers/place', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ cam_x: cam_x, cam_y: cam_y, cam_z: cam_z }),
            })
            .then(function (r) { return r.json(); })
            .then(function (d) {
                if (d.marker_name && markerCell) {
                    markerCell.textContent = d.marker_name;
                }
                log('Marker placed: ' + d.marker_name, 'success');
            })
            .catch(function (e) {
                log('Marker place error: ' + e, 'error');
            });
        });
    }

    function clearCamMarkers() {
        fetch('/api/cam_markers/clear', { method: 'POST' })
        .then(function (r) { return r.json(); })
        .then(function () {
            document.querySelectorAll('[id^="cam-seq-marker-"]').forEach(function (el) {
                el.textContent = '—';
            });
            log('Cam markers cleared', 'success');
        })
        .catch(function (e) {
            log('Marker clear error: ' + e, 'error');
        });
    }

    async function runCottonSequence() {
        if (camSeqRunning) return;

        var rows = document.querySelectorAll('#cam-seq-table-body tr.cam-seq-row');
        if (rows.length === 0) {
            log('No positions in sequence', 'warn');
            return;
        }
        if (!tfReady || !tfMatrix) {
            log('TF not ready — cannot run Cotton sequence', 'error');
            return;
        }

        // Validate all rows — bail if any are invalid
        var valid = true;
        rows.forEach(function (tr) {
            var result = camSeqValidateRow(tr);
            if (!result || !result.valid) { valid = false; }
        });
        if (!valid) {
            log('Cotton sequence: one or more rows are out of range (highlighted in red)', 'error');
            return;
        }

        var armKey = document.getElementById('cam-seq-arm-select')
            ? document.getElementById('cam-seq-arm-select').value
            : 'arm1';
        var cfg = ARM_CONFIGS[armKey];
        var dwellMs = parseFloat(document.getElementById('cam-seq-dwell')
            ? document.getElementById('cam-seq-dwell').value
            : 2) * 1000 || 2000;

        camSeqRunning = true;
        camSeqAborted = false;
        document.getElementById('cam-seq-run-btn').disabled  = true;
        document.getElementById('cam-seq-stop-btn').disabled = false;

        log('=== Cotton Sequence START === (arm=' + armKey + ', rows=' + rows.length + ')');

        for (var i = 0; i < rows.length; i++) {
            if (camSeqAborted || estopActive) {
                log('Cotton sequence halted');
                break;
            }
            var tr     = rows[i];
            var rowIdx = tr.id.replace('cam-seq-row-', '');
            var cam_x  = parseFloat(tr.querySelector('[data-col="cam_x"]').value) || 0;
            var cam_y  = parseFloat(tr.querySelector('[data-col="cam_y"]').value) || 0;
            var cam_z  = parseFloat(tr.querySelector('[data-col="cam_z"]').value) || 0;
            var result = camToJoint(tfMatrix, cam_x, cam_y, cam_z);

            tr.classList.add('cam-seq-active');
            var statusEl = document.getElementById('cam-seq-status-' + rowIdx);
            if (statusEl) statusEl.textContent = '▶';

            log('Cotton step ' + (i + 1) + ': J3=' + result.j3.toFixed(3) +
                ' J4=' + result.j4.toFixed(3) + ' J5=' + result.j5.toFixed(3));

            publishArmJoint(cfg.j3, result.j3);
            publishArmJoint(cfg.j4, result.j4);
            publishArmJoint(cfg.j5, result.j5);
            updateSliderUI(armKey, result.j3, result.j4, result.j5);

            await sleep(dwellMs);

            tr.classList.remove('cam-seq-active');
            if (statusEl) statusEl.textContent = camSeqAborted ? '🛑' : '✅';

            if (camSeqAborted || estopActive) break;
        }

        camSeqRunning = false;
        document.getElementById('cam-seq-run-btn').disabled  = false;
        document.getElementById('cam-seq-stop-btn').disabled = true;
        log('=== Cotton Sequence ' + (camSeqAborted ? 'ABORTED' : 'COMPLETE') + ' ===');
    }

    // =========================================================================
    // Initialisation
    // =========================================================================
    function init() {
        // Default rosbridge URL based on page host
        rosbridgeInput.value = getDefaultUrl();

        // Setup UI
        setupJoystick();
        setupKeyboard();
        setupArmSliders();
        setupSpeedModes();

        // Event listeners
        btnConnect.addEventListener('click', connect);
        rosbridgeInput.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') connect();
        });
        btnEstop.addEventListener('click', toggleEstop);

        btnSpawn.addEventListener('click', function () {
            doSpawn(urdfSelect.value);
        });
        btnRespawn.addEventListener('click', function () {
            doSpawn(urdfSelect.value);
        });

        // Arm cosine test
        setupArmTest();

        // Custom joint sequence — pre-populate with 3 default rows
        setupCustomSequence();
        seqAddRow();
        seqAddRow();
        seqAddRow();

        // Pre-computed camera-to-arm transform (no ROS2 TF needed)
        initCameraToArmTransform();
        updateCamSeqTfStatus(true);

        // Cotton placement (ported from yanthra_move)
        setupCottonPlacement();

        // Cotton position sequence
        setupCottonSequence();

        // Load data
        loadUrdfList();
        pollStatus();
        setInterval(pollStatus, STATUS_POLL_MS);

        // Auto-connect rosbridge
        setTimeout(connect, 500);

        log('Testing UI initialised');
    }

    // Start when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
