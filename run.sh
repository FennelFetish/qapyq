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

# Options for glibc's malloc:
#   https://www.gnu.org/software/libc/manual/html_node/Malloc-Tunable-Parameters.html
# Ensure MMAP threshold is low enough so memory allocated by thumbnails can be released.
# Fix glibc's malloc trim threshold at 64MB to release more memory back to the OS.
export MALLOC_MMAP_THRESHOLD_=32768     # 32 KB
export MALLOC_TRIM_THRESHOLD_=67108864  # 64 MB
export MALLOC_TOP_PAD_=2097152          # 2 MB

# Set working directory and run main.py using the specified Python version.
# Replace current process so it appears correctly in process monitors.
# Write output to terminal and logfile.
cd "$script_dir"
exec ${python_exec} "./main.py" "$1" > >(tee "./last.log") 2>&1

# TODO: Open images in new tab if program already runs
