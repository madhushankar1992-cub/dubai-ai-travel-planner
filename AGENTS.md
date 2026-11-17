# Repository-wide system safety boundary

These instructions apply to every file, command, agent, sub-agent, script, test,
and tool action in this repository.

## Protected system boundary

- Never read, write, query, or modify BIOS, UEFI, firmware, TPM, Secure Boot,
  boot configuration, device drivers, disk partitions, or drive encryption.
- Never read or modify the Windows Registry, WMI/CIM system configuration,
  Windows services, scheduled tasks, Group Policy, firewall, Defender settings,
  environment variables outside the current process, or persistent system settings.
- Never read or modify PowerShell profiles, execution policy, module paths, remoting
  configuration, shell startup files, or terminal configuration.
- Never invoke `powershell`, `pwsh`, `cmd.exe`, `bcdedit`, `diskpart`, `reg`,
  `regedit`, `wmic`, `sc`, `schtasks`, firmware tools, or equivalent system tools
  from project code or model-generated output.
- Never add dynamic shell execution (`subprocess`, `os.system`, `os.popen`,
  `shell=True`, `eval`, or `exec`) to project runtime code. Model responses are
  untrusted data and must remain schema-validated; they must never become commands.

## Workspace and secrets

- Limit file writes to this repository or a task-specific temporary directory.
  Do not write to user profiles, PowerShell directories, Windows/System32,
  Program Files, other repositories, or device paths.
- Do not print, log, commit, or place API keys in commands. Read secrets only via
  the validated settings loader; keep `.env` ignored and `.env.example` secret-free.
- Do not delete or overwrite user data. Use explicit, resolved, workspace-local
  paths and obtain the user's approval before any material destructive action.
- External provider calls must use the existing allowlisted HTTPS gateway. Do not
  broaden its host allowlist or send fields beyond the approved request/catalog
  payload without explicit user authorization.

## Allowed project work

Workspace-local source edits, tests, linting, the project virtual environment,
SQLite files under `runtime/`, and the Streamlit server are allowed. Operating-
system configuration is outside this project's scope even if a task appears to
benefit from it. If a requested step conflicts with this boundary, stop and ask
the user for a safe project-local alternative; do not request elevated access to
cross this boundary.

Before a release or deployment, run `tests/security/test_system_boundaries.py`.

