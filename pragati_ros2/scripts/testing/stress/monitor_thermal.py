#!/usr/bin/env python3
"""
Camera Thermal Monitor V2 - Reads temp without locking camera
Opens/closes device connection per reading so ROS2 node can use camera
"""

import depthai as dai
import time
import csv
import sys
from datetime import datetime
import signal

class ThermalMonitorV2:
    def __init__(self, log_file="camera_thermal_log.csv", interval=5):
        self.log_file = log_file
        self.interval = interval
        self.running = True
        
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
    def signal_handler(self, sig, frame):
        print("\n\n🛑 Stopping thermal monitor...")
        self.running = False
        
    def get_temperature_snapshot(self):
        """
        Open device, read temperature, close device immediately.
        This allows other processes to use the camera.
        """
        try:
            # Open device briefly
            device = dai.Device()
            
            # Read temperature
            chip_temp = device.getChipTemperature()
            temps = {
                'average': chip_temp.average,
                'css': chip_temp.css,
                'mss': chip_temp.mss,
                'upa': chip_temp.upa,
                'dss': chip_temp.dss
            }
            
            # Close device immediately
            del device
            
            return temps
            
        except Exception as e:
            print(f"⚠️  Error reading temperature: {e}")
            return None
            
    def initialize_log(self):
        """Create CSV log file with headers"""
        try:
            with open(self.log_file, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'Timestamp',
                    'Elapsed_Seconds',
                    'Average_Temp_C',
                    'CSS_Temp_C',
                    'MSS_Temp_C',
                    'UPA_Temp_C',
                    'DSS_Temp_C',
                    'Status'
                ])
            print(f"📝 Logging to: {self.log_file}")
            return True
        except Exception as e:
            print(f"❌ Failed to create log file: {e}")
            return False
            
    def get_status(self, temp):
        """Determine temperature status"""
        if temp < 60:
            return "COOL"
        elif temp < 70:
            return "NORMAL"
        elif temp < 75:
            return "WARM"
        elif temp < 80:
            return "WARNING"
        elif temp < 85:
            return "THROTTLING"
        else:
            return "CRITICAL"
            
    def log_reading(self, elapsed, temps):
        """Log temperature reading to CSV and console"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        avg_temp = temps['average']
        status = self.get_status(avg_temp)
        
        # Write to CSV
        try:
            with open(self.log_file, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    timestamp,
                    elapsed,
                    f"{avg_temp:.1f}",
                    f"{temps['css']:.1f}",
                    f"{temps['mss']:.1f}",
                    f"{temps['upa']:.1f}",
                    f"{temps['dss']:.1f}",
                    status
                ])
        except Exception as e:
            print(f"⚠️  Error writing to log: {e}")
            
        # Console output
        status_emoji = {
            "COOL": "❄️ ",
            "NORMAL": "✅",
            "WARM": "🌡️ ",
            "WARNING": "⚠️ ",
            "THROTTLING": "🔥",
            "CRITICAL": "🔴"
        }
        
        emoji = status_emoji.get(status, "  ")
        
        print(f"{emoji} {timestamp} | {elapsed:5d}s | "
              f"Avg: {avg_temp:5.1f}°C | "
              f"CSS: {temps['css']:5.1f}°C | "
              f"MSS: {temps['mss']:5.1f}°C | "
              f"{status}")
              
    def run(self):
        """Main monitoring loop"""
        print("\n" + "="*70)
        print("  🌡️  OAK-D Lite Camera Thermal Monitor V2")
        print("  (Non-blocking - camera available for ROS2)")
        print("="*70)
        print(f"  📊 Interval: {self.interval} seconds")
        print(f"  📝 Log file: {self.log_file}")
        print(f"  ⏸️  Press Ctrl+C to stop")
        print("="*70 + "\n")
        
        # Test camera connection
        print("📷 Testing camera connection...")
        temps = self.get_temperature_snapshot()
        if not temps:
            print("❌ Cannot access camera")
            return False
        print("✅ Camera accessible\n")
        
        if not self.initialize_log():
            return False
            
        print("\n📊 Temperature Readings:\n")
        print("   Timestamp          | Time  | Average  | CSS     | MSS     | Status")
        print("-" * 70)
        
        start_time = time.time()
        reading_count = 0
        
        try:
            while self.running:
                temps = self.get_temperature_snapshot()
                
                if temps:
                    elapsed = int(time.time() - start_time)
                    self.log_reading(elapsed, temps)
                    reading_count += 1
                else:
                    print(f"⚠️  Skipped reading (camera may be busy)")
                    
                time.sleep(self.interval)
                
        except KeyboardInterrupt:
            pass
        finally:
            print("\n" + "="*70)
            print(f"📊 Summary:")
            print(f"   Total readings: {reading_count}")
            print(f"   Duration: {int(time.time() - start_time)} seconds")
            print(f"   Log saved: {self.log_file}")
            print("="*70 + "\n")
                
        return True

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Monitor OAK-D Lite camera temperature (non-blocking)')
    parser.add_argument('-i', '--interval', type=int, default=5,
                       help='Seconds between readings (default: 5)')
    parser.add_argument('-o', '--output', type=str, 
                       default=f"camera_thermal_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                       help='Output CSV file path')
    
    args = parser.parse_args()
    
    monitor = ThermalMonitorV2(log_file=args.output, interval=args.interval)
    success = monitor.run()
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
