class Config:
    version                 = "1.0"
    windowTitle             = "qapyq"
    windowIcon              = "res/qapyq.png"

    # Paths
    pathConfig              = "./qapyq_config.json"
    pathExport              = "."
    pathDebugLoad           = ""

    # View
    viewZoomFactor          = 1.15
    viewZoomMinimum         = 0.5

    # Slideshow
    slideshowInterval       = 4.0
    slideshowShuffle        = False
    slideshowFade           = True

    # Crop
    cropSizePresets         = ["512x512", "512x768", "768x768", "768x1152", "1024x1024", "1024x1536"]
    cropSizeStep            = 64
    cropWheelStep           = 0.02

    # Mask
    maskSuffix              = "-masklabel"
    maskHistorySize         = 20

    # Prompts
    promptCaptionPresets    = dict()
    promptCaptionDefault    = {
        "system_prompt":
            "You are an assistant that describes scenes in detailed, vivid but concise English prose. Write simple, clear sentences and avoid ambiguity.\n"
            "No relative clauses. Don't use pronouns to refer to elements: Repeat the object names if needed.\n"
            "No formatting, no bullet points. No fill words, no embellishment, no juxtaposition. Focus on the observable, no interpretations, no speculation.\n"
            "Describe all elements while maintaining a logical flow from main subject to background: Start with the primary focal point, describe its details, then move to secondary elements in order of prominence.\n"
            "The description is intended as caption for AI training.\n",
        "prompts": "Describe the image in detail. Begin your answer directly with the subject without writing 'The subject', without 'The image', etc."
    }

    promptLLMPresets        = dict()
    promptLLMDefault        = {
        "system_prompt":
            "Your task is to summarize image captions. I will provide multiple descriptions of the same image separated by a line with dash. "
            "I will also include a list of booru tags that accurately categorize the image. "
            "Use your full knowledge about booru tags and use them to inform your summary.\n\n"
            \
            "You will summarize my descriptions and condense all provided information into one paragraph. "
            "The resulting description must encompass all the details provided in my original input. "
            "You may rephrase my input, but never invent anything new. Your output will never contain new information.",
        "prompts":
            "{{captions.caption}}\n-\n"
            "{{captions.caption_round2}}\n-\n"
            "{{captions.caption_round3}}\n-\n"
            "{{tags.tags}}"
    }

    sysPromptFallbackTemplate = "# System Instructions:\n{{systemPrompt}}\n\n# Prompt:\n{{prompt}}"

    # Inference
    inferCaptionPresets     = dict()
    inferLLMPresets         = dict()
    inferTagPresets         = dict()
    inferSelectedPresets    = dict()
    INFER_PRESET_SAMPLECFG_KEY = "sample_config"
    
    # Batch
    batchTemplate           = "{{captions.refined}}\n{{tags.tags}}"

    # Gallery
    galleryThumbnailSize    = 192

    # Window state
    windowStates            = dict()
    windowOpen              = []

    # Misc static
    batchWinLegendWidth     = 130


    @classmethod
    def load(cls):
        import json, os
        if os.path.exists(cls.pathConfig):
            with open(cls.pathConfig, 'r') as file:
                data = json.load(file)
        else:
            data = dict()

        cls.pathExport            = data.get("path_export", cls.pathExport)
        cls.pathDebugLoad         = data.get("path_debug_load", cls.pathDebugLoad)

        cls.viewZoomFactor        = float(data.get("view_zoom_factor", cls.viewZoomFactor))
        cls.viewZoomMinimum       = float(data.get("view_zoom_minimum", cls.viewZoomMinimum))

        cls.slideshowInterval     = float(data.get("slideshow_interval", cls.slideshowInterval))
        cls.slideshowShuffle      = bool(data.get("slideshow_shuffle", cls.slideshowShuffle))
        cls.slideshowFade         = bool(data.get("slideshow_fade", cls.slideshowFade))

        cls.cropSizePresets       = data.get("crop_size_presets", cls.cropSizePresets)
        cls.cropSizeStep          = int(data.get("crop_size_step", cls.cropSizeStep))
        cls.cropWheelStep         = float(data.get("crop_wheel_step", cls.cropWheelStep))

        cls.maskSuffix            = data.get("mask_suffix", cls.maskSuffix)
        cls.maskHistorySize       = int(data.get("mask_history_size", cls.maskHistorySize))

        cls.promptCaptionPresets  = data.get("prompt_caption_presets", cls.promptCaptionPresets)
        cls.promptLLMPresets      = data.get("prompt_llm_presets", cls.promptLLMPresets)
        cls.sysPromptFallbackTemplate = data.get("sys_prompt_fallback_template", cls.sysPromptFallbackTemplate)
        
        cls.inferCaptionPresets   = data.get("infer_caption_presets", cls.inferCaptionPresets)
        cls.inferLLMPresets       = data.get("infer_llm_presets", cls.inferLLMPresets)
        cls.inferTagPresets       = data.get("infer_tag_presets", cls.inferTagPresets)
        cls.inferSelectedPresets  = data.get("infer_selected_presets", cls.inferSelectedPresets)

        cls.batchTemplate         = data.get("batch_template", cls.batchTemplate)

        cls.galleryThumbnailSize  = int(data.get("gallery_thumbnail_size", cls.galleryThumbnailSize))

        cls.windowStates          = data.get("window_states", cls.windowStates)
        cls.windowOpen            = data.get("window_open", cls.windowOpen)


    @classmethod
    def save(cls):
        import json
        data = dict()
        data["version"]                     = cls.version

        data["path_export"]                 = cls.pathExport
        data["path_debug_load"]             = cls.pathDebugLoad

        data["view_zoom_factor"]            = cls.viewZoomFactor
        data["view_zoom_minimum"]           = cls.viewZoomMinimum

        data["slideshow_interval"]          = cls.slideshowInterval
        data["slideshow_shuffle"]           = cls.slideshowShuffle
        data["slideshow_fade"]              = cls.slideshowFade

        data["crop_size_presets"]           = cls.cropSizePresets
        data["crop_size_step"]              = cls.cropSizeStep
        data["crop_wheel_step"]             = cls.cropWheelStep

        data["mask_suffix"]                 = cls.maskSuffix
        data["mask_history_size"]           = cls.maskHistorySize

        data["prompt_caption_presets"]      = cls.promptCaptionPresets
        data["prompt_llm_presets"]          = cls.promptLLMPresets
        data["sys_prompt_fallback_template"] = cls.sysPromptFallbackTemplate

        data["infer_caption_presets"]       = cls.inferCaptionPresets
        data["infer_llm_presets"]           = cls.inferLLMPresets
        data["infer_tag_presets"]           = cls.inferTagPresets
        data["infer_selected_presets"]      = cls.inferSelectedPresets

        data["batch_template"]              = cls.batchTemplate

        data["gallery_thumbnail_size"]      = cls.galleryThumbnailSize

        data["window_states"]               = cls.windowStates
        data["window_open"]                 = cls.windowOpen

        with open(cls.pathConfig, 'w') as file:
            json.dump(data, file, indent=4)
