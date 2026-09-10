"""Plugin permission system.

Each action in a plugin declares the permissions it needs (e.g., NETWORK,
LOCAL_WRITE, SENSITIVE). This module enforces those permissions by checking
against user settings, environment, and QA mode.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from core.plugin_manifest import PermissionLevel, PluginManifest, ActionSchema


@dataclass
class PermissionDecision:
    """Result of a permission check."""
    allowed: bool
    reason: str  # human-readable explanation


class PluginPermissionGuard:
    """Evaluates whether a plugin action is allowed to run."""

    def __init__(self, qa_mode: bool = False, sandbox_mode: bool = False):
        self.qa_mode = qa_mode
        self.sandbox_mode = sandbox_mode
        # User-configured permission overrides per plugin
        self._permission_overrides: dict[str, set[PermissionLevel]] = {}

    def check_action(
        self,
        plugin_name: str,
        action_name: str,
        action: ActionSchema,
        plugin_manifest: PluginManifest,
    ) -> PermissionDecision:
        """Determine if a plugin action is allowed to run."""

        # Check each permission the action declares
        for perm in action.permissions:
            decision = self._check_single_permission(plugin_name, perm, plugin_manifest)
            if not decision.allowed:
                return decision

        return PermissionDecision(allowed=True, reason=f"Action '{action_name}' is allowed.")

    def _check_single_permission(
        self, plugin_name: str, perm: PermissionLevel, manifest: PluginManifest
    ) -> PermissionDecision:
        """Check a single permission level."""

        # Check if user has explicitly allowed this plugin+permission
        if self._is_user_allowed(plugin_name, perm):
            return PermissionDecision(allowed=True, reason=f"User allowed {perm.value} for {plugin_name}.")

        # QA mode: restrict writing actions
        if self.qa_mode:
            if perm in (PermissionLevel.LOCAL_WRITE, PermissionLevel.LOCAL_EXEC, PermissionLevel.LOCAL_READ):
                return PermissionDecision(
                    allowed=False,
                    reason=f"QA mode blocks {perm.value} permissions. Set JARVIS_QA_ALLOW_PLUGINS=1 to override.",
                )
            if perm == PermissionLevel.NETWORK:
                return PermissionDecision(
                    allowed=False,
                    reason=f"QA mode blocks {perm.value} permissions. Set JARVIS_QA_ALLOW_PLUGINS=1 to override.",
                )

        # Sandbox mode: restrict all non-safe actions
        if self.sandbox_mode:
            if perm != PermissionLevel.SAFE:
                return PermissionDecision(
                    allowed=False,
                    reason=f"Sandbox mode only allows {PermissionLevel.SAFE.value} actions. "
                    f"{perm.value} requires sandbox_mode=False.",
                )

        # SENSITIVE is never auto-allowed without explicit user approval
        if perm == PermissionLevel.SENSITIVE:
            return PermissionDecision(
                allowed=False,
                reason=f"Action requires {PermissionLevel.SENSITIVE.value} permissions (access to passwords/keychain). "
                f"User must explicitly approve this plugin.",
            )

        # By default, allow SAFE, NETWORK, LOCAL_WRITE, LOCAL_EXEC (respecting QA/sandbox above)
        return PermissionDecision(allowed=True, reason=f"Permission {perm.value} is granted by default.")

    def set_plugin_permission(self, plugin_name: str, perm: PermissionLevel, allow: bool) -> None:
        """Explicitly allow/deny a permission for a plugin."""
        if plugin_name not in self._permission_overrides:
            self._permission_overrides[plugin_name] = set()
        if allow:
            self._permission_overrides[plugin_name].add(perm)
        else:
            self._permission_overrides[plugin_name].discard(perm)

    def _is_user_allowed(self, plugin_name: str, perm: PermissionLevel) -> bool:
        """Check if user has allowed this permission for this plugin."""
        return perm in self._permission_overrides.get(plugin_name, set())

    def list_required_permissions(self, manifest: PluginManifest) -> set[PermissionLevel]:
        """Return the union of all permissions across all actions in the plugin."""
        required = set()
        for action in manifest.actions:
            required.update(action.permissions)
        return required


# Global permission guard instance (initialized in main.py)
_permission_guard: Optional[PluginPermissionGuard] = None


def get_permission_guard() -> PluginPermissionGuard:
    """Return the global permission guard."""
    global _permission_guard
    if _permission_guard is None:
        _permission_guard = PluginPermissionGuard()
    return _permission_guard


def set_permission_guard(guard: PluginPermissionGuard) -> None:
    """Set the global permission guard (used in tests and initialization)."""
    global _permission_guard
    _permission_guard = guard
