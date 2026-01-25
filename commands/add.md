---
description: Request to add a new secret
---

The user wants to add a new secret. Parse $ARGUMENTS to get the secret name.

If a name was provided (e.g., `/mcp-secrets:add GITHUB_TOKEN`):
1. Ask the user what the secret is for
2. Call `request_secret` with the name and a description based on their answer

If no name was provided:
1. Ask what secret they want to add and what it's for
2. Suggest an appropriate name in UPPER_SNAKE_CASE
3. Call `request_secret` with the name and description
