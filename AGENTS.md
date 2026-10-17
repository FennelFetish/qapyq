# qapyq

AI-assisted media curator for large image/video datasets. Streamlined captioning, cropping, masking for LoRA/diffusion training workflows.
The project is hosted in GitHub: https://github.com/FennelFetish/qapyq

It supports manually editing captions and greyscale masks, and AI automation.

**This file is a map of the codebase.** For feature descriptions and workflows, see
[README.md](README.md) and the wiki (links at the bottom). For anything implementation-specific, the
code and its docstrings are the source of truth — do not duplicate them here.


## Project layout

The repository root **is** the Python package (`__init__.py` at the root), so imports are absolute from
the root: `from lib.filelist import FileList`, never `from qapyq.lib...`. Scripts are run from the repo
root and the relative paths in `config.py` (`./res/...`, `./user/...`) resolve against it.

| Path | Contents |
|---|---|
| `main.py` | GUI entry point |
| `main_inference.py` | Inference worker process (spawned, never run by hand) |
| `main_host.py` | Remote-inference daemon |
| `main_setup.py` | Interactive pip installer (no Qt) |
| `config.py` | `Config` singleton: all persisted settings, defaults and user paths |
| `run*.sh` / `run*.bat` | Launchers; activate `.venv`, set malloc/env vars, exec the entry point |
| `setup.sh` / `setup.bat` | Create the venv, then hand off to `main_setup.py` |
| `lib/` | Framework-agnostic + shared Qt layer: the file model, the template language, caption/mask IO |
| `ui/` | Main window, tabs, the image/video view, and shared widgets |
| `tools/` | The 7 image-viewer tools (view, slideshow, measure, compare, crop, scale, mask) |
| `caption/` | Caption window: editor, rules engine, groups, conditionals, focus, generate, cascade |
| `gallery/` | Gallery window: thumbnails, selection, inline captions, semantic sort |
| `stats/` | Stats window: one tab per summary table over the loaded files |
| `batch/` | Batch window: one tab per whole-folder task |
| `infer/` | Model backends and the inference session/proc layer |
| `host/` | Protocol, inference service, image cache, host config window |
| `scripts/` | Headless CLI front-ends that reuse the GUI's batch task classes |
| `requirements/` | pip lists, composed by `main_setup.py` per compute platform |
| `res/` | Icons, font, Qt palettes, CLIP tokenizer, VAE configs, llama.cpp chat templates |
| `user/` | User data folders; each ships a `.gitignore` ignoring everything except seed files |
| `test/` | Standalone `unittest` scripts |

`ui/` and `stats/` have **no** `__init__.py` (namespace packages); `gallery/__init__.py` re-exports
`Gallery`, which deviates from the empty-`__init__.py` convention below — known, to be cleaned up
separately.


## Entry points

- **`main.py`** — GUI. `SingleInstanceServer` (a `QLocalServer` named `qapyq-single-instance`) forwards
  `sys.argv` paths from a second launch into the running instance. `initLogging()` tees stdout/stderr
  into `./last.log` and preserves the real `fileno()` so subprocess pipes inherit correctly. Also applies
  the color scheme/palette and halves the global `QThreadPool` size.
- **`main_inference.py`** — the inference worker. Reassigns `sys.stdout = sys.stderr` so stdout carries
  only protocol frames; `argv[1]` (comma-separated devices) overrides `Config.inferDevices`.
- **`main_host.py`** — the remote daemon (`run-host.sh`). Lazily spawns `main_inference.py` on the first
  inference frame, then acts as a transparent relay that also holds the remote image cache.
- **`main_setup.py`** — pure-text wizard. A table of `ComputePlatform` entries (CUDA 12.6/12.8/13.0,
  ROCm 6.4/7.2, CPU) plus component choices (all / GUI only / backend only) compose the ordered
  `pip install` invocations from `requirements/`.
- **`scripts/batch_{apply,file}_cli.py`** — headless `QCoreApplication` front-ends. They build the *same*
  `BatchApplyTask` / `BatchFileTask` objects as the GUI; no processing logic is duplicated.


## Architecture overview

1. **The tab is the unit of state.** `ImgTab` (`ui/tab.py`) is a `QMainWindow` embedded in the central
   `QTabWidget`. Each tab owns its own `FileList`, `ImgView`, status bar, live tool instances
   (`tab.tools`, kept alive so per-tool state survives tool switching) and per-tab aux-window content.
   "The current image" always means *the current tab's current file*. Switching tabs re-binds every
   window to the new tab's content.
2. **`FileList` is the single source of truth** (`lib/filelist.py`): files, `currentFile`/`currentIndex`,
   the selection, an optional display order, and a per-file `fileData` dict. Consumers subscribe through
   three duck-typed listener channels — no Qt signals: `addListener` (`onFileChanged` /
   `onFileListChanged`), `addSelectionListener` (`onFileSelectionChanged`), `addDataListener`
   (`onFileDataChanged`). Per-file state that must outlive a view (edited caption, mask layers,
   thumbnail, embedding, changed/saved icon states) belongs in `setData`/`getData` under a `DataKeys`
   key, not in a local map.
