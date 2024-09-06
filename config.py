class Config:
    # Paths
    pathExport              = "/mnt/ai/Datasets/"

    # View
    viewZoomFactor          = 1.15
    viewZoomMinimum         = 0.5

    # Slideshow
    slideshowInterval       = 4.0
    slideshowShuffle        = False

    # Crop
    cropSizePresets         = ["512x512", "512x768", "768x768", "768x1152", "1024x1024", "1024x1536"]
    cropChangePercentage    = 0.02

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