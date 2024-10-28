#!/bin/bash

script_dir="$(dirname "$(readlink -f "$0")")"

venv_name=".venv"
venv_path="${script_dir}/${venv_name}"


create_venv() {
    # Find python
    local python_exec="python"
    if ! which "$python_exec" > /dev/null; then
        python_exec="python3"
    fi

    if ! which "$python_exec" > /dev/null; then
        echo "Python not found"
        exit 1
    else
        echo "Using Python: $(which "$python_exec")"
        $python_exec --version
        echo ""
    fi

    echo "Creating virtual environment '${venv_path}'"
    $python_exec -m venv "$venv_name"
}


activate_venv() {
    if [ -z "${VIRTUAL_ENV}" ]; then
        if [ -d "$venv_path" ]; then
            echo "Virtual environment '${venv_path}' already exists"
        else
            create_venv
        fi

        source "${venv_path}/bin/activate"

        if [ -z "${VIRTUAL_ENV}" ]; then
            echo "Failed to activate virtual environment"
            exit 1
        fi
    fi

    echo "Active environment: '${VIRTUAL_ENV}'"
}


ask_flash_attn() {
    echo ""
    echo "Does your hardware support flash attention 2? (nvidia 30xx GPU, Ampere generation or later)"
    echo -n "[y/N] "
    local flash_attn
    read flash_attn
    echo ""

    if [ "$flash_attn" == "y" ]; then
        return 0 # true
    else
        return 255 # false
    fi
}


do_install() {
    local -i flash_attn="$1"

    local -i steps=4
    if [ "$flash_attn" -eq 0 ]; then
        steps=5
    fi

    echo ""
    echo "(1/${steps}) Installing pytorch"
    pip install -r "${script_dir}/requirements-pytorch.txt"

    echo ""
    echo "(2/${steps}) Installing requirements"
    pip install -r "${script_dir}/requirements.txt"

    echo ""
    echo "(3/${steps}) Installing llama-cpp-python"
    pip install -r "${script_dir}/requirements-llamacpp.txt"

    echo ""
    echo "(4/${steps}) Installing onnxruntime-gpu"
    pip install -r "${script_dir}/requirements-onnx.txt"

    if [ "$flash_attn" -eq 0 ]; then
        echo ""
        echo "(5/${steps}) Installing flash attention"
        pip install wheel
        pip install flash_attn --no-build-isolation
    fi
}


ask_flash_attn
flash_attn="$?"

cd "$script_dir"
activate_venv

do_install "$flash_attn"


echo ""
echo "Setup finished"
