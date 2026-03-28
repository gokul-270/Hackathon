# Field Trial Checklist

**Purpose:** Reusable checklist for cotton-picking robot field trials.
Copy this file before each trial and check off items as completed.

---

## Phase 1: Packing (Day Before)

### Electronics

- [ ] Raspberry Pi 4B units (arm controllers) — qty: ___
- [ ] Raspberry Pi 4B unit (vehicle controller) — qty: 1
- [ ] OAK-D Lite cameras — qty: ___
- [ ] IO boards — qty: ___
- [ ] Power box — verify push button not sticking
- [ ] E-Stop button — verify mounted in panel (not loose)
- [ ] Power supplies and batteries — fully charged
- [ ] CAN cables — qty: ___ (+ spares)
- [ ] USB cables (RPi power, camera connections)
- [ ] SD cards (pre-flashed spares)
- [ ] Ethernet cables (for field SSH access)
- [ ] WiFi router / hotspot device

### Spare Parts

- [ ] Spare EE motor (MG6012)
- [ ] Diodes
- [ ] Fuses
- [ ] Spare belts (arm timing belts)
- [ ] Connectors (CAN, power)
- [ ] Zip ties
- [ ] Electrical tape
- [ ] Heat shrink tubing

### Tools

- [ ] Allen key set
- [ ] Screwdriver set (Phillips + flathead)
- [ ] Adjustable spanner
- [ ] Wire cutter
- [ ] Cutting plier
- [ ] Multimeter
- [ ] Knife / utility blade
- [ ] Tyre inflator (portable, with gauge)
- [ ] Cable ties / tags (for labeling)

### Packing / Transport

- [ ] Bubble wrap (for cameras, electronics)
- [ ] Foam padding for arm transport
- [ ] Tie-down straps for vehicle on trailer/truck
- [ ] Toolbox / organizer for small parts

### Documentation

- [ ] Field trial plan (printed)
- [ ] Motor protection guide (printed)
- [ ] Troubleshooting guide (printed)
- [ ] ROS2 quick reference commands (printed)
- [ ] This checklist (printed)

### Recording

- [ ] Camera / phone (for photos and video)
- [ ] Notebook + pen (field observations)
- [ ] Measuring tape (row spacing, heights)

---

## Phase 2: Pre-Departure (Morning of Trial)

### Vehicle

- [ ] Tyre pressure checked — all tyres inflated to spec
- [ ] Tyre inflator loaded in vehicle (for field top-ups)
- [ ] Fuel / charge level adequate for round trip + field time
- [ ] Robot secured for transport (arms locked, nothing loose)

### Software

- [ ] Latest firmware deployed to all RPi units (`sync.sh --deploy-cross`)
- [ ] RTC clock synced on all RPis (prevents provision failures)
- [ ] Unit tests passing on deployed build
- [ ] Model files present on all arm RPis (YOLOX / detection model)
- [ ] Log directories created and writable

### Electronics Pre-Check

- [ ] Power box powers on, push button works
- [ ] E-Stop triggers and resets correctly
- [ ] Each RPi boots and connects to network
- [ ] CAN bus communication verified (quick motor ping)
- [ ] Camera feeds confirmed (quick detection test)

### Packing Verification

- [ ] Cross-check all Phase 1 items loaded
- [ ] Spare parts bag present
- [ ] Tools bag present
- [ ] Documentation folder present

---

## Phase 3: At-Field Setup

### Site Assessment

- [ ] Row spacing measured and recorded: ___ feet / ___ m
- [ ] Cotton density assessed (sparse / moderate / dense)
- [ ] Terrain condition (dry / muddy / uneven)
- [ ] Sunlight direction noted (affects camera exposure)
- [ ] Shade / work area identified for laptops/tools

### Robot Setup

- [ ] Robot unloaded and positioned at start of row
- [ ] Arms unfolded / unlocked from transport position
- [ ] All CAN cables connected
- [ ] Cameras mounted and secured
- [ ] Power connected, power box ON
- [ ] E-Stop accessible and tested

### Software Boot

- [ ] All RPi units powered and booted
- [ ] SSH access confirmed to each RPi
- [ ] ROS2 nodes launched successfully
- [ ] Camera feeds live — check exposure, no overexposure from sun
- [ ] Detection model running — verify detections on live cotton
- [ ] Motor controllers responding (home sequence or quick jog)
- [ ] MQTT bridge connected (if multi-arm)
- [ ] Logging confirmed — check log files being written

### Safety

- [ ] E-Stop tested in field conditions
- [ ] Emergency procedures briefed to all present
- [ ] Safe standoff distance established for observers
- [ ] First aid kit accessible

### Data Collection Start

- [ ] Session start time recorded: ___
- [ ] Trial identifier / run number: ___
- [ ] Weather conditions noted: ___
- [ ] Video recording started (if applicable)

---

## Phase 4: Post-Trial (Before Leaving Field)

### Data Collection

- [ ] Session end time recorded: ___
- [ ] Total picks attempted / successful: ___ / ___
- [ ] Collect logs from all RPis (`sync.sh --collect-logs`)
- [ ] Verify log files are non-empty and complete
- [ ] Copy detection images from arm RPis
- [ ] Save any field video / photos
- [ ] Record field observations (notebook entries, anomalies)

### Inspection

- [ ] Check arms for mechanical damage or loose parts
- [ ] Check belts for wear, slipping, or breakage
- [ ] Check EE rollers for cotton/seed jamming
- [ ] Check motor temperatures (by touch if no sensor)
- [ ] Check camera mounts — still secure?
- [ ] Note any unusual sounds, smells, or behavior

### Shutdown

- [ ] ROS2 nodes stopped gracefully
- [ ] Motors de-energized
- [ ] Power box OFF
- [ ] E-Stop engaged for transport
- [ ] Arms folded / locked for transport

### Pack Up

- [ ] All tools accounted for (cross-check Phase 1 tools list)
- [ ] All spare parts accounted for
- [ ] All cables disconnected and coiled
- [ ] Robot secured for transport
- [ ] Site left clean (no debris, cables, packaging)

---

## Notes

_Use this space for trial-specific notes, issues encountered, or items to add for next time._

| Item | Note |
|------|------|
|      |      |
|      |      |
|      |      |
