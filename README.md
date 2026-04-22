# SARBot
This project transforms a standard LAFVIN Raspberry Pi car into an autonomous search and rescue robot. It integrates local AI-powered object detection to identify people, cats, and dogs. Key enhancements over the base model include a two-way audio system for real-time communication with survivors and a thermal camera to assess their condition.

**Key Features:**

- AI Object Detection: Uses computer vision to identify people, cats, and dogs.
- Two-Way Audio: Enables real-time communication between a remote operator and a survivor, acting as a mobile walkie-talkie.
- Thermal Camera: Detects body heat signatures to help determine if a victim is alive.
- Base Platform: Built upon the 4WD LAFVIN Raspberry Pi car

## Two‑Way Audio - Hermes

Hermes is a real‑time, full‑duplex audio communication system that turns your rescue robot into a mobile walkie‑talkie.  
It allows a remote operator to speak with a survivor (and hear them back) without any third‑party services.

- **Server (on the robot)**
 Captures audio from a USB microphone, streams it to the operator, and plays back incoming audio through a speaker.  
  It also monitors sound levels and prints an alert when a loud noise (e.g., a cry for help) is detected.

- **Client (on your laptop / controller)**
Connects to the robot, sends your voice to the robot’s speaker, and plays back any sound the robot’s microphone picks up.

Both components use **TCP sockets** and **PyAudio** for low‑latency audio streaming.  
The system is completely self‑contained and no internet required, works on a local network.

Full code, setup instructions, and usage examples are available in the [`hermes/`](hermes/) folder.