# Hermes – Two‑Way Audio for the Rescue Robot

Hermes provides real‑time, bidirectional voice communication between the robot and a remote operator.  
It acts like a **walkie‑talkie** or **phone line** over your local Wi‑Fi network.

## How It Works

- **HermesMonitor (server)** – Runs on the Raspberry Pi (the robot).  
  - Uses a USB microphone to capture ambient sound (including a survivor’s voice).  
  - Streams that audio to the connected client.  
  - Plays back audio received from the client through a speaker.  
  - Monitors audio levels and prints an alert when a loud sound (e.g., a scream) is detected.

- **HermesMonitorClient** – Runs on the operator’s computer (laptop, tablet, or another Pi).  
  - Sends your voice from its microphone to the robot.  
  - Plays back the audio coming from the robot’s microphone.

Both programs use **TCP sockets** and **PyAudio** for low‑latency, full‑duplex streaming.

## Requirements

- Python 3.7+
- PyAudio (`pip install pyaudio`)
- NumPy (`pip install numpy`) – only for the server (audio level monitoring)
- A working microphone and speaker on both ends.

On **Raspberry Pi**, you may need to install PortAudio first:
```bash
sudo apt-get install portaudio19-dev python3-pyaudio
```

## Installation

1. Clone the repository or copy the `hermes/` folder to both the robot and your operator computer.
2. Install the Python dependencies:
   ```bash
   pip install pyaudio numpy
   ```

## Usage

### On the Robot (Server)

Run the server **before** starting the client. The server binds to all network interfaces (for example `192.168.1.100`) and listens on port `5000`.

```bash
cd hermes
python hermes_monitor.py --host 192.168.1.100 --port 5000
```

Optional arguments:
- `--list-devices` – Show available audio input/output devices (useful for selecting the correct mic/speaker).
- `--port` – Change the port if needed.

The server will print:
- Available audio devices (if `--list-devices` is used).
- A command interface where you can type:
  - `status` – Show connected clients and current audio level.
  - `clients` – Number of connected clients.
  - `threshold [value]` – Change the loud‑sound alert threshold.
  - `quit` – Stop the server.

### On the Operator Computer (Client)

Connect to the robot’s IP address:

```bash
cd hermes
python hermes_client.py --server <ROBOT_IP> --port 5000
```

Example:
```bash
python hermes_client.py --server 192.168.1.100
```

Once connected, you can speak into your microphone – your voice will be heard from the robot’s speaker.  
Any sound the robot’s microphone picks up (e.g., a survivor talking) will be played on your computer’s speakers/headphones.

Press `Ctrl+C` on either side to stop the connection.

## Audio Device Selection

By default, the server tries to automatically pick:
- **Input** – The first USB microphone it finds (otherwise the default input).
- **Output** – The built‑in speaker (`bcm2835` or `headphones`) on the Pi.

If you need to use specific devices, run `--list-devices` on the robot, note the device index, and modify the code (look for `input_device` and `output_device` logic in the server).  
A future version will expose these as command‑line arguments.

## Troubleshooting

- **No sound on the robot’s speaker** – Check that the speaker is connected and the volume is not muted.  
  Test with `speaker-test -t sine -f 1000 -c 2` on the Pi.

- **High latency or choppy audio** – Reduce the `chunk` size (default 1024) or lower the sample rate (default 44100).  
  Edit the `HermesMonitor` class parameters in the code.

- **Client cannot connect** – Ensure the robot’s firewall allows the chosen port (e.g., `sudo ufw allow 5000`), and that both devices are on the same network.

## Files

- `hermes_monitor.py` – Server code (robot side).
- `hermes_client.py` – Client code (operator side).

## Future Improvements

- Add command‑line options for selecting audio devices.
- Implement automatic reconnection if the network drops.
- Add audio recording for post‑mission analysis.
