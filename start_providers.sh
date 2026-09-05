#!/bin/bash
# Start all three providers in background

cd /workspaces/x402-skill-provider

# Activate virtual environment
source venv/bin/activate

echo "Starting Provider 1 (Standard) on port 5000..."
python provider_agent/server.py > /tmp/provider1.log 2>&1 &
PROVIDER1_PID=$!
echo "Provider 1 PID: $PROVIDER1_PID"

sleep 2

echo "Starting Provider 2 (Speed Specialist) on port 5001..."
python provider_agent/provider2.py > /tmp/provider2.log 2>&1 &
PROVIDER2_PID=$!
echo "Provider 2 PID: $PROVIDER2_PID"

sleep 2

echo "Starting Provider 3 (Value Hunter) on port 5002..."
python provider_agent/provider3.py > /tmp/provider3.log 2>&1 &
PROVIDER3_PID=$!
echo "Provider 3 PID: $PROVIDER3_PID"

sleep 2

# Save PIDs for cleanup
echo "$PROVIDER1_PID $PROVIDER2_PID $PROVIDER3_PID" > /tmp/provider_pids.txt

# Wait a bit for servers to start
sleep 3

# Check if all are running
for port in 5000 5001 5002; do
  if curl -s http://127.0.0.1:$port/health > /dev/null; then
    echo "✓ Provider on port $port is running"
  else
    echo "✗ Provider on port $port failed to start"
  fi
done
