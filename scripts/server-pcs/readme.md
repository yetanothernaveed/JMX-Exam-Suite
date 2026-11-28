# Server PC setup

Run `setup_script.sh` on the exam server to install the Python server,
database, Piston judge, and the example question/response folders.

Question packages live under:

```text
~/questions/<exam_id>/<qid>/
```

Each question folder contains the delivered files plus `~judge/`,
`~testcases/`, and `~wrapper/`. Only files in the question folder itself are
sent to kiosks; the `~`-prefixed folders stay on the server for grading.

To let students edit a delivered file on the kiosk, prefix its server-side
filename with `writable_`. The daemon removes the prefix and gives the kiosk
user write access to that file only. See
[`docs/writable_question_files.md`](../../docs/writable_question_files.md).
