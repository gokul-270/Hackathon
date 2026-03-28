'use strict';

// ============================================================
//  URDF Visual Editor — Application Logic
//  Pure vanilla ES6, no frameworks
// ============================================================

(function () {

    // ========== STATE ==========
    let urdfDoc = null;                     // parsed XML Document
    let currentFilename = 'robot.urdf';     // active filename
    let selectedElement = null;             // {type:'link'|'joint', name:string, xmlEl:Element}
    let selectedElements = [];              // multi-select array: [{type, name, xmlEl}]
    let undoStack = [];                     // [{xml:string, description:string}]
    let redoStack = [];                     // [{xml:string, description:string}]
    const MAX_UNDO = 50;
    let isDirty = false;

    // Clipboard for copy/paste
    let clipboard = [];                     // [{type, xmlString}] — serialized XML of copied elements

    // SVG viewport state
    let zoom = 1.0;
    let panX = 0;
    let panY = 0;
    let isPanning = false;
    let panStartX = 0;
    let panStartY = 0;
    let panStartPanX = 0;
    let panStartPanY = 0;

    // Layout cache
    let layoutCache = null;   // {nodes: Map, width, height}
    let customPositions = new Map();  // persistent node positions (key → {x, y})

    // Connection health polling
    let healthInterval = null;
    let isConnected = false;

    // Mesh list cache
    let meshListCache = [];

    // Interactive node editor state
    let isDraggingNode = false;
    let dragTarget = null;        // {el:SVGElement, type, name, startX, startY, offsetX, offsetY}
    let isDrawingConnection = false;
    let connectionStart = null;   // {type, name, port:'top'|'bottom'}
    let tempConnectionLine = null;
    let autoSync = false;         // real-time Gazebo sync toggle
    let activePreviewTab = 'node-editor';  // 'node-editor' | 'viewer-3d'
    let contextMenuTarget = null; // {type, name, xmlEl}
    let lastClickedTreeIndex = -1; // for Shift+click range selection in tree

    // ========== DOM REFERENCES ==========
    const $ = (id) => document.getElementById(id);

    const dom = {
        toolbar:            $('toolbar'),
        toolbarLeft:        $('toolbar-left'),
        toolbarCenter:      $('toolbar-center'),
        toolbarRight:       $('toolbar-right'),
        treePanel:          $('tree-panel'),
        treeSearch:         $('tree-search'),
        treeContainer:      $('tree-container'),
        previewPanel:       $('preview-panel'),
        svgContainer:       $('svg-container'),
        previewSvg:         $('preview-svg'),
        previewZoomLabel:   $('preview-zoom-label'),
        propertiesPanel:    $('properties-panel'),
        propertiesContent:  $('properties-content'),
        propertiesEmpty:    $('properties-empty'),
        propertiesActions:  $('properties-actions'),
        selectedTypeBadge:  $('selected-type-badge'),
        statusBar:          $('status-bar'),
        statusBarLeft:      $('status-bar-left'),
        statusBarRight:     $('status-bar-right'),
        statusSavedTime:    $('status-saved-time'),
        statusLinksCount:   $('status-links-count'),
        statusJointsCount:  $('status-joints-count'),
        statusConnectionDot:$('status-connection-dot'),
        btnLoad:            $('btn-load'),
        btnSave:            $('btn-save'),
        btnExport:          $('btn-export'),
        btnAddLink:         $('btn-add-link'),
        btnAddJoint:        $('btn-add-joint'),
        btnUndo:            $('btn-undo'),
        btnRedo:            $('btn-redo'),
        btnFit:             $('btn-fit'),
        btnZoomIn:          $('btn-zoom-in'),
        btnZoomOut:         $('btn-zoom-out'),
        btnApplyProps:      $('btn-apply-props'),
        btnDeleteSelected:  $('btn-delete-selected'),
        // Modals
        addLinkModal:       $('add-link-modal'),
        addJointModal:      $('add-joint-modal'),
        deleteModal:        $('delete-modal'),
        saveModal:          $('save-modal'),
        loadModal:          $('load-modal'),
        // Add link inputs
        addLinkName:        $('add-link-name'),
        addLinkParent:      $('add-link-parent'),
        addLinkMass:        $('add-link-mass'),
        addLinkMeshFile:    $('add-link-mesh-file'),
        addLinkGeomLength:  $('add-link-geometry-length'),
        addLinkGeomWidth:   $('add-link-geometry-width'),
        addLinkGeomHeight:  $('add-link-geometry-height'),
        addLinkGeomRadius:  $('add-link-geometry-radius'),
        // Add joint inputs
        addJointName:       $('add-joint-name'),
        addJointType:       $('add-joint-type'),
        addJointParent:     $('add-joint-parent'),
        addJointChild:      $('add-joint-child'),
        addJointOriginX:    $('add-joint-origin-x'),
        addJointOriginY:    $('add-joint-origin-y'),
        addJointOriginZ:    $('add-joint-origin-z'),
        addJointOriginR:    $('add-joint-origin-r'),
        addJointOriginP:    $('add-joint-origin-p'),
        addJointOriginYaw:  $('add-joint-origin-yaw'),
        addJointAxisX:      $('add-joint-axis-x'),
        addJointAxisY:      $('add-joint-axis-y'),
        addJointAxisZ:      $('add-joint-axis-z'),
        addJointLimitLower: $('add-joint-limit-lower'),
        addJointLimitUpper: $('add-joint-limit-upper'),
        addJointLimitEffort:$('add-joint-limit-effort'),
        addJointLimitVelocity:$('add-joint-limit-velocity'),
        // Save/Load
        saveFilename:       $('save-filename'),
        loadFileList:       $('load-file-list'),
        // Spawn / Validate / Import
        btnSpawn:           $('btn-spawn'),
        btnValidate:        $('btn-validate'),
        btnImport:          $('btn-import'),
        btnImportPkg:       $('btn-import-pkg'),
        importModal:        $('import-modal'),
        importPkgModal:     $('import-pkg-modal'),
        validateModal:      $('validate-modal'),
        importMethod:       $('import-method'),
        importFileInput:    $('import-file-input'),
        importPasteInput:   $('import-paste-input'),
        importPrefix:       $('import-prefix'),
        importAttachLink:   $('import-attach-link'),
        importOffsetX:      $('import-offset-x'),
        importOffsetY:      $('import-offset-y'),
        importOffsetZ:      $('import-offset-z'),
        validateResults:    $('validate-results'),
        addLinkMeshCustom:  $('add-link-mesh-custom'),
        // Interactive Editor additions
        contextMenu:        $('context-menu'),
        chkAutoSync:        $('chk-auto-sync'),
        viewer3dContainer:  $('viewer3d-container'),
        viewer3dCanvas:     $('viewer3d-canvas'),
        statusGazeboDot:    $('status-gazebo-dot'),
        statusGazeboText:   $('status-gazebo-text'),
        reparentModal:      $('reparent-modal'),
        reparentSourceName: $('reparent-source-name'),
        reparentTarget:     $('reparent-target'),
        reparentOx:         $('reparent-ox'),
        reparentOy:         $('reparent-oy'),
        reparentOz:         $('reparent-oz'),
        btnUndo3d:          $('btn-undo-3d'),
        btnRedo3d:          $('btn-redo-3d'),
        // Environment Objects
        btnEnvObjects:      $('btn-env-objects'),
        envObjectsModal:    $('env-objects-modal'),
    };

    // ========== UTILITY: XML HELPERS ==========

    function xmlSerializer() {
        return new XMLSerializer();
    }

    function serializeURDF() {
        if (!urdfDoc) return '';
        return xmlSerializer().serializeToString(urdfDoc);
    }

    function parseXMLString(xmlStr) {
        const parser = new DOMParser();
        const doc = parser.parseFromString(xmlStr, 'application/xml');
        const errNode = doc.querySelector('parsererror');
        if (errNode) {
            throw new Error('XML parse error: ' + errNode.textContent.substring(0, 200));
        }
        return doc;
    }

    function getAttr(el, name, fallback) {
        if (!el) return fallback !== undefined ? fallback : '';
        const v = el.getAttribute(name);
        return v !== null ? v : (fallback !== undefined ? fallback : '');
    }

    function setAttr(el, name, value) {
        if (el) el.setAttribute(name, value);
    }

    function floatAttr(el, name, fallback) {
        const v = getAttr(el, name, null);
        if (v === null) return fallback !== undefined ? fallback : 0;
        const f = parseFloat(v);
        return isNaN(f) ? (fallback !== undefined ? fallback : 0) : f;
    }

    function splitXYZ(str) {
        if (!str) return [0, 0, 0];
        const parts = str.trim().split(/\s+/).map(Number);
        return [parts[0] || 0, parts[1] || 0, parts[2] || 0];
    }

    // ========== URDF DATA EXTRACTION ==========

    function getAllLinks() {
        if (!urdfDoc) return [];
        return Array.from(urdfDoc.querySelectorAll('robot > link'));
    }

    function getAllJoints() {
        if (!urdfDoc) return [];
        return Array.from(urdfDoc.querySelectorAll('robot > joint'));
    }

    function getLinkByName(name) {
        if (!urdfDoc) return null;
        return Array.from(urdfDoc.querySelectorAll('robot > link')).find(
            l => l.getAttribute('name') === name
        ) || null;
    }

    function getJointByName(name) {
        if (!urdfDoc) return null;
        return Array.from(urdfDoc.querySelectorAll('robot > joint')).find(
            j => j.getAttribute('name') === name
        ) || null;
    }

    function getLinkNames() {
        return getAllLinks().map(l => l.getAttribute('name'));
    }

    function getJointNames() {
        return getAllJoints().map(j => j.getAttribute('name'));
    }

    /**
     * Find the joint element where the given link is the child.
     * Returns the XML Element of the parent joint, or null if root link.
     */
    function findParentJoint(linkName) {
        if (!urdfDoc || !linkName) return null;
        const joints = getAllJoints();
        for (const j of joints) {
            const childEl = j.querySelector('child');
            if (childEl && childEl.getAttribute('link') === linkName) {
                return j;
            }
        }
        return null;
    }

    function getRobotName() {
        if (!urdfDoc) return '';
        const robot = urdfDoc.querySelector('robot');
        return robot ? getAttr(robot, 'name', 'robot') : 'robot';
    }

    /**
     * Extract structured link data from XML element.
     */
    function extractLinkData(linkEl) {
        const name = getAttr(linkEl, 'name');
        const data = { name, visual: null, collision: null, inertial: null };

        // Visual
        const vis = linkEl.querySelector('visual');
        if (vis) {
            const geom = vis.querySelector('geometry');
            const origin = vis.querySelector('origin');
            const mat = vis.querySelector('material');
            data.visual = {
                geometry: extractGeometry(geom),
                origin: extractOrigin(origin),
                material: extractMaterial(mat),
            };
        }

        // Collision
        const col = linkEl.querySelector('collision');
        if (col) {
            const geom = col.querySelector('geometry');
            const origin = col.querySelector('origin');
            data.collision = {
                geometry: extractGeometry(geom),
                origin: extractOrigin(origin),
            };
        }

        // Inertial
        const inertial = linkEl.querySelector('inertial');
        if (inertial) {
            const massEl = inertial.querySelector('mass');
            const inertiaEl = inertial.querySelector('inertia');
            data.inertial = {
                mass: massEl ? floatAttr(massEl, 'value', 0) : 0,
                inertia: inertiaEl ? {
                    ixx: floatAttr(inertiaEl, 'ixx', 0),
                    ixy: floatAttr(inertiaEl, 'ixy', 0),
                    ixz: floatAttr(inertiaEl, 'ixz', 0),
                    iyy: floatAttr(inertiaEl, 'iyy', 0),
                    iyz: floatAttr(inertiaEl, 'iyz', 0),
                    izz: floatAttr(inertiaEl, 'izz', 0),
                } : null,
            };
        }
        return data;
    }

    function extractGeometry(geomEl) {
        if (!geomEl) return { type: 'box', dimensions: { x: 0.1, y: 0.1, z: 0.1 } };
        const box = geomEl.querySelector('box');
        if (box) {
            const size = splitXYZ(getAttr(box, 'size', '0.1 0.1 0.1'));
            return { type: 'box', dimensions: { x: size[0], y: size[1], z: size[2] } };
        }
        const cyl = geomEl.querySelector('cylinder');
        if (cyl) {
            return {
                type: 'cylinder',
                dimensions: {
                    radius: floatAttr(cyl, 'radius', 0.05),
                    length: floatAttr(cyl, 'length', 0.1),
                },
            };
        }
        const sph = geomEl.querySelector('sphere');
        if (sph) {
            return { type: 'sphere', dimensions: { radius: floatAttr(sph, 'radius', 0.05) } };
        }
        const mesh = geomEl.querySelector('mesh');
        if (mesh) {
            const filename = getAttr(mesh, 'filename', '');
            const scaleStr = getAttr(mesh, 'scale', '1 1 1');
            const scale = splitXYZ(scaleStr);
            return {
                type: 'mesh',
                dimensions: { filename, scaleX: scale[0], scaleY: scale[1], scaleZ: scale[2] },
            };
        }
        return { type: 'box', dimensions: { x: 0.1, y: 0.1, z: 0.1 } };
    }

    function extractOrigin(originEl) {
        if (!originEl) return { xyz: [0, 0, 0], rpy: [0, 0, 0] };
        return {
            xyz: splitXYZ(getAttr(originEl, 'xyz', '0 0 0')),
            rpy: splitXYZ(getAttr(originEl, 'rpy', '0 0 0')),
        };
    }

    function extractMaterial(matEl) {
        if (!matEl) return { name: '', color: [0.7, 0.7, 0.7, 1.0] };
        const name = getAttr(matEl, 'name', '');
        const colorEl = matEl.querySelector('color');
        let color = [0.7, 0.7, 0.7, 1.0];
        if (colorEl) {
            const rgba = getAttr(colorEl, 'rgba', '0.7 0.7 0.7 1.0');
            const parts = rgba.trim().split(/\s+/).map(Number);
            color = [parts[0] || 0, parts[1] || 0, parts[2] || 0, parts[3] !== undefined ? parts[3] : 1];
        }
        return { name, color };
    }

    /**
     * Extract structured joint data from XML element.
     */
    function extractJointData(jointEl) {
        const name = getAttr(jointEl, 'name');
        const type = getAttr(jointEl, 'type', 'fixed');
        const parentEl = jointEl.querySelector('parent');
        const childEl = jointEl.querySelector('child');
        const originEl = jointEl.querySelector('origin');
        const axisEl = jointEl.querySelector('axis');
        const limitEl = jointEl.querySelector('limit');

        return {
            name,
            type,
            parent: parentEl ? getAttr(parentEl, 'link', '') : '',
            child: childEl ? getAttr(childEl, 'link', '') : '',
            origin: extractOrigin(originEl),
            axis: axisEl ? splitXYZ(getAttr(axisEl, 'xyz', '0 0 1')) : [0, 0, 1],
            limit: limitEl ? {
                lower: floatAttr(limitEl, 'lower', 0),
                upper: floatAttr(limitEl, 'upper', 0),
                effort: floatAttr(limitEl, 'effort', 0),
                velocity: floatAttr(limitEl, 'velocity', 0),
            } : { lower: 0, upper: 0, effort: 0, velocity: 0 },
        };
    }

    // ========== URDF PARSING ==========

    function parseURDF(xmlString) {
        urdfDoc = parseXMLString(xmlString);
        selectedElement = null;
        selectedElements = [];
        layoutCache = null;
        updateStatusCounts();
    }

    // ========== UNDO SYSTEM ==========

    function pushUndo(description, source) {
        const xml = serializeURDF();
        undoStack.push({ xml, description, source: source || 'node-editor' });
        if (undoStack.length > MAX_UNDO) {
            undoStack.shift();
        }
        // Any new change invalidates the redo history
        redoStack.length = 0;
        updateUndoRedoButtons();
        markDirty();
    }

    function performUndo() {
        if (undoStack.length === 0) {
            showToast('Nothing to undo', 'warning');
            return;
        }
        // Save current state to redo stack before restoring
        const currentXml = serializeURDF();
        const entry = undoStack.pop();
        redoStack.push({ xml: currentXml, description: entry.description, source: entry.source });
        try {
            parseURDF(entry.xml);
            selectedElement = null;
            selectedElements = [];
            renderTree();
            renderSVG();
            clearProperties();
            fireURDFChanged();
            showToast('Undo: ' + entry.description, 'info');
        } catch (e) {
            showToast('Undo failed: ' + e.message, 'error');
        }
        updateUndoRedoButtons();
    }

    function performRedo() {
        if (redoStack.length === 0) {
            showToast('Nothing to redo', 'warning');
            return;
        }
        // Save current state to undo stack before redoing
        const currentXml = serializeURDF();
        const entry = redoStack.pop();
        undoStack.push({ xml: currentXml, description: entry.description, source: entry.source });
        try {
            parseURDF(entry.xml);
            selectedElement = null;
            selectedElements = [];
            renderTree();
            renderSVG();
            clearProperties();
            fireURDFChanged();
            showToast('Redo: ' + entry.description, 'info');
        } catch (e) {
            showToast('Redo failed: ' + e.message, 'error');
        }
        updateUndoRedoButtons();
    }

    function updateUndoRedoButtons() {
        if (dom.btnUndo) {
            dom.btnUndo.disabled = undoStack.length === 0;
            dom.btnUndo.title = undoStack.length > 0
                ? 'Undo: ' + undoStack[undoStack.length - 1].description
                : 'Nothing to undo';
        }
        if (dom.btnRedo) {
            dom.btnRedo.disabled = redoStack.length === 0;
            dom.btnRedo.title = redoStack.length > 0
                ? 'Redo: ' + redoStack[redoStack.length - 1].description
                : 'Nothing to redo';
        }
        // Mirror for 3D toolbar buttons
        if (dom.btnUndo3d) {
            dom.btnUndo3d.disabled = undoStack.length === 0;
            dom.btnUndo3d.title = dom.btnUndo ? dom.btnUndo.title : '';
        }
        if (dom.btnRedo3d) {
            dom.btnRedo3d.disabled = redoStack.length === 0;
            dom.btnRedo3d.title = dom.btnRedo ? dom.btnRedo.title : '';
        }
    }

    function markDirty() {
        isDirty = true;
        updateFileStatus();
    }

    function markClean() {
        isDirty = false;
        updateFileStatus();
    }

    function updateFileStatus() {
        const el = $('file-status');
        if (el) {
            el.innerHTML = '<span class="filename">' + escapeHtml(currentFilename) + '</span>'
                + (isDirty ? ' <span style="color:var(--warning)">(unsaved)</span>' : '');
        }
    }

    // ========== TREE VIEW ==========

    /**
     * Get all root link names (links not referenced as child by any joint).
     */
    function getRootLinkNames() {
        const links = getAllLinks();
        const joints = getAllJoints();
        if (links.length === 0) return [];

        const childLinkNames = new Set();
        joints.forEach(j => {
            const cEl = j.querySelector('child');
            if (cEl) childLinkNames.add(cEl.getAttribute('link'));
        });

        const linkNames = links.map(l => l.getAttribute('name'));
        return linkNames.filter(n => !childLinkNames.has(n));
    }

    /**
     * Get orphan root links (all roots except the primary/first one).
     * Returns { primary: string|null, orphans: string[] }
     */
    function getOrphanRootLinks() {
        const roots = getRootLinkNames();
        if (roots.length <= 1) return { primary: roots[0] || null, orphans: [] };
        return { primary: roots[0], orphans: roots.slice(1) };
    }

    /**
     * Build a tree structure from a given root link name.
     */
    function buildTreeFrom(rootName, childJointsMap, depth) {
        const linkEl = getLinkByName(rootName);
        const node = {
            type: 'link',
            name: rootName,
            xmlEl: linkEl,
            depth,
            children: [],
            isOrphan: false, // will be set later
        };

        const childJoints = childJointsMap.get(rootName) || [];
        childJoints.forEach(({ jointEl, data }) => {
            const jointNode = {
                type: 'joint',
                name: data.name,
                jointType: data.type,
                xmlEl: jointEl,
                depth: depth + 1,
                children: [],
            };
            if (data.child && getLinkByName(data.child)) {
                jointNode.children.push(buildTreeFrom(data.child, childJointsMap, depth + 2));
            }
            node.children.push(jointNode);
        });

        return node;
    }

    /**
     * Build tree structures for ALL root links.
     * Returns array of trees. First is primary, rest are orphans.
     */
    function buildAllTrees() {
        const links = getAllLinks();
        const joints = getAllJoints();
        if (links.length === 0) return [];

        const childJointsMap = new Map();
        joints.forEach(j => {
            const jData = extractJointData(j);
            if (!childJointsMap.has(jData.parent)) {
                childJointsMap.set(jData.parent, []);
            }
            childJointsMap.get(jData.parent).push({ jointEl: j, data: jData });
        });

        const rootNames = getRootLinkNames();
        if (rootNames.length === 0 && links.length > 0) {
            // Fallback: use first link
            rootNames.push(links[0].getAttribute('name'));
        }

        const trees = rootNames.map((rn, idx) => {
            const tree = buildTreeFrom(rn, childJointsMap, 0);
            if (idx > 0) tree.isOrphan = true; // mark orphan trees
            return tree;
        });
        return trees;
    }

    /**
     * Build a tree structure: find root link, then recursively attach joints and child links.
     * (Legacy wrapper — returns only the primary tree.)
     */
    function buildTree() {
        const trees = buildAllTrees();
        return trees.length > 0 ? trees[0] : null;
    }

    function renderTree() {
        if (!dom.treeContainer) return;
        const trees = buildAllTrees();
        dom.treeContainer.innerHTML = '';
        if (trees.length === 0) {
            dom.treeContainer.innerHTML = '<div style="padding:16px;color:var(--text-muted);text-align:center;">No URDF loaded</div>';
            return;
        }
        // Primary tree
        const primaryDom = createTreeNodeDOM(trees[0]);
        dom.treeContainer.appendChild(primaryDom);
        // Orphan trees (roots 1..N)
        for (let i = 1; i < trees.length; i++) {
            const orphanHeader = document.createElement('div');
            orphanHeader.className = 'orphan-tree-header';
            orphanHeader.innerHTML = '\u26A0 Orphan: <strong>' + escapeHtml(trees[i].name) + '</strong>'
                + ' <button class="orphan-attach-btn" data-link="' + escapeHtml(trees[i].name) + '">Attach</button>';
            dom.treeContainer.appendChild(orphanHeader);
            const orphanDom = createTreeNodeDOM(trees[i]);
            orphanDom.classList.add('orphan-tree');
            dom.treeContainer.appendChild(orphanDom);
        }
        // Wire up orphan attach buttons
        dom.treeContainer.querySelectorAll('.orphan-attach-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                openAttachOrphanModal(btn.dataset.link);
            });
        });
        applyTreeFilter();
        // Check and show/hide orphan warning
        updateOrphanWarning();
    }

    function createTreeNodeDOM(node) {
        const wrapper = document.createElement('div');
        wrapper.classList.add('tree-node');
        wrapper.dataset.name = node.name;
        wrapper.dataset.type = node.type;

        const indent = node.depth * 16;
        const row = document.createElement('div');
        row.classList.add('tree-node-row');
        row.style.paddingLeft = (8 + indent) + 'px';

        // Is selected? Check both single and multi-select
        if (isMultiSelected(node.type, node.name)) {
            row.classList.add(selectedElements.length > 1 ? 'multi-selected' : 'selected');
        }

        // Toggle
        const toggle = document.createElement('span');
        toggle.classList.add('tree-toggle');
        if (node.children.length > 0) {
            toggle.textContent = '\u25B6'; // right triangle
            toggle.classList.add('expanded');
        } else {
            toggle.classList.add('empty');
        }

        // Icon
        const icon = document.createElement('span');
        icon.classList.add('tree-icon');
        if (node.type === 'link') {
            icon.classList.add('link-icon');
            icon.textContent = 'L';
        } else {
            icon.classList.add('joint-icon');
            const jt = node.jointType || 'fixed';
            if (jt === 'fixed') {
                icon.classList.remove('joint-icon');
                icon.classList.add('joint-fixed-icon');
                icon.textContent = 'F';
            } else if (jt === 'revolute') {
                icon.classList.remove('joint-icon');
                icon.classList.add('joint-revolute-icon');
                icon.textContent = 'R';
            } else if (jt === 'prismatic') {
                icon.classList.remove('joint-icon');
                icon.classList.add('joint-prismatic-icon');
                icon.textContent = 'P';
            } else if (jt === 'continuous') {
                icon.classList.remove('joint-icon');
                icon.classList.add('joint-continuous-icon');
                icon.textContent = 'C';
            } else {
                icon.textContent = 'J';
            }
        }

        // Label
        const label = document.createElement('span');
        label.classList.add('tree-node-label');
        label.textContent = node.name;
        label.title = node.name;

        // Type badge
        const typeBadge = document.createElement('span');
        typeBadge.classList.add('tree-node-type');
        if (node.type === 'joint') {
            typeBadge.textContent = node.jointType || 'joint';
        } else {
            typeBadge.textContent = 'link';
        }

        row.appendChild(toggle);
        row.appendChild(icon);
        row.appendChild(label);
        row.appendChild(typeBadge);
        wrapper.appendChild(row);

        // Children container
        const childrenContainer = document.createElement('div');
        childrenContainer.classList.add('tree-children', 'expanded');

        node.children.forEach(child => {
            childrenContainer.appendChild(createTreeNodeDOM(child));
        });
        wrapper.appendChild(childrenContainer);

        // --- Events ---
        toggle.addEventListener('click', (e) => {
            e.stopPropagation();
            const isExpanded = toggle.classList.contains('expanded');
            if (isExpanded) {
                toggle.classList.remove('expanded');
                childrenContainer.classList.remove('expanded');
            } else {
                toggle.classList.add('expanded');
                childrenContainer.classList.add('expanded');
            }
        });

        row.addEventListener('click', (e) => {
            e.stopPropagation();
            selectElement(node.type, node.name, node.xmlEl, {
                ctrlKey: e.ctrlKey || e.metaKey,
                shiftKey: e.shiftKey
            });
        });

        // Right-click context menu on tree nodes
        row.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            e.stopPropagation();
            // If not already in multi-select, select it alone first
            if (!isMultiSelected(node.type, node.name)) {
                selectElement(node.type, node.name, node.xmlEl);
            }
            showContextMenu(e.clientX, e.clientY, node.type, node.name);
        });

        return wrapper;
    }

    function applyTreeFilter() {
        if (!dom.treeSearch || !dom.treeContainer) return;
        const query = dom.treeSearch.value.trim().toLowerCase();
        const allRows = dom.treeContainer.querySelectorAll('.tree-node');
        if (!query) {
            allRows.forEach(n => n.classList.remove('hidden'));
            return;
        }
        allRows.forEach(n => {
            const name = (n.dataset.name || '').toLowerCase();
            if (name.includes(query)) {
                n.classList.remove('hidden');
                // Also show all ancestors
                let parent = n.parentElement;
                while (parent && parent !== dom.treeContainer) {
                    parent.classList.remove('hidden');
                    if (parent.classList.contains('tree-children')) {
                        parent.classList.add('expanded');
                    }
                    parent = parent.parentElement;
                }
            } else {
                n.classList.add('hidden');
            }
        });
    }

    // ========== ELEMENT SELECTION ==========

    /**
     * Reveal a node in the tree panel: expand all ancestor containers,
     * highlight the row, and scroll it into view (like VS Code explorer).
     */
    function revealInTree(type, name) {
        if (!dom.treeContainer) return;

        // Find the target .tree-node
        let targetNode = null;
        const allNodes = dom.treeContainer.querySelectorAll('.tree-node');
        for (const n of allNodes) {
            if (n.dataset.name === name && n.dataset.type === type) {
                targetNode = n;
                break;
            }
        }
        if (!targetNode) return;

        // Expand all ancestor .tree-children containers so the node is visible
        let ancestor = targetNode.parentElement;
        while (ancestor && ancestor !== dom.treeContainer) {
            if (ancestor.classList.contains('tree-children')) {
                ancestor.classList.add('expanded');
                // Also flip the toggle arrow of the parent tree-node
                const parentNode = ancestor.parentElement;
                if (parentNode && parentNode.classList.contains('tree-node')) {
                    const toggle = parentNode.querySelector(':scope > .tree-node-row > .tree-toggle');
                    if (toggle) toggle.classList.add('expanded');
                }
            }
            // Un-hide if filtered
            if (ancestor.classList.contains('hidden')) {
                ancestor.classList.remove('hidden');
            }
            ancestor = ancestor.parentElement;
        }
        targetNode.classList.remove('hidden');

        // Highlight the row
        const row = targetNode.querySelector(':scope > .tree-node-row');
        if (row) {
            row.classList.add('selected');
            // Smooth-scroll into view within the tree panel
            row.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
    }

    /**
     * Select a single element (replaces any previous selection).
     * When ctrlKey=true, toggle that element in the multi-select set.
     */
    function selectElement(type, name, xmlEl, opts) {
        const ctrlKey = opts && opts.ctrlKey;
        const shiftKey = opts && opts.shiftKey;
        console.log('[urdf_editor] selectElement called:', type, name, '| ctrl:', !!ctrlKey, '| shift:', !!shiftKey);

        if (!xmlEl) {
            xmlEl = type === 'link' ? getLinkByName(name) : getJointByName(name);
        }
        if (!xmlEl) {
            console.warn('[urdf_editor] selectElement: could not find', type, name, 'in URDF (urdfDoc loaded:', !!urdfDoc, ')');
        }

        const item = { type, name, xmlEl };

        if (ctrlKey) {
            // Toggle in multi-select
            const idx = selectedElements.findIndex(e => e.type === type && e.name === name);
            if (idx >= 0) {
                selectedElements.splice(idx, 1);
            } else {
                selectedElements.push(item);
            }
            // Primary selectedElement = last in multi-select or null
            selectedElement = selectedElements.length > 0 ? selectedElements[selectedElements.length - 1] : null;
        } else if (shiftKey && selectedElement) {
            // Range selection in tree order
            const treeOrder = getTreeOrder();
            const anchorIdx = treeOrder.findIndex(e => e.type === selectedElement.type && e.name === selectedElement.name);
            const targetIdx = treeOrder.findIndex(e => e.type === type && e.name === name);
            if (anchorIdx >= 0 && targetIdx >= 0) {
                const start = Math.min(anchorIdx, targetIdx);
                const end = Math.max(anchorIdx, targetIdx);
                selectedElements = treeOrder.slice(start, end + 1).map(e => ({
                    type: e.type, name: e.name,
                    xmlEl: e.type === 'link' ? getLinkByName(e.name) : getJointByName(e.name)
                }));
                selectedElement = item;
            } else {
                selectedElements = [item];
                selectedElement = item;
            }
        } else {
            // Simple click — single select
            selectedElements = [item];
            selectedElement = item;
        }

        // Update tree highlights
        refreshTreeHighlights();

        // Reveal last-clicked in tree
        revealInTree(type, name);

        // Highlight in SVG
        highlightSVGSelection();

        // Show properties of the primary element
        if (selectedElement) {
            showProperties(selectedElement);
        } else {
            clearProperties();
        }

        // Update badge
        updateSelectionBadge();
    }

    /**
     * Get a flat ordered list of {type, name} matching tree traversal order.
     */
    function getTreeOrder() {
        const order = [];
        if (!urdfDoc) return order;
        function walkTree(nodes) {
            for (const n of nodes) {
                order.push({ type: n.type, name: n.name });
                if (n.children) walkTree(n.children);
            }
        }
        const trees = buildAllTrees();
        for (const t of trees) {
            walkTree([t]);
        }
        return order;
    }

    /**
     * Check whether an element is in the current multi-selection.
     */
    function isMultiSelected(type, name) {
        return selectedElements.some(e => e.type === type && e.name === name);
    }

    /**
     * Refresh tree row highlights based on selectedElements.
     */
    function refreshTreeHighlights() {
        if (!dom.treeContainer) return;
        dom.treeContainer.querySelectorAll('.tree-node-row.selected, .tree-node-row.multi-selected').forEach(r => {
            r.classList.remove('selected', 'multi-selected');
        });
        selectedElements.forEach(sel => {
            const wrapper = dom.treeContainer.querySelector(
                '.tree-node[data-type="' + sel.type + '"][data-name="' + sel.name + '"]'
            );
            if (wrapper) {
                const row = wrapper.querySelector('.tree-node-row');
                if (row) {
                    if (selectedElements.length > 1) {
                        row.classList.add('multi-selected');
                    } else {
                        row.classList.add('selected');
                    }
                }
            }
        });
    }

    /**
     * Update the selection type badge.
     */
    function updateSelectionBadge() {
        if (!dom.selectedTypeBadge) return;
        if (selectedElements.length > 1) {
            dom.selectedTypeBadge.textContent = selectedElements.length + ' SELECTED';
            dom.selectedTypeBadge.className = 'selected-type-badge multi-badge';
        } else if (selectedElement) {
            dom.selectedTypeBadge.textContent = selectedElement.type.toUpperCase();
            dom.selectedTypeBadge.className = 'selected-type-badge';
            dom.selectedTypeBadge.classList.add(selectedElement.type === 'link' ? 'link-badge' : 'joint-badge');
        } else {
            dom.selectedTypeBadge.textContent = 'NONE';
            dom.selectedTypeBadge.className = 'selected-type-badge';
        }
    }

    function clearSelection() {
        selectedElement = null;
        selectedElements = [];
        if (dom.treeContainer) {
            dom.treeContainer.querySelectorAll('.tree-node-row.selected, .tree-node-row.multi-selected').forEach(r => {
                r.classList.remove('selected', 'multi-selected');
            });
        }
        highlightSVGSelection();
        clearProperties();
        updateSelectionBadge();
    }

    /**
     * Select all links and joints (Ctrl+A).
     */
    function selectAll() {
        if (!urdfDoc) return;
        selectedElements = [];
        getAllLinks().forEach(l => {
            selectedElements.push({ type: 'link', name: l.getAttribute('name'), xmlEl: l });
        });
        getAllJoints().forEach(j => {
            selectedElements.push({ type: 'joint', name: j.getAttribute('name'), xmlEl: j });
        });
        selectedElement = selectedElements.length > 0 ? selectedElements[0] : null;
        refreshTreeHighlights();
        highlightSVGSelection();
        updateSelectionBadge();
        showToast(selectedElements.length + ' elements selected', 'info');
    }

    // ========== SVG PREVIEW ==========

    const LINK_W = 120;
    const LINK_H = 40;
    const JOINT_SIZE = 20;
    const H_SPACING = 140;
    const V_SPACING = 80;
    const SVG_NS = 'http://www.w3.org/2000/svg';

    /**
     * Compute hierarchical top-down layout.
     * Returns a Map<name, {x, y, type, name, jointType?, width, height}>
     * and overall {width, height}.
     */
    function computeLayout() {
        const trees = buildAllTrees();
        if (trees.length === 0) return null;

        const positions = new Map();
        let maxX = 0;
        let maxY = 0;

        // First pass: compute subtree widths
        function subtreeWidth(node) {
            if (node.children.length === 0) {
                return node.type === 'link' ? LINK_W : JOINT_SIZE;
            }
            let total = 0;
            node.children.forEach((child, i) => {
                if (i > 0) total += 20; // gap between siblings
                total += subtreeWidth(child);
            });
            const ownW = node.type === 'link' ? LINK_W : JOINT_SIZE;
            return Math.max(ownW, total);
        }

        // Second pass: assign positions
        function layoutNode(node, left, top, isOrphan) {
            const sw = subtreeWidth(node);
            const ownW = node.type === 'link' ? LINK_W : JOINT_SIZE;
            const ownH = node.type === 'link' ? LINK_H : JOINT_SIZE;

            const centerX = left + sw / 2;
            const x = centerX - ownW / 2;
            const y = top;

            positions.set(node.type + ':' + node.name, {
                x, y,
                cx: centerX,
                cy: top + ownH / 2,
                type: node.type,
                name: node.name,
                jointType: node.jointType || null,
                width: ownW,
                height: ownH,
                parentName: null,
                isOrphan: isOrphan || false,
            });

            if (x + ownW > maxX) maxX = x + ownW;
            if (y + ownH > maxY) maxY = y + ownH;

            // Layout children
            let childLeft = left;
            node.children.forEach((child, i) => {
                const childSW = subtreeWidth(child);
                if (i > 0) childLeft += 20;
                layoutNode(child, childLeft, top + ownH + V_SPACING, isOrphan);
                // Record parent
                const childKey = child.type + ':' + child.name;
                const childPos = positions.get(childKey);
                if (childPos) {
                    childPos.parentName = node.type + ':' + node.name;
                }
                childLeft += childSW;
            });
        }

        // Layout primary tree
        layoutNode(trees[0], 40, 40, false);

        // Layout orphan trees below the primary tree, separated
        let orphanStartY = maxY + 60;
        for (let i = 1; i < trees.length; i++) {
            // Add a visual separator label position
            const labelKey = '__orphan_label_' + i;
            positions.set(labelKey, {
                x: 40, y: orphanStartY,
                cx: 40, cy: orphanStartY,
                type: '__orphan_label',
                name: trees[i].name,
                width: 0, height: 0,
                parentName: null,
                isOrphan: true,
            });
            orphanStartY += 25;
            layoutNode(trees[i], 40, orphanStartY, true);
            orphanStartY = maxY + 60;
        }

        // Apply persistent custom positions from drag
        customPositions.forEach((customPos, key) => {
            const pos = positions.get(key);
            if (pos) {
                const dx = customPos.x - pos.x;
                const dy = customPos.y - pos.y;
                pos.x = customPos.x;
                pos.y = customPos.y;
                pos.cx = pos.cx + dx;
                pos.cy = pos.cy + dy;
            }
        });

        layoutCache = { nodes: positions, width: maxX + 80, height: maxY + 80 };
        return layoutCache;
    }

    function renderSVG() {
        if (!dom.previewSvg) return;
        dom.previewSvg.innerHTML = '';

        const layout = computeLayout();
        if (!layout) {
            const txt = document.createElementNS(SVG_NS, 'text');
            txt.setAttribute('x', '50%');
            txt.setAttribute('y', '50%');
            txt.setAttribute('text-anchor', 'middle');
            txt.setAttribute('fill', '#556677');
            txt.setAttribute('font-size', '14');
            txt.textContent = 'No URDF loaded. Click Load or Add Link to begin.';
            dom.previewSvg.appendChild(txt);
            return;
        }

        // Draw grid
        const gridGroup = document.createElementNS(SVG_NS, 'g');
        gridGroup.setAttribute('class', 'svg-grid');
        const gridSpacing = 50;
        for (let gx = 0; gx < layout.width + 200; gx += gridSpacing) {
            const line = document.createElementNS(SVG_NS, 'line');
            line.setAttribute('x1', gx);
            line.setAttribute('y1', 0);
            line.setAttribute('x2', gx);
            line.setAttribute('y2', layout.height + 200);
            line.setAttribute('class', gx % (gridSpacing * 4) === 0 ? 'svg-grid-line-major' : 'svg-grid-line');
            gridGroup.appendChild(line);
        }
        for (let gy = 0; gy < layout.height + 200; gy += gridSpacing) {
            const line = document.createElementNS(SVG_NS, 'line');
            line.setAttribute('x1', 0);
            line.setAttribute('y1', gy);
            line.setAttribute('x2', layout.width + 200);
            line.setAttribute('y2', gy);
            line.setAttribute('class', gy % (gridSpacing * 4) === 0 ? 'svg-grid-line-major' : 'svg-grid-line');
            gridGroup.appendChild(line);
        }
        dom.previewSvg.appendChild(gridGroup);

        // Draw connectors first (behind everything)
        const connGroup = document.createElementNS(SVG_NS, 'g');
        layout.nodes.forEach((pos, key) => {
            if (pos.parentName) {
                const parentPos = layout.nodes.get(pos.parentName);
                if (parentPos) {
                    drawConnector(connGroup, parentPos, pos);
                }
            }
        });
        dom.previewSvg.appendChild(connGroup);

        // Draw nodes
        const nodeGroup = document.createElementNS(SVG_NS, 'g');
        layout.nodes.forEach((pos, key) => {
            if (pos.type === '__orphan_label') {
                // Draw orphan separator label
                const txt = document.createElementNS(SVG_NS, 'text');
                txt.setAttribute('x', pos.x);
                txt.setAttribute('y', pos.y);
                txt.setAttribute('fill', '#ffb300');
                txt.setAttribute('font-size', '12');
                txt.setAttribute('font-weight', '700');
                txt.setAttribute('font-family', 'var(--font-ui)');
                txt.textContent = '\u26A0 Orphan: ' + pos.name;
                nodeGroup.appendChild(txt);
            } else if (pos.type === 'link') {
                drawLinkNode(nodeGroup, pos);
            } else if (pos.type === 'joint') {
                drawJointNode(nodeGroup, pos);
            }
        });
        dom.previewSvg.appendChild(nodeGroup);

        updateSVGViewBox();
        highlightSVGSelection();
    }

    function classifyLink(name) {
        const lower = name.toLowerCase();
        if (lower.includes('imu') || lower.includes('camera') ||
            lower.includes('navsat') || lower.includes('gps') ||
            lower.includes('lidar') || lower.includes('sensor')) {
            return 'sensor-link';
        }
        if (lower.startsWith('arm_') || lower.includes('_arm') ||
            lower.includes('gripper') || lower.includes('end_effector')) {
            return 'arm-link';
        }
        return 'vehicle-link';
    }

    function drawLinkNode(group, pos) {
        const g = document.createElementNS(SVG_NS, 'g');
        g.setAttribute('data-type', 'link');
        g.setAttribute('data-name', pos.name);
        g.style.cursor = 'pointer';

        const rect = document.createElementNS(SVG_NS, 'rect');
        rect.setAttribute('x', pos.x);
        rect.setAttribute('y', pos.y);
        rect.setAttribute('width', LINK_W);
        rect.setAttribute('height', LINK_H);
        rect.setAttribute('rx', '4');
        rect.setAttribute('ry', '4');
        rect.setAttribute('class', 'svg-link-rect ' + classifyLink(pos.name)
            + (pos.isOrphan ? ' orphan-link' : ''));
        g.appendChild(rect);

        const label = document.createElementNS(SVG_NS, 'text');
        label.setAttribute('x', pos.cx);
        label.setAttribute('y', pos.y + LINK_H / 2 + 4);
        label.setAttribute('class', 'svg-link-label');
        // Truncate long names
        const displayName = pos.name.length > 14 ? pos.name.substring(0, 12) + '..' : pos.name;
        label.textContent = displayName;
        g.appendChild(label);

        // --- Connection ports ---
        const portTop = document.createElementNS(SVG_NS, 'circle');
        portTop.setAttribute('cx', pos.cx);
        portTop.setAttribute('cy', pos.y);
        portTop.setAttribute('class', 'svg-port');
        portTop.setAttribute('data-port', 'top');
        portTop.setAttribute('data-owner', pos.name);
        portTop.setAttribute('data-owner-type', 'link');
        g.appendChild(portTop);

        portTop.addEventListener('mousedown', (e) => {
            startConnectionDraw(e, 'link', pos.name, 'top');
        });

        const portBot = document.createElementNS(SVG_NS, 'circle');
        portBot.setAttribute('cx', pos.cx);
        portBot.setAttribute('cy', pos.y + LINK_H);
        portBot.setAttribute('class', 'svg-port');
        portBot.setAttribute('data-port', 'bottom');
        portBot.setAttribute('data-owner', pos.name);
        portBot.setAttribute('data-owner-type', 'link');
        g.appendChild(portBot);

        portBot.addEventListener('mousedown', (e) => {
            startConnectionDraw(e, 'link', pos.name, 'bottom');
        });

        // Click to select
        g.addEventListener('click', (e) => {
            e.stopPropagation();
            selectElement('link', pos.name, null, {
                ctrlKey: e.ctrlKey || e.metaKey,
                shiftKey: e.shiftKey
            });
        });

        // Right-click context menu
        g.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            e.stopPropagation();
            if (!isMultiSelected('link', pos.name)) {
                selectElement('link', pos.name, null);
            }
            showContextMenu(e.clientX, e.clientY, 'link', pos.name);
        });

        // Double-click to edit name
        g.addEventListener('dblclick', (e) => {
            e.stopPropagation();
            startInlineRename('link', pos.name);
        });

        group.appendChild(g);
    }

    function drawJointNode(group, pos) {
        const g = document.createElementNS(SVG_NS, 'g');
        g.setAttribute('data-type', 'joint');
        g.setAttribute('data-name', pos.name);
        g.style.cursor = 'pointer';

        const jt = pos.jointType || 'fixed';
        const cx = pos.x + JOINT_SIZE / 2;
        const cy = pos.y + JOINT_SIZE / 2;
        const half = JOINT_SIZE / 2;

        let shape;
        if (jt === 'fixed') {
            // Small square
            shape = document.createElementNS(SVG_NS, 'rect');
            shape.setAttribute('x', pos.x);
            shape.setAttribute('y', pos.y);
            shape.setAttribute('width', JOINT_SIZE);
            shape.setAttribute('height', JOINT_SIZE);
            shape.setAttribute('class', 'svg-joint-shape joint-fixed');
        } else if (jt === 'revolute') {
            // Circle
            shape = document.createElementNS(SVG_NS, 'circle');
            shape.setAttribute('cx', cx);
            shape.setAttribute('cy', cy);
            shape.setAttribute('r', half);
            shape.setAttribute('class', 'svg-joint-shape joint-revolute');
        } else if (jt === 'prismatic') {
            // Diamond
            const points = [
                cx + ',' + (cy - half),
                (cx + half) + ',' + cy,
                cx + ',' + (cy + half),
                (cx - half) + ',' + cy,
            ].join(' ');
            shape = document.createElementNS(SVG_NS, 'polygon');
            shape.setAttribute('points', points);
            shape.setAttribute('class', 'svg-joint-shape joint-prismatic');
        } else if (jt === 'continuous') {
            // Circle with inner dot
            shape = document.createElementNS(SVG_NS, 'circle');
            shape.setAttribute('cx', cx);
            shape.setAttribute('cy', cy);
            shape.setAttribute('r', half);
            shape.setAttribute('class', 'svg-joint-shape joint-continuous');
            g.appendChild(shape);
            // Inner dot
            const dot = document.createElementNS(SVG_NS, 'circle');
            dot.setAttribute('cx', cx);
            dot.setAttribute('cy', cy);
            dot.setAttribute('r', half * 0.3);
            dot.setAttribute('fill', 'var(--joint-continuous)');
            dot.setAttribute('pointer-events', 'none');
            g.appendChild(dot);
            shape = null; // already appended
        } else {
            // Default square
            shape = document.createElementNS(SVG_NS, 'rect');
            shape.setAttribute('x', pos.x);
            shape.setAttribute('y', pos.y);
            shape.setAttribute('width', JOINT_SIZE);
            shape.setAttribute('height', JOINT_SIZE);
            shape.setAttribute('class', 'svg-joint-shape joint-fixed');
        }

        if (shape) {
            g.appendChild(shape);
        }

        // Label below joint
        const label = document.createElementNS(SVG_NS, 'text');
        label.setAttribute('x', cx);
        label.setAttribute('y', pos.y + JOINT_SIZE + 12);
        label.setAttribute('class', 'svg-joint-label');
        const shortName = pos.name.length > 16 ? pos.name.substring(0, 14) + '..' : pos.name;
        label.textContent = shortName;
        g.appendChild(label);

        // --- Connection ports ---
        const portTop = document.createElementNS(SVG_NS, 'circle');
        portTop.setAttribute('cx', cx);
        portTop.setAttribute('cy', pos.y);
        portTop.setAttribute('class', 'svg-port');
        portTop.setAttribute('data-port', 'top');
        portTop.setAttribute('data-owner', pos.name);
        portTop.setAttribute('data-owner-type', 'joint');
        g.appendChild(portTop);

        portTop.addEventListener('mousedown', (e) => {
            startConnectionDraw(e, 'joint', pos.name, 'top');
        });

        const portBot = document.createElementNS(SVG_NS, 'circle');
        portBot.setAttribute('cx', cx);
        portBot.setAttribute('cy', pos.y + JOINT_SIZE);
        portBot.setAttribute('class', 'svg-port');
        portBot.setAttribute('data-port', 'bottom');
        portBot.setAttribute('data-owner', pos.name);
        portBot.setAttribute('data-owner-type', 'joint');
        g.appendChild(portBot);

        portBot.addEventListener('mousedown', (e) => {
            startConnectionDraw(e, 'joint', pos.name, 'bottom');
        });

        // Click to select
        g.addEventListener('click', (e) => {
            e.stopPropagation();
            selectElement('joint', pos.name, null, {
                ctrlKey: e.ctrlKey || e.metaKey,
                shiftKey: e.shiftKey
            });
        });

        // Right-click context menu
        g.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            e.stopPropagation();
            if (!isMultiSelected('joint', pos.name)) {
                selectElement('joint', pos.name, null);
            }
            showContextMenu(e.clientX, e.clientY, 'joint', pos.name);
        });

        // Double-click to edit name
        g.addEventListener('dblclick', (e) => {
            e.stopPropagation();
            startInlineRename('joint', pos.name);
        });

        group.appendChild(g);
    }

    function drawConnector(group, parentPos, childPos) {
        const x1 = parentPos.cx;
        const y1 = parentPos.y + parentPos.height;
        const x2 = childPos.cx;
        const y2 = childPos.y;
        const midY = (y1 + y2) / 2;
        const d = 'M ' + x1 + ' ' + y1
            + ' C ' + x1 + ' ' + midY + ', ' + x2 + ' ' + midY + ', ' + x2 + ' ' + y2;

        const connGroup = document.createElementNS(SVG_NS, 'g');
        connGroup.setAttribute('class', 'svg-connector-group');
        connGroup.setAttribute('data-parent-key', parentPos.type + ':' + parentPos.name);
        connGroup.setAttribute('data-child-key', childPos.type + ':' + childPos.name);

        // Store joint name if the child is a joint
        if (childPos.type === 'joint') {
            connGroup.setAttribute('data-joint-name', childPos.name);
        } else if (parentPos.type === 'joint') {
            connGroup.setAttribute('data-joint-name', parentPos.name);
        }

        // Invisible fat hit area
        const hitPath = document.createElementNS(SVG_NS, 'path');
        hitPath.setAttribute('d', d);
        hitPath.setAttribute('class', 'svg-connector-hit');
        connGroup.appendChild(hitPath);

        // Visible connector line
        const path = document.createElementNS(SVG_NS, 'path');
        path.setAttribute('d', d);
        let cls = 'svg-connector-line';
        if (childPos.type === 'joint' && childPos.jointType === 'fixed') {
            cls += ' fixed-joint';
        }
        path.setAttribute('class', cls);
        connGroup.appendChild(path);

        // Click on connector → show detach tooltip
        connGroup.addEventListener('click', (e) => {
            e.stopPropagation();
            showConnectorTooltip(e.clientX, e.clientY, connGroup);
        });

        group.appendChild(connGroup);
    }

    function highlightSVGSelection() {
        if (!dom.previewSvg) return;
        // Clear previous highlights
        dom.previewSvg.querySelectorAll('.svg-link-rect.selected, .svg-joint-shape.selected, .svg-link-rect.multi-selected, .svg-joint-shape.multi-selected').forEach(el => {
            el.classList.remove('selected', 'multi-selected');
        });

        if (selectedElements.length === 0) return;

        const isMulti = selectedElements.length > 1;

        dom.previewSvg.querySelectorAll('g[data-type][data-name]').forEach(g => {
            const gType = g.dataset.type;
            const gName = g.dataset.name;
            if (selectedElements.some(s => s.type === gType && s.name === gName)) {
                const shapeEl = g.querySelector('.svg-link-rect, .svg-joint-shape');
                if (shapeEl) {
                    shapeEl.classList.add(isMulti ? 'multi-selected' : 'selected');
                }
            }
        });
    }

    function updateSVGViewBox() {
        if (!dom.previewSvg || !layoutCache) return;
        const w = layoutCache.width + 100;
        const h = layoutCache.height + 100;
        const vbX = -panX / zoom;
        const vbY = -panY / zoom;
        const vbW = (dom.svgContainer ? dom.svgContainer.clientWidth : 800) / zoom;
        const vbH = (dom.svgContainer ? dom.svgContainer.clientHeight : 600) / zoom;
        dom.previewSvg.setAttribute('viewBox', vbX + ' ' + vbY + ' ' + vbW + ' ' + vbH);

        if (dom.previewZoomLabel) {
            dom.previewZoomLabel.textContent = Math.round(zoom * 100) + '%';
        }
    }

    function fitView() {
        if (!layoutCache || !dom.svgContainer) return;
        const containerW = dom.svgContainer.clientWidth;
        const containerH = dom.svgContainer.clientHeight;
        const contentW = layoutCache.width + 40;
        const contentH = layoutCache.height + 40;

        if (contentW <= 0 || contentH <= 0) return;

        const scaleX = containerW / contentW;
        const scaleY = containerH / contentH;
        zoom = Math.min(scaleX, scaleY, 2.0);
        zoom = Math.max(zoom, 0.1);

        // Center content
        panX = (containerW - contentW * zoom) / 2;
        panY = (containerH - contentH * zoom) / 2;

        updateSVGViewBox();
    }

    function zoomIn() {
        zoom = Math.min(zoom * 1.2, 5.0);
        updateSVGViewBox();
    }

    function zoomOut() {
        zoom = Math.max(zoom / 1.2, 0.1);
        updateSVGViewBox();
    }

    // ========== SVG PAN / ZOOM INTERACTION ==========

    function initSVGInteraction() {
        if (!dom.svgContainer) return;

        dom.svgContainer.addEventListener('mousedown', (e) => {
            if (e.button !== 0) return;

            // Check if mousedown is inside a node group (for dragging)
            const nodeGroup = e.target.closest('g[data-type][data-name]');
            if (nodeGroup && !e.target.classList.contains('svg-port')) {
                startNodeDrag(e, nodeGroup.dataset.type, nodeGroup.dataset.name);
                return;
            }

            // Only pan if clicking on background (not on a node)
            if (e.target === dom.previewSvg || e.target.classList.contains('svg-grid-line') ||
                e.target.classList.contains('svg-grid-line-major') ||
                e.target.tagName === 'svg') {
                isPanning = true;
                panStartX = e.clientX;
                panStartY = e.clientY;
                panStartPanX = panX;
                panStartPanY = panY;
                dom.svgContainer.classList.add('grabbing');
                e.preventDefault();
            }
        });

        window.addEventListener('mousemove', (e) => {
            if (isDrawingConnection) {
                updateConnectionDraw(e);
                return;
            }
            if (isDraggingNode) {
                onNodeDrag(e);
                return;
            }
            if (!isPanning) return;
            const dx = e.clientX - panStartX;
            const dy = e.clientY - panStartY;
            panX = panStartPanX + dx;
            panY = panStartPanY + dy;
            updateSVGViewBox();
        });

        window.addEventListener('mouseup', (e) => {
            if (isDrawingConnection) {
                endConnectionDraw(e);
                return;
            }
            if (isDraggingNode) {
                endNodeDrag(e);
                return;
            }
            if (isPanning) {
                isPanning = false;
                if (dom.svgContainer) dom.svgContainer.classList.remove('grabbing');
            }
        });

        dom.svgContainer.addEventListener('wheel', (e) => {
            e.preventDefault();
            const delta = e.deltaY > 0 ? 0.9 : 1.1;
            const newZoom = Math.max(0.1, Math.min(5.0, zoom * delta));

            // Zoom towards cursor position
            const rect = dom.svgContainer.getBoundingClientRect();
            const mouseX = e.clientX - rect.left;
            const mouseY = e.clientY - rect.top;

            panX = mouseX - (mouseX - panX) * (newZoom / zoom);
            panY = mouseY - (mouseY - panY) * (newZoom / zoom);
            zoom = newZoom;

            updateSVGViewBox();
        }, { passive: false });

        // Click on SVG background to deselect
        dom.previewSvg.addEventListener('click', (e) => {
            if (e.target === dom.previewSvg || e.target.tagName === 'svg') {
                clearSelection();
            }
        });

        // Right-click on SVG background → show paste/select-all context menu
        dom.previewSvg.addEventListener('contextmenu', (e) => {
            if (e.target === dom.previewSvg || e.target.tagName === 'svg') {
                e.preventDefault();
                e.stopPropagation();
                // Show context menu with only paste + select-all visible
                contextMenuTarget = null;
                if (dom.contextMenu) {
                    dom.contextMenu.querySelectorAll('.context-menu-item').forEach(item => {
                        const action = item.dataset.action;
                        if (action === 'paste' || action === 'select-all') {
                            item.style.display = '';
                            if (action === 'paste') item.classList.toggle('disabled', clipboard.length === 0);
                        } else {
                            item.style.display = 'none';
                        }
                    });
                    const menuW = 200;
                    const menuH = 80;
                    const x = Math.min(e.clientX, window.innerWidth - menuW);
                    const y = Math.min(e.clientY, window.innerHeight - menuH);
                    dom.contextMenu.style.left = x + 'px';
                    dom.contextMenu.style.top = y + 'px';
                    dom.contextMenu.classList.add('visible');
                }
            }
        });
    }

    // ========== PROPERTIES PANEL ==========

    function clearProperties() {
        if (dom.propertiesContent) dom.propertiesContent.innerHTML = '';
        if (dom.propertiesEmpty) dom.propertiesEmpty.classList.remove('hidden');
        if (dom.propertiesActions) dom.propertiesActions.classList.add('hidden');
    }

    function showProperties(element) {
        if (!element || !element.xmlEl) {
            clearProperties();
            return;
        }

        if (dom.propertiesEmpty) dom.propertiesEmpty.classList.add('hidden');
        if (dom.propertiesActions) dom.propertiesActions.classList.remove('hidden');
        if (!dom.propertiesContent) return;

        dom.propertiesContent.innerHTML = '';

        if (element.type === 'link') {
            renderLinkProperties(element);
        } else {
            renderJointProperties(element);
        }
    }

    function renderLinkProperties(element) {
        const data = extractLinkData(element.xmlEl);
        const container = dom.propertiesContent;

        // === Identity Section ===
        container.appendChild(createPropSection('Identity', '\u{1F3F7}', [
            createPropRow('Name', createReadonlyInput('prop-link-name', data.name)),
        ]));

        // === Parent Joint Section ===
        // Find the joint that has this link as its child
        const parentJointInfo = findParentJoint(data.name);
        if (parentJointInfo) {
            const pjData = extractJointData(parentJointInfo);
            const pjRows = [
                createPropRow('Joint Name', createReadonlyInput('prop-pj-name', pjData.name)),
                createPropRow('Joint Type', createReadonlyInput('prop-pj-type', pjData.type)),
                createPropRow('Parent Link', createReadonlyInput('prop-pj-parent', pjData.parent)),
                createCompactRow('Position', [
                    { label: 'x', id: 'prop-pj-ox', value: pjData.origin.xyz[0] },
                    { label: 'y', id: 'prop-pj-oy', value: pjData.origin.xyz[1] },
                    { label: 'z', id: 'prop-pj-oz', value: pjData.origin.xyz[2] },
                ]),
                createCompactRow('Rotation', [
                    { label: 'r', id: 'prop-pj-or', value: pjData.origin.rpy[0] },
                    { label: 'p', id: 'prop-pj-op', value: pjData.origin.rpy[1] },
                    { label: 'y', id: 'prop-pj-ow', value: pjData.origin.rpy[2] },
                ]),
            ];
            // Show axis for non-fixed joints
            if (pjData.type !== 'fixed') {
                pjRows.push(createCompactRow('Axis', [
                    { label: 'x', id: 'prop-pj-ax', value: pjData.axis[0] },
                    { label: 'y', id: 'prop-pj-ay', value: pjData.axis[1] },
                    { label: 'z', id: 'prop-pj-az', value: pjData.axis[2] },
                ]));
            }
            container.appendChild(createPropSection('Parent Joint', '\u{1F517}', pjRows));
        } else {
            // Check if this is an orphan root (not the primary root link)
            const { orphans } = getOrphanRootLinks();
            const isOrphan = orphans.includes(data.name);
            const rootRows = [];
            if (isOrphan) {
                rootRows.push(createInfoRow('\u26A0 Orphan link \u2014 not connected to main tree'));
                // Add "Attach to Parent" button
                const attachBtn = document.createElement('button');
                attachBtn.className = 'prop-action-btn';
                attachBtn.style.cssText = 'width:100%;margin-top:4px;background:#3a2a0e;border-color:#c08030;color:#ffa726;';
                attachBtn.textContent = '\uD83D\uDD17 Attach to Parent Link...';
                attachBtn.addEventListener('click', () => openAttachOrphanModal(data.name));
                const btnRow = document.createElement('div');
                btnRow.style.padding = '4px 8px';
                btnRow.appendChild(attachBtn);
                rootRows.push(btnRow);
            } else {
                rootRows.push(createInfoRow('Root link (no parent joint)'));
            }
            container.appendChild(createPropSection('Parent Joint', '\u{1F517}', rootRows));
        }

        // === Visual Geometry Section ===
        if (data.visual) {
            const geom = data.visual.geometry;
            const geomRows = [];

            // Geometry type dropdown
            const typeSelect = createSelect('prop-vis-geom-type',
                ['box', 'cylinder', 'sphere', 'mesh'], geom.type);
            typeSelect.addEventListener('change', () => {
                // Re-render properties when type changes
                showProperties(selectedElement);
            });
            geomRows.push(createPropRow('Type', typeSelect));

            // Dimension fields based on type
            if (geom.type === 'box') {
                geomRows.push(createCompactRow('Size', [
                    { label: 'x', id: 'prop-vis-box-x', value: geom.dimensions.x },
                    { label: 'y', id: 'prop-vis-box-y', value: geom.dimensions.y },
                    { label: 'z', id: 'prop-vis-box-z', value: geom.dimensions.z },
                ]));
            } else if (geom.type === 'cylinder') {
                geomRows.push(createPropRow('Radius', createNumberInput('prop-vis-cyl-r', geom.dimensions.radius, 0.001)));
                geomRows.push(createPropRow('Length', createNumberInput('prop-vis-cyl-l', geom.dimensions.length, 0.001)));
            } else if (geom.type === 'sphere') {
                geomRows.push(createPropRow('Radius', createNumberInput('prop-vis-sph-r', geom.dimensions.radius, 0.001)));
            } else if (geom.type === 'mesh') {
                geomRows.push(createPropRow('File', createTextInput('prop-vis-mesh-file', geom.dimensions.filename)));
                geomRows.push(createCompactRow('Scale', [
                    { label: 'x', id: 'prop-vis-mesh-sx', value: geom.dimensions.scaleX },
                    { label: 'y', id: 'prop-vis-mesh-sy', value: geom.dimensions.scaleY },
                    { label: 'z', id: 'prop-vis-mesh-sz', value: geom.dimensions.scaleZ },
                ]));
            }

            container.appendChild(createPropSection('Visual Geometry', '\u25A6', geomRows));

            // === Visual Origin ===
            const origin = data.visual.origin;
            container.appendChild(createPropSection('Visual Origin', '\u2316', [
                createCompactRow('XYZ', [
                    { label: 'x', id: 'prop-vis-ox', value: origin.xyz[0] },
                    { label: 'y', id: 'prop-vis-oy', value: origin.xyz[1] },
                    { label: 'z', id: 'prop-vis-oz', value: origin.xyz[2] },
                ]),
                createCompactRow('RPY', [
                    { label: 'r', id: 'prop-vis-or', value: origin.rpy[0] },
                    { label: 'p', id: 'prop-vis-op', value: origin.rpy[1] },
                    { label: 'y', id: 'prop-vis-ow', value: origin.rpy[2] },
                ]),
            ]));

            // === Visual Material ===
            const mat = data.visual.material;
            const hexColor = rgbaToHex(mat.color[0], mat.color[1], mat.color[2]);
            container.appendChild(createPropSection('Material', '\u{1F3A8}', [
                createColorRow('Color', 'prop-vis-color', hexColor),
                createPropRow('Name', createTextInput('prop-vis-mat-name', mat.name)),
            ]));

            // Live 3D color preview: update mesh color as the user picks
            const colorPickerEl = $('prop-vis-color');
            if (colorPickerEl && window.viewer3d && window.viewer3d.updateLinkColor) {
                colorPickerEl.addEventListener('input', () => {
                    const rgb = hexToRgba(colorPickerEl.value);
                    window.viewer3d.updateLinkColor(data.name, rgb[0], rgb[1], rgb[2]);
                });
            }

            // Live 3D scale preview: update mesh scale as the user types
            if (geom.type === 'mesh' && window.viewer3d && window.viewer3d.updateLinkScale) {
                const scaleInputIds = ['prop-vis-mesh-sx', 'prop-vis-mesh-sy', 'prop-vis-mesh-sz'];
                scaleInputIds.forEach(id => {
                    const el = $(id);
                    if (el) {
                        el.addEventListener('input', () => {
                            const sx = parseFloat($('prop-vis-mesh-sx')?.value) || 1;
                            const sy = parseFloat($('prop-vis-mesh-sy')?.value) || 1;
                            const sz = parseFloat($('prop-vis-mesh-sz')?.value) || 1;
                            window.viewer3d.updateLinkScale(data.name, sx, sy, sz);
                        });
                    }
                });
            }
        } else {
            container.appendChild(createPropSection('Visual', '\u25A6', [
                createInfoRow('No visual element defined'),
            ]));
        }

        // === Inertial Section ===
        const massVal = data.inertial ? data.inertial.mass : 0;
        container.appendChild(createPropSection('Inertial', '\u2696', [
            createPropRow('Mass', createNumberInput('prop-inertial-mass', massVal, 0.001)),
        ]));

        // === Collision Section ===
        if (data.collision) {
            const cGeom = data.collision.geometry;
            const collRows = [];
            const cTypeSelect = createSelect('prop-col-geom-type',
                ['box', 'cylinder', 'sphere', 'mesh'], cGeom.type);
            collRows.push(createPropRow('Type', cTypeSelect));

            if (cGeom.type === 'box') {
                collRows.push(createCompactRow('Size', [
                    { label: 'x', id: 'prop-col-box-x', value: cGeom.dimensions.x },
                    { label: 'y', id: 'prop-col-box-y', value: cGeom.dimensions.y },
                    { label: 'z', id: 'prop-col-box-z', value: cGeom.dimensions.z },
                ]));
            } else if (cGeom.type === 'cylinder') {
                collRows.push(createPropRow('Radius', createNumberInput('prop-col-cyl-r', cGeom.dimensions.radius, 0.001)));
                collRows.push(createPropRow('Length', createNumberInput('prop-col-cyl-l', cGeom.dimensions.length, 0.001)));
            } else if (cGeom.type === 'sphere') {
                collRows.push(createPropRow('Radius', createNumberInput('prop-col-sph-r', cGeom.dimensions.radius, 0.001)));
            } else if (cGeom.type === 'mesh') {
                collRows.push(createPropRow('File', createTextInput('prop-col-mesh-file', cGeom.dimensions.filename)));
                collRows.push(createCompactRow('Scale', [
                    { label: 'x', id: 'prop-col-mesh-sx', value: cGeom.dimensions.scaleX },
                    { label: 'y', id: 'prop-col-mesh-sy', value: cGeom.dimensions.scaleY },
                    { label: 'z', id: 'prop-col-mesh-sz', value: cGeom.dimensions.scaleZ },
                ]));
            }

            container.appendChild(createPropSection('Collision', '\u26A0', collRows));
        }
    }

    function renderJointProperties(element) {
        const data = extractJointData(element.xmlEl);
        const container = dom.propertiesContent;
        const linkNames = getLinkNames();

        // === Identity Section ===
        const typeSelect = createSelect('prop-joint-type',
            ['fixed', 'revolute', 'prismatic', 'continuous', 'floating', 'planar'], data.type);
        container.appendChild(createPropSection('Identity', '\u{1F3F7}', [
            createPropRow('Name', createReadonlyInput('prop-joint-name', data.name)),
            createPropRow('Type', typeSelect),
        ]));

        // === Parent / Child ===
        const parentSelect = createSelect('prop-joint-parent', linkNames, data.parent);
        const childSelect = createSelect('prop-joint-child', linkNames, data.child);
        container.appendChild(createPropSection('Connection', '\u{1F517}', [
            createPropRow('Parent', parentSelect),
            createPropRow('Child', childSelect),
        ]));

        // === Origin ===
        container.appendChild(createPropSection('Origin', '\u2316', [
            createCompactRow('XYZ', [
                { label: 'x', id: 'prop-joint-ox', value: data.origin.xyz[0] },
                { label: 'y', id: 'prop-joint-oy', value: data.origin.xyz[1] },
                { label: 'z', id: 'prop-joint-oz', value: data.origin.xyz[2] },
            ]),
            createCompactRow('RPY', [
                { label: 'r', id: 'prop-joint-or', value: data.origin.rpy[0] },
                { label: 'p', id: 'prop-joint-op', value: data.origin.rpy[1] },
                { label: 'y', id: 'prop-joint-ow', value: data.origin.rpy[2] },
            ]),
        ]));

        // === Axis ===
        container.appendChild(createPropSection('Axis', '\u2194', [
            createCompactRow('XYZ', [
                { label: 'x', id: 'prop-joint-ax', value: data.axis[0] },
                { label: 'y', id: 'prop-joint-ay', value: data.axis[1] },
                { label: 'z', id: 'prop-joint-az', value: data.axis[2] },
            ]),
        ]));

        // === Limits ===
        container.appendChild(createPropSection('Limits', '\u2195', [
            createPropRow('Lower', createNumberInput('prop-joint-lim-lower', data.limit.lower, 0.001)),
            createPropRow('Upper', createNumberInput('prop-joint-lim-upper', data.limit.upper, 0.001)),
            createPropRow('Effort', createNumberInput('prop-joint-lim-effort', data.limit.effort, 0.001)),
            createPropRow('Velocity', createNumberInput('prop-joint-lim-vel', data.limit.velocity, 0.001)),
        ]));
    }

    // ========== PROPERTY DOM BUILDERS ==========

    function createPropSection(title, icon, rows) {
        const section = document.createElement('div');
        section.classList.add('prop-section');

        const titleEl = document.createElement('div');
        titleEl.classList.add('prop-section-title');
        const iconSpan = document.createElement('span');
        iconSpan.classList.add('section-icon');
        iconSpan.textContent = icon;
        titleEl.appendChild(iconSpan);
        titleEl.appendChild(document.createTextNode(title));
        section.appendChild(titleEl);

        rows.forEach(row => {
            if (row) section.appendChild(row);
        });
        return section;
    }

    function createPropRow(labelText, inputEl) {
        const row = document.createElement('div');
        row.classList.add('prop-row');
        const label = document.createElement('label');
        label.classList.add('prop-label');
        label.textContent = labelText;
        row.appendChild(label);
        row.appendChild(inputEl);
        return row;
    }

    function createCompactRow(labelText, fields) {
        const row = document.createElement('div');
        row.classList.add('prop-row-compact');

        const label = document.createElement('label');
        label.classList.add('prop-label');
        label.textContent = labelText;
        row.appendChild(label);

        fields.forEach(f => {
            const mini = document.createElement('span');
            mini.classList.add('mini-label');
            mini.textContent = f.label;
            row.appendChild(mini);

            const input = document.createElement('input');
            input.type = 'number';
            input.step = '0.001';
            input.classList.add('prop-input');
            input.id = f.id;
            input.value = roundNum(f.value);
            row.appendChild(input);
        });

        return row;
    }

    function createColorRow(labelText, id, hexValue) {
        const row = document.createElement('div');
        row.classList.add('prop-color-row');

        const label = document.createElement('label');
        label.classList.add('prop-label');
        label.textContent = labelText;
        row.appendChild(label);

        const swatch = document.createElement('div');
        swatch.classList.add('prop-color-swatch');
        swatch.style.backgroundColor = hexValue;
        row.appendChild(swatch);

        const picker = document.createElement('input');
        picker.type = 'color';
        picker.id = id;
        picker.classList.add('prop-color-picker');
        picker.value = hexValue;
        row.appendChild(picker);

        const valueLabel = document.createElement('span');
        valueLabel.classList.add('prop-color-value');
        valueLabel.textContent = hexValue;
        valueLabel.id = id + '-label';
        row.appendChild(valueLabel);

        swatch.addEventListener('click', () => picker.click());
        picker.addEventListener('input', () => {
            swatch.style.backgroundColor = picker.value;
            valueLabel.textContent = picker.value;
        });

        return row;
    }

    function createReadonlyInput(id, value) {
        const input = document.createElement('input');
        input.type = 'text';
        input.classList.add('prop-input');
        input.id = id;
        input.value = value;
        input.readOnly = true;
        return input;
    }

    function createTextInput(id, value) {
        const input = document.createElement('input');
        input.type = 'text';
        input.classList.add('prop-input');
        input.id = id;
        input.value = value || '';
        return input;
    }

    function createNumberInput(id, value, step) {
        const input = document.createElement('input');
        input.type = 'number';
        input.step = String(step || 0.001);
        input.classList.add('prop-input');
        input.id = id;
        input.value = roundNum(value);
        return input;
    }

    function createSelect(id, options, selectedValue) {
        const select = document.createElement('select');
        select.classList.add('prop-input');
        select.id = id;
        options.forEach(opt => {
            const o = document.createElement('option');
            o.value = opt;
            o.textContent = opt;
            if (opt === selectedValue) o.selected = true;
            select.appendChild(o);
        });
        return select;
    }

    function createInfoRow(text) {
        const row = document.createElement('div');
        row.classList.add('prop-row');
        row.style.color = 'var(--text-muted)';
        row.style.fontStyle = 'italic';
        row.style.fontSize = '12px';
        row.textContent = text;
        return row;
    }

    // ========== APPLY PROPERTIES ==========

    function applyProperties() {
        if (!selectedElement || !selectedElement.xmlEl) {
            showToast('No element selected', 'warning');
            return;
        }

        pushUndo('Edit ' + selectedElement.type + ' "' + selectedElement.name + '"');

        try {
            if (selectedElement.type === 'link') {
                applyLinkProperties(selectedElement.xmlEl);
            } else {
                applyJointProperties(selectedElement.xmlEl);
            }
            renderTree();
            renderSVG();
            fireURDFChanged();
            showToast('Properties applied', 'success');
        } catch (e) {
            showToast('Error applying properties: ' + e.message, 'error');
        }
    }

    function applyLinkProperties(linkEl) {
        // Visual geometry
        let vis = linkEl.querySelector('visual');
        if (!vis) {
            vis = urdfDoc.createElement('visual');
            linkEl.appendChild(vis);
        }

        // Geometry type
        const geomTypeEl = $('prop-vis-geom-type');
        if (geomTypeEl) {
            applyGeometryToElement(vis, geomTypeEl.value, 'vis');
        }

        // Visual origin
        applyOriginToElement(vis, 'prop-vis-ox', 'prop-vis-oy', 'prop-vis-oz',
            'prop-vis-or', 'prop-vis-op', 'prop-vis-ow');

        // Material
        const colorPicker = $('prop-vis-color');
        const matNameInput = $('prop-vis-mat-name');
        if (colorPicker) {
            let mat = vis.querySelector('material');
            if (!mat) {
                mat = urdfDoc.createElement('material');
                vis.appendChild(mat);
            }
            // Always ensure material has a name (required by gz sdf -p)
            const linkName = linkEl.getAttribute('name') || 'unnamed';
            if (matNameInput && matNameInput.value) {
                mat.setAttribute('name', matNameInput.value);
            } else if (!mat.getAttribute('name')) {
                mat.setAttribute('name', linkName + '_material');
            }
            let colorEl = mat.querySelector('color');
            if (!colorEl) {
                colorEl = urdfDoc.createElement('color');
                mat.appendChild(colorEl);
            }
            const rgb = hexToRgba(colorPicker.value);
            const rgbaStr = rgb[0].toFixed(4) + ' ' + rgb[1].toFixed(4) + ' ' + rgb[2].toFixed(4) + ' 1.0';
            colorEl.setAttribute('rgba', rgbaStr);

            // Also update <gazebo reference="linkName"> material so Gazebo shows the color
            updateGazeboMaterial(linkName, rgb);
        }

        // Inertial mass
        const massInput = $('prop-inertial-mass');
        if (massInput) {
            let inertial = linkEl.querySelector('inertial');
            if (!inertial) {
                inertial = urdfDoc.createElement('inertial');
                linkEl.appendChild(inertial);
            }
            let massEl = inertial.querySelector('mass');
            if (!massEl) {
                massEl = urdfDoc.createElement('mass');
                inertial.appendChild(massEl);
            }
            massEl.setAttribute('value', parseFloat(massInput.value) || 0);
        }

        // Collision geometry
        const colTypeEl = $('prop-col-geom-type');
        if (colTypeEl) {
            let col = linkEl.querySelector('collision');
            if (!col) {
                col = urdfDoc.createElement('collision');
                linkEl.appendChild(col);
            }
            applyGeometryToElement(col, colTypeEl.value, 'col');
        }
    }

    function applyGeometryToElement(parentEl, type, prefix) {
        let geom = parentEl.querySelector('geometry');
        if (!geom) {
            geom = urdfDoc.createElement('geometry');
            parentEl.appendChild(geom);
        }
        // Remove existing geometry children
        while (geom.firstChild) geom.removeChild(geom.firstChild);

        if (type === 'box') {
            const box = urdfDoc.createElement('box');
            const x = getInputVal(prefix === 'vis' ? 'prop-vis-box-x' : 'prop-col-box-x', 0.1);
            const y = getInputVal(prefix === 'vis' ? 'prop-vis-box-y' : 'prop-col-box-y', 0.1);
            const z = getInputVal(prefix === 'vis' ? 'prop-vis-box-z' : 'prop-col-box-z', 0.1);
            box.setAttribute('size', x + ' ' + y + ' ' + z);
            geom.appendChild(box);
        } else if (type === 'cylinder') {
            const cyl = urdfDoc.createElement('cylinder');
            cyl.setAttribute('radius', getInputVal(prefix === 'vis' ? 'prop-vis-cyl-r' : 'prop-col-cyl-r', 0.05));
            cyl.setAttribute('length', getInputVal(prefix === 'vis' ? 'prop-vis-cyl-l' : 'prop-col-cyl-l', 0.1));
            geom.appendChild(cyl);
        } else if (type === 'sphere') {
            const sph = urdfDoc.createElement('sphere');
            sph.setAttribute('radius', getInputVal(prefix === 'vis' ? 'prop-vis-sph-r' : 'prop-col-sph-r', 0.05));
            geom.appendChild(sph);
        } else if (type === 'mesh') {
            const mesh = urdfDoc.createElement('mesh');
            const fileInput = $(prefix === 'vis' ? 'prop-vis-mesh-file' : 'prop-col-mesh-file');
            mesh.setAttribute('filename', fileInput ? fileInput.value : '');
            const sx = getInputVal(prefix === 'vis' ? 'prop-vis-mesh-sx' : 'prop-col-mesh-sx', 1);
            const sy = getInputVal(prefix === 'vis' ? 'prop-vis-mesh-sy' : 'prop-col-mesh-sy', 1);
            const sz = getInputVal(prefix === 'vis' ? 'prop-vis-mesh-sz' : 'prop-col-mesh-sz', 1);
            mesh.setAttribute('scale', sx + ' ' + sy + ' ' + sz);
            geom.appendChild(mesh);
        }
    }

    function applyOriginToElement(parentEl, xId, yId, zId, rId, pId, yawId) {
        const ox = getInputVal(xId, 0);
        const oy = getInputVal(yId, 0);
        const oz = getInputVal(zId, 0);
        const oR = getInputVal(rId, 0);
        const oP = getInputVal(pId, 0);
        const oY = getInputVal(yawId, 0);

        let origin = parentEl.querySelector('origin');
        if (!origin) {
            origin = urdfDoc.createElement('origin');
            // Insert origin as first child
            if (parentEl.firstChild) {
                parentEl.insertBefore(origin, parentEl.firstChild);
            } else {
                parentEl.appendChild(origin);
            }
        }
        origin.setAttribute('xyz', ox + ' ' + oy + ' ' + oz);
        origin.setAttribute('rpy', oR + ' ' + oP + ' ' + oY);
    }

    function applyJointProperties(jointEl) {
        // Type
        const typeInput = $('prop-joint-type');
        if (typeInput) {
            jointEl.setAttribute('type', typeInput.value);
        }

        // Parent
        const parentInput = $('prop-joint-parent');
        if (parentInput) {
            let parentEl = jointEl.querySelector('parent');
            if (!parentEl) {
                parentEl = urdfDoc.createElement('parent');
                jointEl.appendChild(parentEl);
            }
            parentEl.setAttribute('link', parentInput.value);
        }

        // Child
        const childInput = $('prop-joint-child');
        if (childInput) {
            let childEl = jointEl.querySelector('child');
            if (!childEl) {
                childEl = urdfDoc.createElement('child');
                jointEl.appendChild(childEl);
            }
            childEl.setAttribute('link', childInput.value);
        }

        // Origin
        applyOriginToElement(jointEl, 'prop-joint-ox', 'prop-joint-oy', 'prop-joint-oz',
            'prop-joint-or', 'prop-joint-op', 'prop-joint-ow');

        // Axis
        const ax = getInputVal('prop-joint-ax', 0);
        const ay = getInputVal('prop-joint-ay', 0);
        const az = getInputVal('prop-joint-az', 1);
        let axisEl = jointEl.querySelector('axis');
        if (!axisEl) {
            axisEl = urdfDoc.createElement('axis');
            jointEl.appendChild(axisEl);
        }
        axisEl.setAttribute('xyz', ax + ' ' + ay + ' ' + az);

        // Limits
        const limLower = getInputVal('prop-joint-lim-lower', 0);
        const limUpper = getInputVal('prop-joint-lim-upper', 0);
        const limEffort = getInputVal('prop-joint-lim-effort', 0);
        const limVelocity = getInputVal('prop-joint-lim-vel', 0);

        let limitEl = jointEl.querySelector('limit');
        if (!limitEl) {
            limitEl = urdfDoc.createElement('limit');
            jointEl.appendChild(limitEl);
        }
        limitEl.setAttribute('lower', limLower);
        limitEl.setAttribute('upper', limUpper);
        limitEl.setAttribute('effort', limEffort);
        limitEl.setAttribute('velocity', limVelocity);
    }

    function getInputVal(id, fallback) {
        const el = $(id);
        if (!el) return fallback;
        const v = parseFloat(el.value);
        return isNaN(v) ? fallback : v;
    }

    // ========== ADD LINK ==========

    function openAddLinkModal() {
        if (!dom.addLinkModal) return;

        // Reset form
        if (dom.addLinkName) dom.addLinkName.value = '';
        if (dom.addLinkMass) dom.addLinkMass.value = '1.0';
        if (dom.addLinkGeomLength) dom.addLinkGeomLength.value = '0.1';
        if (dom.addLinkGeomWidth) dom.addLinkGeomWidth.value = '0.1';
        if (dom.addLinkGeomHeight) dom.addLinkGeomHeight.value = '0.1';
        if (dom.addLinkGeomRadius) dom.addLinkGeomRadius.value = '0.05';

        // Populate parent dropdown
        if (dom.addLinkParent) {
            dom.addLinkParent.innerHTML = '';
            const links = getLinkNames();
            links.forEach(name => {
                const opt = document.createElement('option');
                opt.value = name;
                opt.textContent = name;
                if (selectedElement && selectedElement.type === 'link' && selectedElement.name === name) {
                    opt.selected = true;
                }
                dom.addLinkParent.appendChild(opt);
            });
        }

        // Populate mesh dropdown (now a <select>)
        if (dom.addLinkMeshFile) {
            dom.addLinkMeshFile.innerHTML = '<option value="">(none - use custom path)</option>';
            meshListCache.forEach(m => {
                const opt = document.createElement('option');
                opt.value = m.path || m.name;
                opt.textContent = m.name;
                dom.addLinkMeshFile.appendChild(opt);
            });
        }
        if (dom.addLinkMeshCustom) dom.addLinkMeshCustom.value = '';

        // Select default geometry type
        selectGeometryType('box');

        // Fetch latest mesh list
        fetchMeshList();

        showModal(dom.addLinkModal);
    }

    function selectGeometryType(type) {
        const btns = document.querySelectorAll('.geometry-type-btn');
        btns.forEach(btn => {
            btn.classList.toggle('selected', btn.dataset.type === type);
        });

        // Show/hide dimension fields - handle elements that belong to multiple types
        const allGeomFields = document.querySelectorAll(
            '.geom-field-box, .geom-field-cylinder, .geom-field-sphere, .geom-field-mesh'
        );
        allGeomFields.forEach(el => {
            const visible = el.classList.contains('geom-field-' + type);
            el.classList.toggle('hidden', !visible);
        });
    }

    function getSelectedGeometryType() {
        const btn = document.querySelector('.geometry-type-btn.selected');
        return btn ? btn.dataset.type : 'box';
    }

    function confirmAddLink() {
        if (!urdfDoc) {
            // Create a new URDF document
            urdfDoc = parseXMLString('<?xml version="1.0"?><robot name="robot"></robot>');
        }

        const name = dom.addLinkName ? dom.addLinkName.value.trim() : '';
        if (!name) {
            showToast('Link name is required', 'error');
            return;
        }

        // Check for duplicate name
        if (getLinkByName(name)) {
            showToast('A link named "' + name + '" already exists', 'error');
            return;
        }

        pushUndo('Add link "' + name + '"');

        const robot = urdfDoc.querySelector('robot');
        const geomType = getSelectedGeometryType();

        // Create link element
        const linkEl = urdfDoc.createElement('link');
        linkEl.setAttribute('name', name);

        // Visual
        const visual = urdfDoc.createElement('visual');
        const geometry = urdfDoc.createElement('geometry');

        if (geomType === 'box') {
            const box = urdfDoc.createElement('box');
            const l = dom.addLinkGeomLength ? dom.addLinkGeomLength.value : '0.1';
            const w = dom.addLinkGeomWidth ? dom.addLinkGeomWidth.value : '0.1';
            const h = dom.addLinkGeomHeight ? dom.addLinkGeomHeight.value : '0.1';
            box.setAttribute('size', l + ' ' + w + ' ' + h);
            geometry.appendChild(box);
        } else if (geomType === 'cylinder') {
            const cyl = urdfDoc.createElement('cylinder');
            cyl.setAttribute('radius', dom.addLinkGeomRadius ? dom.addLinkGeomRadius.value : '0.05');
            cyl.setAttribute('length', dom.addLinkGeomLength ? dom.addLinkGeomLength.value : '0.1');
            geometry.appendChild(cyl);
        } else if (geomType === 'sphere') {
            const sph = urdfDoc.createElement('sphere');
            sph.setAttribute('radius', dom.addLinkGeomRadius ? dom.addLinkGeomRadius.value : '0.05');
            geometry.appendChild(sph);
        } else if (geomType === 'mesh') {
            const mesh = urdfDoc.createElement('mesh');
            // Prefer dropdown selection, fall back to custom path
            let meshPath = dom.addLinkMeshFile ? dom.addLinkMeshFile.value : '';
            if (!meshPath && dom.addLinkMeshCustom) meshPath = dom.addLinkMeshCustom.value || '';
            mesh.setAttribute('filename', meshPath);
            const sx = $('add-link-mesh-sx') ? $('add-link-mesh-sx').value : '1';
            const sy = $('add-link-mesh-sy') ? $('add-link-mesh-sy').value : '1';
            const sz = $('add-link-mesh-sz') ? $('add-link-mesh-sz').value : '1';
            mesh.setAttribute('scale', sx + ' ' + sy + ' ' + sz);
            geometry.appendChild(mesh);
        }

        visual.appendChild(geometry);

        // Default material
        const material = urdfDoc.createElement('material');
        material.setAttribute('name', name + '_material');
        const color = urdfDoc.createElement('color');
        const colorPicker = $('add-link-color-picker');
        if (colorPicker && colorPicker.value) {
            const rgb = hexToRgba(colorPicker.value);
            color.setAttribute('rgba', rgb.join(' '));
        } else {
            color.setAttribute('rgba', '0.7 0.7 0.7 1.0');
        }
        material.appendChild(color);
        visual.appendChild(material);

        linkEl.appendChild(visual);

        // Collision (mirror visual)
        const collision = urdfDoc.createElement('collision');
        const collGeom = geometry.cloneNode(true);
        collision.appendChild(collGeom);
        linkEl.appendChild(collision);

        // Inertial
        const inertial = urdfDoc.createElement('inertial');
        const mass = urdfDoc.createElement('mass');
        mass.setAttribute('value', dom.addLinkMass ? dom.addLinkMass.value : '1.0');
        inertial.appendChild(mass);
        const inertia = urdfDoc.createElement('inertia');
        inertia.setAttribute('ixx', '0.001');
        inertia.setAttribute('ixy', '0');
        inertia.setAttribute('ixz', '0');
        inertia.setAttribute('iyy', '0.001');
        inertia.setAttribute('iyz', '0');
        inertia.setAttribute('izz', '0.001');
        inertial.appendChild(inertia);
        linkEl.appendChild(inertial);

        robot.appendChild(linkEl);

        // Create a fixed joint to parent (if a parent is selected and links exist)
        const parentName = dom.addLinkParent ? dom.addLinkParent.value : '';
        if (parentName && getLinkByName(parentName)) {
            const jointEl = urdfDoc.createElement('joint');
            jointEl.setAttribute('name', parentName + '_to_' + name + '_joint');
            jointEl.setAttribute('type', 'fixed');

            const parentTag = urdfDoc.createElement('parent');
            parentTag.setAttribute('link', parentName);
            jointEl.appendChild(parentTag);

            const childTag = urdfDoc.createElement('child');
            childTag.setAttribute('link', name);
            jointEl.appendChild(childTag);

            const origin = urdfDoc.createElement('origin');
            origin.setAttribute('xyz', '0 0 0');
            origin.setAttribute('rpy', '0 0 0');
            jointEl.appendChild(origin);

            robot.appendChild(jointEl);
        }

        closeAllModals();
        renderTree();
        renderSVG();
        fitView();
        updateStatusCounts();
        selectElement('link', name, linkEl);
        fireURDFChanged();
        showToast('Link "' + name + '" added', 'success');
    }

    // ========== ADD JOINT ==========

    function openAddJointModal() {
        if (!dom.addJointModal) return;

        const linkNames = getLinkNames();
        if (linkNames.length < 2) {
            showToast('Need at least 2 links to create a joint', 'warning');
            return;
        }

        // Reset form
        if (dom.addJointName) dom.addJointName.value = '';
        if (dom.addJointOriginX) dom.addJointOriginX.value = '0';
        if (dom.addJointOriginY) dom.addJointOriginY.value = '0';
        if (dom.addJointOriginZ) dom.addJointOriginZ.value = '0';
        if (dom.addJointOriginR) dom.addJointOriginR.value = '0';
        if (dom.addJointOriginP) dom.addJointOriginP.value = '0';
        if (dom.addJointOriginYaw) dom.addJointOriginYaw.value = '0';
        if (dom.addJointAxisX) dom.addJointAxisX.value = '0';
        if (dom.addJointAxisY) dom.addJointAxisY.value = '0';
        if (dom.addJointAxisZ) dom.addJointAxisZ.value = '1';
        if (dom.addJointLimitLower) dom.addJointLimitLower.value = '0';
        if (dom.addJointLimitUpper) dom.addJointLimitUpper.value = '0';
        if (dom.addJointLimitEffort) dom.addJointLimitEffort.value = '100';
        if (dom.addJointLimitVelocity) dom.addJointLimitVelocity.value = '1.0';

        // Populate type dropdown
        if (dom.addJointType) {
            dom.addJointType.innerHTML = '';
            ['fixed', 'revolute', 'prismatic', 'continuous'].forEach(t => {
                const opt = document.createElement('option');
                opt.value = t;
                opt.textContent = t;
                dom.addJointType.appendChild(opt);
            });
        }

        // Populate parent/child dropdowns
        [dom.addJointParent, dom.addJointChild].forEach((sel, idx) => {
            if (!sel) return;
            sel.innerHTML = '';
            linkNames.forEach((name, li) => {
                const opt = document.createElement('option');
                opt.value = name;
                opt.textContent = name;
                // Pre-select: parent = first link (or selected), child = second
                if (idx === 0 && selectedElement && selectedElement.type === 'link' && selectedElement.name === name) {
                    opt.selected = true;
                } else if (idx === 0 && li === 0) {
                    opt.selected = true;
                } else if (idx === 1 && li === 1) {
                    opt.selected = true;
                }
                sel.appendChild(opt);
            });
        });

        showModal(dom.addJointModal);
    }

    function confirmAddJoint() {
        if (!urdfDoc) {
            showToast('No URDF loaded', 'error');
            return;
        }

        const name = dom.addJointName ? dom.addJointName.value.trim() : '';
        if (!name) {
            showToast('Joint name is required', 'error');
            return;
        }

        if (getJointByName(name)) {
            showToast('A joint named "' + name + '" already exists', 'error');
            return;
        }

        const type = dom.addJointType ? dom.addJointType.value : 'fixed';
        const parentLink = dom.addJointParent ? dom.addJointParent.value : '';
        const childLink = dom.addJointChild ? dom.addJointChild.value : '';

        if (!parentLink || !childLink) {
            showToast('Parent and child links are required', 'error');
            return;
        }
        if (parentLink === childLink) {
            showToast('Parent and child cannot be the same link', 'error');
            return;
        }

        pushUndo('Add joint "' + name + '"');

        const robot = urdfDoc.querySelector('robot');
        const jointEl = urdfDoc.createElement('joint');
        jointEl.setAttribute('name', name);
        jointEl.setAttribute('type', type);

        const parentTag = urdfDoc.createElement('parent');
        parentTag.setAttribute('link', parentLink);
        jointEl.appendChild(parentTag);

        const childTag = urdfDoc.createElement('child');
        childTag.setAttribute('link', childLink);
        jointEl.appendChild(childTag);

        // Origin
        const origin = urdfDoc.createElement('origin');
        const ox = dom.addJointOriginX ? dom.addJointOriginX.value : '0';
        const oy = dom.addJointOriginY ? dom.addJointOriginY.value : '0';
        const oz = dom.addJointOriginZ ? dom.addJointOriginZ.value : '0';
        const oR = dom.addJointOriginR ? dom.addJointOriginR.value : '0';
        const oP = dom.addJointOriginP ? dom.addJointOriginP.value : '0';
        const oY = dom.addJointOriginYaw ? dom.addJointOriginYaw.value : '0';
        origin.setAttribute('xyz', ox + ' ' + oy + ' ' + oz);
        origin.setAttribute('rpy', oR + ' ' + oP + ' ' + oY);
        jointEl.appendChild(origin);

        // Axis
        const axis = urdfDoc.createElement('axis');
        const ax = dom.addJointAxisX ? dom.addJointAxisX.value : '0';
        const ay = dom.addJointAxisY ? dom.addJointAxisY.value : '0';
        const az = dom.addJointAxisZ ? dom.addJointAxisZ.value : '1';
        axis.setAttribute('xyz', ax + ' ' + ay + ' ' + az);
        jointEl.appendChild(axis);

        // Limit
        const limit = urdfDoc.createElement('limit');
        limit.setAttribute('lower', dom.addJointLimitLower ? dom.addJointLimitLower.value : '0');
        limit.setAttribute('upper', dom.addJointLimitUpper ? dom.addJointLimitUpper.value : '0');
        limit.setAttribute('effort', dom.addJointLimitEffort ? dom.addJointLimitEffort.value : '100');
        limit.setAttribute('velocity', dom.addJointLimitVelocity ? dom.addJointLimitVelocity.value : '1.0');
        jointEl.appendChild(limit);

        robot.appendChild(jointEl);

        closeAllModals();
        renderTree();
        renderSVG();
        fitView();
        updateStatusCounts();
        selectElement('joint', name, jointEl);
        fireURDFChanged();
        showToast('Joint "' + name + '" added', 'success');
    }

    // ========== DELETE ==========

    function openDeleteModal() {
        if (!selectedElement) {
            showToast('No element selected', 'warning');
            return;
        }
        if (!dom.deleteModal) return;

        const nameEl = dom.deleteModal.querySelector('.confirm-item-name');
        const msgEl = dom.deleteModal.querySelector('.confirm-message');
        const warnEl = dom.deleteModal.querySelector('.confirm-warning');

        if (nameEl) nameEl.textContent = selectedElement.name;
        if (msgEl) msgEl.textContent = 'Delete ' + selectedElement.type + ':';

        // Warn about children
        if (warnEl) {
            if (selectedElement.type === 'link') {
                const childJoints = getAllJoints().filter(j => {
                    const pEl = j.querySelector('parent');
                    return pEl && pEl.getAttribute('link') === selectedElement.name;
                });
                if (childJoints.length > 0) {
                    warnEl.textContent = 'This will also remove ' + childJoints.length +
                        ' child joint(s) and their descendant links.';
                    warnEl.classList.remove('hidden');
                } else {
                    warnEl.textContent = '';
                    warnEl.classList.add('hidden');
                }
            } else {
                const jData = extractJointData(selectedElement.xmlEl);
                warnEl.textContent = 'Child link "' + jData.child + '" will become disconnected.';
                warnEl.classList.remove('hidden');
            }
        }

        showModal(dom.deleteModal);
    }

    function confirmDelete() {
        if (!selectedElement || !selectedElement.xmlEl || !urdfDoc) {
            closeAllModals();
            return;
        }

        pushUndo('Delete ' + selectedElement.type + ' "' + selectedElement.name + '"');

        if (selectedElement.type === 'link') {
            deleteLinkRecursive(selectedElement.name);
        } else {
            // Remove the joint element
            const robot = urdfDoc.querySelector('robot');
            if (robot && selectedElement.xmlEl.parentNode === robot) {
                robot.removeChild(selectedElement.xmlEl);
            }
        }

        closeAllModals();
        clearSelection();
        renderTree();
        renderSVG();
        fitView();
        updateStatusCounts();
        fireURDFChanged();
        showToast('Deleted successfully', 'success');
    }

    function deleteLinkRecursive(linkName) {
        const robot = urdfDoc.querySelector('robot');
        if (!robot) return;

        // Find all joints where this link is the parent
        const childJoints = getAllJoints().filter(j => {
            const pEl = j.querySelector('parent');
            return pEl && pEl.getAttribute('link') === linkName;
        });

        // For each child joint, recursively delete its child link
        childJoints.forEach(j => {
            const cEl = j.querySelector('child');
            if (cEl) {
                deleteLinkRecursive(cEl.getAttribute('link'));
            }
            if (j.parentNode === robot) robot.removeChild(j);
        });

        // Also remove any joints where this link is the child
        getAllJoints().filter(j => {
            const cEl = j.querySelector('child');
            return cEl && cEl.getAttribute('link') === linkName;
        }).forEach(j => {
            if (j.parentNode === robot) robot.removeChild(j);
        });

        // Remove the link itself
        const linkEl = getLinkByName(linkName);
        if (linkEl && linkEl.parentNode === robot) {
            robot.removeChild(linkEl);
        }
    }

    // ========== MODAL HELPERS ==========

    function showModal(modalEl) {
        if (modalEl) modalEl.classList.add('visible');
    }

    function closeAllModals() {
        document.querySelectorAll('.modal-overlay').forEach(m => m.classList.remove('visible'));
    }

    // ========== SAVE ==========

    function openSaveModal() {
        if (!dom.saveModal) return;
        if (dom.saveFilename) dom.saveFilename.value = currentFilename;
        showModal(dom.saveModal);
    }

    async function confirmSave() {
        const filename = dom.saveFilename ? dom.saveFilename.value.trim() : currentFilename;
        if (!filename) {
            showToast('Filename is required', 'error');
            return;
        }

        const content = serializeURDF();
        if (!content) {
            showToast('No URDF content to save', 'error');
            return;
        }

        try {
            const resp = await fetch('/api/urdf', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filename, content }),
            });
            if (!resp.ok) {
                const errData = await resp.json().catch(() => ({}));
                throw new Error(errData.detail || 'Save failed with status ' + resp.status);
            }
            currentFilename = filename;
            markClean();
            updateSavedTime();
            closeAllModals();
            showToast('Saved "' + filename + '"', 'success');
        } catch (e) {
            showToast('Save error: ' + e.message, 'error');
        }
    }

    function updateSavedTime() {
        if (dom.statusSavedTime) {
            const now = new Date();
            dom.statusSavedTime.textContent = 'Saved ' + now.toLocaleTimeString();
        }
    }

    // ========== LOAD ==========

    function openLoadModal() {
        if (!dom.loadModal) return;
        if (dom.loadFileList) dom.loadFileList.innerHTML = '<div class="file-list-empty">Loading...</div>';
        showModal(dom.loadModal);
        fetchSavedFiles();
    }

    async function fetchSavedFiles() {
        try {
            const resp = await fetch('/api/saved');
            if (!resp.ok) throw new Error('Failed to fetch file list');
            const data = await resp.json();
            const files = data.files || [];
            renderFileList(files);
        } catch (e) {
            if (dom.loadFileList) {
                dom.loadFileList.innerHTML = '<div class="file-list-empty">Error loading files: ' +
                    escapeHtml(e.message) + '</div>';
            }
        }
    }

    function renderFileList(files) {
        if (!dom.loadFileList) return;
        dom.loadFileList.innerHTML = '';

        if (files.length === 0) {
            dom.loadFileList.innerHTML = '<div class="file-list-empty">No saved URDF files found</div>';
            return;
        }

        const list = document.createElement('div');
        list.classList.add('file-list');

        files.forEach(file => {
            const item = document.createElement('div');
            item.classList.add('file-list-item');

            const nameSpan = document.createElement('span');
            nameSpan.classList.add('file-name');
            nameSpan.textContent = file.name;

            const dateSpan = document.createElement('span');
            dateSpan.classList.add('file-date');
            dateSpan.textContent = file.modified || '';

            item.appendChild(nameSpan);
            item.appendChild(dateSpan);

            item.addEventListener('click', () => {
                list.querySelectorAll('.file-list-item.selected').forEach(i => i.classList.remove('selected'));
                item.classList.add('selected');
            });

            item.addEventListener('dblclick', () => {
                loadFile(file.name);
            });

            list.appendChild(item);
        });

        dom.loadFileList.appendChild(list);
    }

    async function confirmLoad() {
        const selected = dom.loadFileList ? dom.loadFileList.querySelector('.file-list-item.selected .file-name') : null;
        if (!selected) {
            showToast('Select a file to load', 'warning');
            return;
        }
        await loadFile(selected.textContent);
    }

    async function loadFile(filename) {
        try {
            const resp = await fetch('/api/urdf?filename=' + encodeURIComponent(filename));
            if (!resp.ok) throw new Error('Failed to load file');
            const data = await resp.json();
            parseURDF(data.content);
            currentFilename = data.filename || filename;
            undoStack = [];
            markClean();
            renderTree();
            renderSVG();
            fitView();
            clearSelection();
            closeAllModals();
            showToast('Loaded "' + currentFilename + '"', 'success');
        } catch (e) {
            showToast('Load error: ' + e.message, 'error');
        }
    }

    // ========== EXPORT ==========

    function exportURDF() {
        const content = serializeURDF();
        if (!content) {
            showToast('No URDF content to export', 'warning');
            return;
        }

        const blob = new Blob([content], { type: 'application/xml' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = currentFilename || 'robot.urdf';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        showToast('Exported "' + a.download + '"', 'success');
    }

    // ========== FETCH INITIAL URDF ==========

    async function fetchInitialURDF() {
        try {
            const resp = await fetch('/api/urdf');
            if (!resp.ok) throw new Error('Status ' + resp.status);
            const data = await resp.json();
            if (data.content) {
                parseURDF(data.content);
                currentFilename = data.filename || 'robot.urdf';
                renderTree();
                renderSVG();
                fitView();
                setConnectionStatus(true);
                showToast('URDF loaded: ' + currentFilename, 'info');
            } else {
                setConnectionStatus(true);
                showToast('Connected. No URDF file found - start by adding links.', 'info');
            }
        } catch (e) {
            setConnectionStatus(false);
            showToast('Backend connection failed: ' + e.message, 'warning');
        }
        updateFileStatus();
    }

    // ========== MESH LIST ==========

    async function fetchMeshList() {
        try {
            const resp = await fetch('/api/meshes');
            if (!resp.ok) return;
            const data = await resp.json();
            meshListCache = data.meshes || [];

            // Update dropdown if modal is open
            if (dom.addLinkMeshFile && dom.addLinkModal && dom.addLinkModal.classList.contains('visible')) {
                const currentVal = dom.addLinkMeshFile.value;
                dom.addLinkMeshFile.innerHTML = '<option value="">(none - use custom path)</option>';
                meshListCache.forEach(m => {
                    const opt = document.createElement('option');
                    opt.value = m.path || m.name;
                    opt.textContent = m.name + (m.size_bytes ? ' (' + formatBytes(m.size_bytes) + ')' : '');
                    if (opt.value === currentVal) opt.selected = true;
                    dom.addLinkMeshFile.appendChild(opt);
                });
            }
        } catch (e) {
            // silently fail
        }
    }

    // ========== CONNECTION STATUS ==========

    function setConnectionStatus(connected) {
        isConnected = connected;
        if (dom.statusConnectionDot) {
            dom.statusConnectionDot.classList.toggle('disconnected', !connected);
        }
    }

    function startHealthPolling() {
        if (healthInterval) clearInterval(healthInterval);
        healthInterval = setInterval(async () => {
            try {
                const resp = await fetch('/api/status', { method: 'GET' });
                setConnectionStatus(resp.ok);
            } catch (e) {
                setConnectionStatus(false);
            }
        }, 5000);
    }

    // ========== STATUS BAR ==========

    function updateStatusCounts() {
        const links = getAllLinks();
        const joints = getAllJoints();
        if (dom.statusLinksCount) dom.statusLinksCount.textContent = links.length;
        if (dom.statusJointsCount) dom.statusJointsCount.textContent = joints.length;
    }

    // ========== TOAST NOTIFICATIONS ==========

    function showToast(message, type) {
        type = type || 'info';
        let container = $('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            document.body.appendChild(container);
        }

        const toast = document.createElement('div');
        toast.classList.add('toast', 'toast-' + type);

        const iconSpan = document.createElement('span');
        iconSpan.classList.add('toast-icon');
        const icons = {
            success: '\u2713',
            error: '\u2717',
            warning: '\u26A0',
            info: '\u2139',
        };
        iconSpan.textContent = icons[type] || icons.info;

        const msgSpan = document.createElement('span');
        msgSpan.classList.add('toast-message');
        msgSpan.textContent = message;

        toast.appendChild(iconSpan);
        toast.appendChild(msgSpan);
        container.appendChild(toast);

        // Auto-remove after 3 seconds
        setTimeout(() => {
            toast.classList.add('removing');
            setTimeout(() => {
                if (toast.parentNode) toast.parentNode.removeChild(toast);
            }, 300);
        }, 3000);
    }

    // ========== UTILITY FUNCTIONS ==========

    /**
     * Update or create a <gazebo reference="linkName"> block with ambient/diffuse
     * material matching the user-chosen color.  This ensures Gazebo shows the
     * chosen color when the URDF is converted to SDF.
     */
    function updateGazeboMaterial(linkName, rgb) {
        if (!urdfDoc) return;
        const robot = urdfDoc.querySelector('robot');
        if (!robot) return;

        // Find existing <gazebo reference="linkName">
        let gazeboEl = null;
        const allGazebo = robot.querySelectorAll('gazebo');
        for (const g of allGazebo) {
            if (g.getAttribute('reference') === linkName) {
                gazeboEl = g;
                break;
            }
        }

        // Create if missing
        if (!gazeboEl) {
            gazeboEl = urdfDoc.createElement('gazebo');
            gazeboEl.setAttribute('reference', linkName);
            robot.appendChild(gazeboEl);
        }

        // Ensure <visual> child
        let gVis = gazeboEl.querySelector('visual');
        if (!gVis) {
            gVis = urdfDoc.createElement('visual');
            gazeboEl.appendChild(gVis);
        }

        // Ensure <material> child
        let gMat = gVis.querySelector('material');
        if (!gMat) {
            gMat = urdfDoc.createElement('material');
            gVis.appendChild(gMat);
        }

        const colorStr = rgb[0].toFixed(4) + ' ' + rgb[1].toFixed(4) + ' ' + rgb[2].toFixed(4) + ' 1';

        // Set <ambient> and <diffuse>
        let ambient = gMat.querySelector('ambient');
        if (!ambient) {
            ambient = urdfDoc.createElement('ambient');
            gMat.appendChild(ambient);
        }
        ambient.textContent = colorStr;

        let diffuse = gMat.querySelector('diffuse');
        if (!diffuse) {
            diffuse = urdfDoc.createElement('diffuse');
            gMat.appendChild(diffuse);
        }
        diffuse.textContent = colorStr;
    }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function roundNum(n, decimals) {
        decimals = decimals || 6;
        return parseFloat((Number(n) || 0).toFixed(decimals));
    }

    function rgbaToHex(r, g, b) {
        const toHex = (c) => {
            const hex = Math.round(Math.max(0, Math.min(1, c)) * 255).toString(16);
            return hex.length === 1 ? '0' + hex : hex;
        };
        return '#' + toHex(r) + toHex(g) + toHex(b);
    }

    function hexToRgba(hex) {
        hex = hex.replace('#', '');
        const r = parseInt(hex.substring(0, 2), 16) / 255;
        const g = parseInt(hex.substring(2, 4), 16) / 255;
        const b = parseInt(hex.substring(4, 6), 16) / 255;
        return [r, g, b, 1.0];
    }

    function formatBytes(bytes) {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    }

    // ========== SPAWN IN GAZEBO ==========

    async function spawnInGazebo() {
        const content = serializeURDF();
        if (!content) {
            showToast('No URDF content to spawn', 'warning');
            return;
        }

        showToast('Spawning model in Gazebo...', 'info');

        try {
            const resp = await fetch('/api/spawn', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ urdf_content: content }),
            });
            const data = await resp.json();
            if (data.status === 'ok') {
                showToast('Model spawned in Gazebo!', 'success');
            } else {
                showToast('Spawn issue: ' + (data.message || 'Unknown'), 'warning');
            }
        } catch (e) {
            showToast('Spawn error: ' + e.message, 'error');
        }
    }

    // ========== VALIDATE URDF ==========

    async function validateURDF() {
        const content = serializeURDF();
        if (!content) {
            showToast('No URDF content to validate', 'warning');
            return;
        }

        if (dom.validateResults) {
            dom.validateResults.innerHTML = '<div style="text-align:center;color:var(--text-muted);padding:20px;">Running validation...</div>';
        }
        showModal(dom.validateModal);

        try {
            const resp = await fetch('/api/validate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ content }),
            });
            const data = await resp.json();
            renderValidationResults(data);
        } catch (e) {
            if (dom.validateResults) {
                dom.validateResults.innerHTML = '<div style="color:var(--danger);padding:10px;">Validation failed: ' +
                    escapeHtml(e.message) + '</div>';
            }
        }
    }

    function renderValidationResults(data) {
        if (!dom.validateResults) return;
        dom.validateResults.innerHTML = '';

        // Status badge
        const statusDiv = document.createElement('div');
        statusDiv.style.cssText = 'display:flex;align-items:center;gap:10px;margin-bottom:16px;padding:12px;border-radius:6px;';
        if (data.valid) {
            statusDiv.style.background = 'var(--success-bg)';
            statusDiv.style.border = '1px solid #2a5a2a';
            statusDiv.innerHTML = '<span style="font-size:24px;color:var(--success);">&#10003;</span>' +
                '<span style="font-size:15px;font-weight:700;color:var(--success);">URDF is valid</span>';
        } else {
            statusDiv.style.background = 'var(--danger-bg)';
            statusDiv.style.border = '1px solid #5a2020';
            statusDiv.innerHTML = '<span style="font-size:24px;color:var(--danger);">&#10007;</span>' +
                '<span style="font-size:15px;font-weight:700;color:var(--danger);">URDF has errors</span>';
        }
        dom.validateResults.appendChild(statusDiv);

        // Stats
        const statsDiv = document.createElement('div');
        statsDiv.style.cssText = 'display:flex;gap:20px;margin-bottom:14px;padding:8px 12px;background:var(--bg-tertiary);border-radius:4px;';
        const stats = data.stats || {};
        statsDiv.innerHTML =
            '<span style="color:var(--text-secondary);font-size:12px;">Links: <b style="color:var(--accent);">' + (stats.links || 0) + '</b></span>' +
            '<span style="color:var(--text-secondary);font-size:12px;">Joints: <b style="color:var(--accent);">' + (stats.joints || 0) + '</b></span>' +
            '<span style="color:var(--text-secondary);font-size:12px;">Meshes: <b style="color:var(--accent);">' + (stats.meshes || 0) + '</b></span>';
        dom.validateResults.appendChild(statsDiv);

        // Errors
        if (data.errors && data.errors.length > 0) {
            const errSection = document.createElement('div');
            errSection.style.marginBottom = '10px';
            errSection.innerHTML = '<div style="font-size:11px;color:var(--danger);font-weight:700;margin-bottom:6px;text-transform:uppercase;letter-spacing:1px;">Errors</div>';
            data.errors.forEach(err => {
                const item = document.createElement('div');
                item.style.cssText = 'padding:6px 10px;margin-bottom:4px;background:var(--danger-bg);border-radius:3px;font-size:12px;color:var(--danger);border-left:3px solid var(--danger);';
                item.textContent = err;
                errSection.appendChild(item);
            });
            dom.validateResults.appendChild(errSection);
        }

        // Warnings
        if (data.warnings && data.warnings.length > 0) {
            const warnSection = document.createElement('div');
            warnSection.innerHTML = '<div style="font-size:11px;color:var(--warning);font-weight:700;margin-bottom:6px;text-transform:uppercase;letter-spacing:1px;">Warnings</div>';
            data.warnings.forEach(w => {
                const item = document.createElement('div');
                item.style.cssText = 'padding:6px 10px;margin-bottom:4px;background:var(--warning-bg);border-radius:3px;font-size:12px;color:var(--warning);border-left:3px solid var(--warning);';
                item.textContent = w;
                warnSection.appendChild(item);
            });
            dom.validateResults.appendChild(warnSection);
        }
    }

    // ========== IMPORT / MERGE URDF ==========

    function openImportModal() {
        if (!dom.importModal) return;

        // Reset form
        if (dom.importMethod) dom.importMethod.value = 'file';
        if (dom.importFileInput) dom.importFileInput.value = '';
        if (dom.importPasteInput) dom.importPasteInput.value = '';
        if (dom.importPrefix) dom.importPrefix.value = '';
        if (dom.importOffsetX) dom.importOffsetX.value = '0';
        if (dom.importOffsetY) dom.importOffsetY.value = '0';
        if (dom.importOffsetZ) dom.importOffsetZ.value = '0';

        // Toggle file/paste sections
        toggleImportMethod();

        // Populate attach link dropdown
        if (dom.importAttachLink) {
            dom.importAttachLink.innerHTML = '<option value="">(no attachment - merge only)</option>';
            getLinkNames().forEach(name => {
                const opt = document.createElement('option');
                opt.value = name;
                opt.textContent = name;
                dom.importAttachLink.appendChild(opt);
            });
        }

        showModal(dom.importModal);
    }

    function toggleImportMethod() {
        const method = dom.importMethod ? dom.importMethod.value : 'file';
        const fileSection = $('import-file-section');
        const pasteSection = $('import-paste-section');
        const stlSection = $('import-stl-section');
        const prefixRow = $('import-prefix-row');
        if (fileSection) fileSection.classList.toggle('hidden', method !== 'file');
        if (pasteSection) pasteSection.classList.toggle('hidden', method !== 'paste');
        if (stlSection) stlSection.classList.toggle('hidden', method !== 'stl');
        // Hide prefix for STL mode (single link, name set explicitly)
        if (prefixRow) prefixRow.classList.toggle('hidden', method === 'stl');
    }

    async function confirmImport() {
        let xmlString = '';
        const method = dom.importMethod ? dom.importMethod.value : 'file';

        // --- STL upload mode: upload mesh file, then create a new link ---
        if (method === 'stl') {
            await confirmImportSTL();
            return;
        }

        if (method === 'file') {
            const fileInput = dom.importFileInput;
            if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
                showToast('Please select a URDF file', 'error');
                return;
            }
            xmlString = await fileInput.files[0].text();
        } else {
            xmlString = dom.importPasteInput ? dom.importPasteInput.value.trim() : '';
        }

        if (!xmlString) {
            showToast('No URDF content provided', 'error');
            return;
        }

        // Parse the import URDF
        let importDoc;
        try {
            importDoc = parseXMLString(xmlString);
        } catch (e) {
            showToast('Import XML parse error: ' + e.message, 'error');
            return;
        }

        const importRobot = importDoc.querySelector('robot');
        if (!importRobot) {
            showToast('Imported XML has no <robot> root element', 'error');
            return;
        }

        // Ensure we have a target document
        if (!urdfDoc) {
            urdfDoc = parseXMLString('<?xml version="1.0"?><robot name="robot"></robot>');
        }

        pushUndo('Merge URDF');

        const robot = urdfDoc.querySelector('robot');
        const prefix = dom.importPrefix ? dom.importPrefix.value.trim() : '';
        const attachLink = dom.importAttachLink ? dom.importAttachLink.value : '';

        // Collect existing names to check for duplicates
        const existingLinks = new Set(getLinkNames());
        const existingJoints = new Set(getJointNames());

        let importedLinks = 0;
        let importedJoints = 0;
        let importFirstLink = null;

        // Import all links
        const importLinks = importRobot.querySelectorAll(':scope > link');
        importLinks.forEach(linkEl => {
            const origName = linkEl.getAttribute('name');
            const newName = prefix + origName;

            if (existingLinks.has(newName)) {
                return; // skip duplicates
            }

            // Clone into our document
            const newLink = urdfDoc.importNode(linkEl, true);
            newLink.setAttribute('name', newName);

            // Update mesh filenames to use vehicle_arm_sim package path if they use other packages
            newLink.querySelectorAll('mesh').forEach(mesh => {
                const fname = mesh.getAttribute('filename') || '';
                if (fname.startsWith('package://') && !fname.startsWith('package://vehicle_arm_sim/')) {
                    // Keep as-is; user can fix paths later
                }
            });

            robot.appendChild(newLink);
            existingLinks.add(newName);
            importedLinks++;

            if (!importFirstLink) importFirstLink = newName;
        });

        // Import all joints (updating parent/child references)
        const importJoints = importRobot.querySelectorAll(':scope > joint');
        importJoints.forEach(jointEl => {
            const origName = jointEl.getAttribute('name');
            const newName = prefix + origName;

            if (existingJoints.has(newName)) {
                return; // skip duplicates
            }

            const newJoint = urdfDoc.importNode(jointEl, true);
            newJoint.setAttribute('name', newName);

            // Update parent/child link references
            const parentEl = newJoint.querySelector('parent');
            if (parentEl) {
                parentEl.setAttribute('link', prefix + parentEl.getAttribute('link'));
            }
            const childEl = newJoint.querySelector('child');
            if (childEl) {
                childEl.setAttribute('link', prefix + childEl.getAttribute('link'));
            }

            robot.appendChild(newJoint);
            existingJoints.add(newName);
            importedJoints++;
        });

        // Create attachment joint if requested
        if (attachLink && importFirstLink && getLinkByName(attachLink)) {
            // Find the root link of the imported model (link not referenced as child by any imported joint)
            const importChildNames = new Set();
            importJoints.forEach(j => {
                const c = j.querySelector('child');
                if (c) importChildNames.add(prefix + c.getAttribute('link'));
            });

            let importRoot = importFirstLink;
            importLinks.forEach(l => {
                const n = prefix + l.getAttribute('name');
                if (!importChildNames.has(n)) {
                    importRoot = n;
                }
            });

            const attachJoint = urdfDoc.createElement('joint');
            attachJoint.setAttribute('name', attachLink + '_to_' + importRoot + '_joint');
            attachJoint.setAttribute('type', 'fixed');

            const pTag = urdfDoc.createElement('parent');
            pTag.setAttribute('link', attachLink);
            attachJoint.appendChild(pTag);

            const cTag = urdfDoc.createElement('child');
            cTag.setAttribute('link', importRoot);
            attachJoint.appendChild(cTag);

            const origin = urdfDoc.createElement('origin');
            const ox = dom.importOffsetX ? dom.importOffsetX.value : '0';
            const oy = dom.importOffsetY ? dom.importOffsetY.value : '0';
            const oz = dom.importOffsetZ ? dom.importOffsetZ.value : '0';
            origin.setAttribute('xyz', ox + ' ' + oy + ' ' + oz);
            origin.setAttribute('rpy', '0 0 0');
            attachJoint.appendChild(origin);

            robot.appendChild(attachJoint);
        }

        closeAllModals();
        renderTree();
        renderSVG();
        fitView();
        updateStatusCounts();
        fireURDFChanged();
        showToast('Merged ' + importedLinks + ' links, ' + importedJoints + ' joints', 'success');
    }

    /**
     * Import an STL mesh as a new link: upload the file to the server,
     * then create a new <link> with visual/collision referencing the uploaded mesh,
     * and optionally create a fixed joint to attach it to a parent link.
     */
    async function confirmImportSTL() {
        const stlInput = $('import-stl-input');
        if (!stlInput || !stlInput.files || stlInput.files.length === 0) {
            showToast('Please select an STL/mesh file', 'error');
            return;
        }

        const file = stlInput.files[0];
        const linkNameInput = $('import-stl-link-name');
        let linkName = linkNameInput ? linkNameInput.value.trim() : '';
        if (!linkName) {
            // Auto-generate from filename: "my_part.stl" → "my_part"
            linkName = file.name.replace(/\.[^.]+$/, '').replace(/[^a-zA-Z0-9_-]/g, '_');
        }

        // Check for duplicate link name
        if (getLinkNames().includes(linkName)) {
            showToast('Link name "' + linkName + '" already exists. Choose a different name.', 'error');
            return;
        }

        // Upload mesh file to server
        showToast('Uploading mesh file...', 'info');
        const formData = new FormData();
        formData.append('file', file);

        let uploadResult;
        try {
            const resp = await fetch('/api/meshes/upload', {
                method: 'POST',
                body: formData,
            });
            if (!resp.ok) {
                const err = await resp.json().catch(() => ({ detail: resp.statusText }));
                showToast('Upload failed: ' + (err.detail || resp.statusText), 'error');
                return;
            }
            uploadResult = await resp.json();
        } catch (e) {
            showToast('Upload error: ' + e.message, 'error');
            return;
        }

        const packagePath = uploadResult.package_path;

        // Read scale and mass
        const sx = parseFloat($('import-stl-scale-x')?.value) || 1.0;
        const sy = parseFloat($('import-stl-scale-y')?.value) || 1.0;
        const sz = parseFloat($('import-stl-scale-z')?.value) || 1.0;
        const mass = parseFloat($('import-stl-mass')?.value) || 1.0;

        // Ensure we have a target document
        if (!urdfDoc) {
            urdfDoc = parseXMLString('<?xml version="1.0"?><robot name="robot"></robot>');
        }

        pushUndo('Import STL "' + file.name + '"');

        const robot = urdfDoc.querySelector('robot');

        // Create the link element
        const newLink = urdfDoc.createElement('link');
        newLink.setAttribute('name', linkName);

        // Inertial
        const inertial = urdfDoc.createElement('inertial');
        const massEl = urdfDoc.createElement('mass');
        massEl.setAttribute('value', String(mass));
        inertial.appendChild(massEl);
        const inertia = urdfDoc.createElement('inertia');
        const iVal = roundNum(mass * 0.01); // simple approximation
        inertia.setAttribute('ixx', iVal);
        inertia.setAttribute('ixy', '0');
        inertia.setAttribute('ixz', '0');
        inertia.setAttribute('iyy', iVal);
        inertia.setAttribute('iyz', '0');
        inertia.setAttribute('izz', iVal);
        inertial.appendChild(inertia);
        newLink.appendChild(inertial);

        // Visual
        const visual = urdfDoc.createElement('visual');
        const visOrigin = urdfDoc.createElement('origin');
        visOrigin.setAttribute('xyz', '0 0 0');
        visOrigin.setAttribute('rpy', '0 0 0');
        visual.appendChild(visOrigin);
        const visGeom = urdfDoc.createElement('geometry');
        const visMesh = urdfDoc.createElement('mesh');
        visMesh.setAttribute('filename', packagePath);
        if (sx !== 1.0 || sy !== 1.0 || sz !== 1.0) {
            visMesh.setAttribute('scale', sx + ' ' + sy + ' ' + sz);
        }
        visGeom.appendChild(visMesh);
        visual.appendChild(visGeom);
        newLink.appendChild(visual);

        // Collision (same mesh)
        const collision = urdfDoc.createElement('collision');
        const colOrigin = urdfDoc.createElement('origin');
        colOrigin.setAttribute('xyz', '0 0 0');
        colOrigin.setAttribute('rpy', '0 0 0');
        collision.appendChild(colOrigin);
        const colGeom = urdfDoc.createElement('geometry');
        const colMesh = urdfDoc.createElement('mesh');
        colMesh.setAttribute('filename', packagePath);
        if (sx !== 1.0 || sy !== 1.0 || sz !== 1.0) {
            colMesh.setAttribute('scale', sx + ' ' + sy + ' ' + sz);
        }
        colGeom.appendChild(colMesh);
        collision.appendChild(colGeom);
        newLink.appendChild(collision);

        robot.appendChild(newLink);

        // Create attachment joint if parent link is specified
        const attachLink = dom.importAttachLink ? dom.importAttachLink.value : '';
        if (attachLink && getLinkByName(attachLink)) {
            const jointName = attachLink + '_to_' + linkName + '_joint';
            const joint = urdfDoc.createElement('joint');
            joint.setAttribute('name', jointName);
            joint.setAttribute('type', 'fixed');

            const pTag = urdfDoc.createElement('parent');
            pTag.setAttribute('link', attachLink);
            joint.appendChild(pTag);

            const cTag = urdfDoc.createElement('child');
            cTag.setAttribute('link', linkName);
            joint.appendChild(cTag);

            const origin = urdfDoc.createElement('origin');
            const ox = $('import-offset-x') ? $('import-offset-x').value : '0';
            const oy = $('import-offset-y') ? $('import-offset-y').value : '0';
            const oz = $('import-offset-z') ? $('import-offset-z').value : '0';
            origin.setAttribute('xyz', ox + ' ' + oy + ' ' + oz);
            origin.setAttribute('rpy', '0 0 0');
            joint.appendChild(origin);

            robot.appendChild(joint);
        }

        closeAllModals();
        renderTree();
        renderSVG();
        fitView();
        updateStatusCounts();
        fireURDFChanged();
        fetchMeshList(); // Refresh mesh dropdown
        showToast('Added link "' + linkName + '" with mesh ' + file.name, 'success');
    }

    // ========== IMPORT URDF PACKAGE (COMPREHENSIVE) ==========

    let ipkgAnalysis = null;  // Cached analysis result

    function openImportPkgModal() {
        ipkgAnalysis = null;
        const modal = $('import-pkg-modal');
        if (!modal) return;

        // Reset UI
        const step1 = $('ipkg-step1');
        const step2 = $('ipkg-step2');
        if (step1) step1.classList.remove('hidden');
        if (step2) step2.classList.add('hidden');
        const mergeBtn = $('ipkg-merge-btn');
        const backBtn = $('ipkg-back-btn');
        if (mergeBtn) mergeBtn.style.display = 'none';
        if (backBtn) backBtn.style.display = 'none';

        // Set default path to the package source root
        const pathInput = $('ipkg-path');
        if (pathInput && !pathInput.value) {
            pathInput.value = '';
        }

        // Load initial directory browse
        ipkgBrowseDir('');

        modal.classList.add('visible');
    }

    async function ipkgBrowseDir(dir) {
        const listEl = $('ipkg-browse-list');
        const pathEl = $('ipkg-browse-path');
        if (!listEl) return;

        try {
            const url = '/api/browse-urdf' + (dir ? '?directory=' + encodeURIComponent(dir) : '');
            const resp = await fetch(url);
            if (!resp.ok) {
                listEl.innerHTML = '<div style="color:var(--error);padding:8px;">Failed to browse</div>';
                return;
            }
            const data = await resp.json();

            if (pathEl) pathEl.textContent = data.directory;

            let html = '';
            // Parent directory link
            if (data.parent) {
                html += '<div class="ipkg-item ipkg-dir" data-path="' + escapeHtml(data.parent) + '">';
                html += '&#128193; .. (parent)</div>';
            }
            // Directories
            for (const item of data.items) {
                if (item.type === 'directory') {
                    const badge = item.has_urdf ? ' <span style="color:var(--success);font-size:10px;">URDF</span>' : '';
                    const meshBadge = item.has_mesh ? ' <span style="color:var(--accent);font-size:10px;">STL</span>' : '';
                    html += '<div class="ipkg-item ipkg-dir" data-path="' + escapeHtml(item.path) + '">';
                    html += '&#128193; ' + escapeHtml(item.name) + badge + meshBadge + '</div>';
                } else {
                    html += '<div class="ipkg-item ipkg-file" data-path="' + escapeHtml(item.path) + '">';
                    html += '&#128196; ' + escapeHtml(item.name) + '</div>';
                }
            }
            if (!data.items.length) {
                html += '<div style="color:var(--text-muted);padding:8px;font-style:italic;">No URDF files or folders found</div>';
            }
            listEl.innerHTML = html;

            // Bind click handlers
            listEl.querySelectorAll('.ipkg-dir').forEach(el => {
                el.addEventListener('click', () => ipkgBrowseDir(el.dataset.path));
            });
            listEl.querySelectorAll('.ipkg-file').forEach(el => {
                el.addEventListener('click', () => {
                    const pathInput = $('ipkg-path');
                    if (pathInput) pathInput.value = el.dataset.path;
                });
            });
        } catch (e) {
            listEl.innerHTML = '<div style="color:var(--error);padding:8px;">Browse error: ' + e.message + '</div>';
        }
    }

    async function ipkgAnalyze() {
        const pathInput = $('ipkg-path');
        if (!pathInput || !pathInput.value.trim()) {
            showToast('Enter a URDF file path', 'error');
            return;
        }

        const analyzeBtn = $('ipkg-analyze-btn');
        if (analyzeBtn) {
            analyzeBtn.disabled = true;
            analyzeBtn.textContent = 'Analyzing...';
        }

        try {
            const resp = await fetch('/api/analyze-urdf', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ urdf_path: pathInput.value.trim() }),
            });

            if (!resp.ok) {
                const err = await resp.json().catch(() => ({ detail: resp.statusText }));
                showToast('Analysis failed: ' + (err.detail || resp.statusText), 'error');
                return;
            }

            ipkgAnalysis = await resp.json();
            ipkgShowResults();
        } catch (e) {
            showToast('Analysis error: ' + e.message, 'error');
        } finally {
            if (analyzeBtn) {
                analyzeBtn.disabled = false;
                analyzeBtn.textContent = '🔍 Analyze URDF';
            }
        }
    }

    function ipkgShowResults() {
        if (!ipkgAnalysis) return;
        const data = ipkgAnalysis;

        // Switch to step 2
        const step1 = $('ipkg-step1');
        const step2 = $('ipkg-step2');
        if (step1) step1.classList.add('hidden');
        if (step2) step2.classList.remove('hidden');

        const mergeBtn = $('ipkg-merge-btn');
        const backBtn = $('ipkg-back-btn');
        if (mergeBtn) mergeBtn.style.display = '';
        if (backBtn) backBtn.style.display = '';

        // Summary
        const summaryEl = $('ipkg-summary');
        if (summaryEl) {
            summaryEl.innerHTML =
                '<strong>Robot:</strong> ' + escapeHtml(data.robot_name) +
                ' &nbsp;|&nbsp; <strong>Links:</strong> ' + data.total_links +
                ' &nbsp;|&nbsp; <strong>Joints:</strong> ' + data.total_joints +
                ' &nbsp;|&nbsp; <strong>Meshes:</strong> ' + data.total_meshes +
                ' &nbsp;|&nbsp; <strong>Root:</strong> ' + escapeHtml(data.root_link);
        }

        // Warnings
        const warnEl = $('ipkg-warnings');
        if (warnEl) {
            if (data.warnings && data.warnings.length > 0) {
                let html = '<div style="background:var(--warn-bg, #332b00);border:1px solid var(--warn-border, #665500);border-radius:4px;padding:6px 10px;font-size:11px;">';
                html += '<strong style="color:#ffaa00;">⚠ Warnings:</strong><ul style="margin:4px 0 0 16px;padding:0;">';
                data.warnings.forEach(w => {
                    html += '<li style="color:#ffcc44;">' + escapeHtml(w) + '</li>';
                });
                html += '</ul></div>';
                warnEl.innerHTML = html;
            } else {
                warnEl.innerHTML = '<div style="color:var(--success);font-size:11px;">✓ No issues found</div>';
            }
        }

        // Tree visualization
        const treeEl = $('ipkg-tree-viz');
        if (treeEl && data.tree) {
            let treeText = '';
            function renderNode(node, indent, isLast) {
                const prefix = indent ? (isLast ? '└── ' : '├── ') : '';
                const jointInfo = node.joint ? ' [' + (node.joint_type || 'fixed') + ']' : '';
                treeText += indent + prefix + node.name + jointInfo + '\n';
                const childIndent = indent + (isLast ? '    ' : '│   ');
                if (node.children) {
                    node.children.forEach((child, i) => {
                        renderNode(child, childIndent, i === node.children.length - 1);
                    });
                }
            }
            renderNode(data.tree, '', true);
            treeEl.textContent = treeText;
        }

        // Mesh table
        const meshEl = $('ipkg-mesh-table');
        if (meshEl && data.meshes) {
            let html = '<table style="width:100%;border-collapse:collapse;font-size:11px;">';
            html += '<tr style="background:var(--bg-dark);"><th style="text-align:left;padding:3px 6px;">File</th><th>Size</th><th>Exists</th><th>Conflict</th></tr>';
            data.meshes.forEach(m => {
                const existIcon = m.exists ? '<span style="color:var(--success);">✓</span>' : '<span style="color:var(--error);">✗</span>';
                const conflictIcon = m.conflicts_with_main ? '<span style="color:#ffaa00;">⚠</span>' : '—';
                const sizeStr = m.exists ? (m.size_bytes / 1024).toFixed(1) + ' KB' : '—';
                html += '<tr style="border-bottom:1px solid var(--border);">';
                html += '<td style="padding:3px 6px;">' + escapeHtml(m.filename) + '</td>';
                html += '<td style="text-align:center;padding:3px;">' + sizeStr + '</td>';
                html += '<td style="text-align:center;padding:3px;">' + existIcon + '</td>';
                html += '<td style="text-align:center;padding:3px;">' + conflictIcon + '</td>';
                html += '</tr>';
            });
            html += '</table>';
            meshEl.innerHTML = html;
        }

        // Fill prefix suggestion
        const prefixInput = $('ipkg-prefix');
        if (prefixInput && data.suggested_prefix) {
            prefixInput.value = data.suggested_prefix;
        }

        // Fill attach-to dropdown with main URDF links
        const attachSelect = $('ipkg-attach-to');
        if (attachSelect && data.main_urdf_links) {
            attachSelect.innerHTML = '<option value="">(no attachment — floating)</option>';
            data.main_urdf_links.forEach(lname => {
                const opt = document.createElement('option');
                opt.value = lname;
                opt.textContent = lname;
                attachSelect.appendChild(opt);
            });
        }
    }

    function ipkgBack() {
        const step1 = $('ipkg-step1');
        const step2 = $('ipkg-step2');
        if (step1) step1.classList.remove('hidden');
        if (step2) step2.classList.add('hidden');
        const mergeBtn = $('ipkg-merge-btn');
        const backBtn = $('ipkg-back-btn');
        if (mergeBtn) mergeBtn.style.display = 'none';
        if (backBtn) backBtn.style.display = 'none';
    }

    async function ipkgMerge() {
        if (!ipkgAnalysis) {
            showToast('Please analyze a URDF first', 'error');
            return;
        }

        const prefix = ($('ipkg-prefix') ? $('ipkg-prefix').value : '');
        const attachTo = ($('ipkg-attach-to') ? $('ipkg-attach-to').value : '');
        const ox = $('ipkg-offset-x') ? $('ipkg-offset-x').value : '0';
        const oy = $('ipkg-offset-y') ? $('ipkg-offset-y').value : '0';
        const oz = $('ipkg-offset-z') ? $('ipkg-offset-z').value : '0';
        const or_ = $('ipkg-offset-r') ? $('ipkg-offset-r').value : '0';
        const op = $('ipkg-offset-p') ? $('ipkg-offset-p').value : '0';
        const oyaw = $('ipkg-offset-yaw') ? $('ipkg-offset-yaw').value : '0';

        const mergeBtn = $('ipkg-merge-btn');
        if (mergeBtn) {
            mergeBtn.disabled = true;
            mergeBtn.textContent = 'Merging...';
        }

        try {
            const mainXml = serializeURDF();
            const resp = await fetch('/api/merge-urdf', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    urdf_path: ipkgAnalysis.urdf_path,
                    main_urdf_xml: mainXml,
                    prefix: prefix,
                    attach_to: attachTo,
                    offset_xyz: ox + ' ' + oy + ' ' + oz,
                    offset_rpy: or_ + ' ' + op + ' ' + oyaw,
                }),
            });

            if (!resp.ok) {
                const err = await resp.json().catch(() => ({ detail: resp.statusText }));
                showToast('Merge failed: ' + (err.detail || resp.statusText), 'error');
                return;
            }

            const result = await resp.json();

            if (result.status !== 'ok' || !result.xml) {
                showToast('Merge returned no XML', 'error');
                return;
            }

            // Load the merged URDF into the editor
            pushUndo('Import URDF package');
            urdfDoc = parseXMLString(result.xml);

            closeAllModals();
            renderTree();
            renderSVG();
            fitView();
            updateStatusCounts();
            fireURDFChanged();
            fetchMeshList();

            showToast(
                'Merged ' + result.imported_links + ' links, ' +
                result.imported_joints + ' joints, ' +
                result.copied_meshes.length + ' meshes copied',
                'success'
            );
        } catch (e) {
            showToast('Merge error: ' + e.message, 'error');
        } finally {
            if (mergeBtn) {
                mergeBtn.disabled = false;
                mergeBtn.textContent = '⊕ Merge Into Model';
            }
        }
    }

    // ========== ENVIRONMENT OBJECTS ==========

    let envSelectedFolder = null;  // { path, meshes, textures }
    let envSelectedMesh = null;    // filename

    function openEnvObjectsModal() {
        const modal = $('env-objects-modal');
        if (!modal) return;
        envSelectedFolder = null;
        envSelectedMesh = null;
        const noSel = $('env-no-selection');
        const form = $('env-selected-form');
        if (noSel) noSel.style.display = '';
        if (form) form.style.display = 'none';
        envBrowseDir('');
        envRefreshSpawnedList();
        envPopulateAttachTo();
        modal.classList.add('visible');
    }

    async function envBrowseDir(dir) {
        const listEl = $('env-browse-list');
        const pathEl = $('env-browse-path');
        if (!listEl) return;

        try {
            const url = '/api/browse-mesh-folders' + (dir ? '?directory=' + encodeURIComponent(dir) : '');
            const resp = await fetch(url);
            if (!resp.ok) {
                listEl.innerHTML = '<div style="color:var(--error);padding:8px;">Failed to browse</div>';
                return;
            }
            const data = await resp.json();
            if (pathEl) pathEl.textContent = data.directory;

            let html = '';
            // Parent directory
            if (data.parent) {
                html += '<div class="ipkg-item ipkg-dir" data-action="browse" data-idx="-1">';
                html += '&#128193; .. (parent)</div>';
            }

            // Store item data for click handlers (avoids escaping issues in HTML attributes)
            const itemDataStore = [];
            if (data.parent) itemDataStore.push({ action: 'browse', path: data.parent });

            for (const item of data.items) {
                const idx = itemDataStore.length;
                if (item.type === 'directory') {
                    if (item.is_mesh_folder) {
                        itemDataStore.push({ action: 'select-folder', path: item.path, meshes: item.meshes, textures: item.textures });
                        const meshList = item.meshes.join(', ');
                        html += '<div class="ipkg-item ipkg-file" data-action="select-folder" data-idx="' + idx + '"'
                            + ' style="background:rgba(126,207,126,0.12);border-left:3px solid var(--success);">';
                        html += '&#128230; ' + escapeHtml(item.name);
                        html += ' <span style="color:var(--success);font-size:10px;font-weight:bold;">MESH</span>';
                        html += ' <span style="color:var(--text-muted);font-size:10px;">(' + escapeHtml(meshList) + ')</span></div>';
                    } else {
                        itemDataStore.push({ action: 'browse', path: item.path });
                        html += '<div class="ipkg-item ipkg-dir" data-action="browse" data-idx="' + idx + '">';
                        html += '&#128193; ' + escapeHtml(item.name) + '</div>';
                    }
                } else if (item.type === 'mesh') {
                    itemDataStore.push({ action: 'select-loose', path: item.path, filename: item.name });
                    html += '<div class="ipkg-item ipkg-file" data-action="select-loose" data-idx="' + idx + '">';
                    html += '&#128900; ' + escapeHtml(item.name) + ' <span style="color:var(--text-muted);font-size:10px;">(' + item.size_kb + ' KB)</span></div>';
                }
            }

            if (!data.items.length) {
                html += '<div style="color:var(--text-muted);padding:8px;font-style:italic;">No mesh files or folders found</div>';
            }
            listEl.innerHTML = html;

            // Bind click handlers using the data store (no HTML attribute escaping issues)
            listEl.querySelectorAll('[data-idx]').forEach(el => {
                const idx = parseInt(el.dataset.idx);
                if (idx < 0 && data.parent) {
                    // Parent directory
                    el.addEventListener('click', () => envBrowseDir(data.parent));
                    return;
                }
                const d = itemDataStore[idx];
                if (!d) return;
                if (d.action === 'browse') {
                    el.addEventListener('click', () => envBrowseDir(d.path));
                } else if (d.action === 'select-folder') {
                    el.addEventListener('click', () => envSelectFolder(d.path, d.meshes, d.textures));
                } else if (d.action === 'select-loose') {
                    const folder = d.path.substring(0, d.path.lastIndexOf('/'));
                    el.addEventListener('click', () => envSelectFolder(folder, [d.filename], []));
                }
            });
        } catch (e) {
            listEl.innerHTML = '<div style="color:var(--error);padding:8px;">Browse error: ' + e.message + '</div>';
        }
    }

    function envSelectFolder(folderPath, meshes, textures) {
        envSelectedFolder = { path: folderPath, meshes: meshes, textures: textures };
        const noSel = $('env-no-selection');
        const form = $('env-selected-form');
        const infoEl = $('env-selected-info');
        if (!form || !infoEl) return;
        if (noSel) noSel.style.display = 'none';
        form.style.display = '';

        // Auto-select the first mesh file
        envSelectedMesh = meshes[0] || '';
        const folderName = folderPath.split('/').pop();

        let html = '<strong>Folder:</strong> ' + escapeHtml(folderName) + '<br>';
        if (meshes.length > 1) {
            html += '<strong>Mesh file:</strong> <select id="env-mesh-select" style="font-size:11px;background:var(--bg-dark);color:var(--text);border:1px solid var(--border);border-radius:3px;padding:2px;">';
            meshes.forEach(m => {
                html += '<option value="' + escapeHtml(m) + '">' + escapeHtml(m) + '</option>';
            });
            html += '</select><br>';
        } else {
            html += '<strong>Mesh:</strong> ' + escapeHtml(envSelectedMesh) + '<br>';
        }
        if (textures.length > 0) {
            html += '<strong>Textures:</strong> ' + escapeHtml(textures.join(', '));
        }
        infoEl.innerHTML = html;

        // Default name from folder name
        const nameInput = $('env-obj-name');
        if (nameInput) nameInput.value = folderName.replace(/[^a-zA-Z0-9_]/g, '_').toLowerCase();

        // Refresh attach-to with current links
        envPopulateAttachTo();

        // Bind mesh select change if multiple
        const meshSelect = $('env-mesh-select');
        if (meshSelect) {
            meshSelect.addEventListener('change', () => { envSelectedMesh = meshSelect.value; });
        }
    }

    async function envSpawnObject() {
        if (!envSelectedFolder || !envSelectedMesh) {
            showToast('Select a mesh folder first', 'error');
            return;
        }

        const name = ($('env-obj-name') ? $('env-obj-name').value.trim() : '') || 'env_object';
        const x = parseFloat($('env-pos-x')?.value) || 0;
        const y = parseFloat($('env-pos-y')?.value) || 0;
        const z = parseFloat($('env-pos-z')?.value) || 0;
        const roll = parseFloat($('env-rot-r')?.value) || 0;
        const pitch = parseFloat($('env-rot-p')?.value) || 0;
        const yaw = parseFloat($('env-rot-y')?.value) || 0;
        const scale = parseFloat($('env-scale')?.value) || 1.0;

        const spawnBtn = $('env-spawn-btn');
        if (spawnBtn) { spawnBtn.disabled = true; spawnBtn.textContent = 'Spawning...'; }

        try {
            const resp = await fetch('/api/spawn-env-object', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    mesh_folder: envSelectedFolder.path,
                    mesh_file: envSelectedMesh,
                    name: name,
                    x: x, y: y, z: z,
                    roll: roll, pitch: pitch, yaw: yaw,
                    scale: scale,
                }),
            });

            if (!resp.ok) {
                const err = await resp.json().catch(() => ({ detail: resp.statusText }));
                showToast('Spawn failed: ' + (err.detail || resp.statusText), 'error');
                return;
            }

            const result = await resp.json();
            showToast('Spawned "' + result.name + '" in Gazebo', 'success');
            envRefreshSpawnedList();
        } catch (e) {
            showToast('Spawn error: ' + e.message, 'error');
        } finally {
            if (spawnBtn) { spawnBtn.disabled = false; spawnBtn.textContent = '▶ Spawn in Gazebo'; }
        }
    }

    async function envRefreshSpawnedList() {
        const listEl = $('env-spawned-list');
        if (!listEl) return;

        try {
            const resp = await fetch('/api/env-objects');
            const data = await resp.json();

            if (!data.objects || data.objects.length === 0) {
                listEl.innerHTML = '<div style="color:var(--text-muted);font-style:italic;">No environment objects spawned yet</div>';
                return;
            }

            let html = '<table style="width:100%;border-collapse:collapse;font-size:11px;">';
            html += '<tr style="background:var(--bg-dark);"><th style="text-align:left;padding:3px 6px;">Name</th><th>Position</th><th>Scale</th><th>Actions</th></tr>';
            data.objects.forEach(obj => {
                html += '<tr style="border-bottom:1px solid var(--border);">';
                html += '<td style="padding:3px 6px;">' + escapeHtml(obj.name) + '</td>';
                html += '<td style="text-align:center;padding:3px;">' + obj.x.toFixed(1) + ', ' + obj.y.toFixed(1) + ', ' + obj.z.toFixed(1) + '</td>';
                html += '<td style="text-align:center;padding:3px;">' + obj.scale + '</td>';
                html += '<td style="text-align:center;padding:3px;">'
                    + '<button class="env-remove-btn" data-name="' + escapeHtml(obj.name) + '" '
                    + 'style="background:var(--error);color:white;border:none;border-radius:3px;padding:2px 8px;cursor:pointer;font-size:10px;">&#10005; Remove</button></td>';
                html += '</tr>';
            });
            html += '</table>';
            listEl.innerHTML = html;

            // Bind remove buttons
            listEl.querySelectorAll('.env-remove-btn').forEach(btn => {
                btn.addEventListener('click', async () => {
                    const objName = btn.dataset.name;
                    try {
                        await fetch('/api/env-objects/' + encodeURIComponent(objName), { method: 'DELETE' });
                        showToast('Removed "' + objName + '"', 'success');
                        envRefreshSpawnedList();
                    } catch (e) {
                        showToast('Remove failed: ' + e.message, 'error');
                    }
                });
            });
        } catch (e) {
            listEl.innerHTML = '<div style="color:var(--error);">Failed to load: ' + e.message + '</div>';
        }
    }

    function envPopulateAttachTo() {
        const sel = $('env-attach-to');
        if (!sel) return;
        const linkNames = getLinkNames();
        sel.innerHTML = '<option value="">(floating — no parent)</option>';
        linkNames.forEach(n => {
            const opt = document.createElement('option');
            opt.value = n;
            opt.textContent = n;
            sel.appendChild(opt);
        });
    }

    async function envAddToURDF() {
        if (!envSelectedFolder || !envSelectedMesh) {
            showToast('Select a mesh folder first', 'error');
            return;
        }

        const name = ($('env-obj-name') ? $('env-obj-name').value.trim() : '') || 'env_object';
        const x = $('env-pos-x')?.value || '0';
        const y = $('env-pos-y')?.value || '0';
        const z = $('env-pos-z')?.value || '0';
        const roll = $('env-rot-r')?.value || '0';
        const pitch = $('env-rot-p')?.value || '0';
        const yaw = $('env-rot-y')?.value || '0';
        const scale = $('env-scale')?.value || '1';
        const attachTo = $('env-attach-to')?.value || '';

        // Check duplicate link name
        if (getLinkByName(name)) {
            showToast('A link named "' + name + '" already exists. Change the name.', 'error');
            return;
        }

        const addBtn = $('env-add-urdf-btn');
        if (addBtn) { addBtn.disabled = true; addBtn.textContent = 'Copying meshes...'; }

        try {
            // Step 1: Copy mesh files to meshes/ directory
            const copyResp = await fetch('/api/meshes/copy-folder', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    source_folder: envSelectedFolder.path,
                    mesh_file: envSelectedMesh,
                }),
            });

            if (!copyResp.ok) {
                const err = await copyResp.json().catch(() => ({ detail: copyResp.statusText }));
                showToast('Copy failed: ' + (err.detail || copyResp.statusText), 'error');
                return;
            }

            const copyResult = await copyResp.json();
            const meshPackagePath = copyResult.mesh_package_path;

            if (addBtn) addBtn.textContent = 'Creating link...';

            // Step 2: Create URDF link + joint
            if (!urdfDoc) {
                urdfDoc = parseXMLString('<?xml version="1.0"?><robot name="robot"></robot>');
            }

            pushUndo('Add env object "' + name + '"');
            const robot = urdfDoc.querySelector('robot');

            // Create link
            const linkEl = urdfDoc.createElement('link');
            linkEl.setAttribute('name', name);

            // Visual with mesh
            const visual = urdfDoc.createElement('visual');
            const geometry = urdfDoc.createElement('geometry');
            const meshEl = urdfDoc.createElement('mesh');
            meshEl.setAttribute('filename', meshPackagePath);
            meshEl.setAttribute('scale', scale + ' ' + scale + ' ' + scale);
            geometry.appendChild(meshEl);
            visual.appendChild(geometry);

            // Material
            const material = urdfDoc.createElement('material');
            material.setAttribute('name', name + '_material');
            const colorEl = urdfDoc.createElement('color');
            colorEl.setAttribute('rgba', '0.7 0.7 0.7 1.0');
            material.appendChild(colorEl);
            visual.appendChild(material);

            linkEl.appendChild(visual);

            // Collision (mesh)
            const collision = urdfDoc.createElement('collision');
            const collGeom = geometry.cloneNode(true);
            collision.appendChild(collGeom);
            linkEl.appendChild(collision);

            // Inertial (lightweight static object)
            const inertial = urdfDoc.createElement('inertial');
            const mass = urdfDoc.createElement('mass');
            mass.setAttribute('value', '0.1');
            inertial.appendChild(mass);
            const inertia = urdfDoc.createElement('inertia');
            inertia.setAttribute('ixx', '0.0001');
            inertia.setAttribute('ixy', '0');
            inertia.setAttribute('ixz', '0');
            inertia.setAttribute('iyy', '0.0001');
            inertia.setAttribute('iyz', '0');
            inertia.setAttribute('izz', '0.0001');
            inertial.appendChild(inertia);
            linkEl.appendChild(inertial);

            robot.appendChild(linkEl);

            // Create fixed joint if attaching to a parent
            if (attachTo && getLinkByName(attachTo)) {
                const jointEl = urdfDoc.createElement('joint');
                jointEl.setAttribute('name', attachTo + '_to_' + name + '_joint');
                jointEl.setAttribute('type', 'fixed');

                const parentTag = urdfDoc.createElement('parent');
                parentTag.setAttribute('link', attachTo);
                jointEl.appendChild(parentTag);

                const childTag = urdfDoc.createElement('child');
                childTag.setAttribute('link', name);
                jointEl.appendChild(childTag);

                const origin = urdfDoc.createElement('origin');
                origin.setAttribute('xyz', x + ' ' + y + ' ' + z);
                origin.setAttribute('rpy', roll + ' ' + pitch + ' ' + yaw);
                jointEl.appendChild(origin);

                robot.appendChild(jointEl);
            }

            // Refresh everything
            closeAllModals();
            renderTree();
            renderSVG();
            fitView();
            updateStatusCounts();
            selectElement('link', name, linkEl);
            fireURDFChanged();
            fetchMeshList();

            const copiedCount = copyResult.copied.length;
            const skippedCount = copyResult.skipped.length;
            showToast(
                'Added "' + name + '" to URDF (' + copiedCount + ' files copied' +
                (skippedCount > 0 ? ', ' + skippedCount + ' already existed' : '') + ')',
                'success'
            );
        } catch (e) {
            showToast('Add to URDF error: ' + e.message, 'error');
        } finally {
            if (addBtn) { addBtn.disabled = false; addBtn.textContent = '+ Add to URDF'; }
        }
    }

    // ========== INTERACTIVE FEATURES ==========

    function fireURDFChanged() {
        const xml = serializeURDF();
        document.dispatchEvent(new CustomEvent('urdf-changed', { detail: { urdf: xml } }));
        if (window.viewer3d) {
            try {
                window.viewer3d.loadURDF(xml);
            } catch (e) {
                // viewer3d may not be ready
            }
        }
    }

    async function autoSyncToGazebo() {
        if (dom.statusGazeboDot) dom.statusGazeboDot.className = 'syncing';
        if (dom.statusGazeboText) dom.statusGazeboText.textContent = 'Syncing…';
        try {
            const xml = serializeURDF();
            await fetch('/api/urdf', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ urdf: xml, filename: 'auto_sync.urdf' }),
            });
            await fetch('/api/spawn', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: 'vehicle_arm', urdf_file: 'auto_sync.urdf' }),
            });
            if (dom.statusGazeboDot) dom.statusGazeboDot.className = 'connected';
            if (dom.statusGazeboText) dom.statusGazeboText.textContent = 'Synced';
        } catch (err) {
            if (dom.statusGazeboDot) dom.statusGazeboDot.className = '';
            if (dom.statusGazeboText) dom.statusGazeboText.textContent = 'Sync failed';
            showToast('Auto-sync failed: ' + err.message, 'error');
        }
    }

    let activeConnectorGroup = null;  // currently tooltip-ed connector

    function showConnectorTooltip(clientX, clientY, connGroup) {
        const tooltip = $('connector-tooltip');
        if (!tooltip) return;
        activeConnectorGroup = connGroup;

        // Position near click, but relative to preview panel
        const previewPanel = $('preview-panel');
        const panelRect = previewPanel ? previewPanel.getBoundingClientRect() : { left: 0, top: 0 };
        tooltip.style.left = (clientX - panelRect.left + 8) + 'px';
        tooltip.style.top = (clientY - panelRect.top + 8) + 'px';
        tooltip.classList.add('visible');
    }

    function hideConnectorTooltip() {
        const tooltip = $('connector-tooltip');
        if (tooltip) tooltip.classList.remove('visible');
        activeConnectorGroup = null;
    }

    function detachConnectorJoint() {
        if (!activeConnectorGroup || !urdfDoc) {
            hideConnectorTooltip();
            return;
        }
        const jointName = activeConnectorGroup.getAttribute('data-joint-name');
        hideConnectorTooltip();

        if (!jointName) {
            showToast('No joint found for this connector', 'warning');
            return;
        }

        const robot = urdfDoc.querySelector('robot');
        const jointEl = getJointByName(jointName);
        if (!jointEl || !robot) {
            showToast('Joint not found: ' + jointName, 'error');
            return;
        }

        pushUndo('Detach joint "' + jointName + '"');
        robot.removeChild(jointEl);

        renderTree();
        renderSVG();
        updateStatusCounts();
        fireURDFChanged();
        showToast('Joint "' + jointName + '" removed (nodes preserved)', 'info');
    }

    function startConnectionDraw(e, ownerType, ownerName, portSide) {
        e.stopPropagation();
        e.preventDefault();
        isDrawingConnection = true;
        connectionStart = { type: ownerType, name: ownerName, port: portSide };

        // Create temp SVG line
        if (dom.previewSvg) {
            tempConnectionLine = document.createElementNS(SVG_NS, 'line');
            tempConnectionLine.setAttribute('class', 'svg-temp-connection');

            // Get port position
            const key = ownerType + ':' + ownerName;
            const nodeData = layoutCache ? layoutCache.nodes.get(key) : null;
            if (nodeData) {
                const py = portSide === 'bottom' ? nodeData.y + nodeData.height : nodeData.y;
                tempConnectionLine.setAttribute('x1', nodeData.cx);
                tempConnectionLine.setAttribute('y1', py);
                tempConnectionLine.setAttribute('x2', nodeData.cx);
                tempConnectionLine.setAttribute('y2', py);
            }
            dom.previewSvg.appendChild(tempConnectionLine);
        }
    }

    function updateConnectionDraw(e) {
        if (!isDrawingConnection || !tempConnectionLine || !dom.svgContainer) return;
        const svgPt = clientToSVG(e.clientX, e.clientY);
        tempConnectionLine.setAttribute('x2', svgPt.x);
        tempConnectionLine.setAttribute('y2', svgPt.y);
    }

    function endConnectionDraw(e) {
        if (!isDrawingConnection) return;
        isDrawingConnection = false;

        // Remove temp line
        if (tempConnectionLine && tempConnectionLine.parentNode) {
            tempConnectionLine.parentNode.removeChild(tempConnectionLine);
        }
        tempConnectionLine = null;

        if (!connectionStart) return;

        // Find what we dropped on — look for a port element
        const target = e.target;
        const isPort = target && target.classList && target.classList.contains('svg-port');
        if (!isPort) {
            connectionStart = null;
            return;
        }

        const targetType = target.getAttribute('data-owner-type');
        const targetName = target.getAttribute('data-owner');
        const targetPort = target.getAttribute('data-port');

        // Validate: we need a link-to-link connection (which creates a joint)
        const srcName = connectionStart.name;
        const srcType = connectionStart.type;

        if (srcType === targetType && srcType === 'link' && srcName !== targetName) {
            // Create a new joint between the two links
            const jointName = srcName + '_to_' + targetName + '_joint';
            if (getJointByName(jointName)) {
                showToast('Joint already exists: ' + jointName, 'warning');
                connectionStart = null;
                return;
            }

            // Determine parent/child: source bottom port = parent, target top port = child
            let parentLink = srcName;
            let childLink = targetName;
            if (connectionStart.port === 'top') {
                parentLink = targetName;
                childLink = srcName;
            }

            pushUndo('Create joint "' + jointName + '"');
            const robot = urdfDoc.querySelector('robot');
            const jointEl = urdfDoc.createElement('joint');
            jointEl.setAttribute('name', jointName);
            jointEl.setAttribute('type', 'fixed');

            const parentTag = urdfDoc.createElement('parent');
            parentTag.setAttribute('link', parentLink);
            jointEl.appendChild(parentTag);

            const childTag = urdfDoc.createElement('child');
            childTag.setAttribute('link', childLink);
            jointEl.appendChild(childTag);

            const origin = urdfDoc.createElement('origin');
            origin.setAttribute('xyz', '0 0 0');
            origin.setAttribute('rpy', '0 0 0');
            jointEl.appendChild(origin);

            robot.appendChild(jointEl);

            renderTree();
            renderSVG();
            updateStatusCounts();
            fireURDFChanged();
            showToast('Created joint "' + jointName + '"', 'success');
        } else {
            showToast('Connect link-to-link to create a joint', 'info');
        }

        connectionStart = null;
    }

    // ========== 3D TRANSFORM MATH HELPERS ==========
    // Homogeneous 4×4 matrix utilities for child-joint compensation.
    // Matrices are stored as flat Float64Array[16] in column-major order.

    function mat4Identity() {
        return new Float64Array([1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1]);
    }

    /** Build a 4×4 transform from xyz translation and rpy (roll, pitch, yaw) in ZYX order. */
    function mat4FromXyzRpy(x, y, z, roll, pitch, yaw) {
        const cr = Math.cos(roll),  sr = Math.sin(roll);
        const cp = Math.cos(pitch), sp = Math.sin(pitch);
        const cy = Math.cos(yaw),   sy = Math.sin(yaw);

        // Rotation = Rz(yaw) * Ry(pitch) * Rx(roll)  — URDF convention
        const m = new Float64Array(16);
        m[0]  = cy * cp;
        m[1]  = sy * cp;
        m[2]  = -sp;
        m[3]  = 0;
        m[4]  = cy * sp * sr - sy * cr;
        m[5]  = sy * sp * sr + cy * cr;
        m[6]  = cp * sr;
        m[7]  = 0;
        m[8]  = cy * sp * cr + sy * sr;
        m[9]  = sy * sp * cr - cy * sr;
        m[10] = cp * cr;
        m[11] = 0;
        m[12] = x;
        m[13] = y;
        m[14] = z;
        m[15] = 1;
        return m;
    }

    /** Multiply two 4×4 column-major matrices: result = A * B */
    function mat4Multiply(A, B) {
        const R = new Float64Array(16);
        for (let col = 0; col < 4; col++) {
            for (let row = 0; row < 4; row++) {
                R[col * 4 + row] =
                    A[0 * 4 + row] * B[col * 4 + 0] +
                    A[1 * 4 + row] * B[col * 4 + 1] +
                    A[2 * 4 + row] * B[col * 4 + 2] +
                    A[3 * 4 + row] * B[col * 4 + 3];
            }
        }
        return R;
    }

    /** Invert a rigid-body 4×4 matrix (rotation + translation only). */
    function mat4InvertRigid(M) {
        // For a rigid transform [R t; 0 1], inverse is [R^T  -R^T*t; 0 1]
        const inv = new Float64Array(16);
        // Transpose the 3×3 rotation part
        inv[0] = M[0]; inv[1] = M[4]; inv[2]  = M[8];
        inv[4] = M[1]; inv[5] = M[5]; inv[6]  = M[9];
        inv[8] = M[2]; inv[9] = M[6]; inv[10] = M[10];
        // Translation: -R^T * t
        const tx = M[12], ty = M[13], tz = M[14];
        inv[12] = -(inv[0]*tx + inv[4]*ty + inv[8]*tz);
        inv[13] = -(inv[1]*tx + inv[5]*ty + inv[9]*tz);
        inv[14] = -(inv[2]*tx + inv[6]*ty + inv[10]*tz);
        inv[3] = 0; inv[7] = 0; inv[11] = 0; inv[15] = 1;
        return inv;
    }

    /** Extract xyz translation from a 4×4 matrix. */
    function mat4GetXyz(M) {
        return [M[12], M[13], M[14]];
    }

    /** Extract roll-pitch-yaw (ZYX convention) from a 4×4 rotation matrix. */
    function mat4GetRpy(M) {
        // Follows the ZYX Euler angle extraction (same as URDF).
        const sp = -M[2];
        let pitch, roll, yaw;
        if (Math.abs(sp) >= 0.99999) {
            // Gimbal lock
            pitch = Math.sign(sp) * Math.PI / 2;
            yaw = Math.atan2(-M[4], M[5]);
            roll = 0;
        } else {
            pitch = Math.asin(sp);
            roll  = Math.atan2(M[6], M[10]);
            yaw   = Math.atan2(M[1], M[0]);
        }
        return [roll, pitch, yaw];
    }

    /** Read an origin element's xyz+rpy and return a 4×4 matrix. */
    function originToMat4(originEl) {
        if (!originEl) return mat4Identity();
        const xyz = splitXYZ(getAttr(originEl, 'xyz', '0 0 0'));
        const rpy = splitXYZ(getAttr(originEl, 'rpy', '0 0 0'));
        return mat4FromXyzRpy(xyz[0], xyz[1], xyz[2], rpy[0], rpy[1], rpy[2]);
    }

    /** Write xyz+rpy from a 4×4 matrix back to an origin element. */
    function mat4ToOrigin(M, originEl) {
        const xyz = mat4GetXyz(M);
        const rpy = mat4GetRpy(M);
        originEl.setAttribute('xyz',
            roundNum(xyz[0]) + ' ' + roundNum(xyz[1]) + ' ' + roundNum(xyz[2]));
        originEl.setAttribute('rpy',
            roundNum(rpy[0]) + ' ' + roundNum(rpy[1]) + ' ' + roundNum(rpy[2]));
    }

    // ========== 3D TRANSFORM HANDLER ==========

    /** Track whether we've pushed an undo for the current drag session. */
    let transformUndoPushed = false;

    /** Snapshot of mesh scales at the start of a scale-gizmo drag.
     *  { vis: [sx, sy, sz], col: [sx, sy, sz] } or null if not a scale drag. */
    let scaleAtDragStart = null;

    /**
     * When true, dragging a parent link in the 3D viewer moves all children
     * along with it (joint origins are relative, so children follow naturally).
     * When false, children stay at their world positions and their joint
     * origins are compensated to cancel the parent's movement.
     */
    let childrenFollowParent = true;

    function setChildrenFollowParent(follow) {
        childrenFollowParent = !!follow;
        // Update toolbar toggle if present
        const btn = $('btn-children-follow');
        if (btn) {
            btn.classList.toggle('active', childrenFollowParent);
            btn.title = childrenFollowParent
                ? 'Children follow parent (click to lock children in place)'
                : 'Children stay in place (click to make children follow)';
        }
    }

    function handleViewer3dTransform(event) {
        const detail = event.detail;
        console.log('[urdf_editor] viewer3d-transform received:', detail);
        if (!detail || !detail.linkName || !urdfDoc) return;

        const { linkName, position, rotation, scale, mode } = detail;

        // --- Scale mode: update <mesh scale="..."> on the link itself ---
        if (mode === 'scale' && scale) {
            const linkEl = getLinkByName(linkName);
            if (!linkEl) return;

            // Push undo once per drag session
            if (!transformUndoPushed) {
                pushUndo('3D scale "' + linkName + '"', 'viewer-3d');
                transformUndoPushed = true;
            }

            // Use the snapshot from drag start so we don't compound each frame
            const origVis = scaleAtDragStart ? scaleAtDragStart.vis : [1, 1, 1];
            const origCol = scaleAtDragStart ? scaleAtDragStart.col : [1, 1, 1];

            // Update visual mesh scale
            const visMesh = linkEl.querySelector('visual geometry mesh');
            if (visMesh) {
                visMesh.setAttribute('scale',
                    roundNum(origVis[0] * scale.x) + ' ' +
                    roundNum(origVis[1] * scale.y) + ' ' +
                    roundNum(origVis[2] * scale.z));
            }

            // Update collision mesh scale too
            const colMesh = linkEl.querySelector('collision geometry mesh');
            if (colMesh) {
                colMesh.setAttribute('scale',
                    roundNum(origCol[0] * scale.x) + ' ' +
                    roundNum(origCol[1] * scale.y) + ' ' +
                    roundNum(origCol[2] * scale.z));
            }

            // Update property panel live
            if (selectedElement && selectedElement.xmlEl) {
                showProperties(selectedElement);
            }
            isDirty = true;
            return;
        }

        // --- Translate / Rotate mode: update joint origin ---

        // Find the joint that positions this link (where this link is the child)
        const joints = getAllJoints();
        let targetJoint = null;
        for (const j of joints) {
            const cEl = j.querySelector('child');
            if (cEl && cEl.getAttribute('link') === linkName) {
                targetJoint = j;
                break;
            }
        }

        if (!targetJoint) {
            // Root/orphan link — no joint to update, but allow the 3D move
            // so the user can position it and then use "Attach to Parent".
            // The position is preserved in the Object3D and read by
            // openAttachOrphanModal via getLinkTransform().
            // Don't rebuild 3D or mark dirty — the visual position is enough.
            return;
        }

        // Push undo ONCE at the start of a drag session
        if (!transformUndoPushed) {
            pushUndo('3D transform "' + linkName + '"', 'viewer-3d');
            transformUndoPushed = true;
        }

        // --- Record old transform as a 4×4 matrix ---
        let origin = targetJoint.querySelector('origin');
        const oldMat = originToMat4(origin);

        // --- Build new transform from gizmo values ---
        const nx = position ? position.x : 0;
        const ny = position ? position.y : 0;
        const nz = position ? position.z : 0;
        const nr = rotation ? rotation.r : 0;
        const np = rotation ? rotation.p : 0;
        const nw = rotation ? rotation.y : 0;
        const newMat = mat4FromXyzRpy(nx, ny, nz, nr, np, nw);

        // --- Write the new origin for the moved link's parent joint ---
        if (!origin) {
            origin = urdfDoc.createElement('origin');
            targetJoint.appendChild(origin);
        }
        if (position) {
            origin.setAttribute('xyz',
                roundNum(position.x) + ' ' + roundNum(position.y) + ' ' + roundNum(position.z));
        }
        if (rotation) {
            origin.setAttribute('rpy',
                roundNum(rotation.r) + ' ' + roundNum(rotation.p) + ' ' + roundNum(rotation.y));
        }

        // --- Child joint handling ---
        // Default: children follow the parent (joint origins are relative to
        // parent, so no compensation needed — children automatically move).
        // If childrenFollowParent is OFF, compensate child joints so they
        // maintain their world positions despite the parent moving.
        if (!childrenFollowParent) {
            const invNewMat = mat4InvertRigid(newMat);
            const compensationMat = mat4Multiply(invNewMat, oldMat);

            for (const j of joints) {
                const pEl = j.querySelector('parent');
                if (!pEl || pEl.getAttribute('link') !== linkName) continue;
                let childOrigin = j.querySelector('origin');
                if (!childOrigin) {
                    childOrigin = urdfDoc.createElement('origin');
                    childOrigin.setAttribute('xyz', '0 0 0');
                    childOrigin.setAttribute('rpy', '0 0 0');
                    j.appendChild(childOrigin);
                }
                const childOldMat = originToMat4(childOrigin);
                const childNewMat = mat4Multiply(compensationMat, childOldMat);
                mat4ToOrigin(childNewMat, childOrigin);
            }
        }

        // Update properties panel in real-time during drag.
        if (selectedElement && selectedElement.xmlEl) {
            showProperties(selectedElement);
        }

        // Mark dirty but don't re-render SVG during drag (too slow)
        isDirty = true;
    }

    function showContextMenu(clientX, clientY, type, name) {
        if (!dom.contextMenu) return;
        contextMenuTarget = { type, name };

        // Position menu, clamped to viewport
        const menuW = 200;
        const menuH = 340;
        const x = Math.min(clientX, window.innerWidth - menuW);
        const y = Math.min(clientY, window.innerHeight - menuH);
        dom.contextMenu.style.left = x + 'px';
        dom.contextMenu.style.top = y + 'px';

        const isMulti = selectedElements.length > 1;

        // Toggle visibility of type-specific items
        dom.contextMenu.querySelectorAll('.context-menu-item').forEach(item => {
            const action = item.dataset.action;
            if (action === 'add-child-link' && (type === 'joint' || isMulti)) {
                item.style.display = 'none';
            } else if (action === 'add-child-joint' && (type === 'joint' || isMulti)) {
                item.style.display = 'none';
            } else if (action === 'edit' && isMulti) {
                item.style.display = 'none';
            } else if (action === 'detach' && isMulti) {
                item.style.display = 'none';
            } else if (action === 'attach' && isMulti) {
                item.style.display = 'none';
            } else if (action === 'reparent' && isMulti) {
                item.style.display = 'none';
            } else if (action === 'select-children' && isMulti) {
                item.style.display = 'none';
            } else if (action === 'copy-children' && isMulti) {
                item.style.display = 'none';
            } else if (action === 'paste') {
                item.style.display = '';
                item.classList.toggle('disabled', clipboard.length === 0);
            } else {
                item.style.display = '';
            }
        });

        // Update labels for multi-select
        const dupItem = dom.contextMenu.querySelector('[data-action="duplicate"]');
        const delItem = dom.contextMenu.querySelector('[data-action="delete"]');
        const copyItem = dom.contextMenu.querySelector('[data-action="copy"]');
        if (dupItem) dupItem.innerHTML = isMulti ? '&#8916; Duplicate (' + selectedElements.length + ')' : '&#8916; Duplicate';
        if (delItem) delItem.innerHTML = isMulti ? '&#128465; Delete (' + selectedElements.length + ')' : '&#128465; Delete';
        if (copyItem) copyItem.innerHTML = isMulti ? '&#128203; Copy (' + selectedElements.length + ')' : '&#128203; Copy';

        dom.contextMenu.classList.add('visible');
    }

    function hideContextMenu() {
        if (dom.contextMenu) dom.contextMenu.classList.remove('visible');
        contextMenuTarget = null;
    }

    function handleContextAction(action) {
        // Some actions don't need contextMenuTarget
        if (action === 'paste' || action === 'select-all') {
            hideContextMenu();
            if (action === 'paste') handlePaste();
            else selectAll();
            return;
        }
        if (action === 'copy') {
            hideContextMenu();
            handleCopy();
            return;
        }
        if (action === 'select-children') {
            const t = contextMenuTarget;
            hideContextMenu();
            if (t) selectWithChildren(t.type, t.name);
            return;
        }
        if (action === 'copy-children') {
            const t = contextMenuTarget;
            hideContextMenu();
            if (t) copyWithChildren(t.type, t.name);
            return;
        }
        if (!contextMenuTarget) return;
        const { type, name } = contextMenuTarget;
        hideContextMenu();

        switch (action) {
            case 'edit':
                selectElement(type, name, null);
                break;
            case 'add-child-link':
                openAddLinkModal();
                // Pre-select the parent in the dropdown
                if (dom.addLinkParent) {
                    dom.addLinkParent.value = name;
                }
                break;
            case 'add-child-joint':
                openAddJointModal();
                // Pre-select the parent in the dropdown
                if (dom.addJointParent) {
                    dom.addJointParent.value = name;
                }
                break;
            case 'detach':
                handleDetach();
                break;
            case 'reparent':
                openReparentModal();
                break;
            case 'duplicate':
                handleDuplicate();
                break;
            case 'attach':
                if (type === 'link') {
                    openAttachOrphanModal(name);
                }
                break;
            case 'delete':
                if (selectedElements.length > 1) {
                    deleteSelected();
                } else {
                    selectElement(type, name, null);
                    openDeleteModal();
                }
                break;
            default:
                break;
        }
    }

    function startInlineRename(type, name) {
        if (!dom.previewSvg) return;
        const nodeGroup = dom.previewSvg.querySelector(
            'g[data-type="' + type + '"][data-name="' + name + '"]'
        );
        if (!nodeGroup) return;

        const textEl = nodeGroup.querySelector('text');
        if (!textEl) return;

        // Get text position from the existing text element
        const textX = parseFloat(textEl.getAttribute('x'));
        const textY = parseFloat(textEl.getAttribute('y'));
        const fontSize = 11;
        const inputW = type === 'link' ? LINK_W - 8 : JOINT_SIZE * 4;
        const inputH = 20;

        // Create foreignObject overlay
        const fo = document.createElementNS(SVG_NS, 'foreignObject');
        fo.setAttribute('x', textX - inputW / 2);
        fo.setAttribute('y', textY - inputH + 4);
        fo.setAttribute('width', inputW);
        fo.setAttribute('height', inputH);

        const input = document.createElement('input');
        input.type = 'text';
        input.value = name;
        input.style.cssText =
            'width:100%;height:100%;border:1px solid var(--accent);' +
            'background:var(--bg-primary);color:var(--text-primary);' +
            'font-size:' + fontSize + 'px;text-align:center;outline:none;' +
            'padding:0;margin:0;box-sizing:border-box;border-radius:2px;';

        fo.appendChild(input);
        nodeGroup.appendChild(fo);

        // Hide original label
        textEl.style.display = 'none';

        input.focus();
        input.select();

        function applyRename() {
            const newName = input.value.trim();
            // Clean up
            if (fo.parentNode) fo.parentNode.removeChild(fo);
            textEl.style.display = '';

            if (!newName || newName === name) return;

            // Check for duplicate names
            if (type === 'link' && getLinkByName(newName)) {
                showToast('Link "' + newName + '" already exists', 'error');
                return;
            }
            if (type === 'joint' && getJointByName(newName)) {
                showToast('Joint "' + newName + '" already exists', 'error');
                return;
            }

            pushUndo('Rename ' + type + ' "' + name + '" → "' + newName + '"');

            if (type === 'link') {
                // Rename the link element
                const linkEl = getLinkByName(name);
                if (linkEl) linkEl.setAttribute('name', newName);
                // Update all joints referencing this link
                getAllJoints().forEach(j => {
                    const pEl = j.querySelector('parent');
                    const cEl = j.querySelector('child');
                    if (pEl && pEl.getAttribute('link') === name) {
                        pEl.setAttribute('link', newName);
                    }
                    if (cEl && cEl.getAttribute('link') === name) {
                        cEl.setAttribute('link', newName);
                    }
                });
            } else {
                // Rename the joint element
                const jointEl = getJointByName(name);
                if (jointEl) jointEl.setAttribute('name', newName);
            }

            // Update selection if this was selected
            if (selectedElement && selectedElement.type === type && selectedElement.name === name) {
                selectedElement.name = newName;
                selectedElement.xmlEl = type === 'link' ? getLinkByName(newName) : getJointByName(newName);
            }
            // Update multi-select as well
            selectedElements.forEach(sel => {
                if (sel.type === type && sel.name === name) {
                    sel.name = newName;
                    sel.xmlEl = type === 'link' ? getLinkByName(newName) : getJointByName(newName);
                }
            });

            renderTree();
            renderSVG();
            fireURDFChanged();
        }

        let applied = false;
        input.addEventListener('blur', () => {
            if (!applied) { applied = true; applyRename(); }
        });
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                if (!applied) { applied = true; applyRename(); }
            } else if (e.key === 'Escape') {
                // Cancel — restore original
                if (fo.parentNode) fo.parentNode.removeChild(fo);
                textEl.style.display = '';
            }
        });
    }

    function handleDetach() {
        if (!contextMenuTarget || !urdfDoc) return;
        const { type, name } = contextMenuTarget;
        const robot = urdfDoc.querySelector('robot');
        if (!robot) return;

        pushUndo('Detach ' + type + ' "' + name + '"');

        if (type === 'link') {
            // Find the joint where this link is the child and remove that joint
            const joints = getAllJoints();
            for (let i = 0; i < joints.length; i++) {
                const cEl = joints[i].querySelector('child');
                if (cEl && cEl.getAttribute('link') === name) {
                    robot.removeChild(joints[i]);
                    break;
                }
            }
        } else {
            // It's a joint — just remove it
            const jointEl = getJointByName(name);
            if (jointEl && jointEl.parentNode === robot) {
                robot.removeChild(jointEl);
            }
        }

        renderTree();
        renderSVG();
        updateStatusCounts();
        fireURDFChanged();
        showToast('Detached "' + name + '"', 'info');
    }

    // ========== ORPHAN LINK DETECTION & ATTACHMENT ==========

    /**
     * Update the orphan warning banner visibility and content.
     */
    function updateOrphanWarning() {
        const banner = $('orphan-warning-banner');
        if (!banner) return;
        const { orphans } = getOrphanRootLinks();
        if (orphans.length > 0) {
            banner.classList.add('visible');
            const names = orphans.map(n => '"' + n + '"').join(', ');
            banner.innerHTML = '<span class="orphan-warn-icon">\u26A0</span> '
                + '<strong>' + orphans.length + ' orphan link' + (orphans.length > 1 ? 's' : '') + '</strong>'
                + ' not connected to main tree: ' + escapeHtml(names)
                + ' <button class="orphan-fix-btn" id="orphan-fix-all-btn">Fix All</button>';
            const fixBtn = banner.querySelector('#orphan-fix-all-btn');
            if (fixBtn) {
                fixBtn.addEventListener('click', () => {
                    // Auto-attach all orphans to the primary root link
                    const { primary, orphans: orph } = getOrphanRootLinks();
                    if (!primary || orph.length === 0) return;
                    pushUndo('Auto-attach ' + orph.length + ' orphan link(s)');
                    orph.forEach(orphanName => {
                        createAttachmentJoint(orphanName, primary, '0 0 0', '0 0 0');
                    });
                    renderTree();
                    renderSVG();
                    updateStatusCounts();
                    fireURDFChanged();
                    showToast('Attached ' + orph.length + ' orphan link(s) to "' + primary + '"', 'success');
                });
            }
        } else {
            banner.classList.remove('visible');
        }
    }

    /**
     * Create a fixed joint to attach an orphan link to a parent link.
     */
    function createAttachmentJoint(childLinkName, parentLinkName, xyz, rpy) {
        if (!urdfDoc) return;
        const robot = urdfDoc.querySelector('robot');
        if (!robot) return;

        const jointName = parentLinkName + '_to_' + childLinkName;
        // Check if joint already exists
        if (getJointByName(jointName)) return;

        const joint = urdfDoc.createElement('joint');
        joint.setAttribute('name', jointName);
        joint.setAttribute('type', 'fixed');

        const origin = urdfDoc.createElement('origin');
        origin.setAttribute('xyz', xyz || '0 0 0');
        origin.setAttribute('rpy', rpy || '0 0 0');
        joint.appendChild(origin);

        const parent = urdfDoc.createElement('parent');
        parent.setAttribute('link', parentLinkName);
        joint.appendChild(parent);

        const child = urdfDoc.createElement('child');
        child.setAttribute('link', childLinkName);
        joint.appendChild(child);

        robot.appendChild(joint);
    }

    /**
     * Open the "Attach Orphan" modal for a specific orphan link.
     */
    function openAttachOrphanModal(orphanLinkName) {
        const modal = $('attach-orphan-modal');
        if (!modal) return;

        // Set the orphan name label
        const nameSpan = $('attach-orphan-name');
        if (nameSpan) nameSpan.textContent = orphanLinkName;

        // Populate parent link dropdown (exclude the orphan itself + its descendants)
        const orphanDescendants = getDescendantLinks(orphanLinkName);
        orphanDescendants.add(orphanLinkName);

        const parentSelect = $('attach-orphan-parent');
        if (parentSelect) {
            parentSelect.innerHTML = '';
            getLinkNames().forEach(n => {
                if (!orphanDescendants.has(n)) {
                    const opt = document.createElement('option');
                    opt.value = n;
                    opt.textContent = n;
                    parentSelect.appendChild(opt);
                }
            });
        }

        // Reset offset fields — pre-fill from 3D viewer position if available
        const transform3d = window.viewer3d?.getLinkTransform?.(orphanLinkName);
        ['attach-orphan-ox', 'attach-orphan-oy', 'attach-orphan-oz',
         'attach-orphan-or', 'attach-orphan-op', 'attach-orphan-ow'].forEach(id => {
            const el = $(id);
            if (el) el.value = '0';
        });
        if (transform3d) {
            const p = transform3d.position;
            const r = transform3d.rotation;
            if ($('attach-orphan-ox')) $('attach-orphan-ox').value = roundNum(p.x);
            if ($('attach-orphan-oy')) $('attach-orphan-oy').value = roundNum(p.y);
            if ($('attach-orphan-oz')) $('attach-orphan-oz').value = roundNum(p.z);
            if ($('attach-orphan-or')) $('attach-orphan-or').value = roundNum(r.r);
            if ($('attach-orphan-op')) $('attach-orphan-op').value = roundNum(r.p);
            if ($('attach-orphan-ow')) $('attach-orphan-ow').value = roundNum(r.y);
        }

        // Store the orphan name for the confirm handler
        modal.dataset.orphanLink = orphanLinkName;

        // Show modal
        modal.style.display = 'flex';
    }

    /**
     * Confirm attaching an orphan to the selected parent.
     */
    function confirmAttachOrphan() {
        const modal = $('attach-orphan-modal');
        if (!modal) return;

        const orphanLinkName = modal.dataset.orphanLink;
        const parentSelect = $('attach-orphan-parent');
        const parentLinkName = parentSelect ? parentSelect.value : null;
        if (!orphanLinkName || !parentLinkName) {
            showToast('Please select a parent link', 'warning');
            return;
        }

        const ox = parseFloat($('attach-orphan-ox')?.value || 0);
        const oy = parseFloat($('attach-orphan-oy')?.value || 0);
        const oz = parseFloat($('attach-orphan-oz')?.value || 0);
        const or = parseFloat($('attach-orphan-or')?.value || 0);
        const op = parseFloat($('attach-orphan-op')?.value || 0);
        const ow = parseFloat($('attach-orphan-ow')?.value || 0);

        pushUndo('Attach "' + orphanLinkName + '" to "' + parentLinkName + '"');
        createAttachmentJoint(
            orphanLinkName, parentLinkName,
            ox + ' ' + oy + ' ' + oz,
            or + ' ' + op + ' ' + ow
        );

        closeAllModals();
        renderTree();
        renderSVG();
        updateStatusCounts();
        fireURDFChanged();
        showToast('Attached "' + orphanLinkName + '" to "' + parentLinkName + '"', 'success');
    }

    function getDescendantLinks(linkName) {
        // Returns a Set of link names that are descendants of linkName
        const descendants = new Set();
        const queue = [linkName];
        while (queue.length > 0) {
            const current = queue.shift();
            getAllJoints().forEach(j => {
                const pEl = j.querySelector('parent');
                const cEl = j.querySelector('child');
                if (pEl && pEl.getAttribute('link') === current) {
                    const childName = cEl ? cEl.getAttribute('link') : null;
                    if (childName && !descendants.has(childName)) {
                        descendants.add(childName);
                        queue.push(childName);
                    }
                }
            });
        }
        return descendants;
    }

    /**
     * Get all descendant links AND joints of a given link.
     * Returns {links: [{type,name,xmlEl}], joints: [{type,name,xmlEl}]}
     */
    function getSubtreeElements(linkName) {
        const result = { links: [], joints: [] };
        const visited = new Set();
        const queue = [linkName];
        while (queue.length > 0) {
            const current = queue.shift();
            if (visited.has(current)) continue;
            visited.add(current);
            // Add the link itself
            const linkEl = getLinkByName(current);
            if (linkEl) {
                result.links.push({ type: 'link', name: current, xmlEl: linkEl });
            }
            // Find child joints where this link is the parent
            getAllJoints().forEach(j => {
                const pEl = j.querySelector('parent');
                const cEl = j.querySelector('child');
                if (pEl && pEl.getAttribute('link') === current) {
                    const jName = j.getAttribute('name');
                    result.joints.push({ type: 'joint', name: jName, xmlEl: j });
                    const childName = cEl ? cEl.getAttribute('link') : null;
                    if (childName && !visited.has(childName)) {
                        queue.push(childName);
                    }
                }
            });
        }
        return result;
    }

    /**
     * Select a node and all its children (subtree).
     */
    function selectWithChildren(type, name) {
        if (type === 'joint') {
            // For a joint, select the joint + its child link subtree
            const jointEl = getJointByName(name);
            if (!jointEl) return;
            selectedElements = [{ type: 'joint', name, xmlEl: jointEl }];
            const cEl = jointEl.querySelector('child');
            const childName = cEl ? cEl.getAttribute('link') : null;
            if (childName) {
                const subtree = getSubtreeElements(childName);
                selectedElements.push(...subtree.links, ...subtree.joints);
            }
        } else {
            // For a link, select the link + entire subtree
            const subtree = getSubtreeElements(name);
            selectedElements = [...subtree.links, ...subtree.joints];
        }
        selectedElement = selectedElements.length > 0 ? selectedElements[0] : null;
        refreshTreeHighlights();
        highlightSVGSelection();
        updateSelectionBadge();
        const count = selectedElements.length;
        showToast('Selected ' + count + ' element' + (count !== 1 ? 's' : '') + ' (with children)', 'info');
    }

    /**
     * Copy a node and all its children to clipboard.
     */
    function copyWithChildren(type, name) {
        // First select with children, then copy
        selectWithChildren(type, name);
        handleCopy();
    }

    function openReparentModal() {
        if (!contextMenuTarget || !dom.reparentModal) return;
        const { type, name } = contextMenuTarget;
        const sourceName = type === 'link' ? name : null;

        if (!sourceName) {
            showToast('Reparent only works on links', 'warning');
            return;
        }

        if (dom.reparentSourceName) dom.reparentSourceName.textContent = sourceName;

        // Fill target dropdown: all links except source and its descendants
        const descendants = getDescendantLinks(sourceName);
        descendants.add(sourceName);

        if (dom.reparentTarget) {
            dom.reparentTarget.innerHTML = '';
            getLinkNames().forEach(ln => {
                if (!descendants.has(ln)) {
                    const opt = document.createElement('option');
                    opt.value = ln;
                    opt.textContent = ln;
                    dom.reparentTarget.appendChild(opt);
                }
            });
        }

        // Reset offsets
        if (dom.reparentOx) dom.reparentOx.value = '0';
        if (dom.reparentOy) dom.reparentOy.value = '0';
        if (dom.reparentOz) dom.reparentOz.value = '0';

        showModal(dom.reparentModal);
    }

    function confirmReparent() {
        if (!contextMenuTarget || !urdfDoc) {
            closeAllModals();
            return;
        }
        const { type, name } = contextMenuTarget;
        if (type !== 'link') {
            closeAllModals();
            return;
        }

        const robot = urdfDoc.querySelector('robot');
        if (!robot) { closeAllModals(); return; }

        const targetLink = dom.reparentTarget ? dom.reparentTarget.value : '';
        const ox = dom.reparentOx ? dom.reparentOx.value || '0' : '0';
        const oy = dom.reparentOy ? dom.reparentOy.value || '0' : '0';
        const oz = dom.reparentOz ? dom.reparentOz.value || '0' : '0';

        if (!targetLink) {
            showToast('Select a target link', 'warning');
            return;
        }

        pushUndo('Reparent "' + name + '" under "' + targetLink + '"');

        // Remove old joint connecting this link as child
        const joints = getAllJoints();
        for (let i = 0; i < joints.length; i++) {
            const cEl = joints[i].querySelector('child');
            if (cEl && cEl.getAttribute('link') === name) {
                robot.removeChild(joints[i]);
                break;
            }
        }

        // Create new fixed joint from target to source
        const jointName = targetLink + '_to_' + name + '_joint';
        const jointEl = urdfDoc.createElement('joint');
        jointEl.setAttribute('name', jointName);
        jointEl.setAttribute('type', 'fixed');

        const parentEl = urdfDoc.createElement('parent');
        parentEl.setAttribute('link', targetLink);
        jointEl.appendChild(parentEl);

        const childEl = urdfDoc.createElement('child');
        childEl.setAttribute('link', name);
        jointEl.appendChild(childEl);

        const originEl = urdfDoc.createElement('origin');
        originEl.setAttribute('xyz', ox + ' ' + oy + ' ' + oz);
        originEl.setAttribute('rpy', '0 0 0');
        jointEl.appendChild(originEl);

        robot.appendChild(jointEl);

        closeAllModals();
        renderTree();
        renderSVG();
        updateStatusCounts();
        fireURDFChanged();
        showToast('Reparented "' + name + '" under "' + targetLink + '"', 'success');
    }

    function handleDuplicate() {
        if (!contextMenuTarget || !urdfDoc) return;
        const { type, name } = contextMenuTarget;
        const robot = urdfDoc.querySelector('robot');
        if (!robot) return;

        // If we have multi-selected items, duplicate all of them
        if (selectedElements.length > 1 && isMultiSelected(type, name)) {
            duplicateSelected();
            return;
        }

        pushUndo('Duplicate ' + type + ' "' + name + '"');

        const dupeNameMap = new Map();
        if (type === 'link') {
            const linkEl = getLinkByName(name);
            if (!linkEl) return;
            const clone = linkEl.cloneNode(true);
            const copyName = generateUniqueName(name, 'link');
            clone.setAttribute('name', copyName);
            dupeNameMap.set(name, copyName);
            // Do NOT offset visual/collision origins — that misaligns meshes from physics bodies
            robot.appendChild(clone);
            showToast('Duplicated link as "' + copyName + '"', 'success');
        } else {
            const jointEl = getJointByName(name);
            if (!jointEl) return;
            const clone = jointEl.cloneNode(true);
            const copyName = generateUniqueName(name, 'joint');
            clone.setAttribute('name', copyName);
            dupeNameMap.set(name, copyName);
            robot.appendChild(clone);
            showToast('Duplicated joint as "' + copyName + '"', 'success');
        }
        // Clone associated Gazebo elements (materials, controllers)
        cloneGazeboElements(dupeNameMap);

        renderTree();
        renderSVG();
        updateStatusCounts();
        fireURDFChanged();
    }

    // ========== COPY / PASTE / DUPLICATE ==========

    /**
     * Generate a unique name by appending _copy, _copy1, _copy2, etc.
     */
    function generateUniqueName(baseName, type) {
        // Strip any existing _copy / _copyN suffix to find the root
        const root = baseName.replace(/_copy\d*$/, '');
        let copyName = root + '_copy';
        let suffix = 1;
        const nameChecker = type === 'link' ? getLinkByName : getJointByName;
        while (nameChecker(copyName)) {
            copyName = root + '_copy' + suffix;
            suffix++;
        }
        return copyName;
    }

    /**
     * Offset a joint element's origin to visually separate a pasted/duplicated subtree.
     * Only modifies the JOINT origin (parent-child spatial relationship),
     * NEVER link visual/collision origins (which would misalign meshes from physics).
     */
    function offsetJointOrigin(jointEl, offset) {
        let origin = jointEl.querySelector('origin');
        if (!origin) {
            origin = urdfDoc.createElement('origin');
            origin.setAttribute('xyz', '0 0 0');
            origin.setAttribute('rpy', '0 0 0');
            jointEl.appendChild(origin);
        }
        const xyz = splitXYZ(origin.getAttribute('xyz') || '0 0 0');
        xyz[0] = (xyz[0] + offset).toFixed(6);
        origin.setAttribute('xyz', xyz.join(' '));
    }

    /**
     * Clone <gazebo> elements (material references + joint controller plugins)
     * when links/joints are copied, pasted, or duplicated.
     * @param {Map<string,string>} nameMap - old element name → new element name
     */
    function cloneGazeboElements(nameMap) {
        if (!urdfDoc) return;
        const robot = urdfDoc.querySelector('robot');
        if (!robot) return;

        const allGazebo = Array.from(robot.querySelectorAll(':scope > gazebo'));
        const existingTopics = new Set();
        robot.querySelectorAll('plugin > topic').forEach(t => existingTopics.add(t.textContent));

        allGazebo.forEach(gz => {
            const ref = gz.getAttribute('reference');

            // Case 1: <gazebo reference="linkOrJointName"> → clone with new reference
            if (ref && nameMap.has(ref)) {
                const clone = gz.cloneNode(true);
                clone.setAttribute('reference', nameMap.get(ref));
                robot.appendChild(clone);
                return;
            }

            // Case 2: <gazebo><plugin> with <joint_name> matching a copied joint
            if (!ref) {
                const plugins = gz.querySelectorAll('plugin');
                plugins.forEach(plugin => {
                    const jnEls = plugin.querySelectorAll('joint_name');
                    let hasMatch = false;
                    jnEls.forEach(jnEl => {
                        if (nameMap.has(jnEl.textContent)) hasMatch = true;
                    });

                    if (hasMatch) {
                        const gzClone = gz.cloneNode(true);
                        const clonedPlugin = gzClone.querySelector('plugin');
                        if (!clonedPlugin) return;

                        // Update joint_name references; remove those not in nameMap
                        const jnClones = Array.from(clonedPlugin.querySelectorAll('joint_name'));
                        jnClones.forEach(jnEl => {
                            const oldName = jnEl.textContent;
                            if (nameMap.has(oldName)) {
                                jnEl.textContent = nameMap.get(oldName);
                            } else {
                                jnEl.remove();
                            }
                        });

                        // If no joint_names left after filtering, discard
                        if (clonedPlugin.querySelectorAll('joint_name').length === 0) return;

                        // Update topic for controllers (derive from new joint name)
                        const topicEl = clonedPlugin.querySelector('topic');
                        if (topicEl) {
                            const newJointName = clonedPlugin.querySelector('joint_name').textContent;
                            let newTopic = newJointName + '_cmd';
                            let suffix = 1;
                            while (existingTopics.has(newTopic)) {
                                newTopic = newJointName + '_cmd' + suffix;
                                suffix++;
                            }
                            topicEl.textContent = newTopic;
                            existingTopics.add(newTopic);
                        }

                        robot.appendChild(gzClone);
                    }
                });
            }
        });
    }

    /**
     * Copy selected elements to clipboard.
     */
    function handleCopy() {
        if (selectedElements.length === 0) {
            showToast('Nothing selected to copy', 'warning');
            return;
        }

        clipboard = [];
        const ser = new XMLSerializer();

        selectedElements.forEach(sel => {
            let xmlEl = sel.xmlEl;
            if (!xmlEl) {
                xmlEl = sel.type === 'link' ? getLinkByName(sel.name) : getJointByName(sel.name);
            }
            if (xmlEl) {
                clipboard.push({
                    type: sel.type,
                    name: sel.name,
                    xmlString: ser.serializeToString(xmlEl),
                });
            }
        });

        const count = clipboard.length;
        showToast('Copied ' + count + ' element' + (count !== 1 ? 's' : '') + ' to clipboard', 'info');
        updatePasteAvailability();
    }

    /**
     * Paste from clipboard — creates new elements with unique names.
     */
    function handlePaste() {
        if (clipboard.length === 0) {
            showToast('Clipboard is empty — copy something first', 'warning');
            return;
        }
        if (!urdfDoc) return;
        const robot = urdfDoc.querySelector('robot');
        if (!robot) return;

        pushUndo('Paste ' + clipboard.length + ' element(s)');

        const nameMap = new Map();  // old name → new name (for fixing joint references)
        const newElements = [];

        // First pass: create all links with unique names
        clipboard.filter(c => c.type === 'link').forEach(item => {
            const parser = new DOMParser();
            const tmpDoc = parser.parseFromString(item.xmlString, 'text/xml');
            const el = tmpDoc.documentElement;
            const importedEl = urdfDoc.importNode(el, true);

            const origName = importedEl.getAttribute('name');
            const newName = generateUniqueName(origName, 'link');
            importedEl.setAttribute('name', newName);
            nameMap.set(origName, newName);

            // Do NOT offset visual/collision origins — that misaligns meshes from physics bodies
            robot.appendChild(importedEl);
            newElements.push({ type: 'link', name: newName, xmlEl: importedEl });
        });

        // Second pass: create all joints with unique names, fix parent/child references
        const rootJoints = [];  // joints whose parent was NOT copied (subtree roots)
        clipboard.filter(c => c.type === 'joint').forEach(item => {
            const parser = new DOMParser();
            const tmpDoc = parser.parseFromString(item.xmlString, 'text/xml');
            const el = tmpDoc.documentElement;
            const importedEl = urdfDoc.importNode(el, true);

            const origName = importedEl.getAttribute('name');
            const newName = generateUniqueName(origName, 'joint');
            importedEl.setAttribute('name', newName);
            nameMap.set(origName, newName);

            // Fix parent/child link references if those links were also copied
            const parentEl = importedEl.querySelector('parent');
            const childEl = importedEl.querySelector('child');
            let isRootJoint = true;
            if (parentEl) {
                const ref = parentEl.getAttribute('link');
                if (nameMap.has(ref)) {
                    parentEl.setAttribute('link', nameMap.get(ref));
                    isRootJoint = false;
                }
            }
            if (childEl) {
                const ref = childEl.getAttribute('link');
                if (nameMap.has(ref)) childEl.setAttribute('link', nameMap.get(ref));
            }

            robot.appendChild(importedEl);
            newElements.push({ type: 'joint', name: newName, xmlEl: importedEl });
            if (isRootJoint) rootJoints.push(importedEl);
        });

        // Offset only root joint origins to visually separate the pasted subtree
        rootJoints.forEach(j => offsetJointOrigin(j, 0.2));

        // Clone associated Gazebo elements (material refs, controller plugins)
        cloneGazeboElements(nameMap);

        // Select the newly pasted elements
        selectedElements = newElements;
        selectedElement = newElements.length > 0 ? newElements[0] : null;

        renderTree();
        renderSVG();
        updateStatusCounts();
        fireURDFChanged();

        const count = newElements.length;
        showToast('Pasted ' + count + ' element' + (count !== 1 ? 's' : ''), 'success');
    }

    /**
     * Duplicate all currently selected elements (Ctrl+D).
     */
    function duplicateSelected() {
        if (selectedElements.length === 0) {
            showToast('Nothing selected to duplicate', 'warning');
            return;
        }
        if (!urdfDoc) return;
        const robot = urdfDoc.querySelector('robot');
        if (!robot) return;

        pushUndo('Duplicate ' + selectedElements.length + ' element(s)');

        const nameMap = new Map();
        const newElements = [];
        const ser = new XMLSerializer();

        // Duplicate links first (do NOT offset visual origins — preserves mesh alignment)
        selectedElements.filter(s => s.type === 'link').forEach(sel => {
            let xmlEl = sel.xmlEl || getLinkByName(sel.name);
            if (!xmlEl) return;
            const clone = xmlEl.cloneNode(true);
            const newName = generateUniqueName(sel.name, 'link');
            clone.setAttribute('name', newName);
            nameMap.set(sel.name, newName);
            robot.appendChild(clone);
            newElements.push({ type: 'link', name: newName, xmlEl: clone });
        });

        // Duplicate joints
        const rootJoints = [];
        selectedElements.filter(s => s.type === 'joint').forEach(sel => {
            let xmlEl = sel.xmlEl || getJointByName(sel.name);
            if (!xmlEl) return;
            const clone = xmlEl.cloneNode(true);
            const newName = generateUniqueName(sel.name, 'joint');
            clone.setAttribute('name', newName);
            nameMap.set(sel.name, newName);

            // Fix parent/child link references if those links were also duplicated
            const parentEl = clone.querySelector('parent');
            const childEl = clone.querySelector('child');
            let isRootJoint = true;
            if (parentEl) {
                const ref = parentEl.getAttribute('link');
                if (nameMap.has(ref)) {
                    parentEl.setAttribute('link', nameMap.get(ref));
                    isRootJoint = false;
                }
            }
            if (childEl) {
                const ref = childEl.getAttribute('link');
                if (nameMap.has(ref)) childEl.setAttribute('link', nameMap.get(ref));
            }

            robot.appendChild(clone);
            newElements.push({ type: 'joint', name: newName, xmlEl: clone });
            if (isRootJoint) rootJoints.push(clone);
        });

        // Offset only root joint origins for visual separation
        rootJoints.forEach(j => offsetJointOrigin(j, 0.2));

        // Clone associated Gazebo elements (material refs, controller plugins)
        cloneGazeboElements(nameMap);

        // Select the newly duplicated elements
        selectedElements = newElements;
        selectedElement = newElements.length > 0 ? newElements[0] : null;

        renderTree();
        renderSVG();
        updateStatusCounts();
        fireURDFChanged();
        refreshTreeHighlights();
        highlightSVGSelection();
        updateSelectionBadge();

        const count = newElements.length;
        showToast('Duplicated ' + count + ' element' + (count !== 1 ? 's' : ''), 'success');
    }

    /**
     * Delete all currently selected elements (multi-delete).
     */
    function deleteSelected() {
        if (selectedElements.length === 0) {
            showToast('Nothing selected to delete', 'warning');
            return;
        }
        if (!urdfDoc) return;
        const robot = urdfDoc.querySelector('robot');
        if (!robot) return;

        pushUndo('Delete ' + selectedElements.length + ' element(s)');

        // Delete links (recursive) then joints
        const linkNames = selectedElements.filter(s => s.type === 'link').map(s => s.name);
        const jointNames = selectedElements.filter(s => s.type === 'joint').map(s => s.name);

        linkNames.forEach(name => deleteLinkRecursive(name));
        jointNames.forEach(name => {
            const jEl = getJointByName(name);
            if (jEl && jEl.parentNode === robot) {
                robot.removeChild(jEl);
            }
        });

        closeAllModals();
        clearSelection();
        renderTree();
        renderSVG();
        fitView();
        updateStatusCounts();
        fireURDFChanged();
        showToast('Deleted ' + (linkNames.length + jointNames.length) + ' element(s)', 'success');
    }

    /**
     * Enable/disable paste context menu item based on clipboard state.
     */
    function updatePasteAvailability() {
        if (dom.contextMenu) {
            const pasteItem = dom.contextMenu.querySelector('[data-action="paste"]');
            if (pasteItem) {
                pasteItem.classList.toggle('disabled', clipboard.length === 0);
            }
        }
    }

    function switchPreviewTab(tabName) {
        activePreviewTab = tabName;

        // Toggle tab button active state
        document.querySelectorAll('.preview-tab').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tabName);
        });

        // Toggle tab content visibility by IDs
        const svgContainer = $('svg-container');
        const viewer3dContainer = $('viewer3d-container');
        if (svgContainer) svgContainer.classList.toggle('active', tabName === 'node-editor');
        if (viewer3dContainer) viewer3dContainer.classList.toggle('active', tabName === 'viewer-3d');

        if (tabName === 'viewer-3d' && window.viewer3d) {
            try {
                window.viewer3d.loadURDF(serializeURDF());
                window.viewer3d.fitToModel();
                // Force resize since container may have been hidden
                window.dispatchEvent(new Event('resize'));
            } catch (e) {
                // viewer3d may fail
            }
        }
    }

    function pollGazeboStatus() {
        fetch('/api/status', { method: 'GET' })
            .then(resp => resp.json())
            .then(data => {
                const running = !!data.gazebo_running;
                if (dom.statusGazeboDot) {
                    dom.statusGazeboDot.className = running ? 'connected' : '';
                }
                if (dom.statusGazeboText) {
                    dom.statusGazeboText.textContent = running ? 'Gazebo running' : 'Gazebo stopped';
                }
            })
            .catch(() => {
                if (dom.statusGazeboDot) dom.statusGazeboDot.className = '';
                if (dom.statusGazeboText) dom.statusGazeboText.textContent = 'Gazebo unknown';
            });
    }

    // --- Node Dragging Handlers ---

    function clientToSVG(clientX, clientY) {
        // Convert mouse client coords to SVG-space coords using current zoom/pan
        if (!dom.svgContainer) return { x: 0, y: 0 };
        const rect = dom.svgContainer.getBoundingClientRect();
        const svgX = (clientX - rect.left - panX) / zoom;
        const svgY = (clientY - rect.top - panY) / zoom;
        return { x: svgX, y: svgY };
    }

    function startNodeDrag(e, type, name) {
        if (e.button !== 0) return;  // left button only
        e.stopPropagation();
        e.preventDefault();

        const nodeGroup = dom.previewSvg
            ? dom.previewSvg.querySelector('g[data-type="' + type + '"][data-name="' + name + '"]')
            : null;
        if (!nodeGroup) return;

        const key = type + ':' + name;
        const nodeData = layoutCache ? layoutCache.nodes.get(key) : null;
        if (!nodeData) return;

        const svgPt = clientToSVG(e.clientX, e.clientY);

        isDraggingNode = true;
        dragTarget = {
            el: nodeGroup,
            type: type,
            name: name,
            key: key,
            startX: nodeData.x,
            startY: nodeData.y,
            offsetX: svgPt.x - nodeData.x,
            offsetY: svgPt.y - nodeData.y,
        };

        dom.svgContainer.classList.add('grabbing');
    }

    function onNodeDrag(e) {
        if (!isDraggingNode || !dragTarget || !layoutCache) return;

        const svgPt = clientToSVG(e.clientX, e.clientY);
        const newX = svgPt.x - dragTarget.offsetX;
        const newY = svgPt.y - dragTarget.offsetY;

        // Update layout cache position
        const nodeData = layoutCache.nodes.get(dragTarget.key);
        if (nodeData) {
            const dx = newX - nodeData.x;
            const dy = newY - nodeData.y;
            nodeData.x = newX;
            nodeData.y = newY;
            nodeData.cx = nodeData.cx + dx;
            nodeData.cy = nodeData.cy + dy;
        }

        // Move the SVG group visually using translate
        const dx = newX - dragTarget.startX;
        const dy = newY - dragTarget.startY;
        dragTarget.el.setAttribute('transform', 'translate(' + dx + ',' + dy + ')');
    }

    function endNodeDrag(e) {
        if (!isDraggingNode) return;

        // Detect click vs drag: if node barely moved, treat as a click (select)
        let wasClick = false;
        if (dragTarget && layoutCache) {
            const nodeData = layoutCache.nodes.get(dragTarget.key);
            if (nodeData) {
                const dx = Math.abs(nodeData.x - dragTarget.startX);
                const dy = Math.abs(nodeData.y - dragTarget.startY);
                if (dx < 3 && dy < 3) {
                    wasClick = true;
                }
                // Save custom position so it persists across re-renders
                customPositions.set(dragTarget.key, { x: nodeData.x, y: nodeData.y });
            }
        }

        // If it was a click (not a real drag), select the element
        const clickedType = dragTarget ? dragTarget.type : null;
        const clickedName = dragTarget ? dragTarget.name : null;

        isDraggingNode = false;
        dragTarget = null;
        if (dom.svgContainer) dom.svgContainer.classList.remove('grabbing');
        // Re-render to recompute connectors with updated positions
        renderSVG();

        // Select element after re-render (so tree/highlight work on fresh DOM)
        if (wasClick && clickedType && clickedName) {
            selectElement(clickedType, clickedName, null);
        }
    }

    // ========== EVENT BINDING ==========

    function bindEvents() {
        // Toolbar buttons
        if (dom.btnLoad) dom.btnLoad.addEventListener('click', openLoadModal);
        if (dom.btnSave) dom.btnSave.addEventListener('click', openSaveModal);
        if (dom.btnExport) dom.btnExport.addEventListener('click', exportURDF);
        if (dom.btnAddLink) dom.btnAddLink.addEventListener('click', openAddLinkModal);
        if (dom.btnAddJoint) dom.btnAddJoint.addEventListener('click', openAddJointModal);
        if (dom.btnUndo) dom.btnUndo.addEventListener('click', performUndo);
        if (dom.btnRedo) dom.btnRedo.addEventListener('click', performRedo);
        if (dom.btnUndo3d) dom.btnUndo3d.addEventListener('click', performUndo);
        if (dom.btnRedo3d) dom.btnRedo3d.addEventListener('click', performRedo);

        // Spawn / Validate / Import
        if (dom.btnSpawn) dom.btnSpawn.addEventListener('click', spawnInGazebo);
        if (dom.btnValidate) dom.btnValidate.addEventListener('click', validateURDF);
        if (dom.btnImport) dom.btnImport.addEventListener('click', openImportModal);
        if (dom.importMethod) dom.importMethod.addEventListener('change', toggleImportMethod);

        // Import URDF Package
        if (dom.btnImportPkg) dom.btnImportPkg.addEventListener('click', openImportPkgModal);
        const ipkgAnalyzeBtn = $('ipkg-analyze-btn');
        if (ipkgAnalyzeBtn) ipkgAnalyzeBtn.addEventListener('click', ipkgAnalyze);
        const ipkgMergeBtn = $('ipkg-merge-btn');
        if (ipkgMergeBtn) ipkgMergeBtn.addEventListener('click', ipkgMerge);
        const ipkgBackBtn = $('ipkg-back-btn');
        if (ipkgBackBtn) ipkgBackBtn.addEventListener('click', ipkgBack);

        // Environment Objects
        if (dom.btnEnvObjects) dom.btnEnvObjects.addEventListener('click', openEnvObjectsModal);
        const envSpawnBtn = $('env-spawn-btn');
        if (envSpawnBtn) envSpawnBtn.addEventListener('click', envSpawnObject);
        const envAddUrdfBtn = $('env-add-urdf-btn');
        if (envAddUrdfBtn) envAddUrdfBtn.addEventListener('click', envAddToURDF);

        // Preview controls
        if (dom.btnFit) dom.btnFit.addEventListener('click', fitView);
        if (dom.btnZoomIn) dom.btnZoomIn.addEventListener('click', zoomIn);
        if (dom.btnZoomOut) dom.btnZoomOut.addEventListener('click', zoomOut);

        // Property actions
        if (dom.btnApplyProps) dom.btnApplyProps.addEventListener('click', applyProperties);
        if (dom.btnDeleteSelected) dom.btnDeleteSelected.addEventListener('click', openDeleteModal);

        // Tree search
        if (dom.treeSearch) {
            dom.treeSearch.addEventListener('input', applyTreeFilter);
        }

        // Expand/collapse all tree nodes
        const btnExpandAll = $('btn-expand-all');
        const btnCollapseAll = $('btn-collapse-all');
        if (btnExpandAll) {
            btnExpandAll.addEventListener('click', () => {
                dom.treeContainer.querySelectorAll('.tree-toggle').forEach(t => {
                    t.classList.add('expanded');
                });
                dom.treeContainer.querySelectorAll('.tree-children').forEach(c => {
                    c.classList.add('expanded');
                });
            });
        }
        if (btnCollapseAll) {
            btnCollapseAll.addEventListener('click', () => {
                dom.treeContainer.querySelectorAll('.tree-toggle').forEach(t => {
                    t.classList.remove('expanded');
                });
                dom.treeContainer.querySelectorAll('.tree-children').forEach(c => {
                    c.classList.remove('expanded');
                });
            });
        }

        // Geometry type buttons in add-link modal
        document.querySelectorAll('.geometry-type-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                selectGeometryType(btn.dataset.type);
            });
        });

        // Modal close buttons
        document.querySelectorAll('.modal-close-btn').forEach(btn => {
            btn.addEventListener('click', closeAllModals);
        });

        // Modal cancel buttons
        document.querySelectorAll('.modal-btn.cancel-btn').forEach(btn => {
            btn.addEventListener('click', closeAllModals);
        });

        // Overlay click to close
        document.querySelectorAll('.modal-overlay').forEach(overlay => {
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) closeAllModals();
            });
        });

        // Confirm buttons for each modal
        bindModalConfirm('add-link-modal', confirmAddLink);
        bindModalConfirm('add-joint-modal', confirmAddJoint);
        bindModalConfirm('delete-modal', confirmDelete);
        bindModalConfirm('save-modal', confirmSave);
        bindModalConfirm('load-modal', confirmLoad);
        bindModalConfirm('import-modal', confirmImport);

        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            // Ignore shortcuts when typing in inputs
            const tag = e.target.tagName.toLowerCase();
            const isInput = tag === 'input' || tag === 'textarea' || tag === 'select';

            if (e.ctrlKey && e.key === 's') {
                e.preventDefault();
                openSaveModal();
            } else if (e.ctrlKey && e.shiftKey && e.key === 'Z') {
                e.preventDefault();
                performRedo();
            } else if (e.ctrlKey && e.key === 'z') {
                e.preventDefault();
                performUndo();
            } else if (e.ctrlKey && e.key === 'y') {
                e.preventDefault();
                performRedo();
            } else if (e.ctrlKey && e.key === 'c' && !isInput) {
                e.preventDefault();
                handleCopy();
            } else if (e.ctrlKey && e.key === 'v' && !isInput) {
                e.preventDefault();
                handlePaste();
            } else if (e.ctrlKey && e.key === 'd' && !isInput) {
                e.preventDefault();
                duplicateSelected();
            } else if (e.ctrlKey && e.key === 'a' && !isInput) {
                e.preventDefault();
                selectAll();
            } else if (e.key === 'Delete' && !isInput) {
                e.preventDefault();
                if (selectedElements.length > 1) {
                    deleteSelected();
                } else if (selectedElement) {
                    openDeleteModal();
                }
            } else if (e.key === 'Escape') {
                closeAllModals();
                if (selectedElements.length > 1) {
                    clearSelection();
                }
            } else if (e.key === 'w' && !isInput) {
                document.dispatchEvent(new CustomEvent('viewer3d-set-mode', { detail: { mode: 'translate' } }));
                document.querySelectorAll('.v3d-mode-btn').forEach(b => b.classList.toggle('active', b.dataset.mode === 'translate'));
            } else if (e.key === 'e' && !isInput) {
                document.dispatchEvent(new CustomEvent('viewer3d-set-mode', { detail: { mode: 'rotate' } }));
                document.querySelectorAll('.v3d-mode-btn').forEach(b => b.classList.toggle('active', b.dataset.mode === 'rotate'));
            } else if (e.key === 'r' && !isInput) {
                document.dispatchEvent(new CustomEvent('viewer3d-set-mode', { detail: { mode: 'scale' } }));
                document.querySelectorAll('.v3d-mode-btn').forEach(b => b.classList.toggle('active', b.dataset.mode === 'scale'));
            }
        });

        // Window resize: update SVG viewbox
        window.addEventListener('resize', () => {
            updateSVGViewBox();
        });

        // --- Interactive features bindings ---

        // Preview tab switching
        document.querySelectorAll('.preview-tab').forEach(btn => {
            btn.addEventListener('click', () => {
                switchPreviewTab(btn.dataset.tab);
            });
        });

        // Context menu item actions
        if (dom.contextMenu) {
            dom.contextMenu.querySelectorAll('.context-menu-item').forEach(item => {
                item.addEventListener('click', () => {
                    handleContextAction(item.dataset.action);
                });
            });
        }

        // Hide context menu on click elsewhere
        document.addEventListener('click', (e) => {
            if (dom.contextMenu && !dom.contextMenu.contains(e.target)) {
                hideContextMenu();
            }
        });

        // Hide context menu on Escape (already handled above, just ensure hide)
        document.addEventListener('contextmenu', (e) => {
            // Only prevent default if we are showing our own
            if (dom.contextMenu && dom.contextMenu.classList.contains('visible')) {
                // Let new context menu events on nodes be handled by node handlers
            }
        });

        // Auto-sync toggle (disabled — auto-sync removed)
        // dom.chkAutoSync binding intentionally removed

        // 3D viewer toolbar
        document.querySelectorAll('.v3d-mode-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.v3d-mode-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                document.dispatchEvent(new CustomEvent('viewer3d-set-mode', {
                    detail: { mode: btn.dataset.mode }
                }));
            });
        });

        const chkSnap = $('chk-snap');
        if (chkSnap) {
            chkSnap.addEventListener('change', () => {
                document.dispatchEvent(new CustomEvent('viewer3d-set-snap', {
                    detail: { enabled: chkSnap.checked }
                }));
            });
        }

        const btnFit3d = $('btn-fit-3d');
        if (btnFit3d) btnFit3d.addEventListener('click', () => {
            if (window.viewer3d) window.viewer3d.fitToModel();
        });
        const btnDeselect3d = $('btn-deselect-3d');
        if (btnDeselect3d) btnDeselect3d.addEventListener('click', () => {
            if (window.viewer3d) window.viewer3d.deselectAll();
        });

        const btnDetach = $('btn-detach-connector');
        if (btnDetach) btnDetach.addEventListener('click', detachConnectorJoint);

        document.addEventListener('click', (e) => {
            const tooltip = $('connector-tooltip');
            if (tooltip && !tooltip.contains(e.target) && !e.target.closest('.svg-connector-group')) {
                hideConnectorTooltip();
            }
        });

        document.addEventListener('viewer3d-transform', handleViewer3dTransform);

        // Reparent modal confirm
        const reparentConfirmBtn = dom.reparentModal
            ? dom.reparentModal.querySelector('.modal-btn.confirm-btn')
            : null;
        if (reparentConfirmBtn) {
            reparentConfirmBtn.addEventListener('click', confirmReparent);
        }

        // Reparent modal cancel/close
        if (dom.reparentModal) {
            const cancelBtn = dom.reparentModal.querySelector('.modal-btn.cancel-btn');
            if (cancelBtn) cancelBtn.addEventListener('click', closeAllModals);
            const closeBtn = dom.reparentModal.querySelector('.modal-close-btn');
            if (closeBtn) closeBtn.addEventListener('click', closeAllModals);
        }

        // Attach Orphan modal confirm/cancel/close
        const attachOrphanModal = $('attach-orphan-modal');
        if (attachOrphanModal) {
            const confirmBtn = attachOrphanModal.querySelector('.modal-btn.confirm-btn');
            if (confirmBtn) confirmBtn.addEventListener('click', confirmAttachOrphan);
            const cancelBtn = attachOrphanModal.querySelector('.modal-btn.cancel-btn');
            if (cancelBtn) cancelBtn.addEventListener('click', closeAllModals);
            const closeBtn = attachOrphanModal.querySelector('.modal-close-btn');
            if (closeBtn) closeBtn.addEventListener('click', closeAllModals);
        }

        // Cross-panel highlight: 3D viewer click → select in node editor
        document.addEventListener('viewer3d-select', (e) => {
            console.log('[urdf_editor] viewer3d-select received:', e.detail);
            if (e.detail && e.detail.name) {
                const type = e.detail.type || 'link';
                selectElement(type, e.detail.name, null);
            }
        });

        // 3D gizmo drag start → reset undo flag for this drag session
        document.addEventListener('viewer3d-transform-start', (e) => {
            console.log('[urdf_editor] viewer3d-transform-start received, resetting undo flag');
            transformUndoPushed = false;
            // Snapshot the mesh scales at drag start so scale gizmo can compute correctly
            scaleAtDragStart = null;
            const linkName = e.detail?.linkName;
            if (linkName && urdfDoc) {
                const linkEl = getLinkByName(linkName);
                if (linkEl) {
                    const visMesh = linkEl.querySelector('visual geometry mesh');
                    const colMesh = linkEl.querySelector('collision geometry mesh');
                    scaleAtDragStart = {
                        vis: visMesh ? splitXYZ(visMesh.getAttribute('scale') || '1 1 1') : [1, 1, 1],
                        col: colMesh ? splitXYZ(colMesh.getAttribute('scale') || '1 1 1') : [1, 1, 1],
                    };
                }
            }
        });

        // 3D gizmo drag end → rebuild 3D scene from URDF so children
        // reflect their correct positions after parent moved
        document.addEventListener('viewer3d-transform-end', () => {
            console.log('[urdf_editor] viewer3d-transform-end received, rebuilding 3D scene');
            if (isDirty) {
                fireURDFChanged();
                renderSVG();
                isDirty = false;
            }
        });

        // Children-follow-parent toggle button
        const childrenFollowBtn = $('btn-children-follow');
        if (childrenFollowBtn) {
            childrenFollowBtn.classList.add('active');
            childrenFollowBtn.addEventListener('click', () => {
                setChildrenFollowParent(!childrenFollowParent);
            });
        }
    }

    function bindModalConfirm(modalId, handler) {
        const modal = $(modalId);
        if (!modal) return;
        const confirmBtn = modal.querySelector('.modal-btn.confirm-btn, .modal-btn.danger-btn');
        if (confirmBtn) {
            confirmBtn.addEventListener('click', handler);
        }
    }

    // ========== INITIALIZATION ==========

    function init() {
        bindEvents();
        initSVGInteraction();
        clearProperties();
        updateFileStatus();
        updateStatusCounts();
        fetchInitialURDF();
        fetchMeshList();
        startHealthPolling();

        // Initialize preview tab (default to node editor)
        switchPreviewTab('node-editor');

        // Gazebo status polling (every 5s)
        setInterval(pollGazeboStatus, 5000);
        pollGazeboStatus(); // immediate first check
    }

    // Boot
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
