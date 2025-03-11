import os
import time
import subprocess
from time import sleep
from typing import Optional

class CanDaGuardia:
    """
    A utility for monitoring file changes and alerting when a file becomes stuck.
    """
    
    def __init__(self, 
                sound_file: str = "/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga"):
        """
        Initialize the file monitor.
        
        Parameters:
        -----------
        sound_file : str, optional
            Path to the sound file to play when an alert is triggered
        """
        self.sound_file = sound_file if os.path.exists(sound_file) else None
    
    def monitor(self, file_path: str, alert_interval: int = 50, verbose: bool = False) -> None:
        """
        Monitor a file for changes and alert when it becomes stuck.
        
        Parameters:
        -----------
        file_path : str
            Path to the file to monitor
        alert_interval : int, optional
            Number of seconds to wait before triggering an alert when file is stuck
        verbose : bool, optional
            Whether to print more detailed information
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        print(f"Monitoring activated on: {file_path}")
        print("Press Ctrl+C to stop monitoring.")
        
        with open(file_path, 'rb') as f:
            start_time = time.time()
            cur_time = start_time
            stuck = False
            last_alert_time = 0
            f.seek(0, 2)  # Go to end of file
            old_data = f.read()
            
            try:
                while True:
                    data = f.read()
                    cur_time = time.time()
                    
                    if data == old_data and data:  # Only consider stuck if there's data
                        if not stuck and verbose:
                            print(f"No changes detected since {time.strftime('%H:%M:%S', time.localtime(cur_time))}")
                        stuck = True
                    elif data:  # Only update if there's actual data
                        if verbose:
                            print(f"File updated at {time.strftime('%H:%M:%S', time.localtime(cur_time))}")
                        stuck = False
                        old_data = data
                    
                    if stuck and (cur_time - last_alert_time > alert_interval):
                        print(f"⚠️ ALERT: File appears to be stuck! Last change was {int(cur_time - (cur_time - last_alert_time))} seconds ago")
                        self._play_alert()
                        last_alert_time = cur_time
                    
                    sleep(1)
            except KeyboardInterrupt:
                print("\nMonitoring stopped.")
    
    def _play_alert(self) -> None:
        """Play alert sound if sound file is available"""
        if self.sound_file:
            try:
                subprocess.Popen(
                    ["paplay", self.sound_file], 
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            except Exception as e:
                print(f"Failed to play sound: {e}")

if __name__ == "__main__":
    import sys

    n = len(sys.argv)
    if n != 2:
        print("Usage: python candaguardia.py <file>")
        sys.exit(1)

    file = sys.argv[1]
    monitor = CanDaGuardia()
    monitor.monitor(file, verbose=False)