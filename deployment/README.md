# Deployment Scripts

Scripts for setting up the Cannabis Dryer Control System on Raspberry Pi.

## Quick Start

### 1. Setup Kiosk Mode (Run Once)

```bash
cd ~/cannabis-dryer/deployment
chmod +x setup_kiosk_mode.sh
./setup_kiosk_mode.sh
# Follow prompts, reboot when asked
```

This configures:
- Backend service to start on boot
- Chromium to launch in fullscreen after login
- Screen to never sleep
- Automatic power loss recovery

### 2. Exit Fullscreen (When Needed)

**Method 1:** Press `Alt + F4` or `F11`

**Method 2:** 
```bash
~/cannabis-dryer/deployment/exit_kiosk.sh
```

### 3. Test Power Recovery

```bash
cd ~/cannabis-dryer
python3 deployment/test_power_recovery.py
# Follow the prompts
```

## What Gets Created

- `/etc/systemd/system/cannabis-dryer.service` - Backend autostart
- `~/.config/autostart/cannabis-dryer-kiosk.desktop` - GUI autostart  
- `deployment/start_kiosk.sh` - Kiosk launcher

## Management

```bash
# Check backend status
sudo systemctl status cannabis-dryer

# Stop backend
sudo systemctl stop cannabis-dryer

# Start backend
sudo systemctl start cannabis-dryer

# View logs
tail -f ~/cannabis-dryer/logs/dryer_control.log
```

## Power Loss Recovery

**Already built-in!** The system:
- Saves state every 10 seconds
- Recovers exact position in cycle
- Continues from where it left off

Example:
```
Running at Day 2, 50% → Power Loss → Restarts → Resumes at Day 2, 50%
```

## Uninstall

```bash
sudo systemctl stop cannabis-dryer
sudo systemctl disable cannabis-dryer
sudo rm /etc/systemd/system/cannabis-dryer.service
rm ~/.config/autostart/cannabis-dryer-kiosk.desktop
```