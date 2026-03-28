import { h } from "preact";
import { useState, useContext, useCallback, useMemo } from "preact/hooks";
import { html } from "htm/preact";
import { ToastContext } from "../app.js";

// EXPORT FOR TESTING
export function isValidIp(ip) {
    if (!ip) return false;
    const parts = ip.split('.');
    if (parts.length !== 4) return false;

    return parts.every(part => {
        if (!/^\d+$/.test(part)) return false;
        const num = parseInt(part, 10);
        return num >= 0 && num <= 255 && part === num.toString();
    });
}

export function isDuplicateIp(ip, existingEntities) {
    if (!existingEntities || !Array.isArray(existingEntities)) return false;
    return existingEntities.some(entity => entity.ip === ip);
}

/**
 * Derive a default scan subnet from existing entity IPs.
 * Returns the most common /24 prefix, or "192.168.137" as fallback.
 */
function deriveDefaultSubnet(existingEntities) {
    if (!existingEntities || existingEntities.length === 0) return "192.168.137";
    const prefixCounts = {};
    for (const e of existingEntities) {
        if (!e.ip) continue;
        const parts = e.ip.split(".");
        if (parts.length === 4) {
            const prefix = `${parts[0]}.${parts[1]}.${parts[2]}`;
            prefixCounts[prefix] = (prefixCounts[prefix] || 0) + 1;
        }
    }
    const sorted = Object.entries(prefixCounts).sort((a, b) => b[1] - a[1]);
    return sorted.length > 0 ? sorted[0][0] : "192.168.137";
}

// All arm slots for the select dropdown
const ARM_SLOTS = ["arm-1", "arm-2", "arm-3", "arm-4", "arm-5", "arm-6"];

