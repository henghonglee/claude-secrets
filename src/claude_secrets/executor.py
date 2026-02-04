"""Command execution with subprocess management."""

import subprocess
import shlex
from dataclasses import dataclass
from typing import Optional


@dataclass
class ExecutionResult:
    """Result of command execution."""
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False


def execute_command(
    command: str,
    timeout: int = 60,
    shell: bool = True,
    cwd: Optional[str] = None,
) -> ExecutionResult:
    """Execute a command and return the result.

    Args:
        command: Command to execute
        timeout: Timeout in seconds
        shell: Whether to use shell execution
        cwd: Working directory

    Returns:
        ExecutionResult with stdout, stderr, exit_code
    """
    try:
        if shell:
            args = command
        else:
            args = shlex.split(command)

        result = subprocess.run(
            args,
            shell=shell,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )

        return ExecutionResult(
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.returncode,
        )

    except subprocess.TimeoutExpired:
        return ExecutionResult(
            stdout="",
            stderr=f"Command timed out after {timeout} seconds",
            exit_code=-1,
            timed_out=True,
        )
    except FileNotFoundError as e:
        return ExecutionResult(
            stdout="",
            stderr=f"Command not found: {e}",
            exit_code=127,
        )
    except Exception as e:
        return ExecutionResult(
            stdout="",
            stderr=f"Execution error: {e}",
            exit_code=-1,
        )
