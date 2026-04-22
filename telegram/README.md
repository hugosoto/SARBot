# Telegram Alerts for Detected Objects

This folder contains a Bash script that automatically sends any detection image (saved by `server.py`) to a Telegram chat group. It is ideal for remote monitoring during search‑and‑rescue missions.

## How It Works

1. The robot’s AI detection (`server.py`) saves JPEG images with bounding boxes to `/tmp/detected_*.jpg`.
2. The script scans `/tmp/` for files matching `detect*.jpg`.
3. For each file, it uses the Telegram Bot API to send the photo.
4. After sending, it moves the file to `/tmp/processed/` to prevent re‑sending.

## Requirements

- `curl` – usually pre‑installed on Raspberry Pi OS.
- A **Telegram Bot** (create one via [@BotFather](https://t.me/botfather)).
- Your **Chat ID** (the group or user where you want to receive alerts).

## Setup

### 1. Create a Telegram Bot
- Open Telegram and search for `@BotFather`.
- Send `/newbot` and follow the prompts.
- Save the **API token** (looks like `123456789:ABCdefGHIjklmNOPqrstUVwxyz`).

### 2. Get Your Chat ID
- Add your bot to a group (or send a message to it privately).
- Visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
- Find the `"chat":{"id": ...}` value. For a group, it may be negative.

### 3. Configure the Script
Edit `send_detections.sh` and replace:
```bash
TELEGRAM_API_TOKEN="YOUR_TELEGRAM_API_TOKEN"
CHAT_ID="YOUR_CHAT_ID"
```
*Security tip:* Instead of hardcoding, you can read from environment variables:
```
TELEGRAM_API_TOKEN="${TELEGRAM_BOT_TOKEN}"
CHAT_ID="${TELEGRAM_CHAT_ID}"
```

Then set them in ~/.bashrc or a .env file.

---

## 4. Make the Script Executable

    chmod +x telegram/send_detections.sh

---

## Manual Execution

Run it once to test:

    ./telegram/send_detections.sh

If there are any `detected_*.jpg` files in `/tmp/`, they will be sent to Telegram and moved to `/tmp/processed/`.

---

## Automating with Cron

To send images every minute (recommended), add a cron job.

Edit the crontab:

    crontab -e

Add this line:

    * * * * * /home/pi/your-robot-repo/telegram/send_detections.sh > /dev/null 2>&1

**Note:** Replace `/home/pi/your-robot-repo/` with the actual absolute path to your repository.

---

## File Locations

| Path | Purpose |
|------|--------|
| /tmp/detected_*.jpg | Fresh detection images (created by server.py) |
| /tmp/processed/ | Archive of already-sent images (moved automatically) |

---

## Troubleshooting

### No images are sent
- Check that `server.py` is saving files.
- Look for `Imagen guardada:` in the car’s log.

### Telegram returns error
- Verify your API token and chat ID.
- Test manually:

        curl -X POST "https://api.telegram.org/bot<TOKEN>/sendMessage" \
             -d "chat_id=<CHAT_ID>&text=Hello"

### Permission denied
- Ensure the script is executable:

        chmod +x telegram/send_detections.sh

- Ensure the user running the script (e.g., pi) has write access to:

        /tmp/processed/

  (The directory is created automatically by the script.)

---

## Integration with the Main Robot

- `mainv3.py` starts the AI container and the TCP server.
- `server.py` saves detection images to `/tmp/`.
- `send_detections.sh` (via cron) forwards them to Telegram.

No changes are needed inside the Python code — the script works independently.

## Alternative: Run Continuously with `/etc/rc.local`

If you prefer the script to run once at boot and then keep watching for new files (e.g., using `inotify` or a simple loop), you can add it to `/etc/rc.local`. This approach avoids cron and ensures the script is always active.

### Example: Continuous Monitoring Version

First, create a modified script that loops forever:

```bash
#!/bin/bash
# /home/pi/your-robot-repo/telegram/send_detections_daemon.sh

SOURCE_DIR="/tmp"
PROCESSED_DIR="/tmp/processed"
TELEGRAM_API_TOKEN="YOUR_TOKEN"
CHAT_ID="YOUR_CHAT_ID"

mkdir -p "$PROCESSED_DIR"

while true; do
    for file in "$SOURCE_DIR"/detect*.jpg; do
        if [ -f "$file" ]; then
            curl -s -X POST "https://api.telegram.org/bot$TELEGRAM_API_TOKEN/sendPhoto" \
                -F chat_id="$CHAT_ID" \
                -F photo="@${file}"
            mv "$file" "$PROCESSED_DIR"
        fi
    done
    sleep 5   # Check every 5 seconds
done
````
## Make the Script Executable

Make the daemon script executable:

    chmod +x /home/pi/your-robot-repo/telegram/send_detections_daemon.sh

---

## Add to `/etc/rc.local`

Edit `/etc/rc.local` as root:

    sudo nano /etc/rc.local

Before the `exit 0` line, add:

    su - pi -c "/home/pi/your-robot-repo/telegram/send_detections_daemon.sh &"

---

### Notes

- `su - pi` runs the script as the **pi** user  
  (adjust `pi` if you are using a different username).
- The trailing `&` runs the script in the **background**, so the boot process is not blocked.
