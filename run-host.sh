#!/bin/bash

script_dir="$(dirname "$(readlink -f "$0")")"

venv_name=".venv"
venv_path="${script_dir}/${venv_name}"


if [ -z "${VIRTUAL_ENV}" ]; then
    source "${venv_path}/bin/activate"
fi

if [ -z "${VIRTUAL_ENV}" ]; then
    exit 1
fi

python_exec="${venv_path}/bin/python"

export NO_ALBUMENTATIONS_UPDATE=1
export YOLO_OFFLINE="True"

cd "$script_dir"
exec ${python_exec} "./main_host.py" "$@"
