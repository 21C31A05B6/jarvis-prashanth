"""Standardized tool execution result and error classification.

Provides structured results for every JARVIS action, eliminating fake success
messages and ensuring verification across all tools.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ErrorCategory(str, Enum):
    """Categorized error reasons required by JARVIS architecture."""
    COMMAND_UNDERSTOOD_TOOL_UNAVAILABLE = "A_tool_unavailable"
    TOOL_EXECUTION_FAILED              = "B_tool_execution_failed"
    OS_PERMISSION_DENIED               = "C_os_permission_denied"
    APP_PERMISSION_DENIED              = "D_app_permission_denied"
    BROWSER_AUTH_REQUIRED              = "E_browser_auth_required"
    CAPTCHA_OR_MFA_REQUIRED            = "F_captcha_or_mfa_required"
    USER_CONFIRMATION_REQUIRED         = "G_user_confirmation_required"
    FILE_NOT_FOUND                     = "H_file_not_found"
    APP_NOT_FOUND                      = "I_app_not_found"
    TEMPORARY_FAILURE                  = "J_temporary_failure"
    NETWORK_FAILURE                    = "K_network_failure"
    TOOL_TIMEOUT                       = "L_tool_timeout"
    UNKNOWN_FAILURE                    = "M_unknown_failure"


@dataclass
class ToolResult:
    """Standardized response from any tool invocation."""
    success: bool
    status: str = "completed"  # completed | failed | waiting_for_user | running
    result: str = ""
    data: Any = None
    error_type: str | None = None
    error_message: str | None = None
    retryable: bool = False
    requires_user_action: bool = False
    next_action: str | None = None
    artifacts: list[str] = field(default_factory=list)
    verification: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "status": self.status,
            "result": self.result,
            "data": self.data,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "retryable": self.retryable,
            "requires_user_action": self.requires_user_action,
            "next_action": self.next_action,
            "artifacts": self.artifacts,
            "verification": self.verification,
        }

    def __str__(self) -> str:
        if self.success:
            return self.result or "Action completed successfully."
        err = self.error_message or self.result or "Action failed."
        cat = f" [{self.error_type}]" if self.error_type else ""
        return f"Failed{cat}: {err}"

    @classmethod
    def ok(
        cls,
        result: str,
        data: Any = None,
        artifacts: list[str] | None = None,
        verification: dict[str, Any] | None = None,
        next_action: str | None = None,
    ) -> ToolResult:
        return cls(
            success=True,
            status="completed",
            result=result,
            data=data,
            artifacts=artifacts or [],
            verification=verification or {"verified": True},
            next_action=next_action,
        )

    @classmethod
    def fail(
        cls,
        error_message: str,
        error_type: ErrorCategory | str = ErrorCategory.TOOL_EXECUTION_FAILED,
        retryable: bool = False,
        requires_user_action: bool = False,
        next_action: str | None = None,
        data: Any = None,
    ) -> ToolResult:
        err_type_str = error_type.value if isinstance(error_type, ErrorCategory) else str(error_type)
        return cls(
            success=False,
            status="waiting_for_user" if requires_user_action else "failed",
            result=error_message,
            error_type=err_type_str,
            error_message=error_message,
            retryable=retryable,
            requires_user_action=requires_user_action,
            next_action=next_action,
            data=data,
            verification={"verified": False, "reason": error_message},
        )

    @classmethod
    def waiting_for_user(
        cls,
        prompt: str,
        error_type: ErrorCategory = ErrorCategory.USER_CONFIRMATION_REQUIRED,
        next_action: str | None = None,
    ) -> ToolResult:
        return cls(
            success=False,
            status="waiting_for_user",
            result=prompt,
            error_type=error_type.value,
            error_message=prompt,
            retryable=True,
            requires_user_action=True,
            next_action=next_action,
            verification={"waiting_for_user": True},
        )


def coerce_tool_result(raw: Any) -> ToolResult:
    """Convert arbitrary tool return values into a structured ToolResult."""
    if isinstance(raw, ToolResult):
        return raw

    if isinstance(raw, dict):
        if "success" in raw:
            return ToolResult(
                success=bool(raw.get("success")),
                status=str(raw.get("status", "completed" if raw.get("success") else "failed")),
                result=str(raw.get("result", "")),
                data=raw.get("data"),
                error_type=raw.get("error_type"),
                error_message=raw.get("error_message"),
                retryable=bool(raw.get("retryable", False)),
                requires_user_action=bool(raw.get("requires_user_action", False)),
                next_action=raw.get("next_action"),
                artifacts=list(raw.get("artifacts") or []),
                verification=dict(raw.get("verification") or {}),
            )

    text = str(raw or "").strip()
    lowered = text.lower()

    # Detect explicit failure strings that older tools might return
    failure_patterns = [
        ("access denied", ErrorCategory.OS_PERMISSION_DENIED),
        ("permission denied", ErrorCategory.OS_PERMISSION_DENIED),
        ("not found", ErrorCategory.FILE_NOT_FOUND),
        ("could not find", ErrorCategory.FILE_NOT_FOUND),
        ("timed out", ErrorCategory.TOOL_TIMEOUT),
        ("timeout", ErrorCategory.TOOL_TIMEOUT),
        ("element not found", ErrorCategory.TOOL_EXECUTION_FAILED),
        ("browser error", ErrorCategory.TOOL_EXECUTION_FAILED),
        ("execution error", ErrorCategory.TOOL_EXECUTION_FAILED),
        ("failed to", ErrorCategory.TOOL_EXECUTION_FAILED),
        ("error:", ErrorCategory.TOOL_EXECUTION_FAILED),
    ]

    for pattern, cat in failure_patterns:
        if pattern in lowered:
            return ToolResult.fail(
                error_message=text,
                error_type=cat,
                retryable=(cat in (ErrorCategory.TOOL_TIMEOUT, ErrorCategory.TEMPORARY_FAILURE)),
            )

    return ToolResult.ok(result=text or "Done.")
