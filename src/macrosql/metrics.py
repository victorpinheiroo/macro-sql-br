"""Metric catalog: each metric is defined once in metrics/*.yml and validated here."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, model_validator

Aggregation = Literal["compound", "sum", "last", "avg"]
Frequency = Literal["daily", "monthly", "quarterly"]


class Source(BaseModel):
    system: Literal["bcb_sgs", "ibge_sidra", "tesouro"]
    series_id: int


class Derived(BaseModel):
    inputs: list[str]
    formula: str


class Plausibility(BaseModel):
    min: float
    max: float


class Metric(BaseModel):
    name: str
    label: str
    description: str
    frequency: Frequency
    unit: str
    source: Source | None = None
    aggregation: Aggregation | None = None
    derived: Derived | None = None
    plausibility: Plausibility | None = None

    @model_validator(mode="after")
    def _base_or_derived(self) -> Metric:
        if (self.source is None) == (self.derived is None):
            raise ValueError(f"{self.name}: define exactly one of 'source' or 'derived'")
        if self.source is not None and self.aggregation is None:
            raise ValueError(f"{self.name}: base metrics need an 'aggregation' rule")
        return self


class Catalog(BaseModel):
    metrics: dict[str, Metric]

    def get(self, name: str) -> Metric:
        if name not in self.metrics:
            raise KeyError(f"unknown metric '{name}'. Known: {sorted(self.metrics)}")
        return self.metrics[name]

    @model_validator(mode="after")
    def _derived_inputs_exist(self) -> Catalog:
        for m in self.metrics.values():
            if m.derived:
                for dep in m.derived.inputs:
                    if dep not in self.metrics:
                        raise ValueError(f"{m.name}: input '{dep}' is not in the catalog")
                    if self.metrics[dep].frequency != m.frequency:
                        raise ValueError(
                            f"{m.name}: input '{dep}' is {self.metrics[dep].frequency}, "
                            f"metric is {m.frequency}; add an alignment rule first"
                        )
        return self


def load_catalog(directory: Path | str) -> Catalog:
    metrics = {}
    for path in sorted(Path(directory).glob("*.yml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        metric = Metric.model_validate(data)
        if metric.name != path.stem:
            raise ValueError(f"{path.name}: name '{metric.name}' must match file name")
        metrics[metric.name] = metric
    return Catalog(metrics=metrics)
