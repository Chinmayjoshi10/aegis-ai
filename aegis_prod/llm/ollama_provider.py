import subprocess, os, sys

class OllamaProvider:
    def __init__(self, model=None):
        self.model = model or os.getenv("AEGIS_OLLAMA_MODEL", "llama3")

    def generate(self, prompt: str, timeout: int = 120) -> str:
        try:
            proc = subprocess.Popen(
                ["ollama", "run", self.model],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            out, err = proc.communicate(prompt.encode("utf-8"), timeout=timeout)

            if proc.returncode != 0:
                raise RuntimeError(err.decode("utf-8", errors="ignore"))

            return out.decode("utf-8", errors="ignore").strip()

        except subprocess.TimeoutExpired:
            proc.kill()
            raise RuntimeError("OllamaProvider: timeout expired")
