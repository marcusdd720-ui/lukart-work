"""Fail-closed Windows DACL verification for trusted HUMAN configuration files."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

_SYSTEM = "S-1-5-18"
_ADMINISTRATORS = "S-1-5-32-544"
_TRUSTED_INSTALLER = "S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464"
_EVERYONE = "S-1-1-0"
_AUTHENTICATED_USERS = "S-1-5-11"
_BUILTIN_USERS = "S-1-5-32-545"
_CREATOR_OWNER = "S-1-3-0"
_OWNER_RIGHTS = "S-1-3-4"
_TRUSTED_WRITERS = frozenset({_SYSTEM, _ADMINISTRATORS, _TRUSTED_INSTALLER})
_REQUIRED_WRITERS = frozenset({_SYSTEM, _ADMINISTRATORS})
_BROAD_DENY = frozenset({_EVERYONE, _AUTHENTICATED_USERS, _BUILTIN_USERS})
_REPARSE_POINT = 0x400
# FILE_WRITE_DATA, APPEND_DATA, WRITE_EA, WRITE_ATTRIBUTES,
# DELETE_CHILD, DELETE, WRITE_DAC and WRITE_OWNER.
_WRITE_MASK = (
    0x00000002 | 0x00000004 | 0x00000010 | 0x00000100
    | 0x00000040 | 0x00010000 | 0x00040000 | 0x00080000
)

# Static PowerShell only. Paths are supplied through a dedicated environment
# variable and are never interpolated into executable command text.
_ACL_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
try {
    Import-Module Microsoft.PowerShell.Security -ErrorAction Stop
    $targets = ConvertFrom-Json -InputObject $env:LUKART_DACL_TARGETS
    if ($null -eq $targets -or $targets.Count -lt 2) { throw 'DACL_TARGETS_REQUIRED' }
    $rows = @()
    foreach ($target in $targets) {
        $acl = Get-Acl -LiteralPath ([string]$target) -ErrorAction Stop
        if ($null -eq $acl -or $null -eq $acl.Access) { throw 'DACL_MISSING' }
        $owner = $acl.GetOwner([System.Security.Principal.SecurityIdentifier]).Value
        $entries = @()
        foreach ($rule in $acl.Access) {
            $sid = $rule.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value
            $entries += [pscustomobject]@{
                sid = $sid
                type = [string]$rule.AccessControlType
                rights = [int64]$rule.FileSystemRights
                inherited = [bool]$rule.IsInherited
            }
        }
        $rows += [pscustomobject]@{
            path = [string]$target
            owner = $owner
            entries = @($entries)
        }
    }
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [System.Security.Principal.WindowsPrincipal]::new($identity)
    [pscustomobject]@{
        current_sid = $identity.User.Value
        current_is_admin = [bool]$principal.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)
        targets = @($rows)
    } | ConvertTo-Json -Compress -Depth 6
}
catch {
    [pscustomobject]@{
        error_id = [string]$_.FullyQualifiedErrorId
        error_category = [string]$_.CategoryInfo.Category
        error_type = [string]$_.Exception.GetType().FullName
    } | ConvertTo-Json -Compress -Depth 4
}
"""


class WindowsDaclError(ValueError):
    """Trusted Windows file ACL is missing, ambiguous or too permissive."""


def validate_acl_entries(
    entries: Any,
    *,
    owner_sid: str,
    allowed_sids: frozenset[str] = _TRUSTED_WRITERS,
    require_trusted_grants: bool = True,
) -> None:
    """Validate effective ACEs; only trusted OS/admin principals may write."""
    if not isinstance(owner_sid, str) or owner_sid not in allowed_sids:
        raise WindowsDaclError("WINDOWS_DACL_OWNER_UNTRUSTED")
    if not isinstance(entries, list) or not entries:
        raise WindowsDaclError("WINDOWS_DACL_EMPTY_OR_INVALID")

    allowed = {sid: 0 for sid in _REQUIRED_WRITERS}
    denied = {sid: 0 for sid in (*_TRUSTED_WRITERS, *_BROAD_DENY)}
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"sid", "type", "rights", "inherited"}:
            raise WindowsDaclError("WINDOWS_DACL_ENTRY_INVALID")
        sid, ace_type, rights = entry["sid"], entry["type"], entry["rights"]
        if not isinstance(sid, str) or not sid.startswith("S-1-"):
            raise WindowsDaclError("WINDOWS_DACL_SID_INVALID")
        if ace_type not in ("Allow", "Deny") or type(rights) is not int or rights < 0:
            raise WindowsDaclError("WINDOWS_DACL_ACE_INVALID")
        if type(entry["inherited"]) is not bool:
            raise WindowsDaclError("WINDOWS_DACL_ACE_INVALID")

        # CREATOR OWNER / OWNER RIGHTS are safe only because the object owner
        # was independently established as SYSTEM, Administrators or a
        # trusted Windows service above.
        effective_sid = owner_sid if sid in (_CREATOR_OWNER, _OWNER_RIGHTS) else sid
        write_rights = rights & _WRITE_MASK
        if not write_rights:
            continue
        if ace_type == "Allow":
            if effective_sid not in allowed_sids:
                raise WindowsDaclError("WINDOWS_DACL_UNTRUSTED_WRITE_GRANT")
            if effective_sid in allowed:
                allowed[effective_sid] |= write_rights
        elif effective_sid in denied:
            denied[effective_sid] |= write_rights
        elif effective_sid in _BROAD_DENY:
            denied[effective_sid] |= write_rights

    if require_trusted_grants:
        for sid in _REQUIRED_WRITERS:
            if allowed[sid] != _WRITE_MASK:
                raise WindowsDaclError("WINDOWS_DACL_TRUSTED_WRITE_ACCESS_INCOMPLETE")
    if any(denied.values()):
        raise WindowsDaclError("WINDOWS_DACL_TRUSTED_WRITE_ACCESS_DENIED")


