#!/bin/sh
# Run follow-up WhatsApp reminders once per day around 08:00 Asia/Karachi.
set -e
export TZ="${TZ:-Asia/Karachi}"

echo "follow-up reminder loop started (TZ=$TZ)"
while true; do
  H=$(date +%H)
  M=$(date +%M)
  # Window: 08:00–08:04 local
  if [ "$H" = "08" ] && [ "$M" -lt "5" ]; then
    echo "$(date -Iseconds) running send_follow_up_reminders"
    python manage.py send_follow_up_reminders || true
    sleep 300
  fi
  sleep 60
done
