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

    echo "Creating virtual environment: '${venv_path}'"
    $python_exec -m venv "$venv_name"
}


activate_venv() {
    if [ -z "${VIRTUAL_ENV}" ]; then
        if [ ! -d "$venv_path" ]; then
            create_venv
        fi

        source "${venv_path}/bin/activate"

        if [ -z "${VIRTUAL_ENV}" ]; then
            echo "Failed to activate virtual environment in '${venv_path}'"
            exit 1
        fi
    fi

    echo "Active virtual environment: '${VIRTUAL_ENV}'"
}

cd "$script_dir"
activate_venv
echo ""

python_exec="${venv_path}/bin/python"
exec ${python_exec} "./main_setup.py"
