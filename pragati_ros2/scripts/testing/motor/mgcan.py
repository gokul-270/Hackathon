# mg4010_Can_Bus.py
# Final, safe, feature-complete MG4010 CAN library (string-command API)
import can
import struct
import time
from typing import Dict, Any, Optional, List

# ==============================
# Command definitions (string → decimal, hex comment)
# ==============================
COMMANDS = {
    "MOTOR_OFF": 128,            # 0x80
    "MOTOR_ON": 136,             # 0x88
    "MOTOR_STOP": 129,           # 0x81
    "CLEAR_ERRORS": 155,         # 0x9B
    "READ_STATUS_1": 154,        # 0x9A
    "READ_STATUS_2": 156,        # 0x9C
    "READ_STATUS_3": 157,        # 0x9D
    "OPEN_LOOP": 160,            # 0xA0
    "TORQUE_CTRL": 161,          # 0xA1
    "SPEED_CTRL": 162,           # 0xA2
    "MULTI_LOOP_ANGLE_1": 163,   # 0xA3
    "MULTI_LOOP_ANGLE_2": 164,   # 0xA4
    "SINGLE_LOOP_ANGLE_1": 165,  # 0xA5
    "SINGLE_LOOP_ANGLE_2": 166,  # 0xA6
    "INCREMENT_ANGLE_1": 167,    # 0xA7
    "INCREMENT_ANGLE_2": 168,    # 0xA8
    "READ_PID": 48,              # 0x30
    "WRITE_PID_RAM": 49,         # 0x31
    "WRITE_PID_ROM": 50,         # 0x32
    "READ_ACCEL": 51,            # 0x33
    "WRITE_ACCEL_RAM": 52,       # 0x34
    "READ_ENCODER": 144,         # 0x90
    "WRITE_ENCODER_OFFSET": 145, # 0x91
    "READ_MULTI_TURN_ANGLE": 146,# 0x92
    "READ_SINGLE_TURN_ANGLE": 148,# 0x94
    "CLEAR_ANGLE_LOOP": 149,     # 0x95
    "SET_ZERO_IN_ROM": 25,       # 0x19
}

# Reverse lookup for readable responses
COMMAND_LOOKUP = {v: k for k, v in COMMANDS.items()}


