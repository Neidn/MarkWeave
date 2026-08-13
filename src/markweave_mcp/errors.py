"""Error taxonomy. Each maps to a distinct message returned to the MCP client."""


class MarkWeaveError(Exception):
    """Base for every error MarkWeave reports to a client."""


class PathOutsideVault(MarkWeaveError):
    """Path escaped the vault root, was absolute, or was empty."""


class NotMarkdown(MarkWeaveError):
    """Path did not end in .md."""


class NoteNotFound(MarkWeaveError):
    """No note exists at the requested path."""


class NoteExists(MarkWeaveError):
    """create_note target already exists."""


class ShaMismatch(MarkWeaveError):
    """expected_sha256 did not match the file on disk; nothing was written."""


class FileTooLarge(MarkWeaveError):
    """File or payload exceeded the configured byte limit."""


class GraphUnavailable(MarkWeaveError):
    """Graph file is missing or unreadable."""


class GraphTimeout(MarkWeaveError):
    """graphify did not finish within the configured timeout."""
