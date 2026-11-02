"""Error capture: run a command and record its failure with context.

Planned responsibility (Phase 1): wrap any command via Python ``subprocess`` (cross-platform, no
shell tricks), and on non-zero exit collect stderr / stack trace plus context: command, cwd,
project, git branch and commit, language, relevant package versions, OS, and timestamp. Also detect
when a previously failing command later succeeds so the diff can be proposed as the fix.
"""