def _has_reparse_point(path: Path) -> bool:
    try:
        attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    except OSError as exc:
        raise WindowsDaclError("WINDOWS_DACL_PATH_UNREADABLE") from exc
    return bool(attributes & _REPARSE_POINT)


def verify_protected_file(path: str | Path) -> str:
    """Verify the file and containing directory DACL; return the resolved path."""
    if os.name != "nt":
        raise WindowsDaclError("WINDOWS_DACL_VERIFICATION_REQUIRED")
    source = Path(path)
    if not source.is_absolute() or not source.is_file() or _has_reparse_point(source):
        raise WindowsDaclError("TRUSTED_WINDOWS_FILE_REQUIRED")
    parent = source.parent
    if not parent.is_dir() or _has_reparse_point(parent):
        raise WindowsDaclError("TRUSTED_WINDOWS_DIRECTORY_REQUIRED")
    resolved = source.resolve(strict=True)
    resolved_parent = resolved.parent
    if str(resolved).startswith("\\\\") or str(resolved_parent).startswith("\\\\"):
        raise WindowsDaclError("LOCAL_WINDOWS_FILE_REQUIRED")
    system_root = os.environ.get("SystemRoot") or os.environ.get("WINDIR")
    if not system_root:
        raise WindowsDaclError("WINDOWS_SYSTEM_ROOT_REQUIRED")
    powershell = Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if not powershell.is_file():
        raise WindowsDaclError("WINDOWS_ACL_PROVIDER_REQUIRED")

    targets = [str(resolved), str(resolved_parent)]
    env = {
        key: value for key, value in os.environ.items()
        if key.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PSMODULEPATH"}
    }
    env["LUKART_DACL_TARGETS"] = json.dumps(targets)
    env["PSModulePath"] = env.get("PSModulePath") or str(Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "Modules")
    try:
        result = subprocess.run(
            [str(powershell), "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", _ACL_SCRIPT],
            capture_output=True, text=True, encoding="utf-8", errors="strict",
            timeout=10, check=False, env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise WindowsDaclError("WINDOWS_DACL_QUERY_FAILED") from exc
    if result.returncode != 0 or not result.stdout.strip():
        raise WindowsDaclError("WINDOWS_DACL_QUERY_FAILED")
    try:
        document = json.loads(result.stdout)
    except (ValueError, TypeError) as exc:
        raise WindowsDaclError("WINDOWS_DACL_RESULT_INVALID") from exc
    if isinstance(document, dict) and "error_id" in document:
        detail = ":".join(str(document.get(key, "UNKNOWN")) for key in ("error_category", "error_type", "error_id"))
        raise WindowsDaclError("WINDOWS_DACL_QUERY_FAILED:" + detail)
    if not isinstance(document, dict) or set(document) != {"current_sid", "current_is_admin", "targets"}:
        raise WindowsDaclError("WINDOWS_DACL_RESULT_INVALID")
    current_sid, current_is_admin = document["current_sid"], document["current_is_admin"]
    if not isinstance(current_sid, str) or not current_sid.startswith("S-1-") or type(current_is_admin) is not bool:
        raise WindowsDaclError("WINDOWS_DACL_IDENTITY_INVALID")
    allowed_sids = _TRUSTED_WRITERS | ({current_sid} if current_is_admin else set())
    rows = document["targets"]
    if not isinstance(rows, list) or len(rows) != 2:
        raise WindowsDaclError("WINDOWS_DACL_TARGETS_INVALID")
    expected = {str(resolved).casefold(), str(resolved_parent).casefold()}
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"path", "owner", "entries"}:
            raise WindowsDaclError("WINDOWS_DACL_RESULT_INVALID")
        target = row["path"]
        if not isinstance(target, str) or target.casefold() not in expected or target.casefold() in seen:
            raise WindowsDaclError("WINDOWS_DACL_TARGET_MISMATCH")
        seen.add(target.casefold())
        validate_acl_entries(
            row["entries"],
            owner_sid=row["owner"],
            allowed_sids=frozenset(allowed_sids),
        )
    if seen != expected:
        raise WindowsDaclError("WINDOWS_DACL_TARGET_MISMATCH")
    return str(resolved)
