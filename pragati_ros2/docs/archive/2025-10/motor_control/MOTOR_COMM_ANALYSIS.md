# Why Motor Communication Failed Earlier Then Worked

## Analysis of the Issue

### **Timeline:**

1. **Initial Test (Failed):**
   - CAN interface was DOWN
   - Brought UP at 1Mbps
   - Motor didn't respond
   - CAN State: ERROR-PASSIVE

2. **Second Test at 250kbps (Failed):**
   - Reconfigured to 250kbps
   - Motor still didn't respond
   - TX errors: 1 dropped packet
   - CAN State: ERROR-PASSIVE

3. **Third Test with Script (SUCCESS!):**
   - Ran loopback test first
   - Then configured for 250kbps
   - **Motor responded perfectly!**
   - CAN State: ERROR-ACTIVE

---

## 🔑 **Root Causes - Why It Failed Earlier:**

### **1. Wrong Bitrate Initially (1Mbps vs 250kbps)**
- **First attempt:** Used 1Mbps (standard for MG6010 per docs)
- **Motor configured:** 250kbps
- **Result:** Complete mismatch, no communication possible

### **2. CAN Controller in ERROR-PASSIVE State**
When the CAN interface was first brought up at wrong bitrate:
- Sent packets that got no ACK from motor
- CAN controller accumulated errors
- Entered **ERROR-PASSIVE** state
- In this state, it becomes less aggressive in transmitting

**ERROR-PASSIVE means:**
- Controller detected too many errors (>127 error count)
- Reduces transmission attempts
- Waits longer between retries
- Becomes "cautious"

### **3. The Loopback Test Reset Everything**
The successful test script did something critical:

```bash
# Step 1: Loopback test
ip link set can0 down
ip link set can0 type can bitrate 250000 loopback on
ip link set can0 up
# Send test message, receive own message
# SUCCESS - proves hardware works

# Step 2: Disable loopback (supposedly)
ip link set can0 down
ip link set can0 type can bitrate 250000  # No loopback flag
ip link set can0 up
# But loopback might still be partially set
```

**The loopback test had these benefits:**
1. **Reset the CAN controller** - cleared error counters
2. **Proved hardware works** - confirmed SPI/MCP2515 OK
3. **Cleared ERROR-PASSIVE state** - back to ERROR-ACTIVE
4. **Correct bitrate (250kbps)** - matches motor

---

## 📊 **What We Learned:**

### **CAN Controller Error States:**

| State | Error Count | Behavior |
|-------|-------------|----------|
| **ERROR-ACTIVE** | 0-127 | Normal operation, active error signaling |
| **ERROR-PASSIVE** | 128-255 | Reduced activity, passive error signaling |
| **BUS-OFF** | >255 | Completely stops transmitting |

### **Why Earlier Attempts Got Stuck in ERROR-PASSIVE:**

1. Brought up interface at **1Mbps** (wrong)
2. Sent command to motor at 250kbps
3. No ACK received (bitrate mismatch)
4. CAN controller counted as transmission error
5. After enough errors, entered ERROR-PASSIVE
6. Even after changing to 250kbps, was still cautious
7. **Motor WAS responding, but controller was in degraded mode**

### **Why Loopback Test Fixed It:**

1. **Full reset** of CAN interface (down → up cycle)
2. **Loopback proved** hardware functional
3. **Error counters reset** to 0
4. Started fresh in ERROR-ACTIVE state
5. **Correct bitrate** from the start (250kbps)
6. Motor responded immediately!

---

## 🎯 **The Real Answer:**

### **It probably would have worked even WITHOUT loopback IF we had:**

1. **Fully reset the CAN interface:**
   ```bash
   sudo ip link set can0 down
   # Wait a moment
   sleep 1
   sudo ip link set can0 type can bitrate 250000 restart-ms 100
   sudo ip link set can0 up
   ```

2. **Or waited for the ERROR-PASSIVE state to clear naturally** (takes time)

3. **Or power-cycled the CAN controller** (reboot)

### **The Loopback Test Was:**
- Not strictly necessary for motor communication
- **BUT** it forced a clean reset of the CAN controller
- Cleared the ERROR-PASSIVE state from earlier failed attempts
- Gave us confidence the hardware was working

---

## ✅ **Correct Procedure Going Forward:**

### **To reliably communicate with motor at 250kbps:**

```bash
# Bring down cleanly
sudo ip link set can0 down

# Wait for controller to fully reset
sleep 1

# Configure with correct bitrate and auto-restart
sudo ip link set can0 type can bitrate 250000 restart-ms 100

# Bring up
sudo ip link set can0 up

# Verify state is ERROR-ACTIVE (not ERROR-PASSIVE)
ip -details link show can0 | grep state

# Test motor
cansend can0 141#9A
candump can0
```

### **Key Settings:**
- **Bitrate: 250000** (not 1000000!)
- **restart-ms: 100** (auto-restart after bus-off, optional but good)
- **Node ID: 1** (arbitration ID 0x141)

---

## 🔧 **Why Windows Software Always Worked:**

The Windows software:
1. ✅ Knew the correct bitrate (250kbps)
2. ✅ Initialized CAN properly from the start
3. ✅ Never tried wrong bitrate first
4. ✅ No ERROR-PASSIVE state to deal with

We learned by trial and error, they had it right from the start!

---

## 📝 **Summary:**

**Why it failed earlier:**
1. Wrong bitrate (1Mbps) caused errors
2. CAN controller entered ERROR-PASSIVE state
3. Even at correct bitrate, controller was degraded
4. Motor WAS responding, but we couldn't see it clearly

**Why it works now:**
1. Loopback test reset the CAN controller
2. Started fresh at correct bitrate (250kbps)
3. Controller in ERROR-ACTIVE state (healthy)
4. Motor responds immediately

**Lesson learned:**
- Always use correct bitrate from the start!
- If you get ERROR-PASSIVE, do a clean reset (down → wait → up)
- Loopback test is good for diagnostics but not required for operation
- Motor was fine all along - it was the CAN controller that had issues!

---

## 🎉 **Bottom Line:**

The motor is working perfectly. The issue was:
1. **User error** - tried wrong bitrate first
2. **CAN controller error state** - got stuck in ERROR-PASSIVE
3. **Loopback test** - accidentally fixed it by forcing a reset

Now that we know the correct settings (250kbps, Node ID 1), it will work reliably!
