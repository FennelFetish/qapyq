#!/bin/bash

venv_name="venv"
venv_path="./${venv_name}"

# Activate the virtual environment
if [ -z "${VIRTUAL_ENV}" ]; then
    source "${venv_path}/bin/activate"
fi

# Set path to preferred Python version within the virtual environment
python_path="${venv_path}/bin/python"

# If the specified Python path doesn't exist, use the environment's default 'python' command
if [ ! -x "${python_path}" ]; then
    python_path="python"
fi


# Run main.py using the specified Python version and command-line arguments
exec ${python_path} "$(dirname "$0")/main.py" "$1"
