import sys
from host.protocol import Protocol
from host.service_inference import InferenceService
from config import Config


def mainInference() -> int:
    sys.stderr.reconfigure(line_buffering=True)

    # Send data through original stdout, redirect stdout to stderr for logging
    protocol = Protocol(InferenceService.ID.INFERENCE, sys.stdin.buffer, sys.stdout.buffer)
    sys.stdout = sys.stderr

    if not Config.load():
        return 1

    print("Inference subprocess started")
    service = InferenceService(protocol)
    service.loop()
    print("Inference subprocess ending")
    return 0


if __name__ == "__main__":
    sys.exit( mainInference() )
