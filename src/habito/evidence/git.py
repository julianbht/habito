"""Thin, path-scoped wrapper over the ``git`` CLI, run inside the data repo.

Deliberately minimal: the evidence flow only needs add / commit / pull / push and a couple
of status checks. All commands run with ``cwd`` set to the data repo, so this repo (the code
repo) is never touched.

Git never prompts for credentials here. Habito has no console, so a prompt would wait
forever where nobody can see it. A command that needs credentials it doesn't have fails
instead, and the caller treats that like being offline.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


class GitError(RuntimeError):
    def __init__(self, args: list[str], returncode: int, stderr: str) -> None:
        super().__init__(f"git {' '.join(args)} failed ({returncode}): {stderr.strip()}")
        self.returncode = returncode
        self.stderr = stderr


class GitRepo:
    def __init__(self, cwd: Path) -> None:
        self.cwd = Path(cwd)

    def _run(
        self, *args: str, check: bool = True, timeout: float | None = None
    ) -> subprocess.CompletedProcess[str]:
        try:
            proc = subprocess.run(
                ["git", *args],
                cwd=self.cwd,
                capture_output=True,
                text=True,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
                timeout=timeout,
                creationflags=_NO_WINDOW,
            )
        except subprocess.TimeoutExpired as exc:
            raise GitError(list(args), -1, f"timed out after {exc.timeout}s") from exc
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

    def merge_attribute(self, path: str) -> str | None:
        """The merge driver ``.gitattributes`` sets for ``path``, or None when unset."""
        proc = self._run("check-attr", "merge", "--", path, check=False)
        value = proc.stdout.rsplit(":", 1)[-1].strip()
        return None if proc.returncode != 0 or value in ("", "unspecified") else value

    def has_staged_changes(self, path: str) -> bool:
        """True if ``path`` has staged changes to commit (``git diff --cached``)."""
        proc = self._run("diff", "--cached", "--quiet", "--", path, check=False)
        return proc.returncode == 1  # 0 = clean, 1 = differences staged

    # --- mutations -------------------------------------------------------
    def add(self, path: str) -> None:
        self._run("add", "--", path)

    def commit(self, path: str, message: str) -> None:
        self._run("commit", "-m", message, "--", path)

    def pull_rebase(self, remote: str, branch: str, timeout: float | None = None) -> None:
        """Rebase local commits onto the remote's, or leave the repo as it was.

        A failed rebase is aborted, so the repo is never left stopped halfway, which would
        make every later commit and push fail too. ``--autostash`` lets the pull run while
        a day file holds a line not yet committed.
        """
        try:
            self._run("pull", "--rebase", "--autostash", remote, branch, timeout=timeout)
        except GitError:
            self._run("rebase", "--abort", check=False)
            raise

    def push(self, remote: str, branch: str, timeout: float | None = None) -> None:
        self._run("push", remote, branch, timeout=timeout)
