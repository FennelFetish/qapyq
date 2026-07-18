# Can't name this file 'tokenize.py' - it leads to "AttributeError: module 'tokenize' has no attribute 'open'"
# https://github.com/pytorch/text/issues/348

from transformers import CLIPTokenizerFast


class Tokens:
    MAX_LENGTH =  2**31

    def __init__(self, config: dict):
        self.tokenizer: CLIPTokenizerFast = CLIPTokenizerFast.from_pretrained(config["model_path"])
        self.chunkSize = config.get("chunk_size", 75)

        # CLIP's '</w>' at the end of words is needed. Without it, the results are wrong.
        #self.tokenizer.backend_tokenizer.model.end_of_word_suffix = ""


    def setConfig(self, config: dict):
        pass


    def getTokens(self, text: str) -> list[str]:
        return self.tokenizer.tokenize(text, add_special_tokens=False, max_length=self.MAX_LENGTH, truncation=False)

    def getTokenIds(self, text: str) -> list[int]:
        result = self.tokenizer(text, add_special_tokens=False, return_attention_mask=False, max_length=self.MAX_LENGTH, truncation=False)
        return result["input_ids"]

    def getNumTokens(self, text: str) -> int:
        return len(self.getTokens(text))


    def countWithChunkBorders(self, text: str) -> tuple[int, list[int]]:
        lines = text.lower().split("\n")
        borders: list[int] = []
        totalTokens = 0

        offset = 0
        for line in lines:
            if offset > 0:
                borders.append(offset)

            totalTokens += self._getLineChunkBorder(line, borders, offset)
            offset += len(line) + 1

        return totalTokens, borders


    def _getLineChunkBorder(self, line: str, borders: list[int], offset: int) -> int:
        tokens = self.getTokens(line)
        totalTokens = len(tokens)
        if totalTokens < self.chunkSize:
            return totalTokens

        pos = 0
        nextBorder = self.chunkSize
        for i, tok in enumerate(tokens, start=1):
            tok = tok.removesuffix("</w>")

            lineLen = len(line)
            line = line.lstrip()
            pos += lineLen - len(line)

            if line.startswith(tok):
                pos += len(tok)
                line = line[len(tok):]
            else:
                print(f"WARNING: Text doesn't continue with token '{tok}': '{line}'")
                break

            if i >= nextBorder:
                nextBorder += self.chunkSize
                borders.append(pos + offset)

        return totalTokens
