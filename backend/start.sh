#!/bin/bash

# Set UTF-8 encoding (Mac/Linux)
export LANG=en_US.UTF-8

echo "========================================"
echo "   TestHub Service Startup Script (Linux/Mac)"
echo "========================================"
echo ""

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

# Check Python environment
echo "Checking Python environment..."

# Use virtual environment if available
if [ -f "venv/bin/python" ]; then
    echo "Found virtual environment: venv"
    PYTHON_CMD="venv/bin/python"
elif [ -f ".venv/bin/python" ]; then
    echo "Found virtual environment: .venv"
    PYTHON_CMD=".venv/bin/python"
elif [ -n "$VIRTUAL_ENV" ]; then
    echo "Already in virtual environment"
    PYTHON_CMD="python"
else
    # Use specified virtual environment
    VENV_PATH="/d/ENV/TestHub"
    if [ -f "$VENV_PATH/bin/python" ]; then
        echo "Using specified virtual environment: $VENV_PATH"
        PYTHON_CMD="$VENV_PATH/bin/python"
    else
        echo "Error: Virtual environment not found!"
        echo "Please create virtual environment or activate virtual environment"
        echo "Expected path: $VENV_PATH"
        exit 1
    fi
fi

echo "Python command: $PYTHON_CMD"
echo ""

# Activate virtual environment (optional, for setting environment variables)
if [ -f "$VENV_PATH/bin/activate" ]; then
    source "$VENV_PATH/bin/activate"
fi

# Check configuration file
# Note: Script is in backend directory, need to read config.yaml from parent directory
if [ ! -f "../config.yaml" ]; then
    echo "Error: Configuration file ../config.yaml not found"
    exit 1
fi

# Read port configuration from config.yaml
# Note: Script is in backend directory, need to read config.yaml from parent directory
BACKEND_PORT=$(grep "backend_port:" ../config.yaml | awk '{print $2}' | tr -d ' ')

# Use default port if not found
if [ -z "$BACKEND_PORT" ]; then
    BACKEND_PORT=8000
fi

echo "[1/2] Starting Django development server..."
echo "Starting backend server, port: $BACKEND_PORT"

# Start Django server
"$PYTHON_CMD" manage.py runserver 0.0.0.0:"$BACKEND_PORT" &
DJANGO_PID=$!

sleep 2

# Check if process started successfully
if kill -0 $DJANGO_PID 2>/dev/null; then
    echo "✓ Django server started (PID: $DJANGO_PID)"
else
    echo "✗ Django server startup failed"
    exit 1
fi

echo "[2/2] Starting Django-Q task queue service..."

# Start Django-Q
"$PYTHON_CMD" manage.py qcluster &
QCLUSTER_PID=$!

sleep 2

# Check if process started successfully
if kill -0 $QCLUSTER_PID 2>/dev/null; then
    echo "✓ Django-Q cluster started (PID: $QCLUSTER_PID)"
else
    echo "✗ Django-Q cluster startup failed"
    kill $DJANGO_PID 2>/dev/null
    exit 1
fi

echo ""
echo "========================================"
echo "   All services started!"
echo "========================================"
echo ""
echo "Process information:"
echo "  - Django Server: PID $DJANGO_PID"
echo "  - Django-Q Cluster: PID $QCLUSTER_PID"
echo ""
echo "Tips:"
echo "  - Stop services: kill $DJANGO_PID $QCLUSTER_PID"
echo "  - View logs: tail -f logs/django_server.log"
echo "  - View logs: tail -f logs/django_q.log"
echo ""

# Save PID to file
echo "$DJANGO_PID" > django_server.pid
echo "$QCLUSTER_PID" > django_qcluster.pid

# Monitor process
trap cleanup SIGINT SIGTERM

cleanup() {
    echo ""
    echo "Stopping services..."
    kill $DJANGO_PID 2>/dev/null
    kill $QCLUSTER_PID 2>/dev/null
    rm -f django_server.pid django_qcluster.pid
    echo "All services stopped"
    exit 0
}

# Keep script running (optional, if you want script to continue running)
wait
