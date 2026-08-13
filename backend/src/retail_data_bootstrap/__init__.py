"""Pre-embedding Retail 360 data foundation.

This package intentionally has no dependency on the web application or agent
registry. Excel is one source adapter; normalized records, Azure SQL loading,
and semantic document generation are downstream concerns.
"""

from .models import SemanticDocument

__all__ = ["SemanticDocument"]
