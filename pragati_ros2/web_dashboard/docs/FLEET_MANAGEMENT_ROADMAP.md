# Fleet Management Roadmap
**Status:** Planning
**Created:** 2026-03-18
**Scope:** Dashboard-led fleet management for table-top setups and multi-machine deployments

## 1. Problem Statement
The current dashboard model is centered on flat entities such as `arm` and `vehicle`. That is no longer enough for the expected deployment model.

The dashboard needs to support:
- **Table-top setups** with only arms
- **Machine deployments** where one machine contains one vehicle controller and multiple arms
- **Multiple machines** managed from one dev dashboard
- **Cross-machine comparison** such as `machine-1/arm-1` vs `machine-2/arm-1`
- **Controlled config replication** between matching members

The key shift is:
- the dashboard should manage a **fleet of groups**
- each group contains **members**
- members must be understood by **role and slot**, not just by IP

## 2. Target Operator Workflows

### 2.1 Manage a table-top setup
An operator creates a group called `tabletop-lab` and assigns two arms to it. The dashboard shows them together, lets the operator compare them, and later copy approved Pragati configuration from one arm to the other.

### 2.2 Manage a deployed machine
An operator creates `machine-1` and attaches:
- one vehicle member
- one or more arm members

The dashboard shows machine health as a group and lets the operator drill into each member.

### 2.3 Compare matching slots across machines
An operator compares:
- `machine-1/arm-1`
- `machine-2/arm-1`

The intent is usually not “compare any two random RPis,” but “compare the same physical role across machines.”

### 2.4 Copy approved Pragati configuration
An operator selects a known-good source such as `machine-1/arm-2`, reviews a diff, and applies selected Pragati-managed configuration to `machine-2/arm-2`.

### 2.5 Review discovered devices before trusting them
A newly discovered RPi should not immediately become a trusted fleet member. It should first appear as a candidate, then be approved into a group and assigned a slot.

## 3. Core Domain Model

### 3.1 Group-first model
The primary object should be **Group**, not standalone entity.

Recommended hierarchy:

```text
Fleet
├── Group: tabletop-lab
│   ├── Member: arm-1
│   └── Member: arm-2
├── Group: machine-1
│   ├── Member: vehicle
│   ├── Member: arm-1
│   └── Member: arm-2
└── Group: machine-2
    ├── Member: vehicle
    └── Member: arm-1
```

### 3.2 Group
A group represents one logical setup the operator manages as a unit.

Examples:
- `tabletop-lab`
- `machine-1`
- `machine-2`

Group attributes should include:
- `group_id`
- `display_name`
- `group_type` (`tabletop`, `machine`, `custom`)
- `network_context`
- `metadata` such as location, notes, expected topology

### 3.3 Member
A member is a device or logical node inside a group.

Examples:
- `vehicle`
- `arm-1`
- `arm-2`

Member attributes should include:
- `member_id`
- `group_id`
- `member_role` (`vehicle`, `arm`)
- `slot` (`vehicle`, `arm-1`, `arm-2`, ...)
- `identity`
- `endpoints`
- operational state and health

### 3.4 Slot
`slot` is important and should be explicit.

Examples:
- `vehicle`
- `arm-1`
- `arm-2`

Why this matters:
- compare should usually happen across the same slot
- copy should usually happen across the same slot
- discovery approval needs to attach a candidate to a known slot
- the UI should reflect expected machine layout, not only discovered names

### 3.5 Identity vs endpoint
This is a critical design rule:

- **Identity is not IP**
- **IP is only an endpoint**

The roadmap should treat these separately.

#### Identity
Identity is stable and represents “which member this is.”

Examples:
- generated UUID
- persisted agent identity
- stable dashboard-assigned member identity

#### Endpoint
Endpoint is how the dashboard currently reaches the member.

Examples:
- `192.168.137.12:8091`
- `10.0.0.5:8091`
- proxied or forwarded host/port

Endpoints may change due to:
- DHCP
- different physical network
- NAT or port forwarding
- lab vs field setup

This means duplicate IP checks cannot be the main identity rule.

### 3.6 Network context
Network context defines where an endpoint is valid.

Examples:
- `lab-lan`
- `machine-1-local-net`
- `192.168.137.0/24`

This allows the dashboard to distinguish:
- same endpoint value on different isolated setups
- different routes to the same member

## 4. Discovery and Trust Model

### 4.1 Discovery sources
The dashboard may learn about devices from:
- manual configuration
- approved persisted fleet state
- mDNS or similar local discovery
- manual add by operator

### 4.2 Trust order
Discovery sources should not all be treated equally.

Recommended trust order:
1. **manually configured / persisted approved members**
2. **previously approved discovered members**
3. **freshly discovered candidates**

### 4.3 Candidate state
A newly discovered device should first appear as a **candidate**.

Recommended lifecycle:
- `candidate`
- `approved`
- `offline`
- `removed`

Approval should require:
- assigning the candidate to a group
- assigning a slot
- optionally confirming identity/auth

### 4.4 Discovery behavior
The dashboard should support a hybrid model:
- **manual refresh** from the dev dashboard
- **background discovery** for convenience
- **manual add** for devices not reachable by local discovery

