# Native Windows HUMAN authentication

Run the native host with:

```powershell
python -B -X utf8 examples/run_windows_human_operator.py
```

The front-end is a Windows SSPI/SPNEGO (Negotiate) loopback reverse proxy in the
`native_windows` adapter package. The existing WORK operator host remains unchanged;
the front-end authenticates the Windows account, resolves its SID against an
administrator-owned JSON policy, and injects the resulting case-scoped WORK bearer
capability only into the loopback backend request. The browser receives the capability
only as an HttpOnly; SameSite=Strict cookie. JavaScript uses same-origin cookies and
never reads the real token.

The front-end binds to loopback and proxies to a second ephemeral loopback-only
backend port. Use http://localhost:8786/, not a LAN address. Native POST requests
require same-origin Origin and Sec-Fetch-Site headers.

Copy `examples/windows-human-identity-policy.template.json` to a private local path
such as `%ProgramData%\Lukart\Identity\human-policy.json`. The template has no
principals and grants nobody access. The administrator must provision the actual
Windows SID, HUMAN actor UUID, tenant UUID, CASE UUID, and exact actions. Do not use
wildcards. Protect both the policy file and its containing directory with DACLs that
grant write/delete/WRITE_DAC/WRITE_OWNER rights only to SYSTEM and trusted local
Administrators (TrustedInstaller may retain its built-in OS rights).

At startup, the runtime verifies the effective DACL and owner of the policy file and
its containing directory. It fails closed if the owner is not SYSTEM, local
Administrators, TrustedInstaller, or the current process account when that account is
a member of local Administrators; if any other principal has write-capable rights; if
the ACL is missing/ambiguous; or if the file/directory is a reparse point. The current
process account is accepted only when Windows confirms local Administrators group
membership. DACL verification uses the built-in Windows PowerShell ACL provider with
a static script and a bounded timeout; inability to inspect the ACL is a startup denial.

Set `LUKART_HUMAN_IDENTITY_POLICY` and `LUKART_TRUSTED_CASE_HOST` to absolute paths.
The old executable identity adapter hook is not used; identity mapping is validated
JSON and SSPI is versioned code.

SSPI proves Windows authenticated the account represented by the negotiated context.
It does not prove physical user presence, independent legal review, or that a legal
decision occurred. HUMAN decisions remain explicit UI actions. The policy template
grants nobody. Production HUMAN authorization remains NOT CONFIGURED until the
administrator provisions the real SID-to-actor/tenant/CASE/action mapping and verifies
the policy DACL on the target machine. Windows CI uses only a synthetic identity and
read-only GetCaseHead probe; it does not approve documents, issue FINAL, assemble
packages, or certify full ROS-to-WORK H5.
