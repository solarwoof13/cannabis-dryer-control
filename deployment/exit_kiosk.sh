#!/bin/bash
# Exit Kiosk Mode - Return to Desktop

echo "Exiting kiosk mode..."
pkill -f chromium-browser
xset s on
xset +dpms
pkill unclutter
echo "✓ Done. Desktop restored."
echo ""
echo "To restart kiosk: ~/cannabis-dryer/deployment/start_kiosk.sh"