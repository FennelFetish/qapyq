<img src="res/qapyq.png" align="left" />

# qapyq
<sup>(CapPic)</sup><br />
**An image viewer and AI-assisted editing tool that helps with curating datasets for generative AI models, finetunes and LoRA.** 

<br clear="left"/>
<br /><br />

![Screenshot of qapyq with its 4 windows open.](https://www.alchemists.ch/qapyq/overview.jpg)

## Features

- **Image Viewer**: Display and navigate images
  - Quick-starting desktop application built with Qt
  - Modular interface that lets you place windows on different monitors
  - Open multiple tabs
  - Zoom/pan and fullscreen mode
  - Gallery with thumbnails
  - Compare two images
  - Measure size and pixel distances
  - Slideshow

- **Image/Mask Editor**: Prepare images for training
  - Crop and save parts of images
  - Scale images
  - Manually edit masks with multiple layers
  - Support for pressure-sensitive drawing pens
  - Record masking operations into macros
  - Automated masking

- **Captioning**: Describe images with text
  - Edit captions manually with drag-and-drop support
  - Tag sorting and filtering rules
  - Colored text highlighting
  - Automated captioning
  - Prompt presets
  - Iterative prompting with each answer saved to different entries in a `.json` file
  - Further refinement with LLMs

- **Batch Processing**: Process whole folders at once
  - Flexible batch captioning, tagging and transformation
  - Batch scaling of images
  - Batch masking with user-defined macros
  - Customizable batch cropping of images

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
  - [InternVL2](https://huggingface.co/collections/OpenGVLab/internvl-20-667d3961ab5eb12c7ed1463e)
  - [MiniCPM-V-2.6 (GGUF)](https://huggingface.co/openbmb/MiniCPM-V-2_6-gguf) ([alternative link](https://huggingface.co/bartowski/MiniCPM-V-2_6-GGUF))
  - [Molmo](https://huggingface.co/collections/allenai/molmo-66f379e6fe3b8ef090a8ca19) (recommended)
  - [Ovis-1.6](https://huggingface.co/AIDC-AI/Ovis1.6-Gemma2-9B)
  - [Qwen2-VL](https://huggingface.co/collections/Qwen/qwen2-vl-66cee7455501d7126940800d)

- **LLM**
  - Models in GGUF format with embedded chat template (llama-cpp backend).

- **Masking**
  - YOLO/Adetailer detection models
  - [RMBG-2.0](https://huggingface.co/briaai/RMBG-2.0)


## Setup
Requires Python.

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

More information is available in the [Wiki](https://github.com/FennelFetish/qapyq/wiki).

How to setup AI models for automatic captioning and masking: [Model Setup](https://github.com/FennelFetish/qapyq/wiki/Setup#model-setup)

How to use: [User Guide](https://github.com/FennelFetish/qapyq/wiki/User-Guide)


## Planned Features
- [ ] Natural sorting of files
- [ ] Gallery list view with captions
- [ ] Summary and stats of captions and tags
- [ ] Shortcuts and improved ease-of-use
- [x] AI-assisted mask editing
- [ ] Auto-caption after crop
- [ ] Overlays (difference image) for comparison tool
- [x] Image resizing
- [ ] Run inference on remote machines
- [ ] Adapt new captioning and masking models
- [ ] Possibly a plugin system for new tools
- [ ] Integration with ComfyUI
- [ ] Docs, Screenshots, Video Guides

## Known Issues
- Selection of second image for comparison in Gallery Window might be wrong (unfinished GUI).
- Icons in Gallery can be inconsistent.