3. **Aux windows are per-tab, not global.** `ui/aux_window.py:AuxiliaryWindow` installs the current
   tab's cached content widget as its central widget. The four content classes are resolved by name in
   `ui/main_window.py:getAuxWindowClass()`: `gallery` → `Gallery`, `stats` → `StatsContainer`,
   `batch` → `BatchContainer`, `caption` → `CaptionContainer`. Adding a window means a new folder, a
   content class, and an entry there.
4. **Two rendering scenes.** Media lives in `imgview.scene()`; all non-scaling chrome (crop rects,
   rulers, mask layers, video controls, drop zones, brush cursor, confirm flash) lives in
   `imgview._guiScene`, drawn unscaled by `ZoomPanView.drawForeground`. Tools receive input through the
   `Tool.onMouse*` hooks, never by installing event filters.
5. **Everything heavy is a `QRunnable` on the global `QThreadPool`.** Long jobs expose mutex-guarded
   `abort()`/`isAborted()`. A private pool exists only where serialization matters (`ThumbnailCache`,
   the VAE roundtrip). `stats/` is the **only** user of `multiprocessing`; `batch/` and `gallery/` are
   threads.
6. **AI inference never runs in the GUI process.** `Inference().createSession()` hands out workers:
   `main_inference.py` locally, or `ssh ... run-host.sh` remotely, speaking a length-prefixed msgpack
   protocol (`host/protocol.py`). VRAM is only released with the process, so switching model preset
   restarts the worker (`InferenceProcess._updateBackend`). Backends are byte-identical local and remote
   because `host/imagecache.py:ImageFile` abstracts "path locally / uploaded bytes remotely".

Cross-window communication uses Qt signals for widget-internal events and a small number of
module-level signal singletons for global buses (`SIZE_PRESET_SIGNALS`, `ModelSettingsWindow.signals`,
`KeySettingsWindow.signals`). Explicit `QueuedConnection` / `BlockingQueuedConnection` is used wherever
a worker must not block the GUI thread.


## `config.py`

The `Config` class holds every persisted setting as class attributes, with an explicit `_load`/`save`
pair mapping to snake_case keys in `qapyq_config.json`. Notable groups: `exportPresets` (per-tool path
templates), `infer*Presets` (model presets per task family), `inferHosts` (remote hosts), prompt
presets, `windowStates`/`windowOpen`. It imports **nothing** at module scope — all imports live inside
`load`/`save` to keep startup cost at zero.


## `lib/` — framework-agnostic + shared Qt layer

Everything outside `ui/` that more than one window needs. Two spines run through it: `filelist.py`
(the file/selection/data model) and `template_parser.py` (the `{{...}}` expression language reused by
prompts, cascade templates and export paths).

- `filelist.py` — `FileList` (files, current index, selection, order, `fileData`/`DataKeys`),
  `FileSelection`, `FileOrder`, async abortable folder scanning, natural sort. Selection of exactly one
  file is normalized to "no selection".
- `captionfile.py` — per-media `.json` + `.txt` sidecar model (`CaptionFile`, sections `captions` /
  `prompts` / `tags` / `metrics` / `cascade`) and `FileTypeSelector`, the single read/write path for
  captions used by the Caption window, the Gallery list view, Batch and the CLI.
- `cascade.py` — headless cascading-update engine: builds a dependency graph from per-key templates,
  topologically sorts, re-evaluates dependents on save. Folders inherit templates from ancestors.
  (GUI twin: `caption/caption_cascade.py`.)
- `template_parser.py` — the template/expression language: `ExpressionParser`, `TemplateVariableParser`,
  `VariableHighlighter`, `TemplateRulesProcessor` (the `#rules:` bridge into the caption rules engine).
- `mask_macro.py` — JSON macro format (`MacroOp`, `MacroOpItem`, `MaskingMacro`), replay, and
  `ChainedMacroRunner` which interleaves CPU operations with inference steps.
- `mask_macro_vis.py` — renders a macro as a per-layer grid so the user can inspect what it does.
- `qtlib.py` — the shared widget toolbox: fonts, `numpyToQImage`/`qimageToNumpy`, colored buttons, the
  status bar base class, `MenuComboBox`, `LayoutFilter`, `SingletonWindow`.
- `colorlib.py` — theme-aware palette globals plus the HSV helpers used for group colors, bubble styles
  and text highlighting. `initColors()` is called once from `main.py`.
- `imagerw.py` — image loading (PIL always, Qt optionally), sRGB normalization, EXIF orientation, the
  image extension set.
- `videorw.py` — video metadata, keyframes, frame extraction (PyAV with OpenCV/ffprobe fallbacks),
  thumbnails, and `VideoExportProcess` (the ffmpeg `QProcess`). Image export never handles video.
- `csv.py` — `CsvLoader` / `ColumnNameCsvLoader` ABCs for header-based CSV loading (tag implications,
  autocomplete sources).
