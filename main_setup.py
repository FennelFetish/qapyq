import os, sys, subprocess, traceback
from typing import NamedTuple


OLD_TRANSFORMERS_VERSION = "4.45.2"

PIP_ARGS = [sys.executable, "-m", "pip", "install", "--upgrade", "--upgrade-strategy", "eager"]


class Component:
    def __init__(self, title: str, required: bool, args: list[str]):
        self.title: str      = title
        self.required: bool  = required
        self.args: list[str] = args
        self.prepareArgs: list[str] | None  = None

    def pipPrepare(self) -> bool:
        if self.prepareArgs:
            subprocess.check_call(self.prepareArgs)
            return True
        return False

    def pipInstall(self):
        args = PIP_ARGS + self.args
        subprocess.check_call(args)



COMP_ONNX_CPU    = Component("ONNX runtime for CPU",            False, ["onnxruntime"])
COMP_ONNX_ROCM   = Component("ONNX runtime for ROCm/MIGraphX",  False, ["-r", "requirements-onnx-rocm.txt"])
COMP_ONNX_CUDA   = Component("ONNX runtime for CUDA 12",        False, ["onnxruntime-gpu"])
COMP_ONNX_CUDA13 = Component("ONNX runtime for CUDA 13",        False, [
    "--index-url", "https://aiinfra.pkgs.visualstudio.com/PublicPackages/_packaging/ort-cuda-13-nightly/pypi/simple/",
    "onnxruntime-gpu==1.25.0.dev20260331005"  # https://github.com/microsoft/onnxruntime/issues/27944
])

ONNX_UNINSTALL_ARGS = [sys.executable, "-m", "pip", "uninstall", "-y", "onnxruntime", "onnxruntime-gpu"]


# COMP_FLASHATTN_CUDA = Component("FlashAttention", False, ["flash_attn", "--no-build-isolation", "--verbose"])
COMP_FLASHATTN_CUDA   = Component("FlashAttention", False, ["-r", "requirements-flashattn.txt"])
COMP_FLASHATTN_CUDA13 = Component("FlashAttention", False, ["-r", "requirements-flashattn-cuda13.txt"])


COMP_LLAMACPP_CUDA   = Component("llama.cpp for CUDA", False, ["--index-url", "https://abetlen.github.io/llama-cpp-python/whl/cu124", "llama-cpp-python"])
COMP_LLAMACPP_CPU    = Component("llama.cpp for CPU",  False, ["--index-url", "https://abetlen.github.io/llama-cpp-python/whl/cpu",   "llama-cpp-python"])


class ComputePlatform(NamedTuple):
    title: str
    torch: str
    torchIndex: str
    onnx: Component | None = None
    flashAttn: Component | None = None
    llamaCpp: Component | None = None

# PyTorch version affects availability of prebuilt flash_attn wheels
PLATFORMS = {
    "1": ComputePlatform("CUDA 12.8",   "torch==2.8.*",     "https://download.pytorch.org/whl/cu128",    COMP_ONNX_CUDA,    COMP_FLASHATTN_CUDA,    COMP_LLAMACPP_CUDA),
    "2": ComputePlatform("CUDA 13.0",   "torch==2.11.*",    "https://download.pytorch.org/whl/cu130",    COMP_ONNX_CUDA13,  COMP_FLASHATTN_CUDA13,  COMP_LLAMACPP_CUDA),
    "3": ComputePlatform("ROCm 7.2",    "torch==2.11.*",    "https://download.pytorch.org/whl/rocm7.2",  COMP_ONNX_ROCM),
    "4": ComputePlatform("CPU",         "torch==2.11.*",    "https://download.pytorch.org/whl/cpu",      COMP_ONNX_CPU,     None,                   COMP_LLAMACPP_CPU),
}



class ComponentOption(NamedTuple):
    title: str
    gui: bool
    backend: bool

COMPONENT_OPTIONS = {
    "1": ComponentOption("all components",  True,  True),
    "2": ComponentOption("only GUI",        True,  False),
    "3": ComponentOption("only backend",    False, True),
}



