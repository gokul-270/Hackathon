# Tabletop Fleet Test Procedure

Validates fleet hub functionality with 3 physical Raspberry Pi 4B units on a
local network before field deployment.

## Prerequisites

- 3x RPi 4B running Ubuntu 24.04 Server ARM64
- Dev PC (Ubuntu 24.04 desktop or WSL2) on same network
- All RPis provisioned with `./setup_raspberry_pi.sh`
- Dashboard binary deployed to each RPi via `./sync.sh`
- Network switch or router connecting all devices

## Network Setup

| Device     | Role    | Example IP     | Dashboard URL            |
|------------|---------|----------------|--------------------------|
| RPi-1      | vehicle | 192.168.1.100  | http://192.168.1.100:8090 |
| RPi-2      | arm     | 192.168.1.101  | http://192.168.1.101:8090 |
| RPi-3      | arm     | 192.168.1.102  | http://192.168.1.102:8090 |
| Dev PC     | dev     | 192.168.1.10   | http://127.0.0.1:8090     |

Ensure all devices can ping each other before proceeding.

## Config Provisioning

### 1. Vehicle RPi (192.168.1.100)

Edit `dashboard.yaml` on RPi-1:

```yaml
role: vehicle

fleet:
  vehicle:
    name: vehicle-rpi
    ip: 192.168.1.100
  arms:
    - name: arm1-rpi
      ip: 192.168.1.101
    - name: arm2-rpi
      ip: 192.168.1.102

mqtt:
  broker_host: 192.168.1.100
  broker_port: 1883
```

### 2. Arm RPi-2 (192.168.1.101)

Edit `dashboard.yaml` on RPi-2:

```yaml
role: arm

fleet:
  vehicle:
    name: vehicle-rpi
    ip: 192.168.1.100
  arms:
    - name: arm1-rpi
      ip: 192.168.1.101
    - name: arm2-rpi
      ip: 192.168.1.102

mqtt:
  broker_host: 192.168.1.100
  broker_port: 1883
```

### 3. Arm RPi-3 (192.168.1.102)

Same as RPi-2 but with its own IP. The `dashboard.yaml` content is identical
(role: arm, same fleet section, same MQTT broker pointing to vehicle).

### 4. Dev PC (192.168.1.10)

Edit local `web_dashboard/config/dashboard.yaml`:

```yaml
role: dev

fleet:
  vehicle:
    name: vehicle-rpi
    ip: 192.168.1.100
  arms:
    - name: arm1-rpi
      ip: 192.168.1.101
    - name: arm2-rpi
      ip: 192.168.1.102

mqtt:
  broker_host: 192.168.1.100
  broker_port: 1883
```

### Deploy configs

```bash
# Deploy to each RPi (updates config + binaries)
./sync.sh --deploy-cross --ip 192.168.1.100
./sync.sh --deploy-cross --ip 192.168.1.101
./sync.sh --deploy-cross --ip 192.168.1.102
```

Restart the dashboard service on each RPi after deploy:

```bash
ssh ubuntu@192.168.1.100 "sudo systemctl restart pragati-dashboard"
ssh ubuntu@192.168.1.101 "sudo systemctl restart pragati-dashboard"
ssh ubuntu@192.168.1.102 "sudo systemctl restart pragati-dashboard"
```

## Validation Checklist

Run through each check in order. Mark pass/fail for each.

### A. Role-Based Tab Filtering

| # | Check | Expected | Pass? |
|---|-------|----------|-------|
| A1 | Open vehicle dashboard (192.168.1.100:8090) | Sidebar shows: Overview, Multi-Arm, Launch, Safety, Nodes, Topics, Services, Parameters, Bag Manager, Alerts, Settings | |
| A2 | Vehicle dashboard hides excluded tabs | No Fleet, Motor Config, Health, Statistics, Field Analysis tabs | |
| A3 | Open arm1 dashboard (192.168.1.101:8090) | Sidebar shows: Overview, Motor Config, Health, Launch, Safety, Nodes, Topics, Services, Parameters, Bag Manager, Alerts, Settings | |
| A4 | Arm dashboard hides excluded tabs | No Fleet, Multi-Arm, Statistics, Field Analysis tabs | |
| A5 | Open dev PC dashboard (127.0.0.1:8090) | All tabs visible including Fleet group | |

