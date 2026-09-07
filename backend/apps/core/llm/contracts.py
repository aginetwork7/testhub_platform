from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ModelConfig(Protocol):
    model_type: str
    model_name: str
    api_key: str
    base_url: str
    max_tokens: int
    temperature: float
    top_p: float

    def get_model_type_display(self) -> str:
        ...


@dataclass(frozen=True, slots=True)
class LLMCallContext:
    component: str
    operation: str
    execution_id: int | None = None

    def log_prefix(self) -> str:
        parts = [f'component={self.component}', f'operation={self.operation}']
        if self.execution_id is not None:
            parts.append(f'execution_id={self.execution_id}')
        return f"[{' '.join(parts)}]"