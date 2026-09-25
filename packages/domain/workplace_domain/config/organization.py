"""Schema for config/organization.yaml: departments, teams, names and work patterns."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from workplace_domain.enums import EmploymentType

Probability = Annotated[float, Field(ge=0.0, le=1.0)]
PositiveInt = Annotated[int, Field(gt=0)]
WORKDAYS = ("MON", "TUE", "WED", "THU", "FRI")
_TOLERANCE = 1e-6


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DepartmentSpec(_Strict):
    code: Annotated[str, Field(pattern=r"^[A-Z]{2,4}$")]
    name: str
    share: Annotated[float, Field(gt=0, le=1)]
    lead_role: str
    roles: list[str] = Field(min_length=1)


class TeamSizeSpec(_Strict):
    min: PositiveInt
    mean: PositiveInt
    max: PositiveInt

    @model_validator(mode="after")
    def _ordered(self) -> TeamSizeSpec:
        if not self.min <= self.mean <= self.max:
            raise ValueError("team_size must satisfy min <= mean <= max")
        return self


class OfficeDaysSpec(_Strict):
    count_min: Annotated[int, Field(ge=1, le=5)]
    count_max: Annotated[int, Field(ge=1, le=5)]
    weekday_weights: dict[str, Annotated[float, Field(gt=0)]]

    @model_validator(mode="after")
    def _valid(self) -> OfficeDaysSpec:
        if self.count_min > self.count_max:
            raise ValueError("office_days.count_min must be <= count_max")
        if set(self.weekday_weights) != set(WORKDAYS):
            raise ValueError(f"office_days.weekday_weights must have exactly {list(WORKDAYS)}")
        return self


class WorkPatternSpec(_Strict):
    hybrid_office_on_team_day: Probability
    hybrid_remote_on_other_day: Probability


class DateRange(_Strict):
    start: date
    end: date

    @model_validator(mode="after")
    def _ordered(self) -> DateRange:
        if self.start > self.end:
            raise ValueError("date range start must be <= end")
        return self


class OrganizationConfig(_Strict):
    org_id: Annotated[str, Field(pattern=r"^ORG\d{2}$")]
    name: str
    email_domain: str
    departments: list[DepartmentSpec] = Field(min_length=1)
    team_size: TeamSizeSpec
    team_names: list[str] = Field(min_length=1)
    office_days: OfficeDaysSpec
    work_pattern: WorkPatternSpec
    employment_type_mix: dict[EmploymentType, float]
    hire_date_range: DateRange
    first_names: list[str] = Field(min_length=10)
    last_names: list[str] = Field(min_length=10)

    @field_validator("departments")
    @classmethod
    def _departments_valid(cls, v: list[DepartmentSpec]) -> list[DepartmentSpec]:
        codes = [d.code for d in v]
        if len(set(codes)) != len(codes):
            raise ValueError("department codes must be unique")
        total = sum(d.share for d in v)
        if abs(total - 1.0) > _TOLERANCE:
            raise ValueError(f"department shares must sum to 1.0 (got {total:.4f})")
        return v

    @field_validator("employment_type_mix")
    @classmethod
    def _mix_sums_to_one(cls, v: dict[EmploymentType, float]) -> dict[EmploymentType, float]:
        total = sum(v.values())
        if abs(total - 1.0) > _TOLERANCE or any(s < 0 for s in v.values()):
            raise ValueError(f"employment_type_mix must be non-negative and sum to 1.0 ({total})")
        return v

    @field_validator("team_names")
    @classmethod
    def _unique_team_names(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("team_names must be unique")
        return v
