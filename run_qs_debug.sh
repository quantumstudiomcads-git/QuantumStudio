#!/bin/bash

cd ~/QuantumStudio
source .venv/bin/activate

echo "=============================================="
echo " QUANTUM STUDIO — CRASH DIAGNOSTIC"
echo "=============================================="
echo
echo "Working directory:"
pwd
echo
echo "Python:"
python --version
echo
echo "PySide6:"
python -c "import PySide6; print(PySide6.__version__)"
echo

rm -f qs_crash.log

echo "Starting Quantum Studio..."
echo "The terminal will NOT close automatically."
echo
echo "----------------------------------------------"

PYTHONFAULTHANDLER=1 \
python -X faulthandler frontend/main.py \
    > qs_crash.log 2>&1

STATUS=$?

echo
echo "----------------------------------------------"
echo
echo "Quantum Studio exited."
echo
echo "Exit status: $STATUS"
echo
echo "=============================================="
echo "CRASH LOG"
echo "=============================================="
echo

if [ -s qs_crash.log ]; then
    cat qs_crash.log
else
    echo "(No Python traceback was produced.)"
fi

echo
echo "=============================================="
echo
echo "Log saved to:"
echo "  ~/QuantumStudio/qs_crash.log"
echo
echo "The terminal is intentionally being kept open."
echo
read -p "Press ENTER to close..."
