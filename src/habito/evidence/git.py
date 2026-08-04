"""Thin, path-scoped wrapper over the ``git`` CLI, run inside the data repo.

Deliberately minimal: the evidence flow only needs add / commit / push and a couple of
status checks. All commands run with ``cwd`` set to the data repo, so this repo (the code
repo) is never touched.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(RuntimeError):
    def __init__(self, args: list[str], returncode: int, stderr: str) -> None:
        super().__init__(f"git {' '.join(args)} failed ({returncode}): {stderr.strip()}")
        self.returncode = returncode
        self.stderr = stderr


class GitRepo:
    def __init__(self, cwd: Path) -> None:
        self.cwd = Path(cwd)

    def _run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        proc = subprocess.run(
            ["git", *args],
            cwd=self.cwd,
            capture_output=True,
            text=True,
        )
        if check and proc.returncode != 0:
            raise GitError(list(args), proc.returncode, proc.stderr)
        return proc

    # --- status checks ---------------------------------------------------
    def is_repo(self) -> bool:
        if not self.cwd.exists():
            return False
        proc = self._run("rev-parse", "--is-inside-work-tree", check=False)
        return proc.returncode == 0 and proc.stdout.strip() == "true"

    def has_remote(self, remote: str) -> bool:
        proc = self._run("remote", check=False)
        return remote in proc.stdout.split()

    def unpushed_count(self, remote: str, branch: str) -> int:
        """Number of local commits not yet on ``remote/branch`` (0 if unknown)."""
        proc = self._run("rev-list", "--count", f"{remote}/{branch}..HEAD", check=False)
        if proc.returncode != 0:
            return 0
        try:
            return int(proc.stdout.strip())
        except ValueError:
            return 0

    # --- mutations -------------------------------------------------------
    def add(self, path: str) -> None:
        self._run("add", "--", path)

    def commit(self, path: str, message: str) -> None:
        self._run("commit", "-m", message, "--", path)

    def pull_rebase(self, remote: str, branch: str) -> None:
        self._run("pull", "--rebase", remote, branch)

    def push(self, remote: str, branch: str) -> None:
        self._run("push", remote, branch)