- `threadlib.py` — `Future[T]`, a minimal condition-based future used by the inference proc layer.
- `util.py` — odds and ends: the `Singleton` metaclass (used by `Inference`), `CaptionSplitter`, a
  formatting helper, an exception-swallowing decorator.


## `ui/` — main window, tabs and the media view

- `main_window.py` — `MainWindow` (tab host, toolbar, aux-window toggles, fullscreen, quit handling),
  `MainMenu`, `MainToolBar`, and `getAuxWindowClass()` which maps a window name to its content class.
  The main toolbar is the only toolbar here; the status bar belongs to the tab.
- `tab.py` — `ImgTab`: owns the `FileList`, the `ImgView`, the `TabStatusBar`, the tool registry and the
  per-tab aux-window content cache. Creates tools lazily and docks their side toolbars.
- `imgview.py` — `ImgView` (graphics view that arbitrates input between the active tool and the media
  item and swaps the media item on file change) plus the media-item contract `MediaItemMixin`,
  `ImgItem`, `MediaMetadata`.
- `video_player.py` — `VideoItem` / `FrozenVideoItem` and all playback UI: seek bar, keyframe
  navigation, volume, thumbnails. Frame extraction runs on its own `QThread`.
- `zoompan_view.py` — `ZoomPanView`: centered zoom/pan and the two-scene overlay rendering.
- `dropview.py` — `DropView` / `DropRect`: the drag-and-drop zones drawn while files hover the view.
- `aux_window.py` — `AuxiliaryWindow`: geometry persistence and re-binding to the current tab's content.
- `export_settings.py` — the whole image export pipeline: path templates and their variables, formats
  and quality, scaling presets (interpolation, low-pass filter, optional AI upscale), the anti-aliasing
  stack, and the `ImageExportTask` runnable that Crop and Scale subclass.
- `size_preset.py` — reusable `W x H (x frames)` target-size presets and their combo box.
- `autocomplete.py` — autocomplete sources (n-gram tag CSVs, JSON keys, template variables), the fuzzy
  scoring model, the popup, and the `TemplateTextEdit` base editor used by most caption/path fields.
- `edit_table.py` — generic sortable, editable string table used by the rules/settings editors.
- `flow_layout.py` — `FlowLayout` and drag-to-reorder containers, plus the sorted tag-bubble widget.
- `effect.py` — the green confirmation flash drawn after a successful export.


## `tools/` — the image-viewer tools

`Tool` (`tool.py`) is the lifecycle/input contract every tool implements: `getToolbar`, `onEnabled` /
`onDisabled`, `onSceneUpdate`, `onFullscreen`, `onMouse*` (return `True` to consume the event),
`onKeyPress`, `onTablet`, `getDropRects` / `onDrop`, `onGalleryRightClick`, `onMediaEvent`.
`ViewTool` (`view.py`) adds the viewport↔image coordinate mapping that every other tool builds on —
**subclass `ViewTool`, not `Tool`.**

- `tool.py` — the `Tool` base class and the `MediaEvent` enum.
- `view.py` — `ViewTool`: coordinate mapping, default drop zones, arrow-key file/folder navigation,
  status-bar media info.
- `slideshow.py` — `SlideshowTool`: interval/shuffle/fade, auto-hiding toolbar, cross-fade animation.
- `measure.py` — `MeasureTool`: drag-to-measure with live values in the status bar.
- `compare.py` — `CompareTool`: draggable split view, difference overlay, and the asynchronous VAE
  encode/decode roundtrip.
- `crop.py` — `CropTool`: rotation-aware selection, video time-range selection, image/video export.
- `crop_toolbar.py` — crop side panel (target size, selection readout, rotation, video time range).
- `scale.py` — `ScaleTool` and the `ScaleMode` family (fixed, fixed width/height/side, factor, pixel
  count, quantized). Batch Scale reuses these mode widgets.
- `mask.py` — `MaskTool`, `MaskItem` (a layer with its own undo history), mask export.
- `mask_toolbar.py` — mask side panel: layer list, operation selector, history, macro recording, export.
- `mask_ops.py` — every mask operation as a pluggable widget with a testable static `operate()`, plus
  the worker runnables for detect/segment/macro replay. Each mutating op follows the same six steps:
  to numpy → `operate` → from numpy → mark edited → record macro step → add history entry.


## `caption/` — the caption window

`CaptionContainer` is the window's view+controller; `CaptionContext` is the shared state hub (it hosts
the sub-tabs and builds the cached `CaptionRulesProcessor`); `CaptionTab` is the sub-tab base class
declaring `getMultiEditSupport()` and enable/disable hooks.

- `caption_container.py` — `CaptionContainer`: layout, source/destination `FileTypeSelector`s,
  apply-rules, load/save, and the `FileList` listener callbacks.
- `caption_context.py` — `CaptionContext` (sub-tab host + cross-tab signals) and
  `CaptionContextDataSource`, which adapts it to the highlighting engine.
