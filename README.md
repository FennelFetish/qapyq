<img src="res/qapyq.png" align="left" />

# qapyq
<sup>(CapPic)</sup><br />
**An image viewer and AI-assisted editing tool that helps with curating datasets for generative AI models, finetunes and LoRA.** 

<br clear="left"/>
<br /><br />

![Screenshot of qapyq with its 4 windows open.](https://www.alchemists.ch/qapyq/overview.jpg)

## Features

- **Image Viewer**
  - Quick-starting desktop application built with Qt
  - Modular interface that lets you place windows on different monitors
  - Open multiple tabs
  - Zoom/pan and fullscreen mode
  - Gallery with thumbnails
  - Crop and save parts of images
  - Compare two images
  - Measure size and pixel distances
  - Slideshow

- **Captioning**
  - Edit captions manually with drag-and-drop support
  - Tag sorting and filtering rules
  - Colored text highlighting
  - Automated captioning and flexible batch processing
  - Prompt presets
  - Iterative prompting with each answer saved to different entries in a `.json` file
  - Further refinement with LLMs
  - Model and sampling settings, GPU acceleration with CPU offload support
  - On-the-fly NF4 and INT8 quantization
  - Separate inference subprocess isolates potential crashes and allows complete VRAM cleanup


## Supported Models
- **Tagging**
  - [JoyTag](https://github.com/fpgaminer/joytag)
  - [WD (onnx)](https://huggingface.co/SmilingWolf/wd-eva02-large-tagger-v3) (eva02 recommended)

- **Captioning**
  - [InternVL2](https://huggingface.co/collections/OpenGVLab/internvl-20-667d3961ab5eb12c7ed1463e)
  - [MiniCPM-V-2.6 (GGUF)](https://huggingface.co/openbmb/MiniCPM-V-2_6-gguf) ([alternative link](https://huggingface.co/bartowski/MiniCPM-V-2_6-GGUF))
  - [Molmo](https://huggingface.co/collections/allenai/molmo-66f379e6fe3b8ef090a8ca19)
  - [Ovis-1.6](https://huggingface.co/AIDC-AI/Ovis1.6-Gemma2-9B)
  - [Qwen2-VL](https://huggingface.co/collections/Qwen/qwen2-vl-66cee7455501d7126940800d)

- **LLM**
  - Models in GGUF format with embedded chat template (llama-cpp backend).


## Setup
Requires Python.

By default, prebuilt packages for CUDA 12.4 are installed. If you need a different CUDA version, change the index URL in `requirements-pytorch.txt` and `requirements-llamacpp.txt` before running the setup script.

1. Git clone or download this repository.
2. Run `setup.sh` on Linux, `setup.bat` on Windows.
   - This will create a virtual environment that needs 7-9 GB.

Tested with RTX 4090 on Kubuntu 22.04 and Windows 10. Python versions 3.10/3.11.

If the setup scripts didn't work for you, but you manually got it running, please share your solution and raise an issue.


### Models
qapyq makes no internet connections (except during the setup script) and does not automatically download models.
Models need to be downloaded manually from https://huggingface.co and then configured in the Model Settings, accessible via the burger menu in the top left corner of the Main Window.

- GGUF vision models consist of a single `.gguf` file + a multi-modal projector model (mmproj...gguf).
- The WD tagging models need the `.onnx` file + the `selected_tags.csv`.
- All other models need the whole folder with all the files.

> [!NOTE]
> For Ovis-1.6 to run multiple times, I had to make these changes to the model's code: [GitHub Issue](https://github.com/AIDC-AI/Ovis/issues/31#issuecomment-2395469771)

#### Prequantized Models (AWQ/GPTQ)
These should work, but the required packages are not installed by default.
Installing those requires downgrading torch and CUDA versions and may have to be built from source.

#### Model Settings for 24GB VRAM

| Model | Quantization | LLM GPU Layers | Visual GPU Layers |
| ----- | ------------ | -------------- | ----------------- |
| InternVL2 1B-8B | None | -1 | -1 |
| InternVL2 40B | NF4 | -1 | 0 |
| MiniCPM-V-2.6 32K Context | Q8 / f16 | -1 | -1 |
| Molmo-7B-D | None | -1 | -1 |
| Ovis1.6-Gemma2-9B | None | -1 | 0 |
| Qwen2-VL 2B/7B | None | -1 | -1 |

InternVL2-26B could't see the images and only wrote about its hallucinations.
I haven't tried InternVL-2-76B or Qwen2-VL-72B.


## Startup
- Linux: `run.sh`
- Windows: `run.bat` or `run-console.bat`

You can open files or folders directly in qapyq by associating the file types with the respective run script in your OS.
For shortcuts, icons are available in the `qapyq/res` folder.

## Usage
Use the toolbar at the top of the Main Window to select tools and toggle windows.

- Burger menu in top left corner of Main Window
  - Shows available keyboard shortcuts
  - Use the Model Settings to configure your models
- Load image by drag&dropping files or folders into the Main Window
  - Hold SHIFT while dropping to append files
- Zoom image with mouse wheel
- Pan image by dragging with mouse


### Measure Tool
- Right click starts and freezes measurement.
- Status bar at the bottom displays values.


- Useful for estimating:
  - Mask grow/shrink amount
  - Blur radius/kernel size
  - ...

### Compare Tool
- Load second image by dropping it onto the right side of the Main Window.
- Or right-click on an image in the gallery.

### Crop Tool
1. Set export path.
   - Elements of the image path can be included in the destination path (as part of name or as subfolders).
   - The destination path is shown at the bottom.
2. Use the mouse to select the crop region.
3. Press the left mouse button twice.
   - The first click fixes the selection, the second click confirms it.
   - To reset the selection, right click anywhere or left click outside of the selected region.
   - A green flash effect confirms export.


- Mouse wheel adjusts selection size.
  - Hold SHIFT to adjust in 1px steps.
  - Hold CTRL to pan and zoom.
- Target size presets can be edited in the config file (`qapyq_config.json`) in the `crop_size_presets` list.

### Captioning

#### Caption Window
In the `Groups` tab, add tags to groups by either dragging a bubble into a group, or by clicking the "Add Caption" button after putting the text cursor on the respective tag.

Edit the text of an existing tag by right-clicking on it. When its text is completely removed, the tag is removed from the group. Reorder tags inside a group or move them between groups by dragging them around.

Click on a tag inside a group to append it to the text.
Reorder existing tags by dragging the bubbles with the mouse.

When the save button is clicked, the current text is saved to a `.txt` file with the same name as the image, in the same folder.
Edited captions are kept in memory even when another image is selected. However, when another file or directory is loaded, changes are lost!
The Gallery Window shows little icons for the caption state:
- A white icon means that a `.txt` file exists.
- A red icon means that the caption was edited but hasn't been saved yet.
- With a green icon, the caption was edited and saved.


> [!NOTE]
> The caption is loaded from and saved to the `.txt` file directly,
> unlike the Batch Window that saves captions to a `.json` file instead.


#### Batch Window
AI-assisted batch captioning consists of multiple steps:
1. Generate captions and/or tags.
   - This information is stored in `.json` files alongside the images, but separate from the final `.txt` file.
2. (optional) Further transform the entries in the `.json` file using rules or LLMs.
3. Save the final caption in a `.txt` file according to a template.


#### Prompts and Conversations
Through prompts you can ask questions and give instructions to the vision models. You can also ask multiple questions that are sent sequentially and guide the AI towards more in-depth answers. Separate these prompts with a line starting with `---`:

```
Describe the image in detail.
---
What can be said about the soil condition and geology. How was this landscape formed?
--- final ---
Condense all this information into a detailed summary using prose without bullet points.
```

In above example, the name `final` is given to the last answer. The trailing dashes are optional. During batch processing, the answer is saved under this name and can be referenced later using the `{{captions.final}}` variable.
If no name is specified, the default name (default storage key) is used. When there are duplicate names, an increasing counter is appended.

With correct syntax, separate prompts are displayed in different colors.

##### Ignore answers
If the name starts with a `?`, the answer is still part of the conversation, but it's excluded from the output:

```
--- ?
What is the meaning of this image?
--- ? not-saved
What does the subject represent?
---
Summarize your answers.
```

In this example, only the summary is displayed and saved to the `.json` file.

##### Multiple conversations
When prompts are separated by `---`, they will be sent in one conversation and the model will remember previous messages.
To start a new conversation, use `===` instead:

```
Describe the image in detail.
=== funny
Describe the image using funny language.
```

As shown in this example, these prompts also can have names.


#### Templates
In the Batch Window, you can define prompt and save formats using templates. Contents from the `.json` file can be referenced with these variables:

| Variable | Replaced with |
| -------- | -------- |
| `{{captions.X}}` | Caption that was stored with name `X` |
| `{{prompts.X}}` | Prompt that was used to generate caption `X` |
| `{{tags.X}}` | Tags that were stored with name `X` |
| `{{folder}}` | Folder name of the image |

Variables are highlighted in different colors, and the preview shows the replacement text in the same color.


## Planned Features
- Summary and stats of captions and tags
- AI-assisted mask editing
- Auto-caption after crop
- Adapt new captioning models
- Overlays (difference image) for comparison tool
- Possibly a plugin system for new tools

## Known Issues
- I don't know if flash attention actually works on Windows. Some models output warnings.
- Selection of second image for comparison in Gallery Window might be wrong (unfinished GUI).
- InternVL2 doesn't follow system prompts well.
- Qwen2VL raises out-of-memory error when visual layers are offloaded to CPU, or when describing very large images
