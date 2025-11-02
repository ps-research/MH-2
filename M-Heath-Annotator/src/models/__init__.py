"""
Data models for mental health annotation system.
"""
from .annotation import (
    AnnotationRequest,
    AnnotationResult,
    MalformError,
    ProgressMetrics
)

__all__ = [
    'AnnotationRequest',
    'AnnotationResult',
    'MalformError',
    'ProgressMetrics'
]