- `caption_tab.py` — `CaptionTab` base class and `MultiEditSupport` enum.
- `caption_filter.py` — the rules engine: one `CaptionFilter` subclass per stage, `CaptionRulesSettings`
  (per-stage on/off) and `CaptionRulesProcessor.process()`. Stage order is **load-bearing**:
  1. search/replace (on the raw text, before splitting; replacements may use `{{1}}` group refs)
  2. split on the separator
  3. mutually exclusive / priority
  4. ban **or** whitelist-groups (mutually exclusive modes)
  5. conditionals (keep-mode or sidechain-mode)
  6. sort (group order, then spectral seriation for non-group tags)
  7. combine tags into combined tags
  8. remove implications (transitive, CSV-loaded)
  9. remove subsets, then duplicates (subsets first — otherwise exact duplicates get deleted)
  10. join with the separator
  11. prefix/suffix (last, so it always ends the caption)
- `caption_conditionals.py` — `ConditionalRule` (expression + conditions + actions),
  `ConditionalFilterRule` (evaluates the expression with Python's `ast` after rewriting
  `and`/`or`/`xor`), the condition and action registries, and sidechain mode.
- `caption_groups.py` — `CaptionGroups`: reorderable group list with color, exclusivity mode,
  combine-tags, wildcards, and the filter bar. Provides the `MatcherNode` the Gallery filter uses.
- `caption_settings.py` — the Rules tab: separator, prefix/suffix, the stage checkboxes, the
  search/replace table and banned tags. Doubles as the preset editor.
- `caption_preset.py` — the serializable preset document (rules + groups + wildcards + conditionals in
  one JSON) and the `MutualExclusivity` enum.
- `caption_multi_edit.py` — `CaptionMultiEdit`: merges the tags of all selected files into one editable
  text, diffs edits back into per-file tag lists (`SequenceMatcher` → split/merge/replace/delete/insert/
  move), and reports per-tag presence.
- `caption_highlight.py` — the highlighting engine: `CaptionHighlight`, the `HighlightDataSource`
  adapter interface, and `MatcherNode`, the tag trie used everywhere a caption must be split into known
  components.
- `caption_cascade.py` — the Cascade Templates tab: one tab per hierarchy level (file + ancestor
  folders) with add/remove/inherit tri-state entries, live previews, and a cycle check before saving.
- `caption_generate.py` — the Generate tab: prompt editor, inference presets, and the batch inference
  task that writes results back into captions.
- `caption_focus.py` — Focus mode: pin a few focus tags and toggle them with number keys across files.
- `caption_list.py` — the List tab: every `tags.*` / `captions.*` key plus the `.txt` file, all editable,
  saved together with an overwrite-conflict check based on file modification times.
- `caption_bubbles.py` — the draggable tag bubbles shown above the editor.
- `caption_text.py` — `NavigationTextEdit` / `CaptionTextEdit`: caption-aware selection, tag toggling,
  Alt+arrow navigation, token boundary lines.
- `caption_tokens.py` — the CLIP token counter and its tokenizer task.
- `caption_wildcard.py` — the wildcard format (`color: blue, green`) and cartesian expansion.
- `caption_menu.py` — the window's `☰` menu (tokenizer toggle, preset actions, per-stage rule toggles).


## `gallery/` — the gallery window

- `gallery.py` — `Gallery`: window content, caption source selector, view-mode toggle, folder menu tree,
  status bar. Both modes share **one** `QTableView`; the delegate is swapped.
- `gallery_model.py` — `GalleryModel` (`QAbstractTableModel`) over `FileList`, plus `FileItem`,
  `HeaderItem`, `SelectionState`, `GridPos` and the coalescing thumbnail update queue.
- `gallery_view.py` — `GalleryView`: column-count calculation, persistent editors, mouse/keyboard
  navigation, drag-select, item context menu, drag-out of files.
- `gallery_delegate.py` — `GalleryDelegate` base plus the grid and list delegates, and
  `GalleryCaptionEditor` (the inline-editable caption in list mode).
- `gallery_header.py` — `GalleryHeader`: the per-folder header row and its folder actions.
- `gallery_sort.py` — `GallerySortControl` and the semantic sort: embedding task, prompt-template
  loading, scoring, and the on-disk `EmbeddingCache`.
- `gallery_caption.py` — `GalleryCaption`: caption loading plus the per-line `QTextLayout` construction
  used for thumbnail captions (with optional rules/filter processing and ellipsis truncation).
- `thumbnail_cache.py` — `ThumbnailCache` singleton with its own thread pool; decodes on a worker
  thread and creates the `QPixmap` on the GUI thread.


## `stats/` — the stats window

`StatsBaseProxyModel` (`getFiles(index)`) is what makes a row map back to files. `StatsLayout` builds
the shared three-pane UI (filter box + CSV export / table / resulting file list with combine modes
Any-One-Multiple-All, `Negate`, and `With Files...` actions). `StatsLoadTask` is the worker base with
progress, abort, terminate and the `map_multiproc` helper.

