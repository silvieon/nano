from dataclasses import dataclass
from enum import StrEnum

from .models import ExecutionGraph


class SemanticVerdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


class SemanticIssueCode(StrEnum):
    UNRELATED_OPERATION = "UNRELATED_OPERATION"
    MISSING_REQUIRED_OPERATION = "MISSING_REQUIRED_OPERATION"
    INCORRECT_OPERATION = "INCORRECT_OPERATION"
    INCORRECT_DATAFLOW = "INCORRECT_DATAFLOW"
    UNJUSTIFIED_DEPENDENCY = "UNJUSTIFIED_DEPENDENCY"
    MISSING_DEPENDENCY = "MISSING_DEPENDENCY"
    MISINTERPRETED_REQUEST = "MISINTERPRETED_REQUEST"
    INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"


@dataclass(frozen=True)
class SemanticIssue:
    code: SemanticIssueCode
    message: str
    node_id: str | None = None


@dataclass(frozen=True)
class SemanticJudgment:
    verdict: SemanticVerdict
    issues: tuple[SemanticIssue, ...] = ()


def validate_semantic_judgment(
    judgment: SemanticJudgment,
) -> SemanticJudgment:
    """
    Validate the semantic judge's own output.

    This layer deliberately does not attempt to determine whether the
    judge's claims are correct. It only guarantees that the judge
    returned a well-formed verdict.
    """

    if judgment.verdict == SemanticVerdict.PASS:
        if judgment.issues:
            raise ValueError(
                "semantic PASS must not contain issues"
            )

    elif judgment.verdict == SemanticVerdict.UNKNOWN:
        if not judgment.issues:
            raise ValueError(
                "semantic UNKNOWN must explain why judgment "
                "could not be established"
            )

    elif judgment.verdict == SemanticVerdict.FAIL:
        if not judgment.issues:
            raise ValueError(
                "semantic FAIL must contain at least one issue"
            )

    return judgment