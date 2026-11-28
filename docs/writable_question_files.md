# Writable question files

Question authors can allow individual delivered files to be edited on the kiosk
by adding a `writable_` prefix to the filename on the server. No configuration
file, database entry, or daemon setting is involved.

## Rule

For a question package such as:

```text
questions/<exam_id>/Q110/
├── Q110.md
├── writable_q110.py
├── Resume.pdf
└── ~judge/
    └── ...
```

the kiosk receives:

```text
/home/examkiosk/exam_workspace/Q110/
├── Q110.md       root:root   0444  read-only
├── q110.py       examkiosk:examkiosk  0644  writable
└── Resume.pdf    root:root   0444  read-only
```

The prefix is removed by `jmxd` before the file is written. The student sees
`q110.py`, not `writable_q110.py`. File contents are unchanged.

The prefix is exact and case-sensitive: `writable_q110.py` is special;
`Writable_q110.py` is an ordinary read-only file. It can be applied to text or
base64 assets. Files inside `~judge/`, `~testcases/`, and `~wrapper/` are never
delivered, so the prefix has no effect there.

## Why per-file?

A question package can contain a statement that must not change, a starter
source file that students should edit, and an asset such as a PDF that must stay
read-only. Renaming only the starter file expresses that intent without a
separate policy file.

Anything without the prefix stays read-only, so existing question packages keep
their current behavior.

## Collisions and invalid names

After the prefix is stripped, the resulting filename must be unique within its
question package. If both of these exist:

```text
Q110/q110.py
Q110/writable_q110.py
```

the transfer is rejected with a duplicate-file error rather than silently
overwriting one with the other. Similarly, `writable_` by itself, or a prefixed
name containing `/`, `\`, or `..`, is rejected.

Rejected transfers leave the previously written questions in place. Fix the
question package and run `jmx get questions` again (or restart the session).

## What "writable" means

- The file itself can be edited in place by the kiosk user.
- The question directory stays root-owned and mode `0755`, so students cannot
  add, delete, rename, or replace question files.
- Running `jmx get questions` rewrites files from the server source. Any student
  edits to writable files are reset by a refetch.
- `jmx submit` reads code from a file; it does not strip the `writable_` prefix.

## Submitting nested files

`jmx submit -f` accepts a path relative to the exam workspace:

```bash
jmx submit -q Q110 -f Q110/q110.py
jmx submit -q Q110 -f q110.py
```

Absolute paths, `..` components, symlinked path components, and non-regular
files are rejected. The daemon sends only the final filename component to the
server; the server needs it only to choose the wrapper language and name the
stored response.