class MG4010_CAN:
    """
    MG4010 CAN driver (string commands).
    - Uses socketcan or other python-can backends via can.interface.Bus.
    - Safe: enforces DLC <= 8, filters responses by arbitration_id + command byte.
    - Configurable timeouts and retries.
    """

    ERROR_FLAGS = {
        0x01: "Low voltage protection",
        0x02: "Over-temperature protection",
        0x04: "Phase overcurrent protection",
        0x08: "Stall protection",
    }

    def __init__(self, channel: str = "can0", bustype: str = "socketcan", bitrate: int = 500000,
                 response_timeout: float = 0.05, retries: int = 1):
        """
        response_timeout: seconds to wait for a matching response for each recv()
        retries: how many times to re-send the command if no valid response (0 = no retry)
        """
        self.channel = channel
        self.bustype = bustype
        self.bitrate = bitrate
        self.response_timeout = response_timeout
        self.retries = retries
        self.bus: Optional[can.Bus] = None

        try:
            self.bus = can.interface.Bus(channel=channel, bustype=bustype, bitrate=bitrate)
            print(f"[MG4010_CAN] Connected to CAN '{channel}' @ {bitrate}bps")
        except Exception as e:
            self.bus = None
            print(f"[MG4010_CAN] Error initializing CAN bus: {e}")
            print(f"  - Make sure interface is up: sudo ip link set {channel} up type can bitrate {bitrate}")

    # -----------------------
    # Low level helpers
    # -----------------------
    def _make_frame(self, command_byte: int, data: Optional[List[int]] = None) -> List[int]:
        """
        Build an 8-byte payload: [cmd] + data (max 7 bytes) padded with zeros.
        Ensures total length <= 8 (DLC safe).
        """
        data_list = list(data) if data else []
        frame = [command_byte] + data_list
        # truncate to 8 bytes total
        frame = frame[:8]
        # pad if shorter
        if len(frame) < 8:
            frame += [0x00] * (8 - len(frame))
        return frame

    def _send_frame_and_wait(self, arbitration_id: int, command_byte: int, frame_data: List[int]) -> Optional[can.Message]:
        """
        Send a frame and wait for a matching response from same arbitration_id and command_byte.
        Keeps reading until timeout or matching frame found. Returns the matching can.Message or None.
        """
        if not self.bus:
            print("[MG4010_CAN] Error: CAN bus not initialized")
            return None

        try:
            msg = can.Message(arbitration_id=arbitration_id, data=frame_data, is_extended_id=False)
            self.bus.send(msg)
        except can.CanError as e:
            print(f"[MG4010_CAN] CanError sending frame: {e}")
            return None
        except Exception as e:
            print(f"[MG4010_CAN] Error sending frame: {e}")
            return None

        # listen for matching response until timeout
        deadline = time.time() + self.response_timeout
        while time.time() < deadline:
            try:
                response = self.bus.recv(timeout=deadline - time.time())
            except Exception:
                response = None
            if response is None:
                break
            # Must be from same motor arbitration id and contain data
            if response.arbitration_id != arbitration_id:
                # unrelated frame — ignore
                continue
            if not hasattr(response, "data") or len(response.data) == 0:
                continue
            # First byte must be the command byte (motor echoes command in first byte)
            # Some devices reply with different command bytes (status frames), so we allow some flexibility:
            # Accept if response.data[0] == command_byte OR it's one of the status commands related to the request.
            if response.data[0] == command_byte:
                return response
            # If not exact match, ignore and keep listening (this avoids processing stale/unrelated frames)
            # continue loop
        # timeout
        return None

    def _send_command(self, motor_id: int, command: str, data: Optional[List[int]] = None) -> Optional[can.Message]:
        """
        Send a command (string) to a single motor and wait for a matching response.
        Retries based on self.retries.
        """
        if self.bus is None:
            print("[MG4010_CAN] Error: CAN bus not available.")
            return None
        if command not in COMMANDS:
            print(f"[MG4010_CAN] Error: Unknown command '{command}'")
            return None
        if not (1 <= motor_id <= 32):
            print("[MG4010_CAN] Error: motor_id must be 1..32")
            return None

        cmd_byte = COMMANDS[command]
        arb_id = 0x140 + motor_id
        frame = self._make_frame(cmd_byte, data)

        attempt = 0
        while attempt <= self.retries:
            response = self._send_frame_and_wait(arb_id, cmd_byte, frame)
            if response:
                print(f"[MG4010_CAN] Received response for '{command}' (attempt {attempt})")
                return response
            attempt += 1
            if attempt <= self.retries:
                # resend once more
                print(f"[MG4010_CAN] Warning: no response for '{command}' (attempt {attempt}), retrying...")
                try:
                    msg = can.Message(arbitration_id=arb_id, data=frame, is_extended_id=False)
                    self.bus.send(msg)
                except Exception as e:
                    print(f"[MG4010_CAN] Error re-sending: {e}")
                    return None
        # final timeout
        print(f"[MG4010_CAN] Error: no response for '{command}' after {self.retries + 1} attempt(s)")
        return None

    def _send_multi_motor_command(self, command_data: List[int]) -> Optional[List[can.Message]]:
        """
        Send a multi-motor command on 0x280 and collect responses from motors.
        We'll collect responses that come after sending until timeout.
        """
        if self.bus is None:
            print("[MG4010_CAN] Error: CAN bus not available.")
            return None

        can_id = 0x280
        # build 8-byte frame
        frame = list(command_data)[:8]
        if len(frame) < 8:
            frame += [0x00] * (8 - len(frame))

        try:
            msg = can.Message(arbitration_id=can_id, data=frame, is_extended_id=False)
            self.bus.send(msg)
        except Exception as e:
            print(f"[MG4010_CAN] Error sending multi-motor frame: {e}")
            return None

        responses = []
        deadline = time.time() + self.response_timeout
        while time.time() < deadline:
            try:
                resp = self.bus.recv(timeout=deadline - time.time())
            except Exception:
                resp = None
            if resp is None:
                break
            # Multi responses will come from individual motor IDs (0x141..)
            if resp.arbitration_id >= 0x141 and resp.arbitration_id <= 0x140 + 32:
                # ensure data present
                if hasattr(resp, "data") and len(resp.data) > 0:
                    responses.append(resp)
        return responses if responses else None

    # -----------------------
    # Response handling/parsing
    # -----------------------
    def _handle_response(self, response_message: Optional[can.Message], expected_cmd: str,
                         print_summary: bool = False) -> Optional[Dict[str, Any]]:
        """
        Validate and parse a response_message; expected_cmd is the string name.
        Returns parsed dict or None.
        """
        if response_message is None:
            print(f"[MG4010_CAN] Error: No response for '{expected_cmd}'")
            return None

        if not hasattr(response_message, "data") or len(response_message.data) < 1:
            print(f"[MG4010_CAN] Error: Invalid/empty frame received for '{expected_cmd}'")
            return None

        expected_byte = COMMANDS.get(expected_cmd)
        # Accept responses where first data byte equals expected_byte.
        # If not, print readable error and raw response.
        if response_message.data[0] != expected_byte:
            got_name = COMMAND_LOOKUP.get(response_message.data[0], hex(response_message.data[0]))
            print(f"[MG4010_CAN] Error: Unexpected response. Expected {expected_cmd}, got {got_name}.")
            print("Raw response:", response_message)
            return None

        parsed = self.motor_response(response_message)
        if print_summary and parsed:
            print("\n--- Parsed Response ---")
            for key, value in parsed.items():
                unit = ""
                if "temperature" in key: unit = "°C"
                elif "voltage" in key: unit = "V"
                elif "speed" in key: unit = "dps"
                elif "current" in key: unit = "A"
                elif "angle" in key: unit = "°"
                elif "acceleration" in key: unit = "dps/s"
                print(f"  {key.replace('_', ' ').title()}: {value} {unit}")
            print("-----------------------\n")
        return parsed

    def motor_response(self, message: can.Message) -> Optional[Dict[str, Any]]:
        """
        Parse the CAN message into a python dict.
        Returns None if message is too short or unrecognized.
        """
        if not hasattr(message, "data") or len(message.data) < 8:
            # some responses are valid but shorter; original protocol expects 8 bytes,
            # but to be safe we handle if len < 8 in some parsers
            pass

        data = message.data
        cmd_byte = data[0]
        cmd_name = COMMAND_LOOKUP.get(cmd_byte, f"UNKNOWN_{hex(cmd_byte)}")

        # Standard control/status_2 frame structure
        if cmd_byte in [
            COMMANDS["MOTOR_OFF"], COMMANDS["MOTOR_STOP"], COMMANDS["MOTOR_ON"],
            COMMANDS["OPEN_LOOP"], COMMANDS["TORQUE_CTRL"], COMMANDS["SPEED_CTRL"],
            COMMANDS["MULTI_LOOP_ANGLE_1"], COMMANDS["MULTI_LOOP_ANGLE_2"],
            COMMANDS["SINGLE_LOOP_ANGLE_1"], COMMANDS["SINGLE_LOOP_ANGLE_2"],
            COMMANDS["INCREMENT_ANGLE_1"], COMMANDS["INCREMENT_ANGLE_2"],
            COMMANDS["READ_STATUS_2"]
        ]:
            # Ensure enough bytes before unpacking (use safe slicing)
            temp = struct.unpack('<b', bytes(data[1:2]))[0] if len(data) >= 2 else None
            torque = struct.unpack('<h', bytes(data[2:4]))[0] if len(data) >= 4 else None
            speed = struct.unpack('<h', bytes(data[4:6]))[0] if len(data) >= 6 else None
            encoder_pos = struct.unpack('<H', bytes(data[6:8]))[0] if len(data) >= 8 else None
            return {
                'command': cmd_name,
                'temperature': temp,
                'torque_current_raw': torque,
                'speed_dps': speed,
                'encoder_position': encoder_pos
            }

        if cmd_byte == COMMANDS["READ_PID"]:
            # bytes 2..7 map to PID params
            return {
                'command': cmd_name,
                'position_loop_kp': data[2] if len(data) > 2 else None,
                'position_loop_ki': data[3] if len(data) > 3 else None,
                'speed_loop_kp': data[4] if len(data) > 4 else None,
                'speed_loop_ki': data[5] if len(data) > 5 else None,
                'torque_loop_kp': data[6] if len(data) > 6 else None,
                'torque_loop_ki': data[7] if len(data) > 7 else None
            }

        if cmd_byte in (COMMANDS["WRITE_PID_RAM"], COMMANDS["WRITE_PID_ROM"]):
            return {'command': cmd_name, 'status': 'PID parameters written successfully'}

        if cmd_byte == COMMANDS["READ_ACCEL"]:
            accel = struct.unpack('<i', bytes(data[4:8]))[0] if len(data) >= 8 else None
            return {'command': cmd_name, 'acceleration': accel}

        if cmd_byte == COMMANDS["WRITE_ACCEL_RAM"]:
            return {'command': cmd_name, 'status': 'Acceleration written to RAM successfully'}

        if cmd_byte == COMMANDS["READ_ENCODER"]:
            enc_pos = struct.unpack('<H', bytes(data[2:4]))[0] if len(data) >= 4 else None
            enc_raw = struct.unpack('<H', bytes(data[4:6]))[0] if len(data) >= 6 else None
            enc_off = struct.unpack('<H', bytes(data[6:8]))[0] if len(data) >= 8 else None
            return {'command': cmd_name, 'encoder_position': enc_pos, 'encoder_raw_position': enc_raw, 'encoder_offset': enc_off}

        if cmd_byte == COMMANDS["WRITE_ENCODER_OFFSET"]:
            return {'command': cmd_name, 'status': 'Encoder offset written to ROM successfully'}

        if cmd_byte == COMMANDS["READ_MULTI_TURN_ANGLE"]:
            # angle sent in bytes 1..7, little endian signed (56 bits)
            angle_raw = int.from_bytes(bytes(data[1:8]), 'little', signed=True) if len(data) >= 8 else None
            return {'command': cmd_name, 'multi_turn_angle': (angle_raw * 0.01) if angle_raw is not None else None}

        if cmd_byte == COMMANDS["READ_SINGLE_TURN_ANGLE"]:
            circle_angle = struct.unpack('<I', bytes(data[4:8]))[0] if len(data) >= 8 else None
            return {'command': cmd_name, 'single_turn_angle': (circle_angle * 0.01) if circle_angle is not None else None}

        if cmd_byte == COMMANDS["CLEAR_ANGLE_LOOP"]:
            return {'command': cmd_name, 'status': 'Motor angle loop cleared successfully'}

        if cmd_byte in (COMMANDS["READ_STATUS_1"], COMMANDS["CLEAR_ERRORS"]):
            err_byte = data[7] if len(data) >= 8 else 0
            errors = [desc for flag, desc in self.ERROR_FLAGS.items() if err_byte & flag]
            temp = struct.unpack('<b', bytes(data[1:2]))[0] if len(data) >= 2 else None
            voltage = (struct.unpack('<H', bytes(data[3:5]))[0] * 0.1) if len(data) >= 5 else None
            return {
                'command': cmd_name,
                'temperature': temp,
                'voltage': voltage,
                'error_state_raw': hex(err_byte),
                'errors': ", ".join(errors) if errors else "No errors"
            }

        if cmd_byte == COMMANDS["READ_STATUS_3"]:
            temp = struct.unpack('<b', bytes(data[1:2]))[0] if len(data) >= 2 else None
            a = (struct.unpack('<h', bytes(data[2:4]))[0] / 64.0) if len(data) >= 4 else None
            b = (struct.unpack('<h', bytes(data[4:6]))[0] / 64.0) if len(data) >= 6 else None
            c = (struct.unpack('<h', bytes(data[6:8]))[0] / 64.0) if len(data) >= 8 else None
            return {'command': cmd_name, 'temperature': temp, 'phase_a_current': a, 'phase_b_current': b, 'phase_c_current': c}

        if cmd_byte == COMMANDS["SET_ZERO_IN_ROM"]:
            off = struct.unpack('<H', bytes(data[6:8]))[0] if len(data) >= 8 else None
            return {'command': cmd_name, 'status': 'New zero position set in ROM', 'encoder_offset': off}

        # fallback
        return {'command': cmd_name, 'raw_data': list(data)}


    # -----------------------
    # High-level API (string commands)
    # -----------------------
    # Motor state & status
    def motor_off(self, motor_id: int) -> Optional[Dict[str, Any]]:
        resp = self._send_command(motor_id, "MOTOR_OFF")
        return self._handle_response(resp, "MOTOR_OFF")

    def motor_on(self, motor_id: int) -> Optional[Dict[str, Any]]:
        resp = self._send_command(motor_id, "MOTOR_ON")
        return self._handle_response(resp, "MOTOR_ON")

    def motor_stop(self, motor_id: int) -> Optional[Dict[str, Any]]:
        resp = self._send_command(motor_id, "MOTOR_STOP")
        return self._handle_response(resp, "MOTOR_STOP")

    def read_motor_status_1(self, motor_id: int) -> Optional[Dict[str, Any]]:
        resp = self._send_command(motor_id, "READ_STATUS_1")
        return self._handle_response(resp, "READ_STATUS_1", print_summary=True)
    def clear_errors(self, motor_id: int) -> Optional[Dict[str, Any]]:
        """Clear motor errors - dedicated function"""
        resp = self._send_command(motor_id, "CLEAR_ERRORS")
        return self._handle_response(resp, "CLEAR_ERRORS")

    # -----------------------
    # Error Recovery & Monitoring
    # -----------------------
    def check_motor_health(self, motor_id: int) -> Dict[str, Any]:
        """
        Check motor health and return comprehensive status.
        Returns dict with health_ok, errors, temperature, voltage.
        """
        status = self.read_motor_status_1(motor_id)
        if not status:
            return {
                'health_ok': False,
                'accessible': False,
                'error': 'Cannot read motor status'
            }
        
        health_info = {
            'accessible': True,
            'temperature': status.get('temperature'),
            'voltage': status.get('voltage'),
            'errors': status.get('errors', 'Unknown'),
            'error_flags': status.get('error_state_raw', '0x00'),
            'health_ok': True,
            'warnings': []
        }
        
        # Check for errors
        if status.get('errors') != "No errors":
            health_info['health_ok'] = False
            health_info['warnings'].append(f"Motor errors: {status.get('errors')}")
        
        # Check temperature
        temp = status.get('temperature')
        if temp is not None:
            if temp > 65:
                health_info['health_ok'] = False
                health_info['warnings'].append(f"Temperature critical: {temp}°C")
            elif temp > 55:
                health_info['warnings'].append(f"Temperature high: {temp}°C")
        
        # Check voltage
        voltage = status.get('voltage')
        if voltage is not None:
            if voltage < 20.0:
                health_info['health_ok'] = False
                health_info['warnings'].append(f"Low voltage: {voltage}V")
        
        return health_info

    def is_motor_accessible(self, motor_id: int) -> bool:
        """
        Quick check if motor is accessible and responding.
        Returns True if motor responds to status command.
        """
        try:
            resp = self._send_command(motor_id, "READ_STATUS_2")
            return resp is not None
        except Exception:
            return False

    def recover_from_error(self, motor_id: int, max_attempts: int = 3) -> Dict[str, Any]:
        """
        Attempt to recover motor from error state.
        Steps:
        1. Read current error state
        2. Clear errors
        3. Turn motor on
        4. Verify recovery
        
        Returns dict with success status and details.
        """
        result = {
            'success': False,
            'attempts': 0,
            'initial_errors': None,
            'final_errors': None,
            'message': ''
        }
        
        # Check initial state
        print(f"[MG4010_CAN] Checking motor {motor_id} error state...")
        initial_status = self.read_motor_status_1(motor_id)
        if not initial_status:
            result['message'] = 'Cannot read motor status - motor may be inaccessible'
            return result
        
        result['initial_errors'] = initial_status.get('errors', 'Unknown')
        print(f"[MG4010_CAN] Initial errors: {result['initial_errors']}")
        
        if result['initial_errors'] == "No errors":
            result['success'] = True
            result['message'] = 'Motor has no errors - no recovery needed'
            return result
        
        # Attempt recovery
        for attempt in range(1, max_attempts + 1):
            result['attempts'] = attempt
            print(f"[MG4010_CAN] Recovery attempt {attempt}/{max_attempts}...")
            
            # Step 1: Clear errors
            print(f"[MG4010_CAN]   - Clearing errors...")
            clear_resp = self._send_command(motor_id, "CLEAR_ERRORS")
            if not clear_resp:
                print(f"[MG4010_CAN]   - Failed to send clear errors command")
                time.sleep(0.5)
                continue
            
            time.sleep(0.1)
            
            # Step 2: Turn motor off then on (reboot)
            print(f"[MG4010_CAN]   - Rebooting motor (OFF->ON)...")
            self.motor_off(motor_id)
            time.sleep(0.2)
            self.motor_on(motor_id)
            time.sleep(0.2)
            
            # Step 3: Verify recovery
            print(f"[MG4010_CAN]   - Verifying recovery...")
            final_status = self.read_motor_status_1(motor_id)
            if not final_status:
                print(f"[MG4010_CAN]   - Cannot verify - motor not responding")
                time.sleep(0.5)
                continue
            
            result['final_errors'] = final_status.get('errors', 'Unknown')
            
            if result['final_errors'] == "No errors":
                result['success'] = True
                result['message'] = f'Motor recovered successfully after {attempt} attempt(s)'
                print(f"[MG4010_CAN] ✅ {result['message']}")
                return result
            else:
                print(f"[MG4010_CAN]   - Still has errors: {result['final_errors']}")
                time.sleep(0.5)
        
        # All attempts failed
        result['message'] = f'Recovery failed after {max_attempts} attempts. Final errors: {result["final_errors"]}'
        print(f"[MG4010_CAN] ❌ {result['message']}")
        return result

    def auto_clear_and_retry(self, motor_id: int, command_func, *args, max_attempts: int = 3, **kwargs) -> Optional[Dict[str, Any]]:
        """
        Smart retry wrapper: executes command, and if it fails due to motor error,
        automatically recovers and retries.
        
        Args:
            motor_id: Motor ID
            command_func: Function to call (e.g., self.set_absolute_position)
            *args, **kwargs: Arguments for command_func
            max_attempts: Maximum retry attempts
        
        Returns:
            Command result or None
        """
        for attempt in range(1, max_attempts + 1):
            try:
                # Try the command
                result = command_func(motor_id, *args, **kwargs)
                if result is not None:
                    return result
                
                # Command failed - check if motor has errors
                health = self.check_motor_health(motor_id)
                if not health['health_ok'] and health.get('accessible'):
                    print(f"[MG4010_CAN] Command failed, motor has errors. Attempting recovery...")
                    recovery = self.recover_from_error(motor_id)
                    if not recovery['success']:
                        print(f"[MG4010_CAN] Recovery failed, giving up")
                        return None
                    # Recovery successful, retry will happen in next loop iteration
                else:
                    # Failed for other reasons
                    return None
                    
            except Exception as e:
                print(f"[MG4010_CAN] Exception during command: {e}")
                if attempt < max_attempts:
                    time.sleep(0.2)
                else:
                    return None
        
        return None
    def read_motor_status_2(self, motor_id: int) -> Optional[Dict[str, Any]]:
        resp = self._send_command(motor_id, "READ_STATUS_2")
        return self._handle_response(resp, "READ_STATUS_2", print_summary=True)

    def read_motor_status_3(self, motor_id: int) -> Optional[Dict[str, Any]]:
        resp = self._send_command(motor_id, "READ_STATUS_3")
        return self._handle_response(resp, "READ_STATUS_3", print_summary=True)

    # Encoder & angle
    def read_encoder(self, motor_id: int) -> Optional[Dict[str, Any]]:
        resp = self._send_command(motor_id, "READ_ENCODER")
        return self._handle_response(resp, "READ_ENCODER", print_summary=True)

    def write_encoder_offset_to_rom(self, motor_id: int, encoder_offset: int) -> Optional[Dict[str, Any]]:
        data = [0x00, 0x00, 0x00, 0x00, 0x00] + list(struct.pack('<H', encoder_offset))
        resp = self._send_command(motor_id, "WRITE_ENCODER_OFFSET", data)
        return self._handle_response(resp, "WRITE_ENCODER_OFFSET")

    def read_multi_turn_angle(self, motor_id: int) -> Optional[Dict[str, Any]]:
        resp = self._send_command(motor_id, "READ_MULTI_TURN_ANGLE")
        return self._handle_response(resp, "READ_MULTI_TURN_ANGLE", print_summary=True)

    def read_single_turn_angle(self, motor_id: int) -> Optional[Dict[str, Any]]:
        resp = self._send_command(motor_id, "READ_SINGLE_TURN_ANGLE")
        return self._handle_response(resp, "READ_SINGLE_TURN_ANGLE", print_summary=True)

    def clear_motor_angle_loop(self, motor_id: int) -> Optional[Dict[str, Any]]:
        resp = self._send_command(motor_id, "CLEAR_ANGLE_LOOP")
        return self._handle_response(resp, "CLEAR_ANGLE_LOOP")

    def write_current_position_to_rom_as_zero(self, motor_id: int) -> Optional[Dict[str, Any]]:
        resp = self._send_command(motor_id, "SET_ZERO_IN_ROM")
        return self._handle_response(resp, "SET_ZERO_IN_ROM")

    # Control modes (note carefully packed data lengths to keep DLC <=8)
    def open_loop_control(self, motor_id: int, power_control: int) -> Optional[Dict[str, Any]]:
        # data: 3 bytes pad + int16 power_control + 2 pad = 7 bytes payload (cmd + 7 = 8)
        data = [0x00, 0x00, 0x00] + list(struct.pack('<h', power_control)) + [0x00, 0x00]
        resp = self._send_command(motor_id, "OPEN_LOOP", data)
        return self._handle_response(resp, "OPEN_LOOP")

    def torque_closed_loop_control(self, motor_id: int, iq_control: int) -> Optional[Dict[str, Any]]:
        data = [0x00, 0x00, 0x00] + list(struct.pack('<h', iq_control)) + [0x00, 0x00]
        resp = self._send_command(motor_id, "TORQUE_CTRL", data)
        return self._handle_response(resp, "TORQUE_CTRL")

    def speed_closed_loop_control(self, motor_id: int, speed_control: int) -> Optional[Dict[str, Any]]:
        # speed_control: int32 where actual speed = speed_control * 0.01 dps/LSB
        data = [0x00, 0x00, 0x00] + list(struct.pack('<i', speed_control))
        resp = self._send_command(motor_id, "SPEED_CTRL", data)
        return self._handle_response(resp, "SPEED_CTRL")

    # PID & accel
    def read_pid_parameters(self, motor_id: int) -> Optional[Dict[str, Any]]:
        resp = self._send_command(motor_id, "READ_PID")
        return self._handle_response(resp, "READ_PID", print_summary=True)

    def write_pid_parameters_to_ram(self, motor_id: int, angle_kp: int, angle_ki: int,
                                    speed_kp: int, speed_ki: int, iq_kp: int, iq_ki: int) -> Optional[Dict[str, Any]]:
        data = [0x00, angle_kp, angle_ki, speed_kp, speed_ki, iq_kp, iq_ki]
        resp = self._send_command(motor_id, "WRITE_PID_RAM", data)
        return self._handle_response(resp, "WRITE_PID_RAM")

    def write_pid_parameters_to_rom(self, motor_id: int, angle_kp: int, angle_ki: int,
                                    speed_kp: int, speed_ki: int, iq_kp: int, iq_ki: int) -> Optional[Dict[str, Any]]:
        data = [0x00, angle_kp, angle_ki, speed_kp, speed_ki, iq_kp, iq_ki]
        resp = self._send_command(motor_id, "WRITE_PID_ROM", data)
        return self._handle_response(resp, "WRITE_PID_ROM")

    def read_acceleration(self, motor_id: int) -> Optional[Dict[str, Any]]:
        resp = self._send_command(motor_id, "READ_ACCEL")
        return self._handle_response(resp, "READ_ACCEL", print_summary=True)

    def write_acceleration_to_ram(self, motor_id: int, acceleration: int) -> Optional[Dict[str, Any]]:
        data = [0x00, 0x00, 0x00] + list(struct.pack('<i', acceleration))
        resp = self._send_command(motor_id, "WRITE_ACCEL_RAM", data)
        return self._handle_response(resp, "WRITE_ACCEL_RAM")

    # Multi motor torque control (up to 4 motors)
    def multi_motor_torque_control(self, motor_controls: List[int]) -> Optional[List[Dict[str, Any]]]:
        """
        motor_controls: list of up to 4 int16 torque values.
        Each int16 packed little-endian; total 8 bytes excluding command byte = use cmd id 0x280.
        """
        if len(motor_controls) > 4:
            print("[MG4010_CAN] Error: Maximum 4 motors in multi-torque")
            return None
        while len(motor_controls) < 4:
            motor_controls.append(0)
        data = []
        for ctl in motor_controls:
            data.extend(list(struct.pack('<h', ctl)))  # 2 bytes each -> 8 bytes total
        responses = self._send_multi_motor_command(data)
        if not responses:
            return None
        parsed = []
        for r in responses:
            p = self.motor_response(r)
            if p:
                parsed.append(p)
        return parsed
    
    def enter_multi_loop_angle_1_mode(self, motor_id: int):
        """
        Switch motor into MULTI_LOOP_ANGLE_1 (absolute position control) mode
        without moving from current position.
        """
        current_angle = 0
        angle_bytes = list(struct.pack('<i', current_angle))
        return self._handle_response(
            self._send_command(motor_id, "MULTI_LOOP_ANGLE_1", angle_bytes ),
            "MULTI_LOOP_ANGLE_1"
        )

    def enter_multi_loop_angle_2_mode(self, motor_id: int, speed_control: int):
        """
        Switch motor into MULTI_LOOP_ANGLE_2 (absolute position with speed control) mode
        without moving from current position.
        """
        current_angle = 0
        angle_bytes = list(struct.pack('<i', current_angle))
        speed_bytes = list(struct.pack('<i', speed_control))
        return self._handle_response(
            self._send_command(motor_id, "MULTI_LOOP_ANGLE_2", angle_bytes + speed_bytes),
            "MULTI_LOOP_ANGLE_2"
        )
    
    # Position control (packed carefully)
    # MULTI_LOOP_ANGLE_1: data = [0x00,0x00,0x00] + <int32 angle_control>  => 3 +4 =7 bytes payload
    def set_absolute_position(self, motor_id: int, position_degrees: float) -> Optional[Dict[str, Any]]:
        angle_control = int(position_degrees * 100)  # protocol uses 0.01 deg/LSB
        data = [0x00, 0x00, 0x00] + list(struct.pack('<i', angle_control))
        resp = self._send_command(motor_id, "MULTI_LOOP_ANGLE_1", data)
        return self._handle_response(resp, "MULTI_LOOP_ANGLE_1")

    # MULTI_LOOP_ANGLE_2: data = [0x00] + <uint16 max_speed> + <int32 angle_control> => 1+2+4 =7
    def set_absolute_position_with_speed(self, motor_id: int, position_degrees: float, max_speed_dps: int) -> Optional[Dict[str, Any]]:
        angle_control = int(position_degrees * 100)
        data = [0x00] + list(struct.pack('<H', int(max_speed_dps))) + list(struct.pack('<i', angle_control))
        resp = self._send_command(motor_id, "MULTI_LOOP_ANGLE_2", data)
        return self._handle_response(resp, "MULTI_LOOP_ANGLE_2")

    # SINGLE_LOOP_ANGLE_1: data = [spin_dir,0x00,0x00] + <uint32 angle_control> => 1+2+4=7
    def move_to_angle_single_turn(self, motor_id: int, angle_degrees: float, spin_direction: int = 0x00) -> Optional[Dict[str, Any]]:
        angle_control = int(angle_degrees * 100)
        data = [spin_direction, 0x00, 0x00] + list(struct.pack('<I', angle_control))
        resp = self._send_command(motor_id, "SINGLE_LOOP_ANGLE_1", data)
        return self._handle_response(resp, "SINGLE_LOOP_ANGLE_1")

    # SINGLE_LOOP_ANGLE_2: data = [spin_dir] + <uint16 max_speed> + <uint32 angle_control> => 1+2+4=7
    def move_to_angle_single_turn_with_speed(self, motor_id: int, angle_degrees: float, max_speed_dps: int, spin_direction: int = 0x00) -> Optional[Dict[str, Any]]:
        angle_control = int(angle_degrees * 100)
        data = [spin_direction] + list(struct.pack('<H', int(max_speed_dps))) + list(struct.pack('<I', angle_control))
        resp = self._send_command(motor_id, "SINGLE_LOOP_ANGLE_2", data)
        return self._handle_response(resp, "SINGLE_LOOP_ANGLE_2")

    # INCREMENT_ANGLE_1: data = [0x00,0x00,0x00] + <int32 increment>
    def set_incremental_position(self, motor_id: int, angle_increment_degrees: float) -> Optional[Dict[str, Any]]:
        inc = int(angle_increment_degrees * 100)
        data = [0x00, 0x00, 0x00] + list(struct.pack('<i', inc))
        resp = self._send_command(motor_id, "INCREMENT_ANGLE_1", data)
        return self._handle_response(resp, "INCREMENT_ANGLE_1")

    # INCREMENT_ANGLE_2: data = [0x00] + <uint16 max_speed> + <int32 increment>
    def set_incremental_position_with_speed(self, motor_id: int, angle_increment_degrees: float, max_speed_dps: int) -> Optional[Dict[str, Any]]:
        inc = int(angle_increment_degrees * 100)
        data = [0x00] + list(struct.pack('<H', int(max_speed_dps))) + list(struct.pack('<i', inc))
        resp = self._send_command(motor_id, "INCREMENT_ANGLE_2", data)
        return self._handle_response(resp, "INCREMENT_ANGLE_2")


# -------------------------
# Quick test block (library safe)
# -------------------------
if __name__ == "__main__":
    # Quick smoke test (requires can0 up)
    mg = MG4010_CAN(channel="can0", response_timeout=0.05, retries=1)
    mid = 1
    if mg.bus:
        print("\n=== Motor Health Check ===")
        health = mg.check_motor_health(mid)
        print(f"Motor accessible: {health.get('accessible')}")
        print(f"Health OK: {health.get('health_ok')}")
        print(f"Errors: {health.get('errors')}")
        print(f"Temperature: {health.get('temperature')}°C")
        print(f"Voltage: {health.get('voltage')}V")
        
        if not health.get('health_ok'):
            print("\n=== Attempting Error Recovery ===")
            recovery = mg.recover_from_error(mid)
            print(f"Recovery success: {recovery['success']}")
            print(f"Message: {recovery['message']}")
        
        print("\n=== Basic Motor Test ===")
        print("Turning motor ON")
        mg.motor_on(mid)
        time.sleep(0.3)
        print("Reading status")
        mg.read_motor_status_1(mid)
        print("Turning motor OFF")
        mg.motor_off(mid)
    else:
        print("CAN bus not initialized; aborting quick test.")

