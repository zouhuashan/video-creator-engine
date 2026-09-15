# Logging standard

Task commands should use `scripts/run_task.py` so routine execution stays quiet in the terminal while diagnostic output is retained locally.

## Terminal summary

The runner prints exactly four lines:

```text
RUN <TASK>
PASS | FAIL
RESULT <log-file-path>
NEXT <TASK>
```

The runner returns the wrapped command's exit status. On failure, inspect the log named by `RESULT`.

## Log files

- Detailed stdout and stderr are combined in `logs/`.
- Each entry is timestamped in UTC and includes the task name and command executable.
- Filenames include the start time, task slug, and a unique suffix.
- `logs/` is ignored by Git; do not commit run output.
- Common API-key, token, password, secret assignments, and Bearer tokens are redacted before writing. Commands and adapters must still avoid printing credentials or other private data.

Example:

```bash
python3 scripts/run_task.py --task P1-01 --next P1-02 -- python3 -m compileall src
```
