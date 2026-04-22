# LAFVIN Car Control Server (Modified)

This directory contains the modified server code for the LAFVIN 4WD Raspberry Pi car. The original code has been enhanced to support AI integration and provide better operational feedback.

## Modified Files

### `mainv3.py`

This is the main entry point for the car's control server. It manages the TCP server, camera streaming, and now orchestrates the AI server.

**Original functionality** (preserved):
- Starts a TCP server for remote control commands
- Streams video from the Pi Camera
- Monitors power status

**New functionality** (added):
- **AI Server Management**: Automatically starts the CodeProject.AI container using `podman`
- **AI Readiness Probing**: Waits for the AI server to become ready before marking startup as complete
- **Retry Logic**: Attempts to start the AI container up to 3 times with progressive delays (10s, 20s, 30s)
- **Enhanced Buzzer Patterns**: Different beep sequences indicate startup progress, AI readiness, failures, and shutdown
- **Graceful Error Handling**: If the AI server fails to start, the car continues operating (without AI)

**Key functions added**:
- `start_codeproject_ai()`: Manages the `codeproject-ai` container lifecycle
- `wait_for_ai_server()`: Polls the AI status endpoint until ready or timeout
- `beep(count, duration, pause)`: Configurable buzzer patterns for status indication

**Dependencies added**:
- `subprocess`: For executing `podman` commands
- `requests`: For probing the AI server's HTTP API

### `server.py`

(To be documented based on your modifications.)

## Beep Pattern Reference

The buzzer provides the following status indicators:

| Beep Pattern | Meaning |
| :--- | :--- |
| 1 beep (0.3s) | Server startup attempt started |
| 2 beeps (0.2s on, 0.1s off) | AI container is ready |
| 3 beeps (0.1s on, 0.05s off) | Server started successfully (AI ready) |
| 3 rapid beeps (0.1s on, 0.05s off) | AI server failed, continuing without AI |
| 1 short beep (0.1s) | AI retry attempt failed (waiting) |
| 2 long beeps (0.5s on, 0.2s off) | Server stopping |

## Usage

Run the server as a service or directly:

```bash
cd /path/to/lavfin/Pi4/Server
python3 mainv3.py
````

### The script will:

- Beep once
- Start the CodeProject.AI container (if not already running)
- Wait for the AI server to become ready (up to 90 seconds)
- Start the TCP server and video streaming
- Beep three times to indicate full readiness

### Requirements (Additional)
- podman: Container engine (install with sudo apt install podman)
- CodeProject.AI container: Must be created/pulled separately
- Python packages: requests, picamera2, RPi.GPIO

### Logging
All operations are logged to `/var/log/car_server.log` with timestamps and severity levels. This includes AI container start attempts, readiness checks, and any errors encountered.

### Signal Handling
The script responds to the following signals:

**SIGINT, SIGTERM:** Shutdown gracefully
**SIGUSR1:** Stop the server (without full shutdown)
**SIGUSR2:** Restart the server (stop then start)


### `server.py` – AI‑Enhanced Video & Control Server

This is the core network server that handles:
- TCP command reception (motor, servo, LED, etc.)
- Video streaming (JPEG over TCP)
- **New:** Real‑time object detection using CodeProject.AI

#### Modifications Overview

| Original | Modified |
| :--- | :--- |
| No AI capabilities | Full integration with CodeProject.AI Server |
| Single `StreamingOutput` class | Extended with `ai_frame` and `ai_condition` for AI thread |
| Synchronous video streaming only | Asynchronous detection worker with queue‑based frame handling |
| No automatic actions | LED/buzzer responses to detected people, dogs, cats |
| No image saving | Saves detection images with bounding boxes to `/tmp/` |

#### Key New Components

## 1. Extended `StreamingOutput`
```python
class StreamingOutput(io.BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = Condition()
        self.ai_frame = None      # <-- added
        self.ai_condition = Condition()  # <-- added
```

Every written frame is copied to both `frame` (for live video) and `ai_frame` (for detection).

---

## 2. Asynchronous Detection Worker (`async_detection_worker`)

- Runs in a background thread.
- Uses a **single-frame queue** (`maxsize=1`) to always keep the latest frame.  
  Older frames are discarded if the queue is full.
- Posts frames to  
  `http://localhost:32168/v1/vision/detection`  
  with an **8‑second timeout**.
- Old results (**> 3 seconds**) are ignored to prevent lag.

---

## 3. Optimised Detection Loop (`detect_objects` & `ai_detection_loop`)

- Called every **50 ms** (**20 Hz**).
- Resizes frames to **320×240** (from **400×300**).
- Reduces JPEG quality to **60%** for faster AI inference.
- Sends frames to the queue and immediately processes any completed results.

---

## 4. Detection Actions (`on_object_detected`)

- **Person**
  - LED index **1** (red) flashes
  - Buzzer beeps for **0.1 s**
- **Dog or cat**
  - LED index **2** (green) flashes for **0.2 s**

---

## 5. Image Saving (`save_detection_image`)

- Saves a copy of the original frame with:
  - Green bounding box
  - Object label
- Coordinates are scaled from:
  - AI input size **320×240**
  - Back to original **400×300**
- Files are stored as: `/tmp/detected_{label}_{timestamp}_{confidence}.jpg`

## 6. Cooldown & Rate Limiting

- `self.detection_cooldown = 5` seconds between saving images for the same object type.
- Prevents flooding the filesystem with duplicate detections.

---

## Performance Optimisations

- **Single-frame queue**  
  Avoids building a backlog of frames to process.

- **Time-stamped frames**  
  Detection results older than **3 seconds** are discarded.

- **Smaller AI resolution**  
  Uses **320×240** instead of **400×300**.

- **Lower JPEG quality**  
  - **60%** for AI inference  
  - **90%** for live video streaming

- **Non-blocking design**  
  Video streaming continues uninterrupted even if the AI server is slow.

---

## Dependencies Added

- `requests` — HTTP calls to CodeProject.AI
- `cv2` (OpenCV) — image decoding, resizing, and drawing bounding boxes
- `queue` — thread-safe frame passing between threads

---

## Logging & Debugging

- Detection events are printed to the console.  
  Example:
 ````
ALERTA: Detectado PERSON con 0.85
```
- Error messages include:
- API timeouts
- Failed detection requests

---

## Integration with `mainv3.py`

- `mainv3.py`
- Ensures the CodeProject.AI container is running
- Starts the TCP server

- `server.py`
- Assumes the AI server is already available at `localhost:32168`

Together, these components provide a **complete AI-aware robot control system**.
