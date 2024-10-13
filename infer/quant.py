class Quantization:
    def __init__(self):
        pass

    @classmethod
    def getQuantConfig(cls, mode: str):
        match mode:
            case "nf4":
                return cls.bnb_nf4()
            case "int8":
                return cls.bnb_int8()
        return None

    @staticmethod
    def bnb_nf4():
        from transformers import BitsAndBytesConfig
        import torch

        quant_conf = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
            #bnb_4bit_compute_dtype=torch.quint4x2,
            bnb_4bit_quant_type="nf4",
            #load_in_8bit_fp32_cpu_offload=True
            llm_int8_enable_fp32_cpu_offload=True
        )
        return quant_conf
    

    # /mnt/firlefanz/dev-Tools/pyImgSet/venv/lib/python3.10/site-packages/bitsandbytes/autograd/_functions.py:316: 
    #   UserWarning: MatMul8bitLt: inputs will be cast from torch.bfloat16 to float16 during quantization
    @staticmethod
    def bnb_int8():
        from transformers import BitsAndBytesConfig

        quant_conf = BitsAndBytesConfig(
            load_in_8bit=True,
            #load_in_8bit_fp32_cpu_offload=True
            #llm_int8_enable_fp32_cpu_offload=True
        )
        return quant_conf
