#!/bin/bash

script_dir="$(dirname "$(readlink -f "$0")")"

venv_name=".venv"
venv_path="${script_dir}/${venv_name}"

# Activate the virtual environment
if [ -z "${VIRTUAL_ENV}" ]; then
    source "${venv_path}/bin/activate"
fi

if [ -z "${VIRTUAL_ENV}" ]; then
    echo "Failed to activate virtual environment. Please run setup.sh first."
    exit 1
else
    echo "Active environment: '${VIRTUAL_ENV}'"
fi

# Set path to preferred Python version within the virtual environment
python_exec="${venv_path}/bin/python"

# Run main.py using the specified Python version and command-line arguments
# Write output to terminal and last.log
cd "$script_dir"
exec ${python_exec} "./main.py" "$1" > >(tee "./last.log") 2>&1