- `stats_container.py` — `StatsContainer`: hosts the six tabs, forwards file-list changes to them.
- `stats_tags.py` — `TagStats`: per-tag counts and presence; optional combined-tag splitting via the
  Caption window's groups; context menu to push tags into the Caption window or a Batch rules preset.
- `stats_json.py` — `JsonStats`: counts of the flattened keys found in the `.json` sidecars.
- `stats_imgsize.py` — `ImageSizeStats`: buckets by width/height/frames with aspect and Mpx columns.
- `stats_mask.py` — `MaskStats`: white area / white region count / black region count histograms,
  locating masks via a configurable path template.
- `stats_filesuffix.py` — `FileSuffixStats`: groups images by neighbouring filename suffixes.
- `stats_folders.py` — `FolderStats`: a folder tree with counts, percentages and a repeat-balance estimate.


## `batch/` — the batch window

`BatchTask` is the contract: a `QRunnable` with `runPrepare` / `runProcessFile` / `runCleanup`, a log
entry, progress signals and mutex-guarded `abort()`. `BatchInferenceTask` overrides the per-file hook to
pull results from an `InferenceSession` and returns an `InferenceChain` from its `runCheckFile`.
`BatchTaskHandler` owns the Start buttons (All / Selected / Current), the confirmation summary and the
shared progress bars. Each task tab implements `getConfirmOps()` (bullets + "needs inference") and
`createTask(files)`.

- `batch_container.py` — `BatchContainer`: hosts the task tabs, the shared log, progress bars and the
  colour animation on running tabs.
- `batch_task.py` — `BatchTask`, `BatchInferenceTask`, `BatchTaskHandler`, `BatchUtil`, `BatchProgressUpdate`.
- `batch_caption.py` — generate captions/tags into the `.json` sidecars via inference.
- `batch_rules.py` — apply caption rules from one JSON key to another, no inference. Reuses
  `CaptionRulesProcessor` and the conditionals/groups widgets; exposed to Stats.
- `batch_transform.py` — send existing captions to an LLM and store the result in another key.
- `batch_apply.py` — render a template into a destination (`.txt`, JSON key, cascade template), with
  optional backup of the old value and deletion of the sidecars. No inference.
- `batch_scale.py` — batch resize, reusing `tools/scale.py`'s mode widgets and the export pipeline;
  switches to the inference variant when the scaling preset names an AI model.
- `batch_mask.py` — run mask macros over files; the inference variant uses `ChainedMacroRunner`.
- `batch_crop.py` — crop regions found in a mask (or produced by a macro), fitted to the closest size preset.
- `batch_file.py` — copy / move / symlink / zip, with destination templates, mask renaming and caption
  inclusion. Powers `scripts/batch_file_cli.py`.
- `batch_log.py` — per-run log tabs, save-to-file, and the run-group conflict guard for
  caption-mutating tasks.


## `scripts/`

- `scripts_common.py` — `scriptMain`, `CliBatchRunner` (creates a real `FileList`, loads `--src`, runs the
  task, prints a summary and an interactive confirmation), `ScriptLogHandler` (tqdm-based stand-in for
  `BatchLogEntry`).
- `batch_apply_cli.py`, `batch_file_cli.py` — argparse front-ends over the GUI task classes.


## `infer/` — models and the inference layer

- `inference.py` — the `Inference()` singleton: host discovery (`getHosts`, expanding `proc_count`),
  `createSession()`, `InferenceSession` (prepare / `queueFiles` generator / `getFreeProc` scheduling by
  fewest-queued-files then priority), `ProcState`, `InferenceChain` (composable per-file dispatch with
  queue / resultCallback / forwardResult / result), and `ImageUploader` for remote hosts.
- `inference_proc.py` — `InferenceProcess`: one `QProcess` on a dedicated thread, the framed msgpack wire
  protocol, the future-recording mode used to learn a task's result count, the per-task query methods,
  and `_updateBackend`, which **restarts the worker when the model config changes** to release VRAM.
  `InferenceProcConfig` decides local vs remote (`cmd`) and rewrites model paths via `model_base_path`.
- `backend_config.py` — **the model registry.** `BackendTypes` (`LLAMA_CPP`, `TRANSFORMERS`, `ONNX`,
  `TORCH`, `ULTRALYTICS`, `SPANDREL`), `BackendDef`, the six display-name→def catalogues
  (`BackendsCaption`, `BackendsLLM`, `BackendsTag`, `BackendsMask`, `BackendsUpscale`,
  `BackendsEmbedding`), and `BackendLoader._loadBackend()` — the single `match` statement where every
  architecture is instantiated. `def.name` is the wire id persisted in presets.
- `backend.py` — `InferenceBackend` (sampling defaults, system-prompt merging, reasoning stripping) and
  the `CaptionBackend` / `AnswerBackend` ABCs. Note that mask/tag/embed/upscale backends deliberately do
  **not** inherit from it — they only need `setConfig` plus their task methods.
- `model_settings.py` — `ModelSettingsWindow` (`SingletonWindow`), one tab per preset family, with the
  backend combo, model-path row and per-type extras.
