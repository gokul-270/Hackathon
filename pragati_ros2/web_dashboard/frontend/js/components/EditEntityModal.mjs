import { h } from "preact";
import { useState, useContext, useEffect, useRef } from "preact/hooks";
import { html } from "htm/preact";
import { ToastContext } from "../app.js";
import { safeFetch } from "../utils.js";
import { isValidIp, isDuplicateIp } from "./AddEntityModal.mjs";

export function EditEntityModal({ isOpen, onClose, onEntityUpdated, entity, existingEntities }) {
    const { showToast } = useContext(ToastContext);

    const [ip, setIp] = useState('');
    const [name, setName] = useState('');
    const [groupId, setGroupId] = useState('');
    const [slot, setSlot] = useState('');
    const [status, setStatus] = useState('idle'); // idle, verifying, error
    const [errorMessage, setErrorMessage] = useState(null);
    const [fleetEntities, setFleetEntities] = useState(existingEntities || []);

    // Track which entity ID we've initialized from, so we only reset
    // when the actual entity changes — not on every poll refresh.
    const initializedForRef = useRef(null);

    // Fetch existing entities for duplicate validation if not provided
    useEffect(() => {
        if (!existingEntities && isOpen) {
            safeFetch('/api/entities').then((data) => {
                if (data && Array.isArray(data)) {
                    setFleetEntities(data);
                } else if (data && Array.isArray(data.entities)) {
                    setFleetEntities(data.entities);
                }
            });
        }
    }, [existingEntities, isOpen]);

    // Reset fields only when a DIFFERENT entity is opened for editing,
    // not on every parent re-render (which happens on 10s poll refresh).
    useEffect(() => {
        if (entity && isOpen && initializedForRef.current !== entity.id) {
            initializedForRef.current = entity.id;
            setIp(entity.ip || '');
            setName(entity.name || '');
            setGroupId(entity.group_id || '');
            setSlot(entity.slot || '');
            setStatus('idle');
            setErrorMessage(null);
        }
    }, [entity, isOpen]);

    // Clear initialized ref when modal closes so next open re-initializes
    useEffect(() => {
        if (!isOpen) {
            initializedForRef.current = null;
        }
    }, [isOpen]);

    // Early return AFTER all hooks (Preact requires consistent hook ordering)
    if (!isOpen || !entity) return null;

    // Compute which slots are occupied in the selected group (excluding this entity)
    const occupiedSlots = {};
    if (groupId) {
        for (const e of fleetEntities) {
            if (e.id !== entity.id && e.group_id === groupId && e.slot) {
                occupiedSlots[e.slot] = e.name || e.id;
            }
        }
    }

    // Validation
    const ipValid = isValidIp(ip);
    // Ignore duplicate if it's the current entity's IP
    const ipDuplicate = ip !== entity.ip && isDuplicateIp(ip, fleetEntities);
    // Slot is valid when: (a) both group and slot are empty (no assignment), or
    // (b) slot matches the required pattern for the entity type
    const slotValid = !slot
        ? !groupId  // empty slot is OK only if group is also empty
        : entity.entity_type === 'vehicle'
            ? slot === 'vehicle'
            : /^arm-[1-9][0-9]*$/.test(slot);
    const hasChanges =
        ip !== entity.ip ||
        name !== entity.name ||
        groupId !== (entity.group_id || '') ||
        slot !== (entity.slot || '');
    const groupSlotPartial = (groupId && !slot) || (!groupId && slot);
    const canSubmit =
        ipValid && !ipDuplicate && !groupSlotPartial && slotValid && status !== 'verifying' && hasChanges;

    // Derived validation messages
    let validationMsg = null;
    if (ip && !ipValid) validationMsg = 'Enter a valid IPv4 address';
    else if (ip && ipDuplicate) validationMsg = 'This IP is already in the fleet';
    else if (groupSlotPartial) validationMsg = 'Select both group and slot';
    else if (slot && !slotValid) {
        validationMsg = entity.entity_type === 'vehicle'
            ? 'Vehicle slot must be vehicle'
            : 'Arm slot must be arm-N (e.g. arm-3)';
    }

    const handleClose = () => {
        if (status === 'verifying') return;
        onClose();
    };

    const handleOverlayClick = (e) => {
        if (e.target === e.currentTarget) {
            handleClose();
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!canSubmit) return;

        setStatus('verifying');
        setErrorMessage(null);

        const body = {};
        if (ip !== entity.ip) body.ip = ip;
        if (name !== entity.name) body.name = name.trim();
        if (groupId !== (entity.group_id || '')) body.group_id = groupId;
        if (slot !== (entity.slot || '')) body.slot = slot;

        try {
            const response = await fetch(`/api/entities/${encodeURIComponent(entity.id)}`, {
                method: 'PUT',
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
            showToast(`${data.name || 'Entity'} updated successfully`, 'success');
            if (onEntityUpdated) onEntityUpdated(data);
            handleClose();
        } catch {
            setStatus('error');
            setErrorMessage('Failed to update entity. Check agent is running on new IP.');
        }
    };

    return html`
        <div class="modal-overlay" onClick=${handleOverlayClick}>
            <div class="modal-content">
                <div class="modal-header">
                    <h3>Edit Entity</h3>
                </div>

                <div class="modal-body">
                    <form class="add-entity-form" onSubmit=${handleSubmit}>
                        <div class="form-field" style="margin-bottom: 1rem;">
                            <label>Entity ID</label>
                            <input
                                type="text"
                                value=${entity.id}
                                disabled=${true}
                                style="opacity: 0.7; background-color: var(--bg-tertiary);"
                            />
                        </div>

                        <div class="form-field" style="margin-bottom: 1rem;">
                            <label for="edit-entity-ip">IP Address <span style="color: #ef4444;">*</span></label>
                            <input
                                id="edit-entity-ip"
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
                            ${validationMsg && html`<div class="form-error">${validationMsg}</div>`}
                        </div>

                        <div class="form-field" style="margin-bottom: 1.5rem;">
                            <label for="edit-entity-name">Entity Name</label>
                            <input
                                id="edit-entity-name"
                                type="text"
                                value=${name}
                                onInput=${(e) => setName(e.target.value)}
                                disabled=${status === 'verifying'}
                            />
                        </div>

                        <div class="form-field" style="margin-bottom: 1rem;">
                            <label for="edit-entity-group">Target Group</label>
                            <input
                                id="edit-entity-group"
                                type="text"
                                list="edit-group-suggestions"
                                value=${groupId}
                                onInput=${(e) => {
                                    setGroupId(e.target.value);
                                    if (status === 'error') setStatus('idle');
                                }}
                                placeholder="machine-1"
                                disabled=${status === 'verifying'}
                            />
                            <datalist id="edit-group-suggestions">
                                <option value="tabletop-lab"></option>
                                <option value="machine-1"></option>
                            </datalist>
                        </div>

                        <div class="form-field" style="margin-bottom: 1.5rem;">
                            <label for="edit-entity-slot">Target Slot</label>
                            ${entity.entity_type === 'vehicle'
                                ? html`
                                    <select
                                        id="edit-entity-slot"
                                        value=${slot}
                                        onChange=${(e) => {
                                            setSlot(e.target.value);
                                            if (status === 'error') setStatus('idle');
                                        }}
                                        disabled=${status === 'verifying'}
                                    >
                                        <option value="">Select slot</option>
                                        ${(() => {
                                            const taken = occupiedSlots["vehicle"];
                                            return html`<option value="vehicle">
                                                vehicle${taken ? ` \u26A0 (${taken})` : ''}
                                            </option>`;
                                        })()}
                                    </select>
                                `
                                : html`
                                    <select
                                        id="edit-entity-slot"
                                        value=${slot}
                                        onChange=${(e) => {
                                            setSlot(e.target.value);
                                            if (status === 'error') setStatus('idle');
                                        }}
                                        disabled=${status === 'verifying'}
                                    >
                                        <option value="">Select slot</option>
                                        ${[1,2,3,4,5,6].map((n) => {
                                            const slotKey = "arm-" + n;
                                            const takenBy = occupiedSlots[slotKey];
                                            return html`<option
                                                key=${slotKey}
                                                value=${slotKey}
                                            >
                                                ${slotKey}${takenBy ? ` \u26A0 (${takenBy})` : ''}
                                            </option>`;
                                        })}
                                    </select>
                                `}
                            ${slot && occupiedSlots[slot] && html`
                                <div style=${{
                                    fontSize: "0.8rem",
                                    color: "var(--color-warning, #f59e0b)",
                                    marginTop: "4px",
                                }}>
                                    \u26A0 Slot occupied by ${occupiedSlots[slot]}. You'll need to reassign that entity first, or the backend will reject this change.
                                </div>
                            `}
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
                                ${status === 'verifying' ? 'Verifying & Saving...' : 'Save Changes'}
                            </button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    `;
}
