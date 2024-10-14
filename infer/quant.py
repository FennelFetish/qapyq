class Quantization:
    def __init__(self):
        pass

    @classmethod
    def getQuantConfig(cls, mode: str, cpuOffloadEnabled=False):
        match mode:
            case "nf4":
                return cls.bnb_nf4(cpuOffloadEnabled)
            case "int8":
                return cls.bnb_int8(cpuOffloadEnabled)
        return None

    @staticmethod
    def bnb_nf4(cpuOffloadEnabled=False):
        from transformers import BitsAndBytesConfig
        import torch

        quantConf = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            #bnb_4bit_compute_dtype=torch.quint4x2,
            #load_in_8bit_fp32_cpu_offload=True
        )

        if cpuOffloadEnabled:
            quantConf.llm_int8_enable_fp32_cpu_offload = True
        return quantConf
    

    # /mnt/firlefanz/dev-Tools/pyImgSet/venv/lib/python3.10/site-packages/bitsandbytes/autograd/_functions.py:316: 
    #   UserWarning: MatMul8bitLt: inputs will be cast from torch.bfloat16 to float16 during quantization
    @staticmethod
    def bnb_int8(cpuOffloadEnabled=False):
        from transformers import BitsAndBytesConfig

        quantConf = BitsAndBytesConfig(
            load_in_8bit=True,
            #load_in_8bit_fp32_cpu_offload=True
            #llm_int8_enable_fp32_cpu_offload=True
        )

        if cpuOffloadEnabled:
            quantConf.llm_int8_enable_fp32_cpu_offload = True
        return quantConf


    # @staticmethod
    # def awq8():
    #     from transformers import AwqConfig
    #     return AwqConfig(8, pre_quantized=True)

    # RuntimeError: We can only quantize pure text model.
    # @staticmethod
    # def gptq8():
    #     from transformers import GPTQConfig
    #     return GPTQConfig(8)
