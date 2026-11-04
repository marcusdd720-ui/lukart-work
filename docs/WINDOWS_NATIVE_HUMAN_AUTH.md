# Native Windows HUMAN authentication

The local LEGAL OS host uses Windows SSPI/SPNEGO (Negotiate). It does not collect or
persist a Windows password and does not expose a bearer token to JavaScript.

The loopback host challenges the browser with WWW-Authenticate: Negotiate; Windows
SSPI authenticates the account; the server resolves its canonical SID; an administrator-
owned JSON policy maps that SID to one HUMAN actor, tenant, CASE and explicit actions.
WORK receives a process-local capability only in an HttpOnly; SameSite=Strict cookie.
JavaScript never reads the token. The capability has a bounded sliding lifetime
(60–3600 seconds); host shutdown/restart revokes it.

Use http://localhost:<port>/, not a LAN address. Native mode requires same-origin POST
requests and Sec-Fetch-Site: same-origin.

Copy examples/windows-human-identity-policy.template.json to a private local path,
for example %ProgramData%\Lukart\Identity\human-policy.json. The template has an
empty principals array and grants nobody access. The administrator must populate it
with the actual Windows SID, a provisioned HUMAN actor UUID, one tenant UUID, one CASE
UUID and only exact allowed actions. Do not use a wildcard. One SID is bound to one
CASE scope per policy. Protect the file with a DACL allowing writes only to SYSTEM and
trusted local Administrators, and read access to the host account. Never store passwords
or API keys in this file.

Set LUKART_HUMAN_IDENTITY_POLICY to the absolute path of the private JSON policy and
LUKART_TRUSTED_CASE_HOST to the trusted WORK operator/database builder module.
The old LUKART_HUMAN_IDENTITY_ADAPTER Python hook is no longer used; identity mapping
is validated JSON and SSPI is part of the versioned application.

Install with: uv sync --frozen --extra postgres --extra ingestion --extra windows-auth.

SSPI proves Windows authenticated the account represented by the negotiated context.
It does not prove physical user presence, independent legal review, or that a legal
decision occurred. HUMAN decisions remain explicit UI actions and automation must not
generate or record them for a person.

The committed policy template grants nobody identities. Production HUMAN authorization
remains NOT CONFIGURED until an administrator provisions the actual SID-to-actor,
tenant, CASE and action mapping and verifies its DACL on the target machine. Windows CI
uses a synthetic policy and a read-only GetCaseHead probe; it does not use real cases,
approve a document, issue FINAL, assemble a package, or certify full ROS-to-WORK H5.
