import os

MAX_RECENT_SUBMISSIONS = 3


def _no_submissions_message(student_id, qid):
    return (
        f"No submissions found for student ID '{student_id}' "
        f"with question ID '{qid}'."
    )


def _validate_request(payload, user_args):
    """Return (student_id, qid, responses_folder, error) for a query."""
    payload = payload if isinstance(payload, dict) else {}
    user_args = user_args if isinstance(user_args, dict) else {}

    student_id = payload.get("student_id")
    qid = payload.get("qid")

    if not isinstance(student_id, str) or not student_id.strip():
        return None, None, None, "Missing or invalid student_id in payload."
    if not isinstance(qid, str) or not qid.strip():
        return None, None, None, "Missing or invalid qid in payload."

    responses_folder = user_args.get("responses_folder")
    if not isinstance(responses_folder, (str, os.PathLike)):
        return None, None, None, "Missing responses_folder in server arguments."
    responses_folder = os.fspath(responses_folder)
    if not responses_folder:
        return None, None, None, "Missing responses_folder in server arguments."

    student_id = student_id.strip()
    qid = qid.strip().upper()

    # Both values are used as path components, so reject anything that could
    # escape the responses folder before touching the filesystem.
    for value in (student_id, qid):
        if value in (".", "..") or os.path.basename(value) != value:
            return None, None, None, "Invalid student_id or qid."

    return student_id, qid, responses_folder, None


def _find_submissions(qid, folder, limit):
    """Return up to `limit` submission files for `qid`, newest first."""
    if not os.path.isdir(folder):
        return []

    submissions = []
    with os.scandir(folder) as entries:
        for entry in entries:
            if not entry.name.startswith(f"{qid}_"):
                continue
            if not entry.is_file(follow_symlinks=False):
                continue

            try:
                modified = entry.stat(follow_symlinks=False).st_mtime
                with open(entry.path, "r", encoding="utf-8", errors="replace") as file:
                    content = file.read()
            except OSError:
                continue

            submissions.append({
                "filename": entry.name,
                "content": content,
                "extension": os.path.splitext(entry.name)[1].lower(),
                "_modified": modified,
            })

    # A submission's filename only carries the time of day, so use the file
    # timestamp for ordering and the name as a deterministic tie-breaker.
    submissions.sort(key=lambda item: (item["_modified"], item["filename"]), reverse=True)
    submissions = submissions[:limit]
    for submission in submissions:
        del submission["_modified"]

    return submissions


def _get_submissions(payload, user_args, best_only):
    student_id, qid, responses_folder, error = _validate_request(payload, user_args)
    if error:
        return {"status": "ERROR", "message": error}

    student_folder = os.path.join(responses_folder, student_id)
    folder = os.path.join(student_folder, "best") if best_only else student_folder
    limit = 1 if best_only else MAX_RECENT_SUBMISSIONS

    submissions = _find_submissions(qid, folder, limit)
    if not submissions:
        return {
            "status": "SUCCESS",
            "message": _no_submissions_message(student_id, qid),
            "payload": {"submissions": []},
        }

    if best_only:
        message = (
            f"Retrieved the most recent best submission for student ID "
            f"'{student_id}' and question ID '{qid}'."
        )
    else:
        message = (
            f"Retrieved {len(submissions)} recent submission(s) for student ID "
            f"'{student_id}' and question ID '{qid}'."
        )

    return {
        "status": "SUCCESS",
        "message": message,
        "payload": {"submissions": submissions},
    }


def get_recent_submissions_controller(payload, user_args):
    return _get_submissions(payload, user_args, best_only=False)


def get_best_submission_controller(payload, user_args):
    return _get_submissions(payload, user_args, best_only=True)