- `inference_settings.py` — sampling settings widget (gated on `BackendDef.features`) and
  `InferencePresetWidget`, including per-host preset overrides (`RemoteInferenceConfig`).
- `tag_settings.py` — tagger settings (ratings, characters, thresholds, adaptive modes).
- `devmap.py` — the HuggingFace `device_map` builder: GPU/CPU layer placement by percentage, attention
  implementation choice, ONNX provider list. Each transformers backend implements
  `static makeDeviceMap(...)` naming its own submodules.
- `quant.py` — bitsandbytes NF4/INT8 quantization configs.
- `prompt.py` / `prompt_struct.py` — the prompt editor widget and the conversation format:
  `PromptInfo`, `Conversation`, and `ConversationParser`, whose line format is `--- name` (new prompt),
  `=== name` (new conversation), `>>> text` (assistant prefill), with `?` for hidden and `!` for thinking.
- `caption/` — one module per VLM architecture: `florence2`, `internvl`, `joycaption`, `llamacpp`,
  `molmo`, `ovis16`, `ovis2`, `ovis25`, `qwen2vl`, `qwen25vl` (also dispatching Qwen3-VL).
- `tag/` — `tag.py` (base: thresholds, video batching, adaptive thresholding), `wd.py`, `pixai.py`,
  `joytag.py` + `JoytagModels.py` (a **vendored upstream** model definition — not qapyq code).
- `mask/` — `yolo.py` (detection), `briarmbg.py`, `inspyrenet.py` (segmentation), `llamacpp_detect.py`.
- `misc/` — `upscale.py` (spandrel, tiled), `vae.py` (diffusers, per-family config), `tokens.py`
  (CLIP tokenizer; cannot be named `tokenize.py` because it shadows the stdlib module).
- `embedding/` — `embedding_common.py` (processing/aggregate presets), `backend_embedding.py`,
  `clip.py`, `siglip.py`, `siglip_onnx.py` (patch strategies for the ONNX models).


## `host/` — remote inference

- `protocol.py` — `Protocol` (length-prefixed msgpack over two binary streams, `Service.ID.HOST` /
  `Service.ID.INFERENCE`, sub-service routing), the `@msghandler` decorator, `Service` base and
  `MessageLoop`.
- `service_inference.py` — `InferenceService`: the worker's handler set. Every command has a matching
  query method on `InferenceProcess`; replies are dicts with an `error` / `error_type` pair on failure.
- `imagecache.py` — `ImageFile` (path or uploaded bytes, decoding to OpenCV/PIL/URI) and `ImageCache`.
- `host_window.py` — `HostWindow` (`SingletonWindow`): add/remove hosts, priority, process count, queue
  size, `model_base_path`, the `ssh ... run-host.sh` command and its "Test Command" button.


## `res/`, `user/`, `requirements/`

- `res/` — icons and SVGs, the bundled monospace font, `palette-light.json` / `palette-dark.json`
  (loaded by `main.py`, then handed to `colorlib.initColors`), a complete CLIP tokenizer for token
  counting, one VAE config JSON per VAE family, and llama.cpp jinja chat templates.
- `user/` — `autocomplete/` (tag CSVs), `embedding-prompt-templates/` (`{}` templates for semantic sort),
  `mask-macros/`, `tag-implications/` (CSV implications). Each folder git-ignores its contents except
  the seed files it ships.
- `requirements/` — base lists (`requirements.txt`, `-gui`, `-infer`, `-pytorch`) plus platform-specific
  files for onnxruntime, llama.cpp and flash-attn. `main_setup.py` composes the install order, including
  an old `transformers` pin for the model families that need it.


## Where to change things

| To add… | Touch |
|---|---|
| A tool | subclass `ViewTool`, add a case to `ImgTab.createTool`, **and** add the name to the tool list in `MainMenu` and `MainToolBar` — three places must stay in sync |
| A mask operation | a `MaskOperation` in `tools/mask_ops.py`, its key in the `tools/mask_toolbar.py` registry, and a `MacroOp` name in `lib/mask_macro.py` if it must be recordable/replayable |
| A batch task | subclass `BatchTask` or `BatchInferenceTask`, a content widget wired to `BatchTaskHandler`, a tab in `batch_container.py` |
| A stats table | `XxxData`/`XxxSummary`/`XxxModel`/`XxxProxyModel`/`XxxLoadTask` on top of `stats_base.py`, a tab in `stats_container.py` |
| A caption rule stage | a `CaptionFilter` in `caption/caption_filter.py`, wired into `CaptionRulesProcessor.process()`, `CaptionRulesSettings`, and the preset JSON |
| A model architecture | a backend class in `infer/<task>/`, a `BackendDef` in the matching `infer/backend_config.py` catalogue, a `case` in `BackendLoader._loadBackend`; extend `infer/model_settings.py` only if it needs new fields |
| A protocol command | a query method on `InferenceProcess` plus an `@msghandler` in `host/service_inference.py` |
| A remote host | nothing in the protocol — a `Config.inferHosts` entry via `host/host_window.py` |
| A caption sub-tab | a `CaptionTab` subclass added to `CaptionContext` |

