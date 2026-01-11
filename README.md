<img src="res/qapyq.png" align="left" />

# qapyq
<sup>(CapPic)</sup><br />
**An image viewer and AI-assisted editing tool that helps with curating datasets for generative AI models, finetunes and LoRA.**

<br clear="left"/>
<br /><br />

![Screenshot of qapyq with its 5 windows open.](https://www.alchemists.ch/qapyq/overview-3.jpg)

<a href="https://camo.githubusercontent.com/059f5cef1671955473d5d3e096263cf85910a2d52094c389b2924cca1b1a33c5/68747470733a2f2f7777772e616c6368656d697374732e63682f71617079712f647261672d6e2d64726f702e676966"><img alt="Edit captions quickly with drag-and-drop support" src="https://camo.githubusercontent.com/059f5cef1671955473d5d3e096263cf85910a2d52094c389b2924cca1b1a33c5/68747470733a2f2f7777772e616c6368656d697374732e63682f71617079712f647261672d6e2d64726f702e676966" width="30%"></img></a>
<a href="https://camo.githubusercontent.com/71df5556ba81a944f3a28ed3760644b6f7c0c455b4ed639a80418b51d0cae704/68747470733a2f2f7777772e616c6368656d697374732e63682f71617079712f7461675f6d75742d6578636c75736976652e676966"><img alt="Select one-of-many" src="https://camo.githubusercontent.com/71df5556ba81a944f3a28ed3760644b6f7c0c455b4ed639a80418b51d0cae704/68747470733a2f2f7777772e616c6368656d697374732e63682f71617079712f7461675f6d75742d6578636c75736976652e676966" width="30%"></img></a>
<a href="https://camo.githubusercontent.com/9403e354708969d4c5f1262583294913bd238e8b38df640e2a7fc36a313bf686/68747470733a2f2f7777772e616c6368656d697374732e63682f71617079712f72756c65732e676966"><img alt="Apply sorting and filtering rules" src="https://camo.githubusercontent.com/9403e354708969d4c5f1262583294913bd238e8b38df640e2a7fc36a313bf686/68747470733a2f2f7777772e616c6368656d697374732e63682f71617079712f72756c65732e676966" width="30%"></img></a>

<a href="https://camo.githubusercontent.com/74122b177a2f5a1cd4add5d749b90a49ac2f0cec631363ef861199a7c90566d7/68747470733a2f2f7777772e616c6368656d697374732e63682f71617079712f63726f702e676966"><img alt="Quick cropping" src="https://camo.githubusercontent.com/74122b177a2f5a1cd4add5d749b90a49ac2f0cec631363ef861199a7c90566d7/68747470733a2f2f7777772e616c6368656d697374732e63682f71617079712f63726f702e676966" width="30%"></img></a>
<a href="https://camo.githubusercontent.com/d15df56575d4d69fe2cc04c5ed822e6cc95c0208185df3464a21fc351c4b04fb/68747470733a2f2f7777772e616c6368656d697374732e63682f71617079712f636f6d706172652e676966"><img alt="Image comparison" src="https://camo.githubusercontent.com/d15df56575d4d69fe2cc04c5ed822e6cc95c0208185df3464a21fc351c4b04fb/68747470733a2f2f7777772e616c6368656d697374732e63682f71617079712f636f6d706172652e676966" width="30%"></img></a>
<a href="https://camo.githubusercontent.com/1583a08a56e63f4d6dae0c59f6572310558bb7c9f8e7b79e7e4e53af6e2663ee/68747470733a2f2f7777772e616c6368656d697374732e63682f71617079712f6d61736b2d322e676966"><img alt="Draw masks manually or apply automatic detection and segmentation" src="https://camo.githubusercontent.com/1583a08a56e63f4d6dae0c59f6572310558bb7c9f8e7b79e7e4e53af6e2663ee/68747470733a2f2f7777772e616c6368656d697374732e63682f71617079712f6d61736b2d322e676966" width="30%"></img></a>


<a href="https://camo.githubusercontent.com/b6cf81d56d9d4e9e2bbc8fb031e03e9380bc0a5c5e47b4885edd8ff0cc043b6b/68747470733a2f2f7777772e616c6368656d697374732e63682f71617079712f636f6e642d666f6f74776561722d686169722d666c6f6f722e676966"><img alt="Transform tags using conditional rules" src="https://camo.githubusercontent.com/b6cf81d56d9d4e9e2bbc8fb031e03e9380bc0a5c5e47b4885edd8ff0cc043b6b/68747470733a2f2f7777772e616c6368656d697374732e63682f71617079712f636f6e642d666f6f74776561722d686169722d666c6f6f722e676966" width="30%"></img></a>
<a href="https://camo.githubusercontent.com/b094b255ba1d18d83253dba4f7f813ac6d64ea6cedac7330437eb0791479f062/68747470733a2f2f7777772e616c6368656d697374732e63682f71617079712f6d756c7469656469742d666f6375732d636f6d707265737365642e676966"><img alt="Multi-Edit and Focus Mode" src="https://camo.githubusercontent.com/b094b255ba1d18d83253dba4f7f813ac6d64ea6cedac7330437eb0791479f062/68747470733a2f2f7777772e616c6368656d697374732e63682f71617079712f6d756c7469656469742d666f6375732d636f6d707265737365642e676966" width="60%"></img></a>


## Features

- **Image Viewer**: Display and navigate images
  - Quick-starting desktop application built with Qt
  - Runs smoothly with a million images
  - Modular interface that lets you place windows on different monitors
  - Open multiple tabs
  - Zoom/pan and fullscreen mode
  - Gallery with thumbnails and optionally captions <sup>[?](https://github.com/FennelFetish/qapyq/wiki/User-Guide#gallery)</sup>
  - Semantic image sorting with text prompts <sup>[?](https://github.com/FennelFetish/qapyq/wiki/User-Guide#semantic-sort)</sup>
  - Compare two images <sup>[?](https://github.com/FennelFetish/qapyq/wiki/User-Guide#compare-tool)</sup>
  - Measure size, area and pixel distances <sup>[?](https://github.com/FennelFetish/qapyq/wiki/User-Guide#measure-tool)</sup>
  - Slideshow <sup>[?](https://github.com/FennelFetish/qapyq/wiki/User-Guide#slideshow-tool)</sup>

- **Image/Mask Editor**: Prepare images for training
  - Crop and save parts of images <sup>[?](https://github.com/FennelFetish/qapyq/wiki/User-Guide#crop-tool)</sup>
  - Scale images, optionally using AI upscale models <sup>[?](https://github.com/FennelFetish/qapyq/wiki/User-Guide#scale-tool)</sup>
  - Dynamic save paths with template variables <sup>[?](https://github.com/FennelFetish/qapyq/wiki/User-Guide#path-settings)</sup>
  - Manually edit masks with multiple layers <sup>[?](https://github.com/FennelFetish/qapyq/wiki/User-Guide#mask-tool)</sup>
  - Record masking operations into macros <sup>[?](https://github.com/FennelFetish/qapyq/wiki/User-Guide#macro-recording)</sup>
  - Automated masking

- **Captioning**: Describe images with text
  - Edit captions manually with drag-and-drop support <sup>[?](https://github.com/FennelFetish/qapyq/wiki/User-Guide-%E2%80%90-Captioning#caption-window)</sup>
  - Save multiple captions in a JSON file per image <sup>[?](https://github.com/FennelFetish/qapyq/wiki/User-Guide-%E2%80%90-Captioning#captions-in-text-files-vs-json-files)</sup>
  - *Multi-Edit Mode*: Edit captions of multiple images simultaneously <sup>[?](https://github.com/FennelFetish/qapyq/wiki/User-Guide-%E2%80%90-Captioning#multi-edit-mode)</sup>
  - *Focus Mode*: Add the same tags to many files quickly <sup>[?](https://github.com/FennelFetish/qapyq/wiki/User-Guide-%E2%80%90-Captioning#focus-mode)</sup>
  - Tag grouping, merging, sorting, filtering and replacement rules <sup>[?](https://github.com/FennelFetish/qapyq/wiki/User-Guide-%E2%80%90-Captioning#rules)</sup>
  - Colored text highlighting
  - Autocomplete with tags from your groups and CSV files <sup>[?](https://github.com/FennelFetish/qapyq/wiki/User-Guide-%E2%80%90-Captioning#autocomplete)</sup>
  - CLIP Token Counter <sup>[?](https://github.com/FennelFetish/qapyq/wiki/User-Guide-%E2%80%90-Captioning#token-counter)</sup>
  - Automated captioning with support for grounding <sup>[?](https://github.com/FennelFetish/qapyq/wiki/User-Guide-%E2%80%90-Tips-and-Workflows#grounding)</sup>
  - Dynamic prompts with templates and text transformations <sup>[?](https://github.com/FennelFetish/qapyq/wiki/User-Guide-%E2%80%90-Captioning#templates)</sup>
  - Multi-turn conversations with VLMs <sup>[?](https://github.com/FennelFetish/qapyq/wiki/User-Guide-%E2%80%90-Captioning#prompts-and-conversations)</sup>
  - Further refinement with LLMs

- **Stats/Filters**: Summarize your data and get an overview
  - List all tags, image resolutions, masked regions, or size of concept folders <sup>[?](https://github.com/FennelFetish/qapyq/wiki/User-Guide#stats)</sup>
  - Filter images and create subsets <sup>[?](https://github.com/FennelFetish/qapyq/wiki/User-Guide-%E2%80%90-Tips-and-Workflows#training-on-subsets)</sup>
  - Combine and chain filters
  - Export the summaries as CSV

- **Batch Processing**: Process whole folders at once
  - Flexible batch captioning, tagging and transformation <sup>[?](https://github.com/FennelFetish/qapyq/wiki/User-Guide#batch)</sup>
  - Batch scaling of images
  - Batch masking with user-defined macros
  - Batch cropping of images using your macros
  - Copy, move and rename files, create symlinks, ZIP captions for backups

- **AI Assistance**:
  - Support for state-of-the-art captioning and masking models
  - Model and sampling settings, GPU acceleration with CPU offload support
  - On-the-fly NF4 and INT8 quantization
  - Run inference locally and/or on multiple remote machines over SSH <sup>[?](https://github.com/FennelFetish/qapyq/wiki/Setup#host-setup-for-remote-inference)</sup>
  - Separate inference subprocess isolates potential crashes and allows complete VRAM cleanup


## Supported Models
These are the supported architectures with links to the original models.<br>
Find more specialized finetuned models on [huggingface.co](https://huggingface.co/models).

- **Tagging**<br>
  Generate keyword captions for images.
  - [JoyTag](https://github.com/fpgaminer/joytag)
  - [PixAI Tagger (onnx)](https://huggingface.co/deepghs/pixai-tagger-v0.9-onnx)
  - [WD (onnx)](https://huggingface.co/SmilingWolf/wd-eva02-large-tagger-v3) (eva02 recommended)

- **Captioning**<br>
  Generate complete-sentence captions for images.
  - [Florence-2](https://huggingface.co/collections/microsoft/florence-6669f44df0d87d9c3bfb76de)
  - [Gemma3 (GGUF)](https://huggingface.co/collections/unsloth/gemma-3-67d12b7e8816ec6efa7e4e5b)
  - [InternVL2](https://huggingface.co/collections/OpenGVLab/internvl-20-667d3961ab5eb12c7ed1463e), [InternVL2.5](https://huggingface.co/collections/OpenGVLab/internvl25-673e1019b66e2218f68d7c1c), [InternVL2.5-MPO](https://huggingface.co/collections/OpenGVLab/internvl25-mpo-6753fed98cd828219b12f849), [InternVL3](https://huggingface.co/collections/OpenGVLab/internvl3-67f7f690be79c2fe9d74fe9d), [InternVL3.5](https://huggingface.co/collections/OpenGVLab/internvl35-core-68b08a936ded8dc59597179c) (Github Format)
  - [JoyCaption](https://huggingface.co/fancyfeast/llama-joycaption-beta-one-hf-llava)
  - [MiniCPM-V-2.6 (GGUF)](https://huggingface.co/openbmb/MiniCPM-V-2_6-gguf), [MiniCPM-o-2.6 (GGUF)](https://huggingface.co/openbmb/MiniCPM-o-2_6-gguf), [MiniCPM-V-4 (GGUF)](https://huggingface.co/openbmb/MiniCPM-V-4-gguf)
  - [Molmo](https://huggingface.co/collections/allenai/molmo-66f379e6fe3b8ef090a8ca19)
  - [Moondream2 (GGUF)](https://huggingface.co/vikhyatk/moondream2)
  - [Ovis1.6](https://huggingface.co/AIDC-AI/Ovis1.6-Gemma2-9B), [Ovis2](https://huggingface.co/collections/AIDC-AI/ovis2-67ab36c7e497429034874464), [Ovis2.5](https://huggingface.co/collections/AIDC-AI/ovis25-689ec1474633b2aab8809335)
  - [Qwen2-VL](https://huggingface.co/collections/Qwen/qwen2-vl-66cee7455501d7126940800d), [Qwen2.5-VL](https://huggingface.co/collections/Qwen/qwen25-vl-6795ffac22b334a837c0f9a5), [Qwen3-VL](https://huggingface.co/collections/Qwen/qwen3-vl) (Instruct/Thinking)

- **LLM**<br>
  Transform existing captions/tags.
  - Models in GGUF format with embedded chat template (llama-cpp backend).

- **Upscaling**<br>
  Resize images to higher resolutions.
  - Model architectures supported by the [spandrel](https://github.com/chaiNNer-org/spandrel?tab=readme-ov-file#model-architecture-support) backend.
  - Find more models at [openmodeldb.info](https://openmodeldb.info/).

- **Masking**<br>
  Generate greyscale masks.
  - Box Detection
    - YOLO/Adetailer detection models
      - Search for YOLO models on [huggingface.co](https://huggingface.co/models?pipeline_tag=object-detection).
    - [Florence-2](https://huggingface.co/collections/microsoft/florence-6669f44df0d87d9c3bfb76de)
    - [Qwen3-VL](https://huggingface.co/collections/Qwen/qwen3-vl)
  - Segmentation / Background Removal
    - [InSPyReNet](https://github.com/plemeri/InSPyReNet/blob/main/docs/model_zoo.md) (Plus_Ultra)
    - [RMBG-2.0](https://huggingface.co/briaai/RMBG-2.0)
    - [Florence-2](https://huggingface.co/collections/microsoft/florence-6669f44df0d87d9c3bfb76de)

- **Embedding**<br>
  Sort images by their similarity to a prompt.
  - [CLIP](https://huggingface.co/openai/clip-vit-large-patch14)
  - [SigLIP](https://huggingface.co/google/siglip2-so400m-patch14-384)
  - [SigLIP (ONNX)](https://huggingface.co/onnx-community/siglip2-so400m-patch14-384-ONNX), [SigLIP2-giant-opt (ONNX)](https://huggingface.co/onnx-community/siglip2-giant-opt-patch16-384-ONNX)<br>(recommended: largest text model + fp16 vision model)


## Setup
Requires Python 3.10 or later.

By default, prebuilt packages for CUDA 12.8 are installed. If you need a different CUDA version, change the URLs in `requirements-pytorch.txt` and `requirements-flashattn.txt` before running the setup script.

1. Git clone or [download](https://github.com/FennelFetish/qapyq/archive/refs/heads/main.zip) this repository.
2. Run `setup.sh` on Linux, `setup.bat` on Windows.
   - Packages are installed into a virtual environment.

The setup script will ask you a couple of questions.<br>
You can choose to install only the GUI and image processing packages without AI assistance. Or when installing on a headless server for remote inference, you can choose to install only the backend.

If the setup scripts didn't work for you, but you manually got it running, please share your solution and raise an issue.

### Startup
- Linux: `run.sh`
- Windows: `run.bat` or `run-console.bat`

You can open files or folders directly in qapyq by associating the file types with the respective run script in your OS.
For shortcuts, icons are available in the `qapyq/res` folder.

### Update
If git was used to clone the repository, simply use `git pull` to update.<br>
If the repository was downloaded as a zip archive, download it again and replace the installed files.

To update the installed packages in the virtual environment, run the setup script again.

New dependencies may be added. If the program fails to start or crashes, run the setup script to install the missing packages.


## User Guide
More information is available in the [Wiki](https://github.com/FennelFetish/qapyq/wiki).<br>
Use the page index on the right side to find topics and navigate the Wiki.

**How to**:
- Setup and configure AI models: [Model Setup](https://github.com/FennelFetish/qapyq/wiki/Setup#model-setup)
- Use qapyq: [User Guide](https://github.com/FennelFetish/qapyq/wiki/User-Guide)
- Caption with qapyq: [Captioning](https://github.com/FennelFetish/qapyq/wiki/User-Guide-%E2%80%90-Captioning)
- Use qapyq's features in a workflow: [Tips and Workflows](https://github.com/FennelFetish/qapyq/wiki/User-Guide-%E2%80%90-Tips-and-Workflows)

If you have questions, please ask in the [Discussions](https://github.com/FennelFetish/qapyq/discussions).
