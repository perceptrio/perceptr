"""
Utility functions and helpers
"""

from enum import Enum
from typing import List, Optional, Type

from common.enums import IntervalCategory, IntervalSeverity, IssueSortBy
from fastapi import Query


def str_to_enum(enum_type: Type[Enum], value: str) -> Enum:
    return enum_type(value)


def comma_separated_enum_list(
    enum_type: Type[Enum], value: Optional[str] = Query(None)
) -> Optional[List[Enum]]:
    if value is None:
        return None
    return [enum_type(item) for item in value.split(",") if item]


def get_issues_sort_by(
    sort_by: Optional[str] = Query(
        None, description="Sort by (e.g. latest, oldest, most_affected, least_affected)"
    )
) -> IssueSortBy:
    if sort_by is None:
        return IssueSortBy.LATEST
    return str_to_enum(IssueSortBy, sort_by)


def get_issues_severities(
    severities: Optional[str] = Query(
        None, description="Comma-separated list of severities (e.g. HIGH,MEDIUM)"
    )
) -> Optional[List[IntervalSeverity]]:
    return comma_separated_enum_list(IntervalSeverity, severities)


def get_issues_categories(
    categories: Optional[str] = Query(
        None,
        description="Comma-separated list of categories (e.g. NORMAL,BUG,USABILITY_ISSUE,PERFORMANCE_ISSUE,ENHANCEMENT)",
    )
) -> Optional[List[IntervalCategory]]:
    return comma_separated_enum_list(IntervalCategory, categories)
