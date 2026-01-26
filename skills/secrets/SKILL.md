---
name: secrets-management
description: "REQUIRED: Use run_command instead of Bash for ANY command that creates, outputs, or uses secrets/credentials/tokens/API keys/passwords. Prevents secrets from being exposed in chat history."
---

# Secrets Management Skill

**CRITICAL**: You MUST use `run_command` instead of Bash for ANY command involving secrets.

## When to Use (ALWAYS check before using Bash)

Use `run_command` if the command:
- **Generates secrets**: API keys, access tokens, passwords, certificates, SSH keys
- **Outputs secrets**: Credentials in response, tokens in JSON output, keys in any format
- **Requires secrets**: Needs API keys, tokens, passwords, or credentials to run
- **Accesses sensitive services**: Cloud providers, databases, payment systems, auth services

## Common Examples (not exhaustive)

| Category | Commands |
|----------|----------|
| AWS | `create-access-key`, `get-session-token`, `assume-role`, `get-secret-value` |
| GitHub | `gh auth token`, `gh auth login`, creating PATs |
| Docker | `docker login`, registry credentials |
| Databases | Connection strings, `psql`, `mysql` with credentials |
| APIs | Any curl/http request with API keys or tokens |
| SSH/TLS | Key generation, certificate creation |
| CI/CD | Pipeline tokens, deploy keys |
| Any service | Account creation, password resets, token generation |

## Why This Matters

Using Bash exposes secrets in:
- Chat history (visible to user and potentially logged)
- Tool output (stored in conversation)

Using `run_command`:
- Automatically redacts secrets from output
- Captures and stores secrets in encrypted vault
- Enables `{{SECRET_NAME}}` placeholders for future use
- Logs access for audit trail

## Available MCP Tools

You have access to these tools from the `secrets` MCP server:

### `list_secrets`
Discover available secrets before running commands. Always check this first.

```json
{"tag": "aws"}  // Optional: filter by tag
```

Returns secret names with descriptions - use descriptions to understand what each secret is for.

### `run_command`
Execute CLI commands with secret injection and output protection.

**Secret Injection**: Use `{{SECRET_NAME}}` placeholders:
```json
{
  "command": "aws s3 ls --profile {{AWS_PROFILE}}"
}
```

**Secret Capture**: Extract credentials from command output:
```json
{
  "command": "aws sts get-session-token",
  "capture": [
    {
      "path": "$.Credentials.AccessKeyId",
      "name": "AWS_SESSION_KEY_ID",
      "description": "Temporary AWS access key from STS. Use with AWS_SESSION_SECRET and AWS_SESSION_TOKEN for temporary access.",
      "expires_at": "2024-01-24T18:00:00Z"
    },
    {
      "path": "$.Credentials.SecretAccessKey",
      "name": "AWS_SESSION_SECRET",
      "description": "Temporary AWS secret key from STS. Must be used together with AWS_SESSION_KEY_ID and AWS_SESSION_TOKEN.",
      "expires_at": "2024-01-24T18:00:00Z"
    }
  ]
}
```

### `request_secret`
Ask the user to provide a missing secret. Use when `list_secrets` doesn't have what you need.

```json
{
  "name": "GITHUB_TOKEN",
  "description": "Personal access token for GitHub API. Needs 'repo' and 'workflow' scopes for this task."
}
```

The user will see a native dialog prompting them to enter the value.

### `get_permissions`
Check which secrets you have permission to use in this session.

## Workflow (MUST FOLLOW)

**ALWAYS call `list_secrets` FIRST** before any other action involving secrets.

1. **FIRST**: Call `list_secrets` to see what secrets already exist
2. **If secret exists**: Use `{{SECRET_NAME}}` placeholder in `run_command` (use the EXACT name from list_secrets)
3. **ONLY if secret is NOT in list**: Call `request_secret`, then call `list_secrets` again to get the exact name
4. **If command outputs credentials**: Use `capture` to store them for future use

**NEVER call `request_secret` without first calling `list_secrets`** - the secret may already exist with a slightly different name.

## Writing Good Descriptions

When using `request_secret` or `capture`, write descriptions that help future AI assistants:

- What the secret is (API key, token, password, etc.)
- What service/API it's for
- What permissions/scopes it needs
- Related secrets it must be used with
- How it was generated (for captured secrets)
- When it expires (if temporary)

**Good example**:
> "AWS session secret key from STS get-session-token. Temporary credential valid for 12 hours. Must be used together with AWS_SESSION_KEY_ID and AWS_SESSION_TOKEN. Generated from the hh-root profile."

**Bad example**:
> "AWS key"

## Shell Portability

**IMPORTANT**: Use portable shell commands to avoid cross-platform issues.

| Don't Use | Use Instead | Why |
|-----------|-------------|-----|
| `echo -e "line1\nline2"` | `printf 'line1\nline2\n'` | `echo -e` is not portable (writes "-e" literally on macOS/zsh) |
| `echo -n "no newline"` | `printf 'no newline'` | `echo -n` also has portability issues |

For multi-line content, use heredocs:
```bash
cat >> ~/.aws/credentials << 'EOF'
[profile-name]
aws_access_key_id = {{KEY_ID}}
aws_secret_access_key = {{SECRET}}
EOF
```

## Security Notes

- Secrets are automatically redacted from command output
- User must approve each secret's first use in a session
- Captured secrets are encrypted in the vault
- All access is logged to `~/.mcp-secrets/audit.log`
