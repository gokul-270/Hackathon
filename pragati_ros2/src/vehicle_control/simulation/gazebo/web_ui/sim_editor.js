// ============================================
// Pragati Robot — Simulation Editor Logic
// ============================================

(function () {
    'use strict';

    // ---- Constants ----
    const BACKEND_RECONNECT_MS = 3000;
    const ROSBRIDGE_RECONNECT_MS = 3000;
    const GRID_COLOR = 'rgba(79, 195, 247, 0.08)';
    const GRID_AXIS_COLOR = 'rgba(79, 195, 247, 0.25)';
    const TERRAIN_FILL = 'rgba(141, 110, 70, 0.18)';
    const TERRAIN_STROKE = 'rgba(141, 110, 70, 0.5)';
    const PLANT_COLORS = {
        small:  '#66bb6a',
        medium: '#43a047',
        tall:   '#2e7d32',
    };
    const VEHICLE_COLOR = '#ff5722';
    const VEHICLE_SIZE_M = 0.45;  // approximate vehicle footprint in meters

    // ---- Unit conversion (UI uses feet, Gazebo uses meters) ----
    const FT_TO_M = 0.3048;
    const M_TO_FT = 1.0 / FT_TO_M;  // ≈ 3.28084

    // ---- Default Config (spacing in METERS — canonical unit) ----
    const DEFAULTS = {
        rows: 5,
        cols: 7,
        rowSpacing: 0.9,   // meters
        colSpacing: 0.7,   // meters
        terrainScale: 5,
        terrainZ: 0.1,
        autoTerrain: true,
    };

    // ---- State ----
    let backendWs = null;
    let backendReconnectTimer = null;
    let currentConfig = null;  // from backend (parsed SDF)
    let previewConfig = null;  // user-modified config for canvas
    let unitMode = 'ft';       // 'ft' or 'm' — current UI unit for spacing

    // Vehicle pose from odometry (live)
    let vehiclePose = { x: 0, y: 0, theta: 0 };
    let ros = null;
    let odomTopic = null;
    let rosReconnectTimer = null;
    let redrawScheduled = false;

    // ---- DOM References ----
    const canvas = document.getElementById('field-canvas');
    const ctx = canvas.getContext('2d');
    const hoverInfo = document.getElementById('canvas-hover-info');

    const inputRows = document.getElementById('input-rows');
    const inputCols = document.getElementById('input-cols');
    const inputRowSpacing = document.getElementById('input-row-spacing');
    const inputColSpacing = document.getElementById('input-col-spacing');
    const inputTerrainScale = document.getElementById('input-terrain-scale');
    const inputTerrainZ = document.getElementById('input-terrain-z');
    const inputAutoTerrain = document.getElementById('input-auto-terrain');
    const terrainSizeHint = document.getElementById('terrain-size-hint');

    const mixSmall = document.getElementById('mix-small');
    const mixMedium = document.getElementById('mix-medium');
    const mixTall = document.getElementById('mix-tall');
    const mixSmallPct = document.getElementById('mix-small-pct');
    const mixMediumPct = document.getElementById('mix-medium-pct');
    const mixTallPct = document.getElementById('mix-tall-pct');

    const previewBtn = document.getElementById('preview-btn');
    const applyBtn = document.getElementById('apply-btn');
    const resetBtn = document.getElementById('reset-btn');

    const statusEl = document.getElementById('editor-status');
    const statusText = document.getElementById('editor-status-text');
    const statusIcon = document.getElementById('editor-status-icon');

    const backendDot = document.getElementById('backend-dot');
    const backendTextEl = document.getElementById('backend-text');
    const rosDot = document.getElementById('ros-dot');
    const rosTextEl = document.getElementById('ros-text');

    // Current config display elements
    const curGridSize = document.getElementById('cur-grid-size');
    const curRowSpacing = document.getElementById('cur-row-spacing');
    const curColSpacing = document.getElementById('cur-col-spacing');
    const curTotalPlants = document.getElementById('cur-total-plants');
    const curFieldSize = document.getElementById('cur-field-size');
    const curTerrainSize = document.getElementById('cur-terrain-size');
    const curVehiclePose = document.getElementById('cur-vehicle-pose');

    const unitToggleBtn = document.getElementById('unit-toggle-btn');
    const labelRowSpacing = document.getElementById('label-row-spacing');
    const labelColSpacing = document.getElementById('label-col-spacing');

    // ========================================
    // Unit Toggle (ft ↔ m)
    // ========================================

    function updateSpacingLabels() {
        var u = unitLabel();
        if (labelRowSpacing) labelRowSpacing.textContent = 'Row Spacing (' + u + ')';
        if (labelColSpacing) labelColSpacing.textContent = 'Col Spacing (' + u + ')';
        if (unitToggleBtn) {
            unitToggleBtn.textContent = u;
            unitToggleBtn.className = 'unit-toggle-btn ' + (unitMode === 'ft' ? 'active-ft' : 'active-m');
        }
        // Update input constraints
        if (unitMode === 'ft') {
            inputRowSpacing.min = '1.0'; inputRowSpacing.max = '16.0'; inputRowSpacing.step = '0.5';
            inputColSpacing.min = '1.0'; inputColSpacing.max = '16.0'; inputColSpacing.step = '0.5';
        } else {
            inputRowSpacing.min = '0.1'; inputRowSpacing.max = '5.0'; inputRowSpacing.step = '0.05';
            inputColSpacing.min = '0.1'; inputColSpacing.max = '5.0'; inputColSpacing.step = '0.05';
        }
    }

    if (unitToggleBtn) {
        unitToggleBtn.addEventListener('click', function () {
            // Read current values as meters
            var rsM = uiValueToMeters(parseFloat(inputRowSpacing.value) || 0.9);
            var csM = uiValueToMeters(parseFloat(inputColSpacing.value) || 0.7);

            // Flip unit mode
            unitMode = (unitMode === 'ft') ? 'm' : 'ft';

            // Convert meter values to new UI unit
            inputRowSpacing.value = metersToUIValue(rsM).toFixed(unitMode === 'ft' ? 1 : 2);
            inputColSpacing.value = metersToUIValue(csM).toFixed(unitMode === 'ft' ? 1 : 2);

            // Update labels, constraints, and displays
            updateSpacingLabels();
            if (currentConfig) updateCurrentDisplay(currentConfig);
            drawField(previewConfig || currentConfig || getUIConfig());
        });
    }

    // ========================================
    // Rosbridge Connection (live odometry)
    // ========================================

    function connectRos() {
        if (typeof ROSLIB === 'undefined') {
            console.warn('ROSLIB not loaded — vehicle pose will not update live');
            return;
        }

        const host = window.location.hostname || 'localhost';
        const url = 'ws://' + host + ':9090';

        ros = new ROSLIB.Ros({ url: url });

        ros.on('connection', function () {
            if (rosDot) rosDot.className = 'dot connected';
            if (rosTextEl) rosTextEl.textContent = 'ROS';
            clearRosReconnect();
            subscribeOdom();
        });

        ros.on('close', function () {
            if (rosDot) rosDot.className = 'dot disconnected';
            scheduleRosReconnect();
        });

        ros.on('error', function () {
            if (rosDot) rosDot.className = 'dot disconnected';
        });
    }

    function subscribeOdom() {
        if (odomTopic) { odomTopic.unsubscribe(); }

        odomTopic = new ROSLIB.Topic({
            ros: ros,
            name: '/odom',
            messageType: 'nav_msgs/msg/Odometry',
            throttle_rate: 200,  // 5 Hz max
        });

        // Kinematic-center offset from base-v1 (right rear wheel):
        // 0.65 m forward, 0.90 m kinematic-Y (maps to world -Y at θ=0)
        var KC_FWD = 0.65, KC_LAT = 0.90;

        odomTopic.subscribe(function (msg) {
            var pos = msg.pose.pose.position;
            var q = msg.pose.pose.orientation;
            // Quaternion to yaw
            var siny = 2.0 * (q.w * q.z + q.x * q.y);
            var cosy = 1.0 - 2.0 * (q.y * q.y + q.z * q.z);
            var theta = Math.atan2(siny, cosy);
            // Transform from base-v1 to kinematic center
            var cosT = Math.cos(theta), sinT = Math.sin(theta);
            vehiclePose.x = pos.x + KC_FWD * cosT + KC_LAT * sinT;
            vehiclePose.y = pos.y + KC_FWD * sinT - KC_LAT * cosT;
            vehiclePose.theta = theta;

            // Update vehicle pose display
            if (curVehiclePose) {
                curVehiclePose.textContent = vehiclePose.x.toFixed(2) + ', ' + vehiclePose.y.toFixed(2) + ' (\u03b8=' + (vehiclePose.theta * 180 / Math.PI).toFixed(1) + '\u00b0)';
            }

            scheduleRedraw();
        });
    }

    function scheduleRedraw() {
        if (redrawScheduled) return;
        redrawScheduled = true;
        requestAnimationFrame(function () {
            redrawScheduled = false;
            drawField(previewConfig || currentConfig || getUIConfig());
        });
    }

    function scheduleRosReconnect() {
        clearRosReconnect();
        rosReconnectTimer = setTimeout(connectRos, ROSBRIDGE_RECONNECT_MS);
    }

    function clearRosReconnect() {
        if (rosReconnectTimer) { clearTimeout(rosReconnectTimer); rosReconnectTimer = null; }
    }

    // ========================================
    // Backend WebSocket
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
            backendTextEl.textContent = 'Backend';
            clearBackendReconnect();
            // Request current simulation config
            backendSend({ type: 'get_sim_config' });
        };

        backendWs.onclose = function () {
            backendDot.className = 'dot disconnected';
            backendTextEl.textContent = 'Backend';
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
                console.error('Backend parse error:', e);
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

            case 'sim_config':
                currentConfig = msg.config;
                syncUIFromConfig(currentConfig);
                updateCurrentDisplay(currentConfig);
                drawField(currentConfig);
                break;

            case 'sim_config_applied':
                setStatus('success', '\u2713 Applied! ' + (msg.plants_updated || (msg.config.rows * msg.config.cols)) + ' plants updated in Gazebo.');
                applyBtn.disabled = false;
                // Refresh config
                currentConfig = msg.config;
                previewConfig = null;
                syncUIFromConfig(msg.config);
                updateCurrentDisplay(msg.config);
                drawField(msg.config);
                break;

            case 'sim_config_error':
                setStatus('error', 'Error: ' + msg.message);
                applyBtn.disabled = false;
                break;

            case 'error':
                console.warn('Backend error:', msg.message);
                break;

            default:
                break;
        }
    }

    // ========================================
    // Config helpers
    // ========================================

    function uiValueToMeters(val) {
        return unitMode === 'ft' ? val * FT_TO_M : val;
    }

    function metersToUIValue(m) {
        return unitMode === 'ft' ? m * M_TO_FT : m;
    }

    function unitLabel() {
        return unitMode === 'ft' ? 'ft' : 'm';
    }

    function getUIConfig() {
        const rows = parseInt(inputRows.value) || DEFAULTS.rows;
        const cols = parseInt(inputCols.value) || DEFAULTS.cols;
        // Convert UI spacing to meters for Gazebo
        const rowSpacingUI = parseFloat(inputRowSpacing.value) || metersToUIValue(DEFAULTS.rowSpacing);
        const colSpacingUI = parseFloat(inputColSpacing.value) || metersToUIValue(DEFAULTS.colSpacing);
        const rowSpacing = uiValueToMeters(rowSpacingUI);
        const colSpacing = uiValueToMeters(colSpacingUI);
        let terrainScale = parseInt(inputTerrainScale.value) || DEFAULTS.terrainScale;
        const terrainZ = parseFloat(inputTerrainZ.value);

        // Auto-fit terrain (in meters)
        if (inputAutoTerrain.checked) {
            const fieldW = (cols - 1) * colSpacing + 3;  // +3m margin
            const fieldH = (rows - 1) * rowSpacing + 3;
            const needed = Math.max(fieldW, fieldH);
            terrainScale = Math.max(1, Math.ceil(needed / 2));
            inputTerrainScale.value = terrainScale;
        }

        // Build plant grid (in meters)
        const plants = generatePlantGrid(rows, cols, rowSpacing, colSpacing);

        return {
            rows: rows,
            cols: cols,
            row_spacing: rowSpacing,
            col_spacing: colSpacing,
            terrain_scale: terrainScale,
            terrain_z: isNaN(terrainZ) ? DEFAULTS.terrainZ : terrainZ,
            plants: plants,
            field_width: (cols - 1) * colSpacing,
            field_height: (rows - 1) * rowSpacing,
        };
    }

    function generatePlantGrid(rows, cols, rowSpacing, colSpacing) {
        const plants = [];
        const xStart = -(cols - 1) / 2 * colSpacing;
        const yStart = -(rows - 1) / 2 * rowSpacing;

        // Get mix ratios
        const sW = parseInt(mixSmall.value);
        const mW = parseInt(mixMedium.value);
        const tW = parseInt(mixTall.value);
        const total = sW + mW + tW || 1;

        // Use seeded pseudo-random for consistency
        let seed = 42;
        function rand() {
            seed = (seed * 16807 + 0) % 2147483647;
            return seed / 2147483647;
        }

        for (let r = 0; r < rows; r++) {
            for (let c = 0; c < cols; c++) {
                const x = xStart + c * colSpacing;
                const y = yStart + r * rowSpacing;
                const yaw = rand() * Math.PI * 2;

                // Weighted random type
                const roll = rand() * total;
                let plantType = 'small';
                if (roll < sW) plantType = 'small';
                else if (roll < sW + mW) plantType = 'medium';
                else plantType = 'tall';

                plants.push({
                    name: 'cotton_plant_r' + r + '_p' + c,
                    type: plantType,
                    x: parseFloat(x.toFixed(4)),
                    y: parseFloat(y.toFixed(4)),
                    yaw: parseFloat(yaw.toFixed(4)),
                });
            }
        }
        return plants;
    }

    function syncUIFromConfig(config) {
        if (!config) return;
        inputRows.value = config.rows || DEFAULTS.rows;
        inputCols.value = config.cols || DEFAULTS.cols;
        // Config from backend is in meters — convert to current UI unit
        inputRowSpacing.value = metersToUIValue(config.row_spacing || 0.9).toFixed(unitMode === 'ft' ? 1 : 2);
        inputColSpacing.value = metersToUIValue(config.col_spacing || 0.7).toFixed(unitMode === 'ft' ? 1 : 2);
        inputTerrainScale.value = config.terrain_scale || DEFAULTS.terrainScale;
        inputTerrainZ.value = config.terrain_z != null ? config.terrain_z : DEFAULTS.terrainZ;
        updateSpacingLabels();
        updateTerrainHint();
    }

    function updateCurrentDisplay(config) {
        if (!config) return;
        const r = config.rows || 0;
        const c = config.cols || 0;
        const rs = config.row_spacing || 0;
        const cs = config.col_spacing || 0;
        const fw = ((c - 1) * cs).toFixed(2);
        const fh = ((r - 1) * rs).toFixed(2);
        const ts = config.terrain_scale || 5;

        curGridSize.textContent = r + ' rows × ' + c + ' columns';
        var u = unitLabel();
        curRowSpacing.textContent = metersToUIValue(rs).toFixed(2) + ' ' + u;
        curColSpacing.textContent = metersToUIValue(cs).toFixed(2) + ' ' + u;
        curTotalPlants.textContent = (r * c).toString();
        curFieldSize.textContent = metersToUIValue(fw).toFixed(1) + ' × ' + metersToUIValue(fh).toFixed(1) + ' ' + u;
        curTerrainSize.textContent = '~' + (ts * 2) + ' × ' + (ts * 2) + ' m';
        // Vehicle pose is updated live from /odom subscription
    }

    function updateTerrainHint() {
        const scale = parseInt(inputTerrainScale.value) || 5;
        terrainSizeHint.textContent = (scale * 2).toString();
    }

    // ========================================
    // Canvas Drawing
    // ========================================

    function drawField(config) {
        if (!config) config = getUIConfig();

        const wrapper = canvas.parentElement;
        const dpr = window.devicePixelRatio || 1;
        const w = wrapper.clientWidth;
        const h = wrapper.clientHeight;
        canvas.width = w * dpr;
        canvas.height = h * dpr;
        canvas.style.width = w + 'px';
        canvas.style.height = h + 'px';
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

        // Determine world bounds to fit
        const terrainHalfSize = (config.terrain_scale || 5) * 1.0;  // actual meters (scale * 2m base / 2)
        const fieldHalfW = config.field_width ? config.field_width / 2 + 0.5 : 3;
        const fieldHalfH = config.field_height ? config.field_height / 2 + 0.5 : 3;
        // Extend bounds to include vehicle position
        const vExtentX = Math.abs(vehiclePose.x) + 1;
        const vExtentY = Math.abs(vehiclePose.y) + 1;
        const worldHalf = Math.max(terrainHalfSize, fieldHalfW, fieldHalfH, vExtentX, vExtentY, 2) + 0.5;

        // Pixels per meter: fit the world into canvas with padding
        const padPx = 40;
        const ppm = Math.min((w - 2 * padPx) / (2 * worldHalf), (h - 2 * padPx) / (2 * worldHalf));

        // Center of canvas = world origin
        const cx = w / 2;
        const cy = h / 2;

        // World coord → pixel
        function toPixel(wx, wy) {
            return [cx + wx * ppm, cy - wy * ppm];  // Y inverted (up = positive Y)
        }

        // Clear
        ctx.clearRect(0, 0, w, h);

        // ---- Grid lines ----
        const gridStep = getGridStep(worldHalf);
        document.getElementById('grid-scale-label').textContent = gridStep.toFixed(1);

        ctx.lineWidth = 0.5;
        ctx.strokeStyle = GRID_COLOR;
        ctx.beginPath();

        for (let gx = -Math.ceil(worldHalf / gridStep) * gridStep; gx <= worldHalf; gx += gridStep) {
            const [px] = toPixel(gx, 0);
            ctx.moveTo(px, padPx / 2);
            ctx.lineTo(px, h - padPx / 2);
        }
        for (let gy = -Math.ceil(worldHalf / gridStep) * gridStep; gy <= worldHalf; gy += gridStep) {
            const [, py] = toPixel(0, gy);
            ctx.moveTo(padPx / 2, py);
            ctx.lineTo(w - padPx / 2, py);
        }
        ctx.stroke();

        // ---- Axes ----
        ctx.lineWidth = 1;
        ctx.strokeStyle = GRID_AXIS_COLOR;
        ctx.beginPath();
        // X-axis
        ctx.moveTo(padPx / 2, cy);
        ctx.lineTo(w - padPx / 2, cy);
        // Y-axis
        ctx.moveTo(cx, padPx / 2);
        ctx.lineTo(cx, h - padPx / 2);
        ctx.stroke();

        // Axis labels
        ctx.fillStyle = '#556677';
        ctx.font = '11px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('X (m)', w - padPx / 2 + 14, cy - 4);
        ctx.fillText('Y (m)', cx + 14, padPx / 2 - 4);

        // Grid labels
        ctx.fillStyle = '#445566';
        ctx.font = '10px monospace';
        for (let gx = -Math.ceil(worldHalf / gridStep) * gridStep; gx <= worldHalf; gx += gridStep) {
            if (Math.abs(gx) < 0.001) continue;
            const [px] = toPixel(gx, 0);
            ctx.fillText(gx.toFixed(1), px, cy + 14);
        }
        for (let gy = -Math.ceil(worldHalf / gridStep) * gridStep; gy <= worldHalf; gy += gridStep) {
            if (Math.abs(gy) < 0.001) continue;
            const [, py] = toPixel(0, gy);
            ctx.fillText(gy.toFixed(1), cx - 20, py + 4);
        }

        // ---- Terrain rectangle ----
        const tHalf = (config.terrain_scale || 5);  // terrain is scale*2m, so half = scale
        const [tLeft, tTop] = toPixel(-tHalf, tHalf);
        const terrainPxW = tHalf * 2 * ppm;
        const terrainPxH = tHalf * 2 * ppm;

        ctx.fillStyle = TERRAIN_FILL;
        ctx.fillRect(tLeft, tTop, terrainPxW, terrainPxH);
        ctx.strokeStyle = TERRAIN_STROKE;
        ctx.lineWidth = 1.5;
        ctx.setLineDash([6, 4]);
        ctx.strokeRect(tLeft, tTop, terrainPxW, terrainPxH);
        ctx.setLineDash([]);

        // Terrain label
        ctx.fillStyle = 'rgba(141, 110, 70, 0.6)';
        ctx.font = '10px sans-serif';
        ctx.textAlign = 'left';
        ctx.fillText('Terrain ' + (tHalf * 2).toFixed(0) + '×' + (tHalf * 2).toFixed(0) + 'm', tLeft + 4, tTop + 12);

        // ---- Plant dots ----
        const plants = config.plants || [];
        const plantRadius = Math.max(4, Math.min(10, ppm * 0.08));

        plants.forEach(function (p) {
            const [px, py] = toPixel(p.x, p.y);
            const color = PLANT_COLORS[p.type] || PLANT_COLORS.small;

            // Outer glow
            ctx.beginPath();
            ctx.arc(px, py, plantRadius + 2, 0, Math.PI * 2);
            ctx.fillStyle = color + '33';  // alpha
            ctx.fill();

            // Main dot
            ctx.beginPath();
            ctx.arc(px, py, plantRadius, 0, Math.PI * 2);
            ctx.fillStyle = color;
            ctx.fill();

            // Inner highlight
            ctx.beginPath();
            ctx.arc(px - 1, py - 1, plantRadius * 0.35, 0, Math.PI * 2);
            ctx.fillStyle = 'rgba(255,255,255,0.25)';
            ctx.fill();
        });

        // ---- Vehicle (from live odometry) ----
        const [vx, vy] = toPixel(vehiclePose.x, vehiclePose.y);
        const vSizePx = Math.max(12, VEHICLE_SIZE_M * ppm);

        ctx.save();
        ctx.translate(vx, vy);
        // Rotate: canvas Y is inverted, theta is CCW from +X
        ctx.rotate(-vehiclePose.theta);

        ctx.fillStyle = VEHICLE_COLOR + 'cc';
        ctx.strokeStyle = VEHICLE_COLOR;
        ctx.lineWidth = 2;

        // Draw as a small arrow/triangle pointing in +X direction
        ctx.beginPath();
        ctx.moveTo(vSizePx * 0.6, 0);        // nose (+X)
        ctx.lineTo(-vSizePx * 0.4, -vSizePx * 0.35);
        ctx.lineTo(-vSizePx * 0.25, 0);
        ctx.lineTo(-vSizePx * 0.4, vSizePx * 0.35);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();

        // Center dot
        ctx.beginPath();
        ctx.arc(0, 0, 3, 0, Math.PI * 2);
        ctx.fillStyle = '#fff';
        ctx.fill();
        ctx.restore();

        // Vehicle label
        ctx.fillStyle = '#ff8a65';
        ctx.font = '10px sans-serif';
        ctx.textAlign = 'left';
        ctx.fillText('Vehicle', vx + vSizePx * 0.7, vy - 6);
        ctx.font = '9px monospace';
        ctx.fillStyle = '#cc7755';
        ctx.fillText('(' + vehiclePose.x.toFixed(1) + ', ' + vehiclePose.y.toFixed(1) + ')', vx + vSizePx * 0.7, vy + 6);

        // ---- Field boundary (plant extent) ----
        if (plants.length > 0) {
            const fw = config.field_width || 0;
            const fh = config.field_height || 0;
            const [bLeft, bTop] = toPixel(-fw / 2 - 0.15, fh / 2 + 0.15);
            const bW = (fw + 0.3) * ppm;
            const bH = (fh + 0.3) * ppm;

            ctx.strokeStyle = 'rgba(102, 187, 106, 0.3)';
            ctx.lineWidth = 1;
            ctx.setLineDash([3, 3]);
            ctx.strokeRect(bLeft, bTop, bW, bH);
            ctx.setLineDash([]);
        }

        // Store transform info for hover
        canvas._fieldInfo = { cx, cy, ppm, worldHalf, padPx };
    }

    function getGridStep(worldHalf) {
        const range = worldHalf * 2;
        if (range <= 4) return 0.5;
        if (range <= 8) return 1.0;
        if (range <= 16) return 2.0;
        if (range <= 32) return 5.0;
        return 10.0;
    }

    // ---- Hover tooltip ----
    canvas.addEventListener('mousemove', function (e) {
        if (!canvas._fieldInfo) return;
        const rect = canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        const fi = canvas._fieldInfo;

        const wx = ((mx - fi.cx) / fi.ppm).toFixed(2);
        const wy = ((fi.cy - my) / fi.ppm).toFixed(2);
        hoverInfo.textContent = 'X: ' + wx + ' m, Y: ' + wy + ' m';
    });

    canvas.addEventListener('mouseleave', function () {
        hoverInfo.textContent = 'Hover over the field for coordinates';
    });

    // ========================================
    // Input Event Handlers
    // ========================================

    // Live preview on input change
    [inputRows, inputCols, inputRowSpacing, inputColSpacing].forEach(function (el) {
        el.addEventListener('input', function () {
            updateAutoTerrain();
            drawField(getUIConfig());
        });
    });

    inputTerrainScale.addEventListener('input', function () {
        updateTerrainHint();
        drawField(getUIConfig());
    });

    inputTerrainZ.addEventListener('input', function () {
        drawField(getUIConfig());
    });

    inputAutoTerrain.addEventListener('change', function () {
        inputTerrainScale.disabled = this.checked;
        if (this.checked) {
            updateAutoTerrain();
        }
        drawField(getUIConfig());
    });

    function updateAutoTerrain() {
        if (!inputAutoTerrain.checked) return;
        const cols = parseInt(inputCols.value) || DEFAULTS.cols;
        const rows = parseInt(inputRows.value) || DEFAULTS.rows;
        // Convert UI spacing to meters for terrain calculation
        const csUI = parseFloat(inputColSpacing.value) || DEFAULTS.colSpacing;
        const rsUI = parseFloat(inputRowSpacing.value) || DEFAULTS.rowSpacing;
        const cs = uiValueToMeters(csUI);
        const rs = uiValueToMeters(rsUI);
        const fieldW = (cols - 1) * cs + 3;
        const fieldH = (rows - 1) * rs + 3;
        const needed = Math.max(fieldW, fieldH);
        const scale = Math.max(1, Math.ceil(needed / 2));
        inputTerrainScale.value = scale;
        updateTerrainHint();
    }

    // Mix sliders
    [mixSmall, mixMedium, mixTall].forEach(function (slider) {
        slider.addEventListener('input', function () {
            mixSmallPct.textContent = mixSmall.value + '%';
            mixMediumPct.textContent = mixMedium.value + '%';
            mixTallPct.textContent = mixTall.value + '%';
            drawField(getUIConfig());
        });
    });

    // Preset buttons (data-rs/data-cs are in meters)
    document.querySelectorAll('.preset-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            document.querySelectorAll('.preset-btn').forEach(function (b) { b.classList.remove('active'); });
            btn.classList.add('active');

            inputRows.value = btn.dataset.rows;
            inputCols.value = btn.dataset.cols;
            // Convert preset meters to current UI unit
            var rsM = parseFloat(btn.dataset.rs);
            var csM = parseFloat(btn.dataset.cs);
            inputRowSpacing.value = metersToUIValue(rsM).toFixed(unitMode === 'ft' ? 1 : 2);
            inputColSpacing.value = metersToUIValue(csM).toFixed(unitMode === 'ft' ? 1 : 2);
            updateAutoTerrain();
            drawField(getUIConfig());
        });
    });

    // ========================================
    // Action Buttons
    // ========================================

    previewBtn.addEventListener('click', function () {
        previewConfig = getUIConfig();
        drawField(previewConfig);
        setStatus('', 'Preview updated. Click "Apply to Gazebo" to save changes.');
    });

    applyBtn.addEventListener('click', function () {
        const config = getUIConfig();
        setStatus('working', 'Applying to Gazebo \u2014 removing old plants, spawning new ones...');
        applyBtn.disabled = true;
        backendSend({
            type: 'update_sim_config',
            config: config,
        });
    });

    resetBtn.addEventListener('click', function () {
        inputRows.value = DEFAULTS.rows;
        inputCols.value = DEFAULTS.cols;
        // Defaults are in meters — convert to current UI unit
        inputRowSpacing.value = metersToUIValue(DEFAULTS.rowSpacing).toFixed(unitMode === 'ft' ? 1 : 2);
        inputColSpacing.value = metersToUIValue(DEFAULTS.colSpacing).toFixed(unitMode === 'ft' ? 1 : 2);
        inputTerrainScale.value = DEFAULTS.terrainScale;
        inputTerrainZ.value = DEFAULTS.terrainZ;
        inputAutoTerrain.checked = DEFAULTS.autoTerrain;
        inputTerrainScale.disabled = true;
        mixSmall.value = 33; mixMedium.value = 34; mixTall.value = 33;
        mixSmallPct.textContent = '33%';
        mixMediumPct.textContent = '34%';
        mixTallPct.textContent = '33%';

        document.querySelectorAll('.preset-btn').forEach(function (b) { b.classList.remove('active'); });
        document.querySelector('.preset-btn[data-rows="5"][data-cols="7"]').classList.add('active');

        updateSpacingLabels();
        updateAutoTerrain();
        drawField(getUIConfig());
        setStatus('', 'Reset to defaults. Click Apply to save.');
    });

    // ========================================
    // Status
    // ========================================

    function setStatus(level, message) {
        statusEl.className = 'editor-status' + (level ? ' ' + level : '');
        statusText.textContent = message;
        if (level === 'working') {
            statusIcon.textContent = '⏳';
        } else if (level === 'success') {
            statusIcon.textContent = '✓';
        } else if (level === 'error') {
            statusIcon.textContent = '✗';
        } else {
            statusIcon.textContent = '';
        }
    }

    // ========================================
    // Resize handling
    // ========================================

    let resizeTimer;
    window.addEventListener('resize', function () {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(function () {
            drawField(previewConfig || currentConfig || getUIConfig());
        }, 100);
    });

    // ========================================
    // Initialization
    // ========================================

    inputTerrainScale.disabled = inputAutoTerrain.checked;
    // Set initial spacing values in the default unit (ft)
    inputRowSpacing.value = metersToUIValue(DEFAULTS.rowSpacing).toFixed(unitMode === 'ft' ? 1 : 2);
    inputColSpacing.value = metersToUIValue(DEFAULTS.colSpacing).toFixed(unitMode === 'ft' ? 1 : 2);
    updateSpacingLabels();
    updateAutoTerrain();
    updateTerrainHint();

    // Draw initial field with defaults
    drawField(getUIConfig());

    // Connect to backend
    connectBackend();

    // Connect to rosbridge for live odometry
    connectRos();

})();
