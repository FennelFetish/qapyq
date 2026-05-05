#!/bin/bash

script_dir="$(dirname "$(realpath "$0")")"

venv_name=".venv"
venv_path="${script_dir}/${venv_name}"

python_exec="python"


select_python() {
    local -a candidates=("$python_exec" "python3" "python3.10" "python3.11" "python3.12" "python3.13" "python3.14")
    local -a available=()

    echo "Choose Python version for the virtual environment:"
    echo ""

    declare -i count=0
    for cand in "${candidates[@]}"; do
        path="$(command -v "$cand" 2>/dev/null)" || continue
        display_path="$(realpath "$path" 2>/dev/null || echo "$path")"

        available+=("$cand")
        ((count++))
        printf "  [%d] %-16s %s" "$count" "$cand" "$display_path"
        echo ""
    done

    if [ $count -le 0 ]; then
        echo "No Python found. Please install python3 and python3-venv with your package manager."
        exit 1
    fi

    echo ""

    declare -i choice=-1
    while [ "$choice" -lt 1 ] || [ "$choice" -gt "$count" ]; do
        echo -n "[1-${count}, default 1] "
        read choice

        if [ "$choice" -eq 0 ]; then
            choice=1
        fi
    done

    ((choice--))
    python_exec="${available[$choice]}"

    echo ""
    echo "Using Python: $(command -v "$python_exec")"
    "$python_exec" --version
    echo ""
}


create_venv() {
    select_python

    "$python_exec" -m venv --help >/dev/null 2>&1
    if [ "$?" -ne 0 ]; then
        echo "Failed to create virtual environment: venv module not found"
        echo "Please install python3-venv with your package manager and restart this setup script."
        exit 1
    fi

    echo "Creating virtual environment: '${venv_path}'"
    "$python_exec" -m venv "$venv_path"
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

    python_exec="${venv_path}/bin/python"
    "$python_exec" --version
}


cd "$script_dir"
activate_venv
echo ""

exec "$python_exec" "./main_setup.py"
