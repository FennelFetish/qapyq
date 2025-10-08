import os, sys, subprocess, traceback
from typing import NamedTuple


PIP_ARGS = [sys.executable, "-m", "pip", "install", "--upgrade", "--upgrade-strategy", "eager"]


class Component:
    def __init__(self, title: str, required: bool, args: list[str]):
        self.title = title
        self.required = required
        self.args = args

    def pipInstall(self):
        args = PIP_ARGS + self.args
        subprocess.check_call(args)


class ComponentList(NamedTuple):
    title: str
    backend: bool
    components: list[Component]


OLD_TRANSFORMERS_VERSION = "4.45.2"
COMP_INFERENCE = Component("inference backend", True,   ["-r", "requirements-infer.txt"])
COMP_FLASHATTN = Component("FlashAttention",    False,  ["-r", "requirements-flashattn.txt"])
#COMP_FLASHATTN = Component("FlashAttention",    False,  ["flash_attn", "--no-build-isolation", "--verbose"])

COMPONENTS = {
    "1": ComponentList("all components", True, [
        Component("GUI requirements",       True,   ["-r", "requirements.txt"]),
        Component("wheel",                  True,   ["wheel"]),
        Component("PyTorch",                True,   ["-r", "requirements-pytorch.txt"]),
        COMP_INFERENCE,
        Component("llama.cpp",              False,  ["-r", "requirements-llamacpp.txt"]),
    ]),
    "2": ComponentList("only GUI", False, [
        Component("GUI requirements",       True,   ["-r", "requirements.txt"]),
    ]),
    "3": ComponentList("only backend", True, [
        Component("base requirements",      True,   ["wheel", "msgpack"]),
        Component("PyTorch",                True,   ["-r", "requirements-pytorch.txt"]),
        COMP_INFERENCE,
        Component("llama.cpp",              False,  ["-r", "requirements-llamacpp.txt"]),
    ])
}



def printSep(text: str):
    print(text.strip())
    print()


ASK_COMPONENTS_TEXT = """
qapyq supports automatic captioning, upscaling, masking and semantic sorting using AI models.
The required packages are installed into a virtual environment that needs 12 GB of space.

You can also choose to install only the GUI and image processing packages,
which need around 900 MB.

When installing on a headless server for remote inference, you can choose to
install only the backend.

Which components do you want to install?
  [1] All components:    GUI, image processing, AI assistance
  [2] Only GUI:          GUI, image processing
  [3] Only backend:           image processing, AI assistance
"""

def askComponents() -> ComponentList:
    printSep(ASK_COMPONENTS_TEXT)
    while True:
        choice = input("[1/2/3, default 1] ").strip() or "1"
        if components := COMPONENTS.get(choice):
            printSep(f"Selecting {components.title} for installation.")
            return components

        printSep("Invalid selection. Please enter a number from 1 to 3.")


ASK_TRANSFORMERS_TEXT = """
Some visual models need a recent version of the transformers library,
while other models are no longer compatible with those versions.

Model compatibility with transformers version:
                4.45.2 (old)    4.57 (new)
Florence 2      OK              -
InternVL 2      OK              -
InternVL 2.5    OK              -
InternVL 3      OK              OK
InternVL 3.5    -               OK
JoyCaption      OK              OK
Molmo           OK              -
Ovis 1.6        OK              -
Ovis 2          OK              -
Ovis 2.5        -               OK
Qwen2-VL        OK              OK
Qwen2.5-VL      -               OK

Do you want to install the OLD version of transformers?
(Compatibility with GGUF models is not affected by this choice.)"""

def askOldTransformers() -> bool:
    print(ASK_TRANSFORMERS_TEXT)
    while True:
        choice = input("[y/n, default n] ").strip().lower() or "n"
        if choice == "y":
            printSep(f"Selecting transformers version {OLD_TRANSFORMERS_VERSION} for installation.")
            return True
        if choice == "n":
            printSep("Selecting the most recent transformers version for installation.")
            return False

        printSep("Invalid selection. Please enter 'y' for the old version or 'n' for the newest version.")


def askFlashAttention() -> bool:
    print()
    print("Does your hardware support FlashAttention 2? (nvidia 30xx GPU, Ampere generation or later)")
    while True:
        choice = input("[y/n, default n] ").strip().lower() or "n"
        if choice == "y":
            printSep("Selecting FlashAttention for installation.")
            return True
        if choice == "n":
            printSep("Not installing FlashAttention.")
            return False

        printSep("Invalid selection. Please enter 'y' for yes or 'n' for no.")



LINE = "---------------------------------------------------------------------------------------------"

def mainSetup() -> int:
    compList = askComponents()
    components = compList.components.copy()
    if compList.backend:
        if askOldTransformers():
            COMP_INFERENCE.args.append(f"transformers=={OLD_TRANSFORMERS_VERSION}")
        if askFlashAttention():
            components.append(COMP_FLASHATTN)

    print(LINE)

    failed = list[Component]()
    numSteps = len(components)
    for i, comp in enumerate(components, 1):
        print()
        print(f"({i}/{numSteps}) Installing {comp.title}")

        try:
            comp.pipInstall()
        except KeyboardInterrupt:
            raise
        except:
            print()
            printSep(traceback.format_exc())
            print(f"Setup of {comp.title} failed")

            failed.append(comp)
            if comp.required:
                return i

    if failed:
        print()
        printSep(LINE)
        print("WARNING: The following components failed to install:")
        for failedComp in failed:
            print(f"  - {failedComp.title}")
        print("Some features might be unavailable.")

    return 0



VENV_FAIL_TEXT = """
Setup failed: Virtual environment not active

Please run
  'setup.sh'  on Linux/MacOS or
  'setup.bat' on Windows
These scripts will create and activate the virtual environment.
"""

def checkVenv() -> bool:
    if os.environ.get('VIRTUAL_ENV') or os.environ.get('CONDA_DEFAULT_ENV'):
        return True
    if hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix:
        return True

    print(VENV_FAIL_TEXT.strip())
    return False



HEADER = """
┏┓┏┓┏┓┓┏┏┓  =====================================--------------------------------------------
┗┫┗┻┣┛┗┫┗┫  https://github.com/FennelFetish/qapyq
 ┗  ┛  ┛ ┗  =====================================--------------------------------------------
"""

LICENSE = f"""
{LINE}
  qapyq is free software: you can redistribute it and/or modify it under the terms of the
  GNU Affero General Public License as published by the Free Software Foundation,
  either version 3 of the License, or (at your option) any later version.

  qapyq is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
  without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
  See the GNU Affero General Public License for more details.

  You should have received a copy of the GNU Affero General Public License along with qapyq.
  If not, see <https://www.gnu.org/licenses/>.
{LINE}
"""

if __name__ == "__main__":
    printSep(HEADER)

    if not checkVenv():
        sys.exit(254)

    try:
        if errorStep := mainSetup():
            sys.exit(errorStep)
        else:
            print(LICENSE)
            print("Setup finished")

    except (KeyboardInterrupt, EOFError):
        print()
        print("Setup aborted")
        sys.exit(255)
