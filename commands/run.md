---
description: Run a command with secret injection
---

Execute a CLI command with automatic secret injection.

Parse $ARGUMENTS to get the command to run.

1. Identify any credentials or secrets the command might need
2. Call `list_secrets` to check what's available
3. Construct the command with `{{SECRET_NAME}}` placeholders for any needed secrets
4. If secrets are missing, call `request_secret` for each one
5. Call `run_command` with the command

If the command is expected to output credentials (like `aws sts get-session-token`), add appropriate `capture` specs.
