class Config:
    # Paths
    pathConfig              = "./pyimgset_config.json"
    pathExport              = "./export/"

    # View
    viewZoomFactor          = 1.15
    viewZoomMinimum         = 0.5

    # Slideshow
    slideshowInterval       = 4.0
    slideshowShuffle        = False

    # Crop
    cropSizePresets         = ["512x512", "512x768", "768x768", "768x1152", "1024x1024", "1024x1536"]
    cropSelectionChange     = 0.02

    # Inference
    inferCaptionModelPath   = "/mnt/ai/Models/MM-LLM/MiniCPM-V-2.6_Q8_0.gguf"
    inferCaptionClipPath    = "/mnt/ai/Models/MM-LLM/MiniCPM-V-2.6_mmproj-model-f16.gguf"
    inferTagModelPath       = "/mnt/ai/Models/MM-LLM/joytag"

    inferSystemPrompt       = "You are an assistant that perfectly describes scenes in concise English language. You're always certain and you don't guess. " \
                            + "You are never confused or distracted by semblance. You state facts. Refer to a person using gendered pronouns like she/he. " \
                            + "Don't format your response into numered lists or bullet points."

    inferPrompt             = "Describe the image in detail."
    inferTagThreshold       = 0.4
    
    # Batch
    batchTemplate           = "{{?caption.caption}}\n{{?tags}}"

    # Window state
    windowStates            = dict()


    @classmethod
    def load(cls):
        import json, os, sys
        if os.path.exists(cls.pathConfig):
            with open(cls.pathConfig, 'r') as file:
                data = json.load(file)
        else:
            data = dict()

        cls.pathExport            = data.get("path_export", cls.pathExport)

        cls.viewZoomFactor        = float(data.get("view_zoom_factor", cls.viewZoomFactor))
        cls.viewZoomMinimum       = float(data.get("view_zoom_minimum", cls.viewZoomMinimum))

        cls.slideshowInterval     = float(data.get("slideshow_interval", cls.slideshowInterval))
        cls.slideshowShuffle      = bool(data.get("slideshow_shuffle", cls.slideshowShuffle))

        cls.cropSizePresets       = data.get("crop_size_presets", cls.cropSizePresets)
        cls.cropSelectionChange   = float(data.get("crop_selection_change", cls.cropSelectionChange))

        cls.inferCaptionModelPath = data.get("infer_caption_model_path", cls.inferCaptionModelPath)
        cls.inferCaptionClipPath  = data.get("infer_caption_clip_path", cls.inferCaptionClipPath)
        cls.inferTagModelPath     = data.get("infer_tag_model_path", cls.inferTagModelPath)

        cls.inferSystemPrompt     = data.get("infer_system_prompt", cls.inferSystemPrompt)
        cls.inferPrompt           = data.get("infer_prompt", cls.inferPrompt)
        cls.inferTagThreshold     = float(data.get("infer_tag_threshold", cls.inferTagThreshold))

        cls.batchTemplate         = data.get("batch_template", cls.batchTemplate)

        cls.windowStates          = data.get("window_states", dict())


    @classmethod
    def save(cls):
        import json
        data = dict()
        data["path_export"]                 = cls.pathExport

        data["view_zoom_factor"]            = cls.viewZoomFactor
        data["view_zoom_minimum"]           = cls.viewZoomMinimum

        data["slideshow_interval"]          = cls.slideshowInterval
        data["slideshow_shuffle"]           = cls.slideshowShuffle

        data["crop_size_presets"]           = cls.cropSizePresets
        data["crop_selection_change"]       = cls.cropSelectionChange

        data["infer_caption_model_path"]    = cls.inferCaptionModelPath
        data["infer_caption_clip_path"]     = cls.inferCaptionClipPath
        data["infer_tag_model_path"]        = cls.inferTagModelPath

        data["infer_system_prompt"]         = cls.inferSystemPrompt
        data["infer_prompt"]                = cls.inferPrompt
        data["infer_tag_threshold"]         = cls.inferTagThreshold

        data["batch_template"]              = cls.batchTemplate

        data["window_states"]               = cls.windowStates

        with open(cls.pathConfig, 'w') as file:
            json.dump(data, file, indent=4)
