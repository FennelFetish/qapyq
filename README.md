<img src="res/qapyq.png" align="left" />

# qapyq
<sup>(CapPic)</sup><br />
**An image viewer and AI-assisted editing tool that helps with curating datasets for generative AI models, finetunes and LoRA.**

<br clear="left"/>
<br /><br />

![Screenshot of qapyq with its 5 windows open.](https://www.alchemists.ch/qapyq/overview-3.jpg)

<a href="https://camo.githubusercontent.com/2cfe9d36a4920abfbe30172373048a8b6e23a796c18b11651c7cdd7105c0433c/68747470733a2f2f7777772e616c6368656d697374732e63682f71617079712f647261672d6e2d64726f702e676966"><img alt="Edit captions quickly with drag-and-drop support" src="https://camo.githubusercontent.com/2cfe9d36a4920abfbe30172373048a8b6e23a796c18b11651c7cdd7105c0433c/68747470733a2f2f7777772e616c6368656d697374732e63682f71617079712f647261672d6e2d64726f702e676966" width="30%"></img></a>
<a href="https://camo.githubusercontent.com/5a27e2ae34499523dfba4d412409af0b7ae3ce7a81f8f966f2c3f9b154151715/68747470733a2f2f7777772e616c6368656d697374732e63682f71617079712f7461675f6d75742d6578636c75736976652e676966"><img alt="Select one-of-many" src="https://camo.githubusercontent.com/5a27e2ae34499523dfba4d412409af0b7ae3ce7a81f8f966f2c3f9b154151715/68747470733a2f2f7777772e616c6368656d697374732e63682f71617079712f7461675f6d75742d6578636c75736976652e676966" width="30%"></img></a>
<a href="https://camo.githubusercontent.com/74f8628523509b94014f88162823125706f9e07933b1e3a24b6ed1bd0a8de9cb/68747470733a2f2f7777772e616c6368656d697374732e63682f71617079712f72756c65732e676966"><img alt="Apply sorting and filtering rules" src="https://camo.githubusercontent.com/74f8628523509b94014f88162823125706f9e07933b1e3a24b6ed1bd0a8de9cb/68747470733a2f2f7777772e616c6368656d697374732e63682f71617079712f72756c65732e676966" width="30%"></img></a>

<a href="https://camo.githubusercontent.com/2099d08b3e161e7dd1ba906ef7a1a134b078c83001c2ce604f751b26d225168f/68747470733a2f2f7777772e616c6368656d697374732e63682f71617079712f63726f702e676966"><img alt="Quick cropping" src="https://camo.githubusercontent.com/2099d08b3e161e7dd1ba906ef7a1a134b078c83001c2ce604f751b26d225168f/68747470733a2f2f7777772e616c6368656d697374732e63682f71617079712f63726f702e676966" width="30%"></img></a>
<a href="https://camo.githubusercontent.com/9400e59363cb8ba71b2eca5b45ec33e7d06b6e6dd27de427f86fc109f987ebc6/68747470733a2f2f7777772e616c6368656d697374732e63682f71617079712f636f6d706172652e676966"><img alt="Image comparison" src="https://camo.githubusercontent.com/9400e59363cb8ba71b2eca5b45ec33e7d06b6e6dd27de427f86fc109f987ebc6/68747470733a2f2f7777772e616c6368656d697374732e63682f71617079712f636f6d706172652e676966" width="30%"></img></a>
<a href="https://camo.githubusercontent.com/7ccd546901e97b3b5f23723a5200afff2b2bd86a7243fdf5716555bf12770bcf/68747470733a2f2f7777772e616c6368656d697374732e63682f71617079712f6d61736b2d322e676966"><img alt="Draw masks manually or apply automatic detection and segmentation" src="https://camo.githubusercontent.com/7ccd546901e97b3b5f23723a5200afff2b2bd86a7243fdf5716555bf12770bcf/68747470733a2f2f7777772e616c6368656d697374732e63682f71617079712f6d61736b2d322e676966" width="30%"></img></a>


<a href="https://camo.githubusercontent.com/3b132c3a7c20e98f5a7ee7df966ec5074804d40e13dcba22a792bc57843594b4/68747470733a2f2f7777772e616c6368656d697374732e63682f71617079712f636f6e642d666f6f74776561722d686169722d666c6f6f722e676966"><img alt="Transform tags using conditional rules" src="https://camo.githubusercontent.com/3b132c3a7c20e98f5a7ee7df966ec5074804d40e13dcba22a792bc57843594b4/68747470733a2f2f7777772e616c6368656d697374732e63682f71617079712f636f6e642d666f6f74776561722d686169722d666c6f6f722e676966" width="30%"></img></a>
<a href="https://camo.githubusercontent.com/d57801611e8f7d849867425838297b78f910424e8b740575869727f4105d7154/68747470733a2f2f7777772e616c6368656d697374732e63682f71617079712f6d756c7469656469742d666f6375732d636f6d707265737365642e676966"><img alt="Multi-Edit and Focus Mode" src="https://camo.githubusercontent.com/d57801611e8f7d849867425838297b78f910424e8b740575869727f4105d7154/68747470733a2f2f7777772e616c6368656d697374732e63682f71617079712f6d756c7469656469742d666f6375732d636f6d707265737365642e676966" width="60%"></img></a>


## Features

- **Image Viewer**: Display and navigate images
  - Quick-starting desktop application built with Qt
  - Runs smoothly with tens of thousands of images
  - Modular interface that lets you place windows on different monitors
  - Open multiple tabs
  - Zoom/pan and fullscreen mode
  - Gallery with thumbnails and optionally captions
  - Compare two images
  - Measure size, area and pixel distances
  - Slideshow

- **Image/Mask Editor**: Prepare images for training
  - Crop and save parts of images
  - Scale images, optionally using AI upscale models
  - Manually edit masks with multiple layers
  - Support for pressure-sensitive drawing pens
  - Record masking operations into macros
  - Automated masking

- **Captioning**: Describe images with text
  - Edit captions manually with drag-and-drop support
  - *Multi-Edit Mode* for editing captions of multiple images simultaneously
  - *Focus Mode* where one key stroke adds a tag, saves the file and skips to the next image
  - Tag grouping, merging, sorting, filtering and replacement rules
  - Colored text highlighting
  - Automated captioning with support for grounding
  - Prompt presets
  - Multi-turn conversations with each answer saved to different entries in a `.json` file
  - Further refinement with LLMs

- **Stats/Filters**: Summarize your data and get an overview
  - List all tags, image resolutions or size of concept folders
  - Filter images and create subsets
  - Combine and chain filters
  - Export the summaries as CSV

- **Batch Processing**: Process whole folders at once
  - Flexible batch captioning, tagging and transformation
  - Batch scaling of images
  - Batch masking with user-defined macros
  - Batch cropping of images using your macros
  - Copy and move files, create symlinks, ZIP captions for backups

- **AI Assistance**:
  - Support for state-of-the-art captioning and masking models
  - Model and sampling settings, GPU acceleration with CPU offload support
  - On-the-fly NF4 and INT8 quantization
  - Separate inference subprocess isolates potential crashes and allows complete VRAM cleanup


## Supported Models
- **Tagging**
  - [JoyTag](https://github.com/fpgaminer/joytag)
  - [WD (onnx)](https://huggingface.co/SmilingWolf/wd-eva02-large-tagger-v3) (eva02 recommended)

- **Captioning**
  - [Florence-2](https://huggingface.co/collections/microsoft/florence-6669f44df0d87d9c3bfb76de)
  - [InternVL2](https://huggingface.co/collections/OpenGVLab/internvl-20-667d3961ab5eb12c7ed1463e), [InternVL2.5](https://huggingface.co/collections/OpenGVLab/internvl25-673e1019b66e2218f68d7c1c), [InternVL2.5-MPO](https://huggingface.co/collections/OpenGVLab/internvl25-mpo-6753fed98cd828219b12f849), [InternVL3](https://huggingface.co/collections/OpenGVLab/internvl3-67f7f690be79c2fe9d74fe9d)
  - [JoyCaption](https://huggingface.co/fancyfeast/llama-joycaption-alpha-two-hf-llava)
  - [MiniCPM-V-2.6 (GGUF)](https://huggingface.co/openbmb/MiniCPM-V-2_6-gguf) ([alternative link](https://huggingface.co/bartowski/MiniCPM-V-2_6-GGUF))
  - [Molmo](https://huggingface.co/collections/allenai/molmo-66f379e6fe3b8ef090a8ca19)
  - [Moondream2 (GGUF)](https://huggingface.co/vikhyatk/moondream2)
  - [Ovis-1.6](https://huggingface.co/AIDC-AI/Ovis1.6-Gemma2-9B), [Ovis2](https://huggingface.co/collections/AIDC-AI/ovis2-67ab36c7e497429034874464)
  - [Qwen2-VL](https://huggingface.co/collections/Qwen/qwen2-vl-66cee7455501d7126940800d)
  - [Qwen2.5-VL](https://huggingface.co/collections/Qwen/qwen25-vl-6795ffac22b334a837c0f9a5) (needs transformers 4.49 manually installed)

- **LLM**
  - Models in GGUF format with embedded chat template (llama-cpp backend).

- **Upscaling**
  - Model architectures supported by the [spandrel](https://github.com/chaiNNer-org/spandrel?tab=readme-ov-file#model-architecture-support) backend.
  - Find more models at [openmodeldb.info](https://openmodeldb.info/).

- **Masking**
  - Box Detection
    - YOLO/Adetailer detection models
      - Search for YOLO models on [huggingface.co](https://huggingface.co/models?pipeline_tag=object-detection).
    - [Florence-2](https://huggingface.co/collections/microsoft/florence-6669f44df0d87d9c3bfb76de)
    - [Qwen2.5-VL](https://huggingface.co/collections/Qwen/qwen25-vl-6795ffac22b334a837c0f9a5)
  - Segmentation / Background Removal
    - [InSPyReNet](https://github.com/plemeri/InSPyReNet/blob/main/docs/model_zoo.md) (Plus_Ultra)
    - [RMBG-2.0](https://huggingface.co/briaai/RMBG-2.0)
    - [Florence-2](https://huggingface.co/collections/microsoft/florence-6669f44df0d87d9c3bfb76de)


## Setup
Requires Python 3.10.

By default, prebuilt packages for CUDA 12.4 are installed. If you need a different CUDA version, change the index URL in `requirements-pytorch.txt` and `requirements-llamacpp.txt` before running the setup script.

1. Git clone or [download](https://github.com/FennelFetish/qapyq/archive/refs/heads/main.zip) this repository.
2. Run `setup.sh` on Linux, `setup.bat` on Windows.
   - This will create a virtual environment that needs 7-9 GB.

If the setup scripts didn't work for you, but you manually got it running, please share your solution and raise an issue.

### Startup
- Linux: `run.sh`
- Windows: `run.bat` or `run-console.bat`

You can open files or folders directly in qapyq by associating the file types with the respective run script in your OS.
For shortcuts, icons are available in the `qapyq/res` folder.

### Update
If git was used to clone the repository, simply use `git pull` to update.

If the repository was downloaded as a zip archive, download it again and replace the installed files.

New dependencies may be added. If the program fails to start or crashes, run the setup script again to install the missing packages.


## User Guide

More information is available in the [Wiki](https://github.com/FennelFetish/qapyq/wiki).<br>
Use the page index on the right side to find topics and navigate the Wiki.

How to setup AI models for automatic captioning and masking: [Model Setup](https://github.com/FennelFetish/qapyq/wiki/Setup#model-setup)

How to use qapyq: [User Guide](https://github.com/FennelFetish/qapyq/wiki/User-Guide)

How to caption with qapyq: [Captioning](https://github.com/FennelFetish/qapyq/wiki/User-Guide-%E2%80%90-Captioning)

How to use qapyq's features in a workflow: [Tips and Workflows](https://github.com/FennelFetish/qapyq/wiki/User-Guide-%E2%80%90-Tips-and-Workflows)


## Planned Features
- [x] Natural sorting of files
- [x] Gallery list view with captions
- [x] Summary and stats of captions and tags
- [ ] Shortcuts and improved ease-of-use
- [x] AI-assisted mask editing
- [ ] Overlays (difference image) for comparison tool
- [x] Image resizing
- [ ] Run inference on remote machines
- [ ] Adapt new captioning and masking models
- [ ] Possibly a plugin system for new tools
- [ ] Integration with ComfyUI
- [ ] Docs, Screenshots, Video Guides
