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

    // Preset scenario URL map — single source of truth for both
    // "Start Run" and "Run All Modes" buttons.
    var _PRESET_MAP = {
        contention: '/scenarios/contention_pack.json',
        geometry:   '/scenarios/geometry_pack.json',
    };

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

    // Pick animation state
    var pickRunning = false;
    var pickAborted = false;

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

    function showToast(message, type) {
        var toast = document.createElement('div');
        toast.className = 'toast toast-' + (type || 'info');
        toast.textContent = message;
        document.body.appendChild(toast);
        setTimeout(function () { toast.remove(); }, 5000);
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

    async function triplePublish(topic, value) {
        for (var i = 0; i < 3; i++) {
            publishArmJoint(topic, value);
            if (i < 2) await sleep(500);
        }
    }

    async function executePickAnimation(armKey, cottonName, j3, j4, j5) {
        var cfg = ARM_CONFIGS[armKey];
        if (!cfg) { log('Unknown arm: ' + armKey, 'error'); return; }

        function shouldAbort() { return estopActive || pickAborted; }

        // Step 1: J4 lateral
        if (shouldAbort()) return;
        await triplePublish(cfg.j4, j4);
        updateSliderUI(armKey, 0, j4, 0);
        await sleep(800);

        // Step 2: J3 tilt
        if (shouldAbort()) return;
        await triplePublish(cfg.j3, j3);
        updateSliderUI(armKey, j3, j4, 0);
        await sleep(800);

        // Step 3: J5 extend
        if (shouldAbort()) return;
        await triplePublish(cfg.j5, j5);
        updateSliderUI(armKey, j3, j4, j5);
        await sleep(1400);

        // Step 4: mark-picked
        if (shouldAbort()) return;
        try {
            await fetch('/api/cotton/' + cottonName + '/mark-picked', { method: 'POST' });
        } catch (e) {
            log('mark-picked failed: ' + e, 'error');
        }

        // Step 5: J5 retract
        if (shouldAbort()) return;
        await triplePublish(cfg.j5, 0);
        updateSliderUI(armKey, j3, j4, 0);
        await sleep(800);

        // Step 6: J3 home
        if (shouldAbort()) return;
        await triplePublish(cfg.j3, 0);
        updateSliderUI(armKey, 0, j4, 0);
        await sleep(800);

        // Step 7: J4 home
        if (shouldAbort()) return;
        await triplePublish(cfg.j4, 0);
        updateSliderUI(armKey, 0, 0, 0);
        await sleep(900);
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

    async function pickArmCottons(armKey, cottons) {
        for (var i = 0; i < cottons.length; i++) {
            if (pickAborted || estopActive) break;
            var c = cottons[i];
            log('[' + armKey + '] Picking ' + c.name + ' (' + (i + 1) + '/' + cottons.length + ')');
            await executePickAnimation(armKey, c.name, c.j3, c.j4, c.j5);
        }
    }

    async function cottonPickAll() {
        var params = getCottonParams();
        var pickAllBtn = document.getElementById('cotton-pick-all-btn');
        var removeAllBtn = document.getElementById('cotton-remove-all-btn');
        var statusDiv = document.getElementById('cotton-pick-status');
        var statusText = document.getElementById('cotton-pick-status-text');

        if (pickRunning) return;
        pickRunning = true;
        pickAborted = false;
        if (pickAllBtn) pickAllBtn.disabled = true;
        if (removeAllBtn) removeAllBtn.disabled = true;
        statusDiv.style.display = 'block';
        statusDiv.className = 'pick-status picking';
        statusText.textContent = 'Computing...';

        try {
            var resp = await fetch('/api/cotton/pick-all', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    enable_phi_compensation: params.enable_phi_compensation,
                }),
            });

            var data = await resp.json();
            if (!resp.ok) {
                log('Pick-all error: ' + (data.detail || 'unknown'), 'error');
                statusDiv.className = 'pick-status';
                statusText.textContent = 'Error';
                return;
            }

            if (data.status === 'nothing_to_pick') {
                log('No cottons to pick', 'warn');
                statusDiv.style.display = 'none';
                return;
            }

            if (data.warnings && data.warnings.length > 0) {
                data.warnings.forEach(function (w) { log('Warning: ' + w, 'warn'); });
            }

            var armKeys = Object.keys(data.arms);
            var total = armKeys.reduce(function (sum, k) { return sum + data.arms[k].length; }, 0);
            log('Pick-all: ' + total + ' cotton(s) across ' + armKeys.length + ' arm(s)', 'success');
            statusText.textContent = 'Animating ' + total + ' cotton(s)...';

            // Parallel across arms, sequential within each arm
            var promises = armKeys.map(function (armKey) {
                return pickArmCottons(armKey, data.arms[armKey]);
            });
            await Promise.all(promises);

            statusDiv.className = 'pick-status done';
            statusText.textContent = 'Done';
            log('Pick-all complete', 'success');
            setTimeout(function () { statusDiv.style.display = 'none'; }, 3000);
        } catch (e) {
            log('Pick-all error: ' + e, 'error');
            statusDiv.className = 'pick-status';
            statusText.textContent = 'Error';
        } finally {
            pickRunning = false;
            if (pickAllBtn) pickAllBtn.disabled = false;
            if (removeAllBtn) removeAllBtn.disabled = false;
        }
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

    async function cottonPick() {
        var params = getCottonParams();
        var pickBtn = document.getElementById('cotton-pick-btn');
        var statusDiv = document.getElementById('cotton-pick-status');
        var statusText = document.getElementById('cotton-pick-status-text');

        if (pickRunning) return;
        pickRunning = true;
        pickAborted = false;
        pickBtn.disabled = true;
        statusDiv.style.display = 'block';
        statusDiv.className = 'pick-status picking';
        statusText.textContent = 'Computing...';

        try {
            var resp = await fetch('/api/cotton/pick', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    arm: params.arm,
                    enable_phi_compensation: params.enable_phi_compensation,
                }),
            });

            if (!resp.ok) {
                var err = await resp.json();
                throw new Error(err.detail || ('HTTP ' + resp.status));
            }

            var d = await resp.json();
            if (!d.reachable) {
                log('Unreachable: ' + (d.reason || 'target out of range'), 'error');
                showToast('Unreachable: ' + (d.reason || 'target out of range'), 'error');
                statusDiv.className = 'pick-status';
                statusText.textContent = 'Unreachable';
                return;
            }

            log('Pick: J3=' + d.j3.toFixed(3) + ' J4=' + d.j4.toFixed(3) +
                ' J5=' + d.j5.toFixed(3) + ' → animating...', 'success');
            statusText.textContent = 'Animating...';

            await executePickAnimation(d.arm, d.cotton_name, d.j3, d.j4, d.j5);

            statusDiv.className = 'pick-status done';
            statusText.textContent = 'Done';
            log('Pick complete', 'success');
            setTimeout(function () { statusDiv.style.display = 'none'; }, 3000);
        } catch (e) {
            log('Pick error: ' + e, 'error');
            statusDiv.className = 'pick-status';
            statusText.textContent = 'Error';
        } finally {
            pickRunning = false;
            pickBtn.disabled = false;
        }
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

        // Cotton placement (ported from yanthra_move)
        setupCottonPlacement();

        // UI Run Flow
        setupRunFlow();
        setupRunAllModes();

        // Load data
        loadUrdfList();
        pollStatus();
        setInterval(pollStatus, STATUS_POLL_MS);

        // Auto-connect rosbridge
        setTimeout(connect, 500);

        log('Testing UI initialised');
    }

    // ---------------------------------------------------------------------------
    // UI Run Flow
    // ---------------------------------------------------------------------------
    function setupRunFlow() {
        const startBtn = document.getElementById('run-start-btn');
        const statusEl = document.getElementById('run-status-text');
        const reportLinks = document.getElementById('run-report-links');
        const jsonLink = document.getElementById('run-report-json-link');
        const mdLink = document.getElementById('run-report-md-link');

        if (!startBtn) return;

        startBtn.addEventListener('click', async () => {
            statusEl.textContent = 'Starting run...';
            reportLinks.style.display = 'none';

            // Resolve scenario data
            let scenarioData = null;

            // 1. Check file input first
            const fileInput = document.getElementById('run-scenario-file');
            if (fileInput && fileInput.files.length > 0) {
                try {
                    const text = await fileInput.files[0].text();
                    scenarioData = JSON.parse(text);
                } catch (e) {
                    statusEl.textContent = 'Error: could not parse JSON file.';
                    return;
                }
            }

            // 2. Fall back to preset select
            if (!scenarioData) {
                const presetSelect = document.getElementById('run-scenario-select');
                const preset = presetSelect ? presetSelect.value : '';
                if (preset) {
                    try {
                        const resp = await fetch(_PRESET_MAP[preset]);
                        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                        scenarioData = await resp.json();
                    } catch (e) {
                        statusEl.textContent = `Error: could not load preset scenario.`;
                        return;
                    }
                }
            }

            if (!scenarioData) {
                statusEl.textContent = 'Error: no scenario selected.';
                return;
            }

            const modeSelect = document.getElementById('run-mode-select');
            const mode = modeSelect ? parseInt(modeSelect.value, 10) : 0;

            const armPairSelect = document.getElementById('run-arm-pair-select');
            const armPair = armPairSelect ? armPairSelect.value.split(',') : ['arm1', 'arm2'];

            const phiCompCheckbox = document.getElementById('cotton-phi-comp');
            const enablePhiComp = phiCompCheckbox ? phiCompCheckbox.checked : true;

            // Open SSE stream BEFORE starting the run so we capture all events
            var evtSource = new EventSource('/api/run/events');
            evtSource.onmessage = function (e) {
                try {
                    var evt = JSON.parse(e.data);
                    var t = evt.type || 'unknown';
                    if (t === 'cotton_spawn') {
                        log('Cotton spawned: step ' + evt.step_id +
                            ' ' + evt.arm_id +
                            ' cam_z=' + evt.cam_z);
                    } else if (t === 'step_start') {
                        log('Step ' + evt.step_id + ' ' + evt.arm_id +
                            ' starting -> target (x:' + evt.cam_x +
                            ', y:' + evt.cam_y +
                            ', z:' + evt.cam_z + ')');
                    } else if (t === 'cotton_reached') {
                        log(evt.arm_id + ' reached cotton (step:' + evt.step_id +
                            ', x:' + evt.cam_x +
                            ', y:' + evt.cam_y +
                            ', z:' + evt.cam_z + ')', 'success');
                    } else if (t === 'contention_detected') {
                        log('Contention at step ' + evt.step_id + ': ' +
                            evt.winner_arm + ' wins, ' +
                            evt.loser_arm + ' waits (gap=' + evt.j4_gap + 'm)', 'warn');
                    } else if (t === 'dispatch_order') {
                        var seq = evt.sequence || [];
                        if (evt.order === 'sequential') {
                            log('Step ' + evt.step_id + ': sequential dispatch [' +
                                seq[0] + ' -> ' + seq[1] + ']');
                        } else {
                            log('Step ' + evt.step_id + ': parallel dispatch [' +
                                seq.join(', ') + ']');
                        }
                    } else if (t === 'reorder_applied') {
                        log('Reorder applied: ' + evt.reordered_step_count +
                            ' steps, min j4 gap=' + evt.min_j4_gap + 'm', 'success');
                    } else if (t === 'step_complete') {
                        var cls = evt.collision ? 'warn' : 'success';
                        var status = evt.terminal_status || 'complete';
                        log('Step ' + evt.step_id + ' ' + status +
                            (evt.collision ? ' (COLLISION)' : ''), cls);
                    } else if (t === 'run_complete') {
                        log('Run complete: ' + evt.run_id, 'success');
                        evtSource.close();
                    }
                } catch (err) {
                    log('SSE parse error: ' + err.message, 'error');
                }
            };
            evtSource.onerror = function () {
                // Do NOT call close() here — that permanently disables
                // the browser's built-in EventSource auto-reconnect. Let the browser
                // reconnect on its own; run_complete handler closes the stream cleanly.
            };

            try {
                const resp = await fetch('/api/run/start', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        mode,
                        scenario: scenarioData,
                        arm_pair: armPair,
                        enable_phi_compensation: enablePhiComp,
                    }),
                });
                if (!resp.ok) {
                    const err = await resp.text();
                    statusEl.textContent = `Run failed: ${err}`;
                    evtSource.close();
                    return;
                }
                const data = await resp.json();
                statusEl.textContent = `Run complete (id: ${data.run_id})`;
                jsonLink.href = '/api/run/report/json';
                mdLink.href = '/api/run/report/markdown';
                reportLinks.style.display = '';
            } catch (e) {
                statusEl.textContent = `Error: ${e.message}`;
                evtSource.close();
            }
        });
    }

    // ---------------------------------------------------------------------------
    // All-Modes Comparison
    // ---------------------------------------------------------------------------

    function openModal() {
        const modal = document.getElementById('all-modes-modal');
        if (modal) modal.style.display = 'flex';
    }

    function closeModal() {
        const modal = document.getElementById('all-modes-modal');
        if (modal) modal.style.display = 'none';
    }

    function renderComparisonTable(summaries, recommendation) {
        const container = document.getElementById('all-modes-table-container');
        const recEl = document.getElementById('all-modes-recommendation');
        if (!container) return;

        const cols = [
            'Mode', 'Total Steps', 'Near-Collision', 'Collision',
            'Blocked', 'Blocked+Skipped', 'Completed Picks'
        ];
        let html = '<table class="comparison-table"><thead><tr>';
        cols.forEach(c => { html += `<th>${c}</th>`; });
        html += '</tr></thead><tbody>';

        summaries.forEach(s => {
            const isBest = (s.mode === recommendation);
            const rowCls = isBest ? ' class="row-best"' : '';
            html += `<tr${rowCls}>`;
            html += `<td>${s.mode}</td>`;
            html += `<td>${s.total_steps}</td>`;
            html += _colorCell(s.steps_with_near_collision, 'near');
            html += _colorCell(s.steps_with_collision, 'collision');
            html += `<td>${s.steps_with_motion_blocked}</td>`;
            const bs = s.steps_with_blocked_or_skipped
                       != null ? s.steps_with_blocked_or_skipped
                       : s.steps_with_motion_blocked;
            html += `<td>${bs}</td>`;
            html += `<td>${s.completed_picks}</td>`;
            html += '</tr>';
        });

        html += '</tbody></table>';
        container.innerHTML = html;

        if (recEl) {
            recEl.textContent = recommendation
                ? `Recommended mode: ${recommendation}`
                : '';
        }
    }

    function _colorCell(value, type) {
        if (value === 0) {
            return `<td class="cell-green">${value}</td>`;
        }
        if (type === 'collision') {
            return `<td class="cell-red">${value}</td>`;
        }
        return `<td class="cell-amber">${value}</td>`;
    }

    function setupRunAllModes() {
        const btn = document.getElementById('run-all-modes-btn');
        const statusEl = document.getElementById('run-all-modes-status');
        const modalCloseBtn = document.getElementById('all-modes-modal-close');
        const modal = document.getElementById('all-modes-modal');

        if (!btn) return;

        // Close modal handlers
        if (modalCloseBtn) {
            modalCloseBtn.addEventListener('click', closeModal);
        }
        if (modal) {
            modal.addEventListener('click', (e) => {
                if (e.target === modal) closeModal();
            });
        }

        btn.addEventListener('click', async () => {
            btn.disabled = true;
            btn.innerHTML =
                '<span class="spinner"></span>Running...';
            if (statusEl) statusEl.textContent = '';

            // Resolve scenario: file input takes priority over preset
            let scenario = null;
            const fileInput = document.getElementById('run-scenario-file');
            const presetSel = document.getElementById('run-scenario-select');

            if (fileInput && fileInput.files.length > 0) {
                try {
                    const text = await fileInput.files[0].text();
                    scenario = JSON.parse(text);
                } catch (err) {
                    if (statusEl) statusEl.textContent =
                        `JSON parse error: ${err.message}`;
                    btn.disabled = false;
                    btn.textContent = 'Run All Modes';
                    return;
                }
            } else if (presetSel && presetSel.value) {
                try {
                    const url = _PRESET_MAP[presetSel.value];
                    if (!url) throw new Error(
                        'Unknown preset: ' + presetSel.value
                    );
                    const resp = await fetch(url);
                    if (!resp.ok) throw new Error(resp.statusText);
                    scenario = await resp.json();
                } catch (err) {
                    if (statusEl) statusEl.textContent =
                        `Preset load error: ${err.message}`;
                    btn.disabled = false;
                    btn.textContent = 'Run All Modes';
                    return;
                }
            }

            if (!scenario) {
                if (statusEl) statusEl.textContent =
                    'Select a preset or load a JSON file first.';
                btn.disabled = false;
                btn.textContent = 'Run All Modes';
                return;
            }

            // Read arm pair and phi compensation from existing selects
            const armPairSel =
                document.getElementById('run-arm-pair-select');
            const armPair = armPairSel
                ? armPairSel.value.split(',')
                : ['arm1', 'arm2'];

            const phiCheckbox =
                document.getElementById('run-phi-compensation');
            const enablePhi = phiCheckbox
                ? phiCheckbox.checked : true;

            try {
                const resp = await fetch('/api/run/start-all-modes', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        scenario: scenario,
                        arm_pair: armPair,
                        enable_phi_compensation: enablePhi,
                    }),
                });

                if (!resp.ok) {
                    const err = await resp.json();
                    throw new Error(
                        err.detail || `HTTP ${resp.status}`
                    );
                }

                const data = await resp.json();
                renderComparisonTable(
                    data.summaries, data.recommendation
                );
                openModal();
                if (statusEl) statusEl.textContent = 'Complete';
                log('All-modes comparison complete: recommended '
                    + data.recommendation);
            } catch (err) {
                if (statusEl) statusEl.textContent =
                    `Error: ${err.message}`;
                log('All-modes run failed: ' + err.message);
            } finally {
                btn.disabled = false;
                btn.textContent = 'Run All Modes';
            }
        });
    }

    // Start when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
