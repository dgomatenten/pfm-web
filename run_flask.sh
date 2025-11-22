#!/bin/bash

# Script to run Flask development server with virtual environment

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"


# Get local IP address for display
LOCAL_IP=$(hostname -I | awk '{print $1}')

echo "========================================"
echo "Starting Flask development server"
echo "Local URL: http://127.0.0.1:5000"
echo "Network URL: http://$LOCAL_IP:5000"
echo "API Base URL for Android: http://$LOCAL_IP:5000/api/v1"
echo "========================================"
echo ""

# Run Flask app
./pfm/bin/python3 app.py

