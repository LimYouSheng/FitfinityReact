"""Dependencies and mutable evidence owned by one operator invocation."""

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class OperatorContext:
    report: dict = field(default_factory=dict)
    aws_call: Callable | None = None
    write_allowed: bool = False
    reads: set = field(default_factory=set)
    writes: set = field(default_factory=set)
