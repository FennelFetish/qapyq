import time, json, traceback
from abc import abstractmethod
from typing_extensions import override
from host.imagecache import ImageFile
from infer.caption.llamacpp import LlamaCppVisionBackend


class LlamaCppDetectBackend(LlamaCppVisionBackend):
    @override
    def setConfig(self, config: dict):
        super().setConfig(config)
        self.config["max_tokens"] = 2000
        self.config["temperature"] = 0.0
        self.config["top_p"] = 0.2
        self.config["min_p"] = 0.0
        self.config["top_k"] = 5
        self.config["repeat_penalty"] = 1.0
        self.config["present_penalty"] = 0.0


    def detectBoxes(self, imgFile: ImageFile, classes: list[str]) -> list[dict]:
        try:
            self._imgBytes = self._loadMedia(imgFile)
            messages = self._getDetectMessages(classes)

            t = time.monotonic_ns()

            completion = self.llm.create_chat_completion(
                messages,
                stop=self.stop,
                **self.config
            )

            self._printSpeed(t, completion["usage"]["completion_tokens"])

            msg = completion["choices"][0]["message"]
            answer: str = msg["content"]

            try:
                return self._parseBoxes(answer)
            except Exception as ex:
                print("Warning: Failed to parse detection result:")
                print(answer)
                traceback.print_exc()
                raise ValueError(f"Failed to parse detection result: {ex}") from None
        finally:
            self._imgBytes.clear()

    def getClassNames(self):
        raise NotImplementedError("This backend has no default classes. Use any prompt.")


    @abstractmethod
    def _getDetectMessages(self, classes: list[str]) -> list[dict]:
        raise NotImplementedError()

    @abstractmethod
    def _parseBoxes(self, answer: str) -> list[dict]:
        raise NotImplementedError()



class Qwen35DetectBackend(LlamaCppDetectBackend):
    SYSPROMPT = "You are a precise visual grounding assistant."
    PROMPT    = 'Locate every instance that belongs to the following categories: {{classes}}\n\n' \
                'For each instance, report bbox coordinates in JSON format like this: {"bbox_2d": [x1, y1, x2, y2], "label": "category"}'
    PREFILL   = "```json\n["


    @override
    def _getDetectMessages(self, classes: list[str]) -> list[dict]:
        classesStr = ", ".join(f'"{c}"' for c in classes)
        prompt = self.PROMPT.replace("{{classes}}", classesStr)
        return [
            {"role": "system", "content": self.SYSPROMPT},
            {"role": "user", "content": self._getUserContent(prompt, 0)},
            {"role": "assistant", "content": self.PREFILL},
        ]

    @override
    def _parseBoxes(self, answer: str) -> list[dict]:
        results = []
        listEnd = answer.rfind("]")
        if listEnd < 0:
            return results

        answer = "[" + answer[:listEnd+1].replace("'", '"')
        detections: list[dict] = json.loads(answer)

        for det in detections:
            coords: list[int] = det["bbox_2d"]
            label: str        = det["label"]

            p0x, p0y, p1x, p1y = coords
            results.append({
                "name": label,
                "confidence": 1.0,
                "p0": self._normalizePoint(p0x, p0y),
                "p1": self._normalizePoint(p1x, p1y)
            })

        return results

    @staticmethod
    def _normalizePoint(x: int, y: int) -> tuple[float, float]:
        return (x/999, y/999)
