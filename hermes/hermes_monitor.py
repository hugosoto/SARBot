import pyaudio
import socket
import threading
import time
import numpy as np
import argparse
from collections import deque

class HermesMonitor:
    def __init__(self, host='0.0.0.0', port=5000, audio_format=pyaudio.paInt16, channels=1, rate=44100, chunk=1024):
        self.audio_format = audio_format
        self.channels = channels
        self.rate = rate
        self.chunk = chunk
        self.host = host
        self.port = port
        
        self.audio = pyaudio.PyAudio()
        self.is_running = False
        self.clients = []
        
        # Audio level monitoring for hermes cries
        self.audio_levels = deque(maxlen=100)  # Store last 100 audio levels
        self.alert_threshold = 1000  # Adjust based on testing
        
    def find_audio_devices(self):
        """Find available audio input and output devices"""
        print("Available audio devices:")
        for i in range(self.audio.get_device_count()):
            info = self.audio.get_device_info_by_index(i)
            print(f"{i}: {info['name']} - Inputs: {info['maxInputChannels']}, Outputs: {info['maxOutputChannels']}")
            
    def start_server(self):
        """Start the hermes monitor server"""
        self.is_running = True
        
        # Create TCP server socket
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        
        print(f"Hermes Monitor Server started on {self.host}:{self.port}")
        print("Waiting for connections...")
        
        # Start audio streaming thread
        audio_thread = threading.Thread(target=self.stream_audio)
        audio_thread.daemon = True
        audio_thread.start()
        
        # Start client acceptance thread
        accept_thread = threading.Thread(target=self.accept_clients)
        accept_thread.daemon = True
        accept_thread.start()
        
        # Start command interface
        self.command_interface()
        
    def accept_clients(self):
        """Accept incoming client connections"""
        while self.is_running:
            try:
                client_socket, address = self.server_socket.accept()
                print(f"New connection from {address}")
                self.clients.append(client_socket)
                
                # Start thread to handle incoming audio from this client
                client_thread = threading.Thread(target=self.handle_client_audio, args=(client_socket,))
                client_thread.daemon = True
                client_thread.start()
                
            except Exception as e:
                if self.is_running:
                    print(f"Error accepting client: {e}")
    
    def stream_audio(self):
        """Stream audio from microphone to connected clients"""
        try:
            # Try to find USB microphone (usually higher index)
            input_device = None
            for i in range(self.audio.get_device_count()):
                info = self.audio.get_device_info_by_index(i)
                if info['maxInputChannels'] > 0 and 'USB' in info['name'].upper():
                    input_device = i
                    print(f"Using USB microphone: {info['name']}")
                    break
            
            if input_device is None:
                print("USB microphone not found, using default input device")
                input_device = None
            
            stream = self.audio.open(
                format=self.audio_format,
                channels=self.channels,
                rate=self.rate,
                input=True,
                input_device_index=input_device,
                frames_per_buffer=self.chunk
            )
            
            print("Started audio streaming from microphone...")
            
            while self.is_running:
                try:
                    # Read audio data
                    data = stream.read(self.chunk, exception_on_overflow=False)
                    
                    # Calculate audio level for hermes cry detection
                    audio_data = np.frombuffer(data, dtype=np.int16)
                    audio_level = np.sqrt(np.mean(audio_data**2))
                    self.audio_levels.append(audio_level)
                    
                    # Check for loud sounds (potential hermes cry)
                    if audio_level > self.alert_threshold and len(self.audio_levels) > 10:
                        avg_level = np.mean(list(self.audio_levels)[-10:])
                        if avg_level > self.alert_threshold:
                            print(f"🔊 Loud sound detected! Level: {audio_level:.0f}")
                    
                    # Send to all connected clients
                    self.broadcast_to_clients(data)
                    
                except Exception as e:
                    print(f"Error in audio streaming: {e}")
                    time.sleep(0.1)
                    
            stream.stop_stream()
            stream.close()
            
        except Exception as e:
            print(f"Error opening audio stream: {e}")
    
    def handle_client_audio(self, client_socket):
        """Handle incoming audio from client and play through speaker"""
        try:
            # Setup output stream for speaker
            output_device = None
            for i in range(self.audio.get_device_count()):
                info = self.audio.get_device_info_by_index(i)
                if info['maxOutputChannels'] > 0 and ('bcm2835' in info['name'].lower() or 'headphones' in info['name'].lower()):
                    output_device = i
                    print(f"Using speaker: {info['name']}")
                    break
            
            if output_device is None:
                print("Speaker not found, using default output device")
                output_device = None
            
            output_stream = self.audio.open(
                format=self.audio_format,
                channels=self.channels,
                rate=self.rate,
                output=True,
                output_device_index=output_device,
                frames_per_buffer=self.chunk
            )
            
            while self.is_running:
                try:
                    # Receive audio data from client
                    data = client_socket.recv(self.chunk * 2)  # *2 because 16-bit = 2 bytes
                    if not data:
                        break
                    
                    # Play the received audio
                    output_stream.write(data)
                    
                except Exception as e:
                    print(f"Error handling client audio: {e}")
                    break
                    
            output_stream.stop_stream()
            output_stream.close()
            
        except Exception as e:
            print(f"Error setting up output stream: {e}")
        
        # Remove client when done
        if client_socket in self.clients:
            self.clients.remove(client_socket)
        client_socket.close()
    
    def broadcast_to_clients(self, data):
        """Send audio data to all connected clients"""
        disconnected_clients = []
        for client in self.clients:
            try:
                client.sendall(data)
            except:
                disconnected_clients.append(client)
        
        # Remove disconnected clients
        for client in disconnected_clients:
            self.clients.remove(client)
            client.close()
    
    def command_interface(self):
        """Simple command interface for local control"""
        print("\nHermes Monitor Command Interface")
        print("Commands: 'status', 'clients', 'threshold [value]', 'quit'")
        
        while self.is_running:
            try:
                cmd = input("> ").strip().lower()
                
                if cmd == 'status':
                    print(f"Connected clients: {len(self.clients)}")
                    if self.audio_levels:
                        current_level = self.audio_levels[-1]
                        print(f"Current audio level: {current_level:.0f}")
                        
                elif cmd == 'clients':
                    print(f"Connected to {len(self.clients)} client(s)")
                    
                elif cmd.startswith('threshold'):
                    try:
                        new_threshold = int(cmd.split()[1])
                        self.alert_threshold = new_threshold
                        print(f"Alert threshold set to: {new_threshold}")
                    except:
                        print(f"Current alert threshold: {self.alert_threshold}")
                        
                elif cmd == 'quit':
                    self.stop()
                    break
                    
            except KeyboardInterrupt:
                self.stop()
                break
            except Exception as e:
                print(f"Command error: {e}")
    
    def stop(self):
        """Stop the hermes monitor"""
        self.is_running = False
        print("Stopping hermes monitor...")
        
        # Close all client connections
        for client in self.clients:
            client.close()
        
        # Close server socket
        if hasattr(self, 'server_socket'):
            self.server_socket.close()
        
        # Terminate PyAudio
        self.audio.terminate()

def main():
    parser = argparse.ArgumentParser(description='Hermes Monitor Server')
    parser.add_argument('--host', default='0.0.0.0', help='Host IP address')
    parser.add_argument('--port', type=int, default=5000, help='Port number')
    parser.add_argument('--list-devices', action='store_true', help='List audio devices')
    
    args = parser.parse_args()
    
    monitor = HermesMonitor(host=args.host, port=args.port)
    
    if args.list_devices:
        monitor.find_audio_devices()
        return
    
    try:
        monitor.start_server()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        monitor.stop()

if __name__ == "__main__":
    main()
