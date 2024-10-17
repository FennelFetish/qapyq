#!/bin/bash

venv_name="venv"
venv_path="./${venv_name}"


if [ -z "${VIRTUAL_ENV}" ]; then
    # Create venv if it doesn't exist yet
    if [ -d "$venv_path" ]; then
        echo "Virtual environment '${venv_path}' already exists"
    else
        echo "Creating virtual environment '${venv_path}'"
        python -m venv "$venv_name"
    fi

    source "${venv_path}/bin/activate"
fi


if [ -z "${VIRTUAL_ENV}" ]; then
    echo "Failed to activate virtual environment"
    exit 1
fi


echo "Virtual environment: ${VIRTUAL_ENV}"
script_dir="$(dirname "$0")"

echo ""
echo "Installing requirements"
pip install -r "${script_dir}/requirements.txt"

echo ""
echo "Installing llama-cpp-python"
pip install -r "${script_dir}/requirements-llamacpp.txt"

echo ""
echo "Installing onnxruntime-gpu"
pip install -r "${script_dir}/requirements-onnx.txt"
