# Raspberry Pi Setup Guide

## Initial Pi Configuration

1. **Install Raspberry Pi OS**
   - Use Raspberry Pi Imager
   - Choose "Raspberry Pi OS (64-bit)" 
   - Enable SSH during setup

2. **Enable I2C**
```bash
   sudo raspi-config
   # Interface Options -> I2C -> Enable
   sudo reboot