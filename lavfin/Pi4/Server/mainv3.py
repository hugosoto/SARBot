import io
import os
import socket
import struct
import time
import picamera2
import sys
import signal
import threading
import logging
import subprocess
import requests
from server import Server
import RPi.GPIO as GPIO

# 配置日志
logging.basicConfig(filename='/var/log/car_server.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

BUZZER_PIN = 17

class ServerController:
    def __init__(self):
        self.TCP_Server = Server()
        self.is_running = False
        self.threads = []
        self.stop_event = threading.Event()

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(BUZZER_PIN, GPIO.OUT)
        GPIO.output(BUZZER_PIN, GPIO.LOW)

    def beep(self, count=1, duration=0.3, pause=0.2):
        """Make beep pattern with specified count and timing"""
        try:
            for i in range(count):
                GPIO.output(BUZZER_PIN, GPIO.HIGH)
                time.sleep(duration)
                GPIO.output(BUZZER_PIN, GPIO.LOW)
                if i < count - 1:  # Don't pause after the last beep
                    time.sleep(pause)
        except Exception as e:
            logging.error(f"Buzzer error: {e}")

    def start_codeproject_ai(self):
        """Start CodeProject AI container with retries and beep feedback"""
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                logging.info(f"Attempt {attempt + 1}/{max_retries} to start CodeProject AI container...")
                
                # First, check if container exists and get its status
                check_result = subprocess.run(
                    ["podman", "ps", "-a", "--filter", "name=codeproject-ai", "--format", "{{.Names}}:{{.Status}}"],
                    capture_output=True, text=True, timeout=10
                )
                
                container_found = False
                container_running = False
                
                if "codeproject-ai" in check_result.stdout:
                    container_found = True
                    if "Up" in check_result.stdout:
                        container_running = True
                        logging.info("CodeProject AI container is already running")
                        # Beep twice to indicate AI is ready
                        threading.Thread(target=self.beep, args=(2, 0.2, 0.1), daemon=True).start()
                        return True
                
                # If container exists but isn't running, start it
                if container_found and not container_running:
                    logging.info("Container exists but not running - starting it...")
                    start_result = subprocess.run(
                        ["podman", "start", "codeproject-ai"],
                        capture_output=True, text=True, timeout=30
                    )
                else:
                    # If container doesn't exist or we need to restart it
                    logging.info("Starting/restarting CodeProject AI container...")
                    start_result = subprocess.run(
                        ["podman", "restart", "codeproject-ai"],
                        capture_output=True, text=True, timeout=30
                    )
                
                if start_result.returncode == 0:
                    logging.info("CodeProject AI container command executed successfully")
                    
                    # Wait for AI server to be ready with progress beeps
                    if self.wait_for_ai_server(attempt + 1):
                        # Success - beep twice
                        threading.Thread(target=self.beep, args=(2, 0.2, 0.1), daemon=True).start()
                        return True
                    else:
                        logging.warning(f"AI server not ready after container start (attempt {attempt + 1})")
                        # Beep once to indicate failure on this attempt
                        threading.Thread(target=self.beep, args=(1, 0.1, 0), daemon=True).start()
                else:
                    logging.error(f"Failed to start container (attempt {attempt + 1}): {start_result.stderr}")
                    # Beep once to indicate failure
                    threading.Thread(target=self.beep, args=(1, 0.1, 0), daemon=True).start()
                
                # Wait before retry (longer wait after each failure)
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 10  # 10, 20, 30 seconds
                    logging.info(f"Waiting {wait_time} seconds before retry...")
                    time.sleep(wait_time)
                    
            except subprocess.TimeoutExpired:
                logging.error(f"Timeout starting CodeProject AI container (attempt {attempt + 1})")
                # Beep once to indicate timeout
                threading.Thread(target=self.beep, args=(1, 0.1, 0), daemon=True).start()
                
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 10
                    logging.info(f"Waiting {wait_time} seconds before retry...")
                    time.sleep(wait_time)
                    
            except Exception as e:
                logging.error(f"Error starting CodeProject AI container (attempt {attempt + 1}): {e}")
                # Beep once to indicate error
                threading.Thread(target=self.beep, args=(1, 0.1, 0), daemon=True).start()
                
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 10
                    logging.info(f"Waiting {wait_time} seconds before retry...")
                    time.sleep(wait_time)
        
        logging.error(f"Failed to start CodeProject AI container after {max_retries} attempts")
        return False

    def wait_for_ai_server(self, attempt, timeout=90):
        """Wait for CodeProject AI server to be ready with progress indication"""
        logging.info(f"Waiting for CodeProject AI server to be ready (attempt {attempt})...")
        start_time = time.time()
        check_count = 0
        
        while time.time() - start_time < timeout:
            try:
                # Try to connect to the AI server
                response = requests.get("http://localhost:32168/v1/status", timeout=5)
                if response.status_code == 200:
                    logging.info("CodeProject AI server is ready and responding!")
                    return True
            except requests.exceptions.ConnectionError:
                pass  # Server not ready yet
            except Exception as e:
                logging.debug(f"AI server check error: {e}")
            
            check_count += 1
            
            # Beep every 10 checks to show we're still waiting (but only short beeps)
            if check_count % 10 == 0:
                threading.Thread(target=self.beep, args=(1, 0.05, 0), daemon=True).start()
            
            time.sleep(2)
            
            # Log progress every 20 seconds
            if check_count % 10 == 0:
                elapsed = time.time() - start_time
                logging.info(f"Still waiting for AI server... ({elapsed:.0f}s elapsed)")
        
        logging.error(f"CodeProject AI server did not become ready within {timeout} seconds")
        return False

    def start_server(self):
        if not self.is_running:
            logging.info("Starting server...")
            
            # Start with a single beep to indicate server start attempt
            threading.Thread(target=self.beep, args=(1, 0.3, 0), daemon=True).start()
            
            # Start CodeProject AI container first
            ai_ready = self.start_codeproject_ai()
            
            if not ai_ready:
                logging.warning("CodeProject AI container not available, AI features will not work")
                # Three short beeps to indicate AI failure but server will start
                threading.Thread(target=self.beep, args=(3, 0.1, 0.05), daemon=True).start()
            else:
                logging.info("CodeProject AI container is ready")
            
            # Start TCP server
            self.TCP_Server.StartTcpServer()
            self.threads = [
                threading.Thread(target=self.run_thread, args=(self.TCP_Server.readdata, "ReadData")),
                threading.Thread(target=self.run_thread, args=(self.TCP_Server.sendvideo, "SendVideo")),
                threading.Thread(target=self.run_thread, args=(self.TCP_Server.Power, "Power"))
            ]
            for thread in self.threads:
                thread.daemon = True
                thread.start()
            self.is_running = True
            logging.info("Server started")

            # Final success beep pattern
            threading.Thread(target=self.beep, args=(3, 0.1, 0.05), daemon=True).start()
        else:
            logging.info("Server is already running")

    def run_thread(self, target, name):
        while not self.stop_event.is_set():
            try:
                target()
            except Exception as e:
                logging.error(f"Error in {name} thread: {e}")
                break

    def stop_server(self):
        if self.is_running:
            logging.info("Stopping server...")
            self.stop_event.set()
            self.TCP_Server.StopTcpServer()
            for thread in self.threads:
                thread.join(timeout=3)  # 给每个线程3秒时间来结束
            self.is_running = False
            # Two long beeps to indicate server stop
            threading.Thread(target=self.beep, args=(2, 0.5, 0.2), daemon=True).start()
            logging.info("Server stopped")
        else:
            logging.info("Server is not running")

    def run(self):
        self.start_server()  # 自动开启 TCP 服务器
        try:
            while not self.stop_event.is_set():
                time.sleep(1)  # 主循环中的简单等待
        except KeyboardInterrupt:
            logging.info("Program interrupted by user")
        finally:
            self.stop_server()

def cleanup():
    logging.info("Cleaning up resources...")
    try:
        if hasattr(picamera2.Picamera2, 'global_cleanup'):
            picamera2.Picamera2.global_cleanup()
        else:
            logging.warning("Picamera2 global_cleanup not available")
        GPIO.cleanup()
    except Exception as e:
        logging.error(f"Error during cleanup: {e}")

def handle_stop(signum, frame):
    logging.info("Stop signal received")
    controller.stop_server()

def handle_restart(signum, frame):
    logging.info("Restart signal received")
    controller.stop_server()
    controller.start_server()

if __name__ == '__main__':
    controller = ServerController()
    
    def shutdown(signum, frame):
        logging.info("Shutdown signal received")
        controller.stop_server()
        cleanup()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGUSR1, handle_stop)  # 用于停止服务器
    signal.signal(signal.SIGUSR2, handle_restart)  # 用于重启服务器

    try:
        controller.run()
    finally:
        cleanup()
        
        logging.info("Waiting for all threads to finish (10 seconds timeout)...")
        timeout = time.time() + 10
        while threading.active_count() > 1 and time.time() < timeout:
            time.sleep(0.1)
        
        remaining_threads = threading.enumerate()
        if len(remaining_threads) > 1:
            logging.warning(f"Force quitting. {len(remaining_threads) - 1} threads did not finish in time:")
            for thread in remaining_threads:
                if thread != threading.current_thread():
                    logging.warning(f"- {thread.name}")
            os._exit(1)
        else:
            logging.info("All threads finished. Exiting normally.")
            sys.exit(0)