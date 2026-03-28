# MG6010 Test Nodes - Visual Architecture

## The Two Nodes Side-by-Side

```
┌─────────────────────────────────────────────────────────────────────┐
│                        MG6010 Motor Test Nodes                      │
└─────────────────────────────────────────────────────────────────────┘

   mg6010_test_node              mg6010_controller_node
   (Protocol Test)                (Production Controller)
   
┌────────────────────┐         ┌────────────────────────────────────┐
│                    │         │  ROS Topics & Services             │
│  No ROS Topics     │         │  • /joint_states                   │
│  No ROS Services   │         │  • /jointX_position_controller/... │
│  Direct CAN test   │         │  • /enable_motors                  │
│                    │         │  • /disable_motors                 │
└────────────────────┘         └────────────────────────────────────┘
         ↓                                    ↓
┌────────────────────┐         ┌────────────────────────────────────┐
│  MG6010Protocol    │         │  MotorControllerInterface          │
│  • motor_on()      │         │  • set_position()                  │
│  • motor_off()     │         │  • set_velocity()                  │
│  • set_position()  │         │  • get_status()                    │
│  • read_status()   │         │  • set_enabled()                   │
└────────────────────┘         └────────────────────────────────────┘
         ↓                                    ↓
         ↓                      ┌────────────────────────────────────┐
         ↓                      │  MG6010Controller                  │
         ↓                      │  • Homing sequences                │
         ↓                      │  • Multi-motor coordination        │
         ↓                      │  • State management                │
         ↓                      └────────────────────────────────────┘
         ↓                                    ↓
         ↓                      ┌────────────────────────────────────┐
         ↓                      │  MG6010Protocol                    │
         └──────────────────────┤  (Same underlying protocol)        │
                                └────────────────────────────────────┘
                                               ↓
                ┌──────────────────────────────────────────────┐
                │         CAN Hardware Interface               │
                │         • GenericCANInterface                │
                │         • can0 @ 500kbps                     │
                └──────────────────────────────────────────────┘
                                   ↓
                ┌──────────────────────────────────────────────┐
                │         Physical MG6010 Motors               │
                │         • Motor ID 1, 2, 3, ...              │
                └──────────────────────────────────────────────┘
```

## When to Use Which

### Use `mg6010_test_node` when:
- 🔧 Debugging CAN communication
- 🔍 Testing if motor responds at all
- ⚡ Quick hardware check
- 🐛 Isolating protocol issues
- 📝 Validating basic commands work

**Launch:**
```bash
ros2 launch motor_control_ros2 mg6010_test.launch.py test_mode:=status
```

**Behavior:** Runs test, prints result, exits

---

### Use `mg6010_controller_node` when:
- 🤖 Running actual robot operations
- 🎯 Testing multi-motor coordination
- 🏠 Need homing sequences
- 📡 Need ROS topic/service integration
- 🚀 Production motor control
- 🎮 Testing with MoveIt or other ROS tools

**Launch:**
```bash
ros2 launch motor_control_ros2 mg6010_controller.launch.py
```

**Behavior:** Runs continuously, publishes topics, responds to commands

---

## Stack Depth Comparison

```
Low-level (Hardware):

    mg6010_test_node          mg6010_controller_node
    
         Thin                        Full Stack
          |                               |
       Protocol                     ROS Interface
          |                               |
        CAN                          Controller
          |                               |
       Motor                          Protocol
                                           |
                                         CAN
                                           |
                                         Motor
```

## Remember

❌ **DON'T SAY**: "the motor control node" or "the test node"  
✅ **DO SAY**: "`mg6010_test_node`" or "`mg6010_controller_node`"

**These are DIFFERENT nodes with DIFFERENT purposes!**
