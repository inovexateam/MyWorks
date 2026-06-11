from dataclasses import dataclass, field
from enum import Enum


class DocStyle(str, Enum):
    XML_DOC   = "xml_doc"      # C# /// <summary>
    JAVADOC   = "javadoc"      # Java /** @param */
    JSDOC     = "jsdoc"        # TypeScript /** */
    GOOGLE    = "google"       # Python Google style
    NUMPY     = "numpy"        # Python NumPy style


@dataclass
class MissingDoc:
    """A symbol that has no or incomplete documentation."""
    name:        str
    kind:        str       # 'method', 'class', 'function', 'property'
    file:        str
    line:        int
    language:    str
    signature:   str       # full signature text for AI context
    body_snippet: str      # first ~10 lines of body for context
    class_context: str     # containing class name
    has_partial: bool = False  # has some doc but missing params/returns
    existing_doc: str = ""

    def id(self) -> str:
        import hashlib
        return hashlib.sha1(f"{self.file}:{self.line}:{self.name}".encode()).hexdigest()[:10]


@dataclass
class GeneratedDoc:
    """AI-generated docstring for one symbol."""
    symbol:      MissingDoc
    docstring:   str        # the generated text (style-formatted)
    confidence:  float      # 0–1, based on how much context was available
    style:       DocStyle
    tokens_used: int = 0

    def patch(self) -> str:
        """Return file content with docstring inserted."""
        return self.docstring
