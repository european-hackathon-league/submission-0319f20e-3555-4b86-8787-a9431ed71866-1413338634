class EvidenceError(Exception):
    """A public, sanitized error; never attach provider bodies or credentials."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")