Reuse before adding: path templates come from `Config.exportPresets`, target sizes from
`ui/size_preset.py`, image saving from `ui/export_settings.py`, and the CLI reuses the GUI's batch tasks.


## Persistent formats

| Format | Owner | Shape |
|---|---|---|
| `qapyq_config.json` | `config.py` | All persisted settings, presets, host list, window geometry |
| `<media>.json` + `<media>.txt` | `lib/captionfile.py` | Sections `captions` / `prompts` / `tags` / `metrics` / `cascade`; written **only** through `FileTypeSelector` |
| `qapyq_cascade.json` | `lib/cascade.py` | Per-folder key→template map, inherited by subfolders |
| caption rules preset | `caption/caption_preset.py` | Rules + groups + wildcards + conditionals in one file |
| mask macro | `lib/mask_macro.py` | JSON list of ops; recorded in parallel with the undo history |
| inference presets | `infer/model_settings.py` | One dict per preset per task family, keyed by backend wire id |


## Gotchas

- **Lazy function-local imports are load-bearing, not style.** They keep GUI startup fast and keep
  torch/transformers/llama-cpp out of the GUI process. Don't hoist them to module scope.
- **Three deliberate circular-import breaks**: `gallery_model.py` imports `thumbnail_cache` at the
  bottom of the file; `gallery_delegate.py` imports `GalleryView` inside `GalleryDelegate.__init__`;
  `gallery_sort.py` imports `infer.inference` inside task methods. Preserve them.
- **Images are BGR by default.** `qtlib.qimageToNumpy` / `numpyToQImage` and `imagerw.loadMatBGR` are
  BGR; respect the flag instead of assuming RGB. Saving always goes through `export_settings.saveImage`.
- `Service` handlers must be defined in the concrete class's own `__dict__` — they are not inherited.
- The mask undo history stores the raw array first and a PNG-compressed copy asynchronously; undoing
  also disables that step in any macro currently being recorded.


## Windows

All windows depend on the current tab's current file, and can be placed on separate monitors.

- **Main window** — tabbed; tool bar with menu, tool selection (`Ctrl+1`..`Ctrl+7`) and window toggles;
  per-tab status bar with media info and messages.
  - Tools: View, Slideshow, Measure, Compare, Crop, Scale, Mask.
- **Gallery** (`F1`) — thumbnails of the files that Batch will process. Folder dropdown, multi-selection,
  two display modes (Grid with optional captions, List with inline-editable captions), semantic sort.
- **Stats** (`F2`) — Tag Count, JSON Keys, Media Size, Mask, File Suffix, Folders.
- **Batch** (`F3`) — Caption, Rules, Transform, Apply, Scale, Mask, Crop, File, plus the Log tab.
- **Caption** (`F4`) — Rules, Groups, Conditionals, Focus, Generate, List, Cascade Templates.


## Wiki

Reference documentation for users. Read the relevant page before changing behaviour that is documented
here.

- User guide: https://github.com/FennelFetish/qapyq/wiki/User-Guide
  - Basics, image viewer, video player
  - Tools: View, Slideshow, Measure, Compare, Crop, Scale, Mask
  - Media export: scaling presets, image formats/quality, anti-aliasing, color profiles
  - Auxiliary windows: Gallery, Stats, Batch, Caption
- Captioning guide: https://github.com/FennelFetish/qapyq/wiki/User-Guide-%E2%80%90-Captioning
  - Captions saved in per-media JSON files + txt file
  - Autocomplete
  - Rules processing: search/replace, banned tags, remove subsets, remove implications, sorting
  - Groups: mutually exclusive, combine tags, wildcards
  - Conditional rules: conditions/actions, sidechain, expressions with variables
  - Multi-Edit mode: splitting/merging tags
  - Focus mode
  - Cascading updates with hierarchical templates
  - Prompt and conversation format
  - Template syntax with functions and subexpressions
- Setup and model configuration: https://github.com/FennelFetish/qapyq/wiki/Setup
  - Compute platform selection, host setup for remote inference, per-task model setup
- Tips and workflows: https://github.com/FennelFetish/qapyq/wiki/User-Guide-%E2%80%90-Tips-and-Workflows
  - Grounding, training on subsets, end-to-end curation recipes


## Tech Stack

- Python 3.10 and above
- OS targets: Linux, Windows
- GUI: Qt / PySide6
- Processing: PIL, OpenCV, numpy, PyAV, ffmpeg (external)
- Inference: transformers, torch, llama-cpp-python, onnxruntime-gpu
- venv, pip with custom setup script


## Development environment

- Dev happens inside a Docker container: bare Ubuntu 26.04 LTS, user `ubuntu`
  (uid 1000). The project is bind-mounted from the host at /data/qapyq.