The roadmap should avoid making mDNS the source of truth. It is a convenience, not the fleet model.

## 5. Authentication Model

### 5.1 Separate the two trust boundaries
There are two distinct security problems:

1. **User → dashboard**
2. **Dashboard → agent**

They should be designed separately.

### 5.2 Agent authentication should come early
Minimal agent authentication should be added before advanced compare/copy work.

Reason:
- without agent auth, any reachable client may call agent APIs
- later write operations become high-risk
- discovery trust is weaker without authenticated agents

### 5.3 Recommended phased auth approach

#### Phase A: minimal agent auth
- per-agent API key or equivalent shared secret
- dashboard stores trusted credential mapping per approved member

#### Phase B: basic dashboard auth
- simple single-admin auth or similar low-complexity gate

#### Phase C: stronger enrollment and approval
- secure approval flow for newly discovered candidates

#### Phase D: richer multi-user auth
- only if operational need appears later

## 6. Compare Model

### 6.1 Comparison levels
Comparison across members is useful at four levels:

1. **System**
   - OS version
   - kernel
   - hardware summary
   - systemd/service state

2. **Installed software**
   - ROS packages
   - Python packages
   - installed Pragati software version

3. **Pragati-managed configuration**
   - YAML config
   - selected dashboard-managed settings
   - launch/config artifacts the dashboard understands

4. **Runtime**
   - node state
   - metrics
   - temperatures
   - online/offline status

### 6.2 Comparison scope
The best default comparison target is:
- same `member_role`
- same `slot`
- across different groups

Examples:
- `machine-1/arm-1` vs `machine-2/arm-1`
- `tabletop-lab/arm-1` vs `machine-1/arm-1`

### 6.3 Comparison result style
The roadmap should define comparison as:
- read-only
- operator-focused
- diff-oriented

It should help answer:
- what is different?
- is the difference expected?
- is the difference safe to reconcile?

## 7. Copy Model

### 7.1 Copy must start narrow
The previous version was too broad. Initial copy should be limited to:
- **Pragati-managed configuration only**

It should not start with:
- arbitrary system files
- apt package state
- full ROS install state
- transient runtime state

### 7.2 Initial copy target
Initial supported copy should focus on:
- matching role
- matching slot where sensible
- known dashboard-managed config artifacts

Examples:
- motor profile settings
- selected Pragati YAML config
- selected dashboard-managed agent settings

### 7.3 Copy workflow
Recommended workflow:
1. select source member
2. select target member
3. show semantic diff for supported config items
4. validate compatibility
5. require explicit confirmation
6. apply
7. record audit trail

### 7.4 Copy safety rules
Initial safety rules should include:
- arm → arm only
- vehicle → vehicle only
- runtime values are never copied
- unsupported files/settings are visible but not copyable

## 8. Discovery and Addressing Rules

### 8.1 Duplicate IP handling
The old statement “duplicate IPs are already handled” is not enough for the intended model.

Correct rule:
- duplicate IP is only meaningful within an active network context and endpoint scope
- IP conflict detection is about reachability, not identity

This means the system should not rely on global IP uniqueness.

### 8.2 Addressing model
The dashboard should ideally address a member using:
- stable identity for recordkeeping
- current approved endpoint for communication

This supports:
- same IP reused in different isolated groups
- endpoint changes over time
- forwarded/proxied access paths

## 9. Phased Rollout

### Phase 1: Core fleet model
- introduce group-first fleet model
- add slot semantics
- separate identity from endpoint
- migrate flat entities into group/member representation

### Phase 2: Minimal security and trusted discovery
- add minimal agent auth
- add candidate vs approved discovery states
- make refresh and approval workflow explicit

### Phase 3: Read-only comparison
- group-aware compare UI
- compare by slot across groups
- system/software/config/runtime comparison views

### Phase 4: Controlled config copy
- support only Pragati-managed config
- add validation, confirmation, and audit trail

### Phase 5: Higher-level operational polish
- richer dashboard auth if needed
- better discovery UX
- fleet-level health summaries
- optional templates or baseline profiles

## 10. Must-Decide Questions Before Implementation

### Core model
- Should group membership always be explicit, or can members remain ungrouped?
- Is slot mandatory for machine groups?
- What is the stable identity source for each approved member?

### Discovery
- What makes a discovered candidate trustworthy enough to approve?
- What becomes the source of truth after approval: persisted dashboard state, config, or discovery?
- Should discovery continuously suggest candidates, or only during manual refresh?

### Copy
- Which Pragati config artifacts are officially dashboard-managed in v1?
- Should copy be restricted to same-slot targets at first?

### Security
- What is the minimum acceptable agent auth for first rollout?
- Should dashboard auth be required immediately or only before write operations?

## 11. Deferred Questions
These can wait until after the core model is stable:
- nested groups
- automated key rotation
- OAuth or richer user roles
- VPN/cloud-discovery support
- wide-scope system/software replication

## 12. Recommended Document Split
This document should stay as the **product/architecture roadmap** for fleet management.

Follow-up implementation work should be split into separate changes such as:
- group/member core model
- candidate discovery and approval
- minimal agent auth
- read-only compare
- controlled config copy

That will keep this roadmap stable while implementation details evolve.