export function AddEntityModal({ isOpen, onClose, onEntityAdded, existingEntities }) {
    if (!isOpen) return null;

    const { showToast } = useContext(ToastContext);

    const [ip, setIp] = useState('');
    const [name, setName] = useState('');
    const [entityType, setEntityType] = useState('arm');
    const [groupId, setGroupId] = useState('');
    const [slot, setSlot] = useState('');
    const [status, setStatus] = useState('idle'); // idle, verifying, error
    const [errorMessage, setErrorMessage] = useState(null);

    // Scan state
    const [scanSubnet, setScanSubnet] = useState(() => deriveDefaultSubnet(existingEntities));
    const [scanning, setScanning] = useState(false);
    const [scanResults, setScanResults] = useState(null); // null = not scanned, [] = scanned empty
    const [scanError, setScanError] = useState(null);

    // Batch add state
    const [selectedForBatch, setSelectedForBatch] = useState(new Set()); // Set of IPs
    const [batchGroupId, setBatchGroupId] = useState('');
    const [batchSlots, setBatchSlots] = useState({}); // { ip: slot }
    const [batchTypes, setBatchTypes] = useState({}); // { ip: 'arm'|'vehicle' }
    const [batchAdding, setBatchAdding] = useState(false);
    const [batchErrors, setBatchErrors] = useState([]); // [{ip, error}]

    // Track selected IP for multi-IP (dual-interface) devices
    // Key: hostname or primary ip, Value: chosen ip
    const [selectedIps, setSelectedIps] = useState({}); // { hostname_or_primary_ip: chosen_ip }

    // Helper: get the effective (user-chosen) IP for a scan result
    const getEffectiveIp = useCallback((r) => {
        const key = r.hostname || r.ip;
        return selectedIps[key] || r.ip;
    }, [selectedIps]);

    // Helper: get the effective type for a batch IP
    // Priority: user override > scan result entity_type > 'arm'
    const getBatchType = useCallback((batchIp) => {
        if (batchTypes[batchIp]) return batchTypes[batchIp];
        const r = scanResults && scanResults.find((sr) => getEffectiveIp(sr) === batchIp || sr.ip === batchIp);
        return (r && r.entity_type) || 'arm';
    }, [batchTypes, scanResults, getEffectiveIp]);

    const setBatchType = useCallback((ip, type) => {
        setBatchTypes((prev) => ({ ...prev, [ip]: type }));
        // If switching to vehicle, auto-set slot to 'vehicle'; clear arm slot
        setBatchSlots((prev) => {
            const next = { ...prev };
            if (type === 'vehicle') {
                next[ip] = 'vehicle';
            } else if (prev[ip] === 'vehicle') {
                next[ip] = '';
            }
            return next;
        });
    }, []);

    // Validation
    const ipValid = isValidIp(ip);
    const ipDuplicate = isDuplicateIp(ip, existingEntities);
    const slotValid = entityType === 'vehicle'
        ? slot === 'vehicle'
        : /^arm-[1-9][0-9]*$/.test(slot);
    const hasGroupAndSlot = Boolean(groupId && slot && slotValid);
    const canSubmit = ipValid && !ipDuplicate && hasGroupAndSlot && status !== 'verifying';

    // Slot occupancy map: for the selected group, which slots are taken?
    const slotOccupancy = useMemo(() => {
        const map = {};
        if (!existingEntities || !groupId) return map;
        for (const e of existingEntities) {
            if (e.group_id === groupId && e.slot) {
                map[e.slot] = e.name || e.id;
            }
        }
        return map;
    }, [existingEntities, groupId]);

    // Derived validation messages
    let validationMsg = null;
    if (ip && !ipValid) validationMsg = 'Enter a valid IPv4 address';
    else if (ip && ipDuplicate) validationMsg = 'This IP is already in the fleet';
    else if ((groupId && !slot) || (!groupId && slot)) {
        validationMsg = 'Select both group and slot';
    } else if (slot && !slotValid) {
        validationMsg = entityType === 'vehicle'
            ? 'Vehicle slot must be vehicle'
            : 'Arm slot must be arm-N (e.g. arm-3)';
    }

    const handleClose = () => {
        if (status === 'verifying' || batchAdding) return; // Don't close while verifying

        // Reset state
        setIp('');
        setName('');
        setEntityType('arm');
        setGroupId('');
        setSlot('');
        setStatus('idle');
        setErrorMessage(null);
        setScanResults(null);
        setScanError(null);
        setScanning(false);
        setSelectedForBatch(new Set());
        setSelectedIps({});
        setBatchGroupId('');
        setBatchSlots({});
        setBatchAdding(false);
        setBatchErrors([]);
        onClose();
    };

    const handleOverlayClick = (e) => {
        if (e.target === e.currentTarget) {
            handleClose();
        }
    };

    const handleScan = useCallback(async () => {
        if (!scanSubnet.trim()) return;
        setScanning(true);
        setScanError(null);
        setScanResults(null);

        try {
            const response = await fetch('/api/entities/scan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    subnet: scanSubnet.trim(),
                    timeout: 2.0,
                    concurrency: 100,
                }),
            });

            if (!response.ok) {
                const detail = await response.json().catch(() => ({}));
                const msg = detail?.detail || `Scan failed (HTTP ${response.status})`;
                setScanError(String(msg));
                setScanning(false);
                return;
            }

            const data = await response.json();
            setScanResults(data.results || []);
            const agentCount = data.agents_found || 0;
            const hostCount = data.hosts_found || 0;
            const total = (data.results || []).length;
            if (total > 0) {
                const parts = [];
                if (agentCount > 0) parts.push(`${agentCount} agent(s)`);
                if (hostCount > 0) parts.push(`${hostCount} host(s) without agent`);
                showToast(
                    `Found ${parts.join(', ')} on ${scanSubnet}.*`,
                    'info'
                );
            } else {
                showToast(`No devices found on ${scanSubnet}.*`, 'info');
            }
        } catch {
            setScanError('Network error during scan');
        }
        setScanning(false);
    }, [scanSubnet, showToast]);

    const handleSelectScanResult = useCallback((result) => {
        const effectiveIp = getEffectiveIp(result);
        setIp(effectiveIp);
        if (result.hostname && !name) {
            setName(result.hostname);
        }
        if (result.entity_type && result.entity_type !== entityType) {
            setEntityType(result.entity_type);
            if (result.entity_type === 'vehicle') {
                setSlot('vehicle');
            }
        }
    }, [name, entityType, getEffectiveIp]);

    const toggleBatchSelect = useCallback((effectiveIp) => {
        setSelectedForBatch((prev) => {
            const next = new Set(prev);
            if (next.has(effectiveIp)) {
                next.delete(effectiveIp);
            } else {
                next.add(effectiveIp);
            }
            return next;
        });
    }, []);

    const setBatchSlot = useCallback((ip, slot) => {
        setBatchSlots((prev) => ({ ...prev, [ip]: slot }));
    }, []);

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!canSubmit) return;

        setStatus('verifying');
        setErrorMessage(null);

        const body = {
            ip,
            entity_type: entityType,
            group_id: groupId,
            slot,
        };
        if (name.trim()) {
            body.name = name.trim();
        }

        try {
            const response = await fetch('/api/entities', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(body)
            });
            if (!response.ok) {
                const detail = await response.json().catch(() => ({}));
                const reason = detail?.detail?.error || detail?.detail || `HTTP ${response.status}`;
                setStatus('error');
                setErrorMessage(String(reason));
                showToast(String(reason), 'error');
                return;
            }
            const data = await response.json();
            // Success
            showToast(
                `${data.name || 'Entity'} (${data.ip}) added to ${groupId}/${slot}`,
                'success'
            );
            onEntityAdded(data);
            handleClose();
        } catch {
            setStatus('error');
            setErrorMessage('Failed to add entity. Check agent is running.');
        }
    };

    // Batch slot occupancy: combines existing entities + already-submitted batch entries
    const batchSlotOccupancy = useMemo(() => {
        const map = {};
        if (!existingEntities || !batchGroupId) return map;
        for (const e of existingEntities) {
            if (e.group_id === batchGroupId && e.slot) {
                map[e.slot] = e.name || e.id;
            }
        }
        // Also mark slots assigned to other batch rows
        for (const [bip, bslot] of Object.entries(batchSlots)) {
            if (bslot && selectedForBatch.has(bip)) {
                if (!map[bslot]) {
                    // Find scan result by effective IP (bip may be the chosen IP, not sr.ip)
                    const r = scanResults && scanResults.find((sr) => getEffectiveIp(sr) === bip || sr.ip === bip);
                    map[bslot] = r ? (r.hostname || bip) : bip;
                }
            }
        }
        return map;
    }, [existingEntities, batchGroupId, batchSlots, selectedForBatch, scanResults, getEffectiveIp]);

    const canBatchSubmit = useMemo(() => {
        if (!batchGroupId.trim() || selectedForBatch.size === 0 || batchAdding) return false;
        for (const batchIp of selectedForBatch) {
            const s = batchSlots[batchIp];
            if (!s) return false;
            const type = getBatchType(batchIp);
            if (type === 'vehicle') {
                if (s !== 'vehicle') return false;
            } else {
                if (!/^arm-[1-9][0-9]*$/.test(s)) return false;
            }
        }
        return true;
    }, [batchGroupId, selectedForBatch, batchSlots, batchAdding, getBatchType]);

    const handleBatchSubmit = async () => {
        if (!canBatchSubmit) return;
        setBatchAdding(true);
        setBatchErrors([]);

        const errors = [];
        let successCount = 0;

        for (const batchIp of selectedForBatch) {
            const type = getBatchType(batchIp);
            const batchSlot = batchSlots[batchIp];
            const r = scanResults && scanResults.find((sr) => getEffectiveIp(sr) === batchIp || sr.ip === batchIp);

            const body = {
                ip: batchIp,
                entity_type: type,
                group_id: batchGroupId.trim(),
                slot: batchSlot,
            };
            if (r && r.hostname) {
                body.name = r.hostname;
            }

            try {
                const response = await fetch('/api/entities', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                if (!response.ok) {
                    const detail = await response.json().catch(() => ({}));
                    const reason = detail?.detail?.error || detail?.detail || `HTTP ${response.status}`;
                    errors.push({ ip: batchIp, error: String(reason) });
                } else {
                    const data = await response.json();
                    onEntityAdded(data);
                    successCount++;
                }
            } catch {
                errors.push({ ip: batchIp, error: 'Network error' });
            }
        }

        setBatchAdding(false);
        setBatchErrors(errors);

        if (successCount > 0) {
            showToast(
                `Added ${successCount} entity(s) to ${batchGroupId.trim()}`,
                'success'
            );
        }
        if (errors.length > 0) {
            showToast(
                `${errors.length} failed to add`,
                'error'
            );
        }
        if (errors.length === 0) {
            handleClose();
        } else {
            // Remove successfully added IPs from selection
            setSelectedForBatch((prev) => {
                const next = new Set(prev);
                for (const batchIp of prev) {
                    if (!errors.some((e) => e.ip === batchIp)) {
                        next.delete(batchIp);
                    }
                }
                return next;
            });
        }
    };

    // Estimate scan size for user info
    const subnetParts = scanSubnet.trim().split(".");
    const estimatedHosts = subnetParts.length === 3 ? 253
        : subnetParts.length === 2 ? "~65K" : "?";

    return html`
        <div class="modal-overlay" onClick=${handleOverlayClick}>
            <div class="modal-content" style=${{ maxWidth: "520px" }}>
                <div class="modal-header">
                    <h3>Add Entity to Fleet</h3>
                </div>

                <div class="modal-body">
                    <!-- Subnet scan section -->
                    <div style=${{
                        marginBottom: "20px",
                        padding: "12px",
                        borderRadius: "6px",
                        backgroundColor: "var(--bg-tertiary, #f9fafb)",
                        border: "1px solid var(--border-color, #e5e7eb)",
                    }}>
                        <div style=${{
                            fontSize: "0.85rem",
                            fontWeight: "600",
                            marginBottom: "8px",
                        }}>
                            Scan Network for Agents
                        </div>
                        <div style=${{
                            display: "flex",
                            gap: "8px",
                            alignItems: "center",
                            flexWrap: "wrap",
                        }}>
                            <input
                                type="text"
                                value=${scanSubnet}
                                onInput=${(e) => setScanSubnet(e.target.value)}
                                placeholder="192.168.137"
                                disabled=${scanning}
                                style=${{
                                    flex: "1",
                                    minWidth: "140px",
                                    padding: "6px 10px",
                                    fontSize: "0.85rem",
                                    borderRadius: "4px",
                                    border: "1px solid var(--border-color, #d1d5db)",
                                }}
                            />
                            <button
                                type="button"
                                class="btn"
                                onClick=${handleScan}
                                disabled=${scanning || !scanSubnet.trim()}
                                style=${{
                                    padding: "6px 14px",
                                    fontSize: "0.85rem",
                                    whiteSpace: "nowrap",
                                }}
                            >
                                ${scanning ? "Scanning..." : "Scan"}
                            </button>
                        </div>
                        <div style=${{
                            fontSize: "0.72rem",
                            color: "var(--color-text-muted)",
                            marginTop: "4px",
                        }}>
                            Scans ${estimatedHosts} hosts on port 8091. Use 2 octets (e.g. 192.168) for /16, 3 octets for /24.
                        </div>

                        ${scanError && html`
                            <div style=${{
                                marginTop: "8px",
                                fontSize: "0.8rem",
                                color: "var(--color-error, #ef4444)",
                            }}>
                                ${scanError}
                            </div>
                        `}

                        <!-- Scan results -->
                        ${scanResults !== null && html`
                            <div style=${{ marginTop: "10px" }}>
                                ${scanResults.length === 0 && html`
                                    <div style=${{
                                        fontSize: "0.8rem",
                                        color: "var(--color-text-muted)",
                                        fontStyle: "italic",
                                    }}>
                                        No devices found on ${scanSubnet}.*
                                    </div>
                                `}
                                ${scanResults.length > 0 && html`
                                    <div style=${{
                                        fontSize: "0.78rem",
                                        color: "var(--color-text-muted)",
                                        marginBottom: "6px",
                                    }}>
                                        Found ${scanResults.length} device(s). Click row to fill form, or check to batch-add:
                                    </div>
                                    <div style=${{
                                        maxHeight: "200px",
                                        overflowY: "auto",
                                        display: "flex",
                                        flexDirection: "column",
                                        gap: "4px",
                                    }}>
                                        ${scanResults.map((r) => {
                                            const effectiveIp = getEffectiveIp(r);
                                            const isMultiIp = r.ips && r.ips.length > 1;
                                            const isSelected = ip === effectiveIp;
                                            const isInBatch = selectedForBatch.has(effectiveIp);
                                            return html`
                                            <div
                                                key=${r.hostname || r.ip}
                                                style=${{
                                                    display: "flex",
                                                    alignItems: "center",
                                                    gap: "8px",
                                                    padding: "6px 10px",
                                                    borderRadius: "4px",
                                                    border: isSelected
                                                        ? "2px solid var(--accent-primary, #3b82f6)"
                                                        : isInBatch
                                                            ? "2px solid var(--color-success, #22c55e)"
                                                            : "1px solid var(--border-color, #e5e7eb)",
                                                    backgroundColor: r.already_configured
                                                        ? "var(--bg-tertiary, #f3f4f6)"
                                                        : isInBatch
                                                            ? "color-mix(in srgb, var(--color-success, #22c55e) 8%, transparent)"
                                                            : (isSelected ? "color-mix(in srgb, var(--accent-primary, #3b82f6) 8%, transparent)" : "transparent"),
                                                    opacity: r.already_configured ? "0.6" : "1",
                                                    fontSize: "0.82rem",
                                                }}
                                            >
                                                <!-- Checkbox for batch select -->
                                                <input
                                                    type="checkbox"
                                                    checked=${isInBatch}
                                                    disabled=${r.already_configured}
                                                    onChange=${() => toggleBatchSelect(effectiveIp)}
                                                    onClick=${(e) => e.stopPropagation()}
                                                    style=${{
                                                        flexShrink: "0",
                                                        cursor: r.already_configured ? "not-allowed" : "pointer",
                                                    }}
                                                />
                                                <!-- Clickable row content for single-select -->
                                                <div
                                                    onClick=${() => !r.already_configured && handleSelectScanResult(r)}
                                                    style=${{
                                                        display: "flex",
                                                        alignItems: "center",
                                                        justifyContent: "space-between",
                                                        flex: "1",
                                                        cursor: r.already_configured ? "not-allowed" : "pointer",
                                                        minWidth: "0",
                                                    }}
                                                >
                                                    <div style=${{ display: "flex", alignItems: "center", gap: "6px", minWidth: "0" }}>
                                                        <span style=${{
                                                            width: "6px",
                                                            height: "6px",
                                                            borderRadius: "50%",
                                                            backgroundColor: r.status === "agent_found"
                                                                ? "var(--color-success, #22c55e)"
                                                                : "var(--color-warning, #f59e0b)",
                                                            flexShrink: "0",
                                                        }}></span>
                                                        ${r.hostname
                                                            ? html`
                                                                <span style=${{ fontWeight: "500" }}>${r.hostname}</span>
                                                                ${!isMultiIp && html`
                                                                    <span style=${{ color: "var(--color-text-muted)", fontSize: "0.75rem" }}>
                                                                        (${r.ip})
                                                                    </span>
                                                                `}
                                                            `
                                                            : html`
                                                                <span style=${{ fontWeight: "500" }}>${r.ip}</span>
                                                            `
                                                        }
                                                        ${isMultiIp && html`
                                                            <select
                                                                value=${effectiveIp}
                                                                onChange=${(e) => {
                                                                    e.stopPropagation();
                                                                    const newIp = e.target.value;
                                                                    const key = r.hostname || r.ip;
                                                                    setSelectedIps((prev) => ({ ...prev, [key]: newIp }));
                                                                    // If this device is already in the batch, update the batch selection
                                                                    const oldIp = effectiveIp;
                                                                    if (selectedForBatch.has(oldIp)) {
                                                                        setSelectedForBatch((prev) => {
                                                                            const next = new Set(prev);
                                                                            next.delete(oldIp);
                                                                            next.add(newIp);
                                                                            return next;
                                                                        });
                                                                        // Migrate batch slot assignment to new IP
                                                                        setBatchSlots((prev) => {
                                                                            const next = { ...prev };
                                                                            if (next[oldIp] !== undefined) {
                                                                                next[newIp] = next[oldIp];
                                                                                delete next[oldIp];
                                                                            }
                                                                            return next;
                                                                        });
                                                                    }
                                                                    // If this device was in the single-select IP field, update it
                                                                    if (ip === oldIp) {
                                                                        setIp(newIp);
                                                                    }
                                                                }}
                                                                onClick=${(e) => e.stopPropagation()}
                                                                style=${{
                                                                    fontSize: "0.72rem",
                                                                    padding: "1px 4px",
                                                                    border: "1px solid var(--border-color, #e5e7eb)",
                                                                    borderRadius: "3px",
                                                                    backgroundColor: "transparent",
                                                                    color: "var(--color-text-muted)",
                                                                    cursor: "pointer",
                                                                    maxWidth: "140px",
                                                                }}
                                                            >
                                                                ${r.ips.map((ipOption) => html`
                                                                    <option key=${ipOption} value=${ipOption}>${ipOption}</option>
                                                                `)}
                                                            </select>
                                                        `}
                                                    </div>
                                                    <div style=${{ display: "flex", alignItems: "center", gap: "6px", flexShrink: "0" }}>
                                                        ${r.entity_type && html`
                                                            <span style=${{
                                                                fontSize: "0.65rem",
                                                                padding: "1px 5px",
                                                                borderRadius: "6px",
                                                                backgroundColor: "var(--bg-tertiary, #f3f4f6)",
                                                                border: "1px solid var(--border-color, #e5e7eb)",
                                                                textTransform: "uppercase",
                                                            }}>
                                                                ${r.entity_type}
                                                            </span>
                                                        `}
                                                        ${r.already_configured && html`
                                                            <span style=${{
                                                                fontSize: "0.65rem",
                                                                padding: "1px 5px",
                                                                borderRadius: "6px",
                                                                backgroundColor: "var(--color-warning, #f59e0b)",
                                                                color: "#fff",
                                                            }}>
                                                                Configured
                                                            </span>
                                                        `}
                                                        ${r.status === "host_found" && html`
                                                            <span style=${{
                                                                fontSize: "0.65rem",
                                                                padding: "1px 5px",
                                                                borderRadius: "6px",
                                                                backgroundColor: "var(--color-text-muted, #6b7280)",
                                                                color: "#fff",
                                                            }}>
                                                                No Agent
                                                            </span>
                                                        `}
                                                    </div>
                                                </div>
                                            </div>
                                        `; })}
                                    </div>
                                `}
                            </div>
                        `}
                    </div>

                    <!-- Batch assignment section (shown when checkboxes selected) -->
                    ${selectedForBatch.size > 0 && html`
                        <div style=${{
                            marginBottom: "20px",
                            padding: "12px",
                            borderRadius: "6px",
                            backgroundColor: "color-mix(in srgb, var(--color-success, #22c55e) 5%, var(--bg-tertiary, #f9fafb))",
                            border: "1px solid var(--color-success, #22c55e)",
                        }}>
                            <div style=${{
                                fontSize: "0.85rem",
                                fontWeight: "600",
                                marginBottom: "10px",
                            }}>
                                Batch Add ${selectedForBatch.size} Device(s)
                            </div>

                            <!-- Shared group -->
                            <div style=${{ marginBottom: "10px" }}>
                                <label style=${{ fontSize: "0.78rem", fontWeight: "500", display: "block", marginBottom: "4px" }}>
                                    Target Group <span style="color: #ef4444;">*</span>
                                </label>
                                <input
                                    type="text"
                                    list="batch-group-suggestions"
                                    value=${batchGroupId}
                                    onInput=${(e) => setBatchGroupId(e.target.value)}
                                    placeholder="tabletop-lab"
                                    disabled=${batchAdding}
                                    style=${{
                                        width: "100%",
                                        padding: "6px 10px",
                                        fontSize: "0.82rem",
                                        borderRadius: "4px",
                                        border: "1px solid var(--border-color, #d1d5db)",
                                        boxSizing: "border-box",
                                    }}
                                />
                                <datalist id="batch-group-suggestions">
                                    <option value="tabletop-lab"></option>
                                    <option value="machine-1"></option>
                                </datalist>
                            </div>

                            <!-- Per-device slot assignment table -->
                            <div style=${{
                                fontSize: "0.78rem",
                                maxHeight: "200px",
                                overflowY: "auto",
                            }}>
                                <table style=${{ width: "100%", borderCollapse: "collapse", fontSize: "0.78rem" }}>
                                    <thead>
                                        <tr style=${{ borderBottom: "1px solid var(--border-color, #e5e7eb)" }}>
                                            <th style=${{ textAlign: "left", padding: "4px 6px", fontWeight: "600" }}>IP</th>
                                            <th style=${{ textAlign: "left", padding: "4px 6px", fontWeight: "600" }}>Name</th>
                                            <th style=${{ textAlign: "left", padding: "4px 6px", fontWeight: "600" }}>Type</th>
                                            <th style=${{ textAlign: "left", padding: "4px 6px", fontWeight: "600" }}>Slot *</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        ${Array.from(selectedForBatch).map((batchIp) => {
                                            const r = scanResults && scanResults.find((sr) => getEffectiveIp(sr) === batchIp || sr.ip === batchIp);
                                            const type = getBatchType(batchIp);
                                            const scannedType = (r && r.entity_type) || '';
                                            const hostname = (r && r.hostname) || '';
                                            const currentSlot = batchSlots[batchIp] || '';
                                            return html`
                                                <tr key=${batchIp} style=${{ borderBottom: "1px solid var(--border-color, #e5e7eb)" }}>
                                                    <td style=${{ padding: "4px 6px", fontFamily: "monospace" }}>${batchIp}</td>
                                                    <td style=${{ padding: "4px 6px", color: hostname ? "inherit" : "var(--color-text-muted)" }}>
                                                        ${hostname || '(auto)'}
                                                    </td>
                                                    <td style=${{ padding: "4px 6px" }}>
                                                        <select
                                                            value=${type}
                                                            onChange=${(e) => setBatchType(batchIp, e.target.value)}
                                                            disabled=${batchAdding || (scannedType !== '')}
                                                            title=${scannedType ? `Detected by agent as ${scannedType}` : 'No agent detected — select type manually'}
                                                            style=${{
                                                                fontSize: "0.78rem",
                                                                padding: "2px 4px",
                                                                width: "100%",
                                                                opacity: scannedType ? "0.8" : "1",
                                                                cursor: scannedType ? "not-allowed" : "pointer",
                                                            }}
                                                        >
                                                            <option value="arm">arm</option>
                                                            <option value="vehicle">vehicle</option>
                                                        </select>
                                                    </td>
                                                    <td style=${{ padding: "4px 6px" }}>
                                                        ${type === 'vehicle'
                                                            ? html`
                                                                <select
                                                                    value=${currentSlot}
                                                                    onChange=${(e) => setBatchSlot(batchIp, e.target.value)}
                                                                    disabled=${batchAdding}
                                                                    style=${{ fontSize: "0.78rem", padding: "2px 4px", width: "100%" }}
                                                                >
                                                                    <option value="">--</option>
                                                                    <option value="vehicle">
                                                                        vehicle${batchSlotOccupancy["vehicle"] && batchSlots[batchIp] !== "vehicle" ? ` \u26A0` : ""}
                                                                    </option>
                                                                </select>
                                                            `
                                                            : html`
                                                                <select
                                                                    value=${currentSlot}
                                                                    onChange=${(e) => setBatchSlot(batchIp, e.target.value)}
                                                                    disabled=${batchAdding}
                                                                    style=${{ fontSize: "0.78rem", padding: "2px 4px", width: "100%" }}
                                                                >
                                                                    <option value="">--</option>
                                                                    ${ARM_SLOTS.map((s) => {
                                                                        const occupant = batchSlotOccupancy[s];
                                                                        const selfAssigned = batchSlots[batchIp] === s;
                                                                        return html`
                                                                            <option key=${s} value=${s}>
                                                                                ${s}${occupant && !selfAssigned ? ` \u26A0 (${occupant})` : ""}
                                                                            </option>
                                                                        `;
                                                                    })}
                                                                </select>
                                                            `
                                                        }
                                                    </td>
                                                </tr>
                                            `;
                                        })}
                                    </tbody>
                                </table>
                            </div>

                            <!-- Batch errors -->
                            ${batchErrors.length > 0 && html`
                                <div style=${{ marginTop: "8px" }}>
                                    ${batchErrors.map((err) => html`
                                        <div key=${err.ip} style=${{
                                            fontSize: "0.75rem",
                                            color: "var(--color-error, #ef4444)",
                                            padding: "2px 0",
                                        }}>
                                            ${err.ip}: ${err.error}
                                        </div>
                                    `)}
                                </div>
                            `}

                            <!-- Batch submit button -->
                            <div style=${{ marginTop: "10px", display: "flex", justifyContent: "flex-end" }}>
                                <button
                                    type="button"
                                    class="btn btn-primary"
                                    onClick=${handleBatchSubmit}
                                    disabled=${!canBatchSubmit}
                                    style=${{
                                        padding: "6px 16px",
                                        fontSize: "0.82rem",
                                        background: !canBatchSubmit ? "#9ca3af" : "var(--color-success, #22c55e)",
                                        color: "white",
                                        border: "none",
                                        borderRadius: "4px",
                                        cursor: !canBatchSubmit ? "not-allowed" : "pointer",
                                    }}
                                >
                                    ${batchAdding ? "Adding..." : `Add ${selectedForBatch.size} to ${batchGroupId || '...'}`}
                                </button>
                            </div>
                        </div>
                    `}

                    <!-- Divider when batch is active -->
                    ${selectedForBatch.size > 0 && html`
                        <div style=${{
                            fontSize: "0.75rem",
                            color: "var(--color-text-muted)",
                            textAlign: "center",
                            margin: "0 0 12px 0",
                            fontStyle: "italic",
                        }}>
                            \u2014 or add a single entity below \u2014
                        </div>
                    `}

                    <form class="add-entity-form" onSubmit=${handleSubmit}>
                        <div class="form-field">
                            <label for="entity-type">Entity Type:</label>
                            <div class="radio-group" >
                                <label >
                                    <input
                                        type="radio"
                                        name="entityType"
                                        value="arm"
                                        checked=${entityType === 'arm'}
                                        onChange=${(e) => {
                                            setEntityType(e.target.value);
                                            setSlot('');
                                        }}
                                        disabled=${status === 'verifying'}
                                    />
                                    Arm
                                </label>
                                <label >
                                    <input
                                        type="radio"
                                        name="entityType"
                                        value="vehicle"
                                        checked=${entityType === 'vehicle'}
                                        onChange=${(e) => {
                                            setEntityType(e.target.value);
                                            setSlot('vehicle');
                                        }}
                                        disabled=${status === 'verifying'}
                                    />
                                    Vehicle
                                </label>
                            </div>
                        </div>

                        <div class="form-field" style="margin-bottom: 1rem;">
                            <label for="entity-group">Target Group <span style="color: #ef4444;">*</span></label>
                            <input
                                id="entity-group"
                                type="text"
                                list="entity-group-suggestions"
                                value=${groupId}
                                onInput=${(e) => {
                                    setGroupId(e.target.value);
                                    if (status === 'error') setStatus('idle');
                                }}
                                placeholder="machine-1"
                                disabled=${status === 'verifying'}
                            />
                            <datalist id="entity-group-suggestions">
                                <option value="tabletop-lab"></option>
                                <option value="machine-1"></option>
                            </datalist>
                        </div>

                        <div class="form-field" style="margin-bottom: 1rem;">
                            <label for="entity-slot">Target Slot <span style="color: #ef4444;">*</span></label>
                            ${entityType === 'vehicle'
                                ? html`
                                    <select
                                        id="entity-slot"
                                        value=${slot}
                                        onChange=${(e) => {
                                            setSlot(e.target.value);
                                            if (status === 'error') setStatus('idle');
                                        }}
                                        disabled=${status === 'verifying'}
                                    >
                                        <option value="">Select slot</option>
                                        <option value="vehicle">
                                            vehicle${slotOccupancy["vehicle"] ? ` \u26A0 (${slotOccupancy["vehicle"]})` : ""}
                                        </option>
                                    </select>
                                `
                                : html`
                                    <select
                                        id="entity-slot"
                                        value=${slot}
                                        onChange=${(e) => {
                                            setSlot(e.target.value);
                                            if (status === 'error') setStatus('idle');
                                        }}
                                        disabled=${status === 'verifying'}
                                    >
                                        <option value="">Select slot</option>
                                        ${ARM_SLOTS.map((s) => {
                                            const occupant = slotOccupancy[s];
                                            return html`
                                                <option key=${s} value=${s}>
                                                    ${s}${occupant ? ` \u26A0 (${occupant})` : ""}
                                                </option>
                                            `;
                                        })}
                                    </select>
                                `}
                            ${slot && slotOccupancy[slot] && html`
                                <div style=${{
                                    fontSize: "0.75rem",
                                    color: "var(--color-warning, #f59e0b)",
                                    marginTop: "4px",
                                }}>
                                    Slot occupied by ${slotOccupancy[slot]}. Adding will cause a conflict.
                                </div>
                            `}
                        </div>

                        <div class="form-field" style="margin-bottom: 1rem;">
                            <label for="entity-ip">IP Address <span style="color: #ef4444;">*</span></label>
                            <input
                                id="entity-ip"
                                type="text"
                                value=${ip}
                                onInput=${(e) => {
                                    setIp(e.target.value);
                                    if (status === 'error') setStatus('idle');
                                }}
                                placeholder="192.168.x.x"
                                disabled=${status === 'verifying'}
                                class=${validationMsg ? 'error-input' : ''} style=${{ borderColor: validationMsg ? "var(--color-error, #ef4444)" : undefined }}
                            />
                            ${validationMsg && html`<div class="form-error" >${validationMsg}</div>`}
                        </div>

                        <div class="form-field" style="margin-bottom: 1.5rem;">
                            <label for="entity-name">Entity Name (Optional)</label>
                            <input
                                id="entity-name"
                                type="text"
                                value=${name}
                                onInput=${(e) => setName(e.target.value)}
                                placeholder=${entityType === 'arm' ? 'Auto-generated (e.g. Arm 3 RPi)' : 'Vehicle RPi'}
                                disabled=${status === 'verifying'}

                            />
                        </div>

                        ${status === 'error' && errorMessage && html`
                            <div class="form-error" style="background: var(--bg-tertiary); border: 1px solid var(--color-error);">
                                ${errorMessage}
                            </div>
                        `}

                        <div style="display: flex; justify-content: flex-end; gap: 0.5rem; margin-top: 1rem;">
                            <button
                                type="button"
                                class="btn btn-secondary"
                                onClick=${handleClose}
                                disabled=${status === 'verifying'}
                                style="padding: 0.5rem 1rem; border: 1px solid #d1d5db; background: white; border-radius: 4px; cursor: pointer;"
                            >
                                Cancel
                            </button>
                            <button
                                type="submit"
                                class="btn btn-primary"
                                disabled=${!canSubmit}
                                style="padding: 0.5rem 1rem; background: ${!canSubmit ? '#9ca3af' : '#2563eb'}; color: white; border: none; border-radius: 4px; cursor: ${!canSubmit ? 'not-allowed' : 'pointer'};"
                            >
                                ${status === 'verifying' ? 'Verifying...' : 'Verify & Add'}
                            </button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    `;
}