- The container is headless: run GUI imports/tests with `QT_QPA_PLATFORM=offscreen`.
- Only the GUI requirements are installed into the venv.
- **Do NOT commit** until the user has run and tested the changes on the
  HOST. Make the changes, verify in the container, then wait for the user's go-ahead before committing.
- **Do NOT stage files** to allow viewing the diff vs. other stages files.
  Generally, do not alter any git state unless explicitly asked.
- **Use the `question` tool** any time you need to ask the user for
  clarification, a decision, or preferences — don't guess or assume. This
  also applies to user suggestions: don't overthink them, and don't follow
  them blindly — the user may not have considered every consequence. If a
  suggestion seems off, flag it and ask via the `question` tool before
  implementing.
- If you need more specification, abort your thinking immediately and call the `question` tool
  without further processing. In that case you may output only the question itself. After the user has
  answered your questions, you will be able to continue where you've left off.


## Conventions

### System/Architectural

- Paths are OS-agnostic: use `os.path` for any path transformation and never split/join on a hardcoded `/`.
- One folder per window: `gallery/`, `stats/`, `batch/`, `caption/` map to the auxiliary windows, and
  `tools/` holds everything the main window's tool bar can select.
- The code that runs inside the inference worker stays Qt-free: `infer/backend.py`,
  `infer/backend_config.py`, `infer/devmap.py`, `infer/quant.py`, everything under
  `infer/{caption,tag,mask,misc,embedding}/`, and `host/protocol.py`,
  `host/service_inference.py`, `host/imagecache.py`. GUI requirements are optional for
  headless-server installs, so anything the worker imports must not need them. Note that
  `infer/` also holds GUI-side modules (the session client, the `*_settings.py` widgets,
  `prompt.py`) — the split is by role, not by folder.
- The GUI must not import the model backends; importing the GUI-side parts of `infer/`
  (`Inference`, `InferenceProcess`, `InferenceChain`, `ModelSettingsWindow`, `PromptWidget`, …)
  is expected and keeps torch/transformers/llama-cpp out of the GUI process.

### Code Style

- camelCase for variables and functions (aligned with Qt/PySide6).
- Line length should stay below 160.
- Type hints on all functions, dataclasses or NamedTuples.
- No type checker installed — but keep static typing/IDE autocomplete working with proper annotations.
- Annotate every method that overrides a base-class method with `@override` (from `typing_extensions`).
- Prefer simple/empty `__init__.py` files (docstring at most — no re-exports);
  import symbols directly from their defining module.
- Prefer guards and early-exit at the top of functions instead of nesting.
- The walrus operator (`:=`) is explicitly allowed and preferred in `if`/`while` conditions when it is the only statement,
  i.e. the paren-free form (e.g. `while chunk := f.read(8192):`). Use it where it makes the code more concise;
  don't force it where plain code is clearer.
- Avoid allocation of temporary objects. E.g. use defaultdict: `groups[k].append(x)` instead of `groups.setdefault(k, []).append(x)`.
- Prefer full churn over shims: when a signature or data model changes, update every call site instead of adding
  optional parameters, aliases, or `None`-fallback compatibility paths. Solo project: no merge conflicts to fear,
  no external consumers to protect. A second way to do the same thing is permanent complexity, while a clean break is one commit.
  Design for extensibility in the future instead of short-circuiting in the present, so the next change builds on one canonical path
  rather than routing around yesterday's shortcut.

### Documentation

- Document every assumption you make IN THE CODE, right where it matters: add
  a short comment explaining the "why", any preconditions you rely on, and
  invariants that must hold. Prefer context next to the code over prose in AGENTS.md.
- Every function gets a docstring, even a single sentence: what it does, its
  assumptions/preconditions, and what it returns. Private helpers too.
- Don't overdo the documentation and keep it concise. Needing to think about
  certain aspects is a good hint that it should be documented to remember your findings.
- Document what the code does NOW, not why it was changed. State important
  findings as preconditions/invariants instead of referring to the past.
- The goal: information lives where it's relevant (in the code). AGENTS.md
  captures cross-cutting architecture, repo-wide conventions, and quirks that
  span files — not per-function detail.
- Remember to keep documentation across files consistent with the implementation.


### Testing

- Plain `unittest`. No pytest, no CI config, no `conftest.py`.
- Every file in `test/` is a **standalone script**: it prepends the repo root to `sys.path` itself and
  ends with `unittest.main(verbosity=2)`. Run one file at a time from the repo root:
  `python test/test_template_parser.py`.
- Only pure-logic modules are covered, and they are tested directly: `lib/cascade.py`,
  `lib/template_parser.py`, `caption/caption_filter.py`, `caption/caption_multi_edit.py`,
  `caption/caption_conditionals.py` and `caption/caption_highlight.py:MatcherNode`.
  Test files that print large intermediate states are intentional debugging aids.
- `test/test_flashattn.py` is a manual CUDA smoke check, not a real test.
- Nothing tests Qt widgets. For those, verify imports under
  `QT_QPA_PLATFORM=offscreen python -c "import <module>"` and leave the visual check to the user.
