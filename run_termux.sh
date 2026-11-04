#!/data/data/com.termux/files/usr/bin/bash
# Android (Termux) node.  Usage: bash run_termux.sh phone1 [dashboard_url]
cd "$(dirname "$0")"
NAME=${1:-phone$RANDOM}
if [ -n "$2" ]; then python -m node.node --name "$NAME" --port 7001 --web 8001 --dashboard "$2" --cli
else python -m node.node --name "$NAME" --port 7001 --web 8001 --cli; fi