def buildComponents(choice: ComponentOption, platform: ComputePlatform, oldTransformers: bool, flashAttn: bool) -> list[Component]:
    components = [
        Component("package installer", True, ["pip"]),
        Component("base requirements", True, ["-r", "requirements.txt"]),
    ]

    if choice.gui:
        components.append( Component("GUI requirements", True, ["-r", "requirements-gui.txt"]) )

    if choice.backend:
        components.append( Component("PyTorch", True, ["--extra-index-url", platform.torchIndex, "-r", "requirements-pytorch.txt", platform.torch]) )

        transformersArgs = [f"transformers=={OLD_TRANSFORMERS_VERSION}"] if oldTransformers else []
        components.append( Component("inference backend", True, ["-r", "requirements-infer.txt", platform.torch, *transformersArgs]) )

        if platform.onnx:
            platform.onnx.prepareArgs = ONNX_UNINSTALL_ARGS
            components.append(platform.onnx)

        if platform.llamaCpp:
            components.append(platform.llamaCpp)

        if flashAttn and platform.flashAttn:
            platform.flashAttn.args.append(platform.torch)
            components.append(platform.flashAttn)

    return components



def printSep(text: str):
    print(text.strip())
    print()



ASK_COMPONENTS_TEXT = """
qapyq supports automatic captioning, upscaling, masking and semantic sorting using AI models.
The required packages are installed into a virtual environment that needs 10-15 GB of space.

You can also choose to install only the GUI and media processing packages,
which need around 1 GB.

When installing on a headless server for remote inference, you can choose to
install only the backend.

Which components do you want to install?
  [1] All components:    GUI, media processing, AI assistance
  [2] Only GUI:          GUI, media processing
  [3] Only backend:           media processing, AI assistance
"""

def askComponents() -> ComponentOption:
    printSep(ASK_COMPONENTS_TEXT)
    while True:
        choice = input("[1/2/3, default 1] ").strip() or "1"
        if option := COMPONENT_OPTIONS.get(choice):
            printSep(f"Selecting {option.title} for installation.")
            return option

        printSep("Invalid selection. Please enter a number from 1 to 3.")



ASK_PLATFORM_TEXT = """
To run AI models, the installed compute platform must match your hardware and driver.

If you have an nvidia GPU with recent driver, and 'nvidia-smi' shows a CUDA version >= 13.0,
you can install the CUDA 13.0 platform. Otherwise, choose CUDA 12.8 for older drivers.

Choose ROCm if you have an AMD GPU. Note that qapyq with ROCm is untested.

Select your compute platform:"""

def askPlatform():
    printSep(LINE)
    print(ASK_PLATFORM_TEXT.lstrip())
    for key, platform in PLATFORMS.items():
        print(f"  [{key}] {platform.title}")
    print()

    count = len(PLATFORMS)
    while True:
        choice = input(f"[1-{count}, default 1] ").strip() or "1"
        if platform := PLATFORMS.get(choice):
            printSep(f"Selecting {platform.title} for installation")
            return platform

        printSep(f"Invalid selection. Please enter a number from 1 to {count}.")



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
Qwen3-VL        -               OK

Do you want to install the OLD version of transformers?
(Compatibility with GGUF models is not affected by this choice.)"""

def askOldTransformers() -> bool:
    printSep(LINE)
    print(ASK_TRANSFORMERS_TEXT.lstrip())
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
    printSep(LINE)
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
    platform = ComputePlatform("No backend", "", "")
    oldTransformers = False
    flashAttn = False

    choice = askComponents()
    if choice.backend:
        platform = askPlatform()
        if platform.flashAttn:
            flashAttn = askFlashAttention()

        oldTransformers = askOldTransformers()

    components = buildComponents(choice, platform, oldTransformers, flashAttn)

    print(LINE)

    failed = list[Component]()
    numSteps = len(components)
    for i, comp in enumerate(components, 1):
        print()
        print(f"({i}/{numSteps}) Installing {comp.title}")

        try:
            if comp.pipPrepare():
                print()

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
