import pyaudio
import socket
import threading
import argparse
import time

class HermesMonitorClient:
    def __init__(self, server_host, server_port, audio_format=pyaudio.paInt16, channels=1, rate=44100, chunk=1024):
        self.server_host = server_host
        self.server_port = server_port
        self.audio_format = audio_format
        self.channels = channels
        self.rate = rate
        self.chunk = chunk
        
        self.audio = pyaudio.PyAudio()
        self.is_running = False
        self.server_socket = None
    
    def connect(self):
        """Connect to the hermes monitor server"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.connect((self.server_host, self.server_port))
            print(f"Connected to hermes monitor at {self.server_host}:{self.server_port}")
            return True
        except Exception as e:
            print(f"Failed to connect: {e}")
            return False
    
    def start(self):
        """Start the client"""
        if not self.connect():
            return
        
        self.is_running = True
        
        # Thread for receiving audio from server (listening to hermes)
        receive_thread = threading.Thread(target=self.receive_audio)
        receive_thread.daemon = True
        receive_thread.start()
        
        # Thread for sending audio to server (talking to hermes)
        send_thread = threading.Thread(target=self.send_audio)
        send_thread.daemon = True
        send_thread.start()
        
        print("Hermes monitor client started!")
        print("Press Ctrl+C to stop")
        
        try:
            while self.is_running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.stop()
    
    def receive_audio(self):
        """Receive audio from server and play it"""
        try:
            stream = self.audio.open(
                format=self.audio_format,
                channels=self.channels,
                rate=self.rate,
                output=True,
                frames_per_buffer=self.chunk
            )
            
            while self.is_running:
                try:
                    data = self.server_socket.recv(self.chunk * 2)
                    if not data:
                        break
                    stream.write(data)
                except Exception as e:
                    print(f"Error receiving audio: {e}")
                    break
                    
            stream.stop_stream()
            stream.close()
            
        except Exception as e:
            print(f"Error in receive audio: {e}")
    
    def send_audio(self):
        """Send audio from microphone to server"""
        try:
            stream = self.audio.open(
                format=self.audio_format,
                channels=self.channels,
                rate=self.rate,
                input=True,
                frames_per_buffer=self.chunk
            )
            
            while self.is_running:
                try:
                    data = stream.read(self.chunk, exception_on_overflow=False)
                    self.server_socket.sendall(data)
                except Exception as e:
                    print(f"Error sending audio: {e}")
                    break
                    
            stream.stop_stream()
            stream.close()
            
        except Exception as e:
            print(f"Error in send audio: {e}")
    
    def stop(self):
        """Stop the client"""
        self.is_running = False
        if self.server_socket:
            self.server_socket.close()
        self.audio.terminate()
        print("Client stopped")

def main():
    parser = argparse.ArgumentParser(description='Hermes Monitor Client')
    parser.add_argument('--server', required=True, help='Server IP address')
    parser.add_argument('--port', type=int, default=5000, help='Server port')
    
    args = parser.parse_args()
    
    client = HermesMonitorClient(args.server, args.port)
    
    try:
        client.start()
    except KeyboardInterrupt:
        print("\nShutting down client...")
    finally:
        client.stop()

if __name__ == "__main__":
    main()
