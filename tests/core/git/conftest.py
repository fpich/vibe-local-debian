from __future__ import annotations

import shutil

from git import Git

Git.refresh(shutil.which("git") or "git")