### B. Fleet Hub (Dev PC only)

| # | Check | Expected | Pass? |
|---|-------|----------|-------|
| B1 | Navigate to Fleet tab on dev PC | Fleet tab renders 3 RPi cards | |
| B2 | All 3 RPis show "online" status | Green status dots on all 3 cards | |
| B3 | RPi cards show correct names | vehicle-rpi, arm1-rpi, arm2-rpi | |
| B4 | RPi cards show correct roles | vehicle badge, arm badges | |
| B5 | CPU and memory bars populated | Non-zero values for all online RPis | |
| B6 | Click vehicle-rpi card header | Opens http://192.168.1.100:8090 in new tab | |
| B7 | Click arm1-rpi card header | Opens http://192.168.1.101:8090 in new tab | |
| B8 | Fleet summary shows "3/3 online" | Top summary text correct | |

### C. MQTT Status Flow

| # | Check | Expected | Pass? |
|---|-------|----------|-------|
| C1 | Arm RPis publish status via MQTT | Dev fleet tab shows operational state for arms | |
| C2 | Start a pick operation on arm1 | arm1 card shows "PICKING" state, pick count increments | |
| C3 | Vehicle Multi-Arm tab shows arm status | Arm status updates visible on vehicle dashboard | |

### D. Fleet Actions

| # | Check | Expected | Pass? |
|---|-------|----------|-------|
| D1 | Click "Sync All" on dev fleet tab | Sync starts, progress shown per RPi | |
| D2 | Click "Collect Logs" on dev fleet tab | Log collection starts, progress shown per RPi | |

### E. Failure Detection

| # | Check | Expected | Pass? |
|---|-------|----------|-------|
| E1 | Disconnect arm2 RPi power cable | Fleet tab shows arm2-rpi as "offline" within 15s | |
| E2 | Reconnect arm2 RPi power cable | arm2-rpi returns to "online" after boot (~60s) | |
| E3 | Fleet summary updates | Shows "2/3 online" during disconnect, "3/3 online" after reconnect | |

### F. Hash Navigation Guards

| # | Check | Expected | Pass? |
|---|-------|----------|-------|
| F1 | On vehicle dashboard, type #fleet in URL | Redirects to #overview | |
| F2 | On arm dashboard, type #multi-arm in URL | Redirects to #overview | |
| F3 | On dev dashboard, type #fleet in URL | Fleet tab loads normally | |

## Troubleshooting

### RPi not showing "online" in fleet tab

1. Verify RPi is reachable: `ping 192.168.1.10x`
2. Verify dashboard is running: `ssh ubuntu@192.168.1.10x "systemctl status pragati-dashboard"`
3. Check fleet config on dev PC: `role` must be `dev`, `fleet` section must list correct IPs
4. Check dev PC dashboard logs for HTTP timeout errors
5. Verify firewall allows port 8090: `ssh ubuntu@192.168.1.10x "sudo ufw status"`

### MQTT status not updating

1. Verify Mosquitto broker is running on vehicle RPi:
   `ssh ubuntu@192.168.1.100 "systemctl status mosquitto"`
2. Verify arm RPis can reach broker:
   `ssh ubuntu@192.168.1.101 "mosquitto_pub -h 192.168.1.100 -t test -m hello"`
3. Check MQTT topics are being published:
   `mosquitto_sub -h 192.168.1.100 -t 'pragati/+/status' -v`
4. Check `mqtt.broker_host` in each RPi's `dashboard.yaml` points to vehicle IP

### Sync/Logs actions fail

1. Verify `sync.sh` is available on dev PC and works for each RPi:
   `./sync.sh --deploy-cross --ip 192.168.1.10x` (dry-run first)
2. Verify SSH key-based auth is set up (sync.sh requires passwordless SSH)
3. Check dev PC dashboard logs for subprocess timeout errors (120s limit)

### Dashboard not starting on RPi

1. Check service logs: `journalctl -u pragati-dashboard -n 50`
2. Verify Python dependencies: `pip3 list | grep -E "fastapi|uvicorn|httpx"`
3. Check port conflict: `ss -tlnp | grep 8090`
4. Verify config is valid YAML: `python3 -c "import yaml; yaml.safe_load(open('/path/to/dashboard.yaml'))"`
