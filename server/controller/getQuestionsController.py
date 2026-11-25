import base64
import mimetypes
import os

# Text files are sent verbatim as UTF-8 strings. Binary assets are base64
# encoded so they fit in the existing JSON-over-SALP transport.
TEXT_EXTENSIONS = {'.md', '.txt', '.java', '.py', '.cpp', '.c', '.h'}
BINARY_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'}

# Base64 expands by 4/3 and the SALP frame limit is 128 MiB. Leave headroom
# for the surrounding JSON so a single asset cannot overflow the frame.
MAX_QUESTION_ASSET_BYTES = 90 * 1024 * 1024


def serialize_question(qid, path, extension):
    """Build the JSON object for one question file.

    Text questions keep the original `content` string shape; binary assets add
    an explicit encoding, MIME type and size so the remote can decode them and
    write byte-identical files.
    """
    filename = os.path.basename(path)

    if extension in BINARY_EXTENSIONS:
        with open(path, 'rb') as file:
            raw = file.read()

        if len(raw) > MAX_QUESTION_ASSET_BYTES:
            raise ValueError(
                f"Question asset '{filename}' is too large: "
                f"{len(raw)} bytes (limit {MAX_QUESTION_ASSET_BYTES})"
            )

        return {
            "qid": qid,
            "filename": filename,
            "extension": extension,
            "encoding": "base64",
            "mime_type": mimetypes.guess_type(filename)[0] or "application/octet-stream",
            "size": len(raw),
            "content": base64.b64encode(raw).decode('ascii')
        }

    with open(path, 'r', encoding='utf-8') as file:
        content = file.read()

    return {
        "qid": qid,
        "filename": filename,
        "extension": extension,
        "encoding": "text",
        "mime_type": "text/plain",
        "size": len(content.encode('utf-8')),
        "content": content
    }


def get_questions_controller(payload, user_args):
    if not user_args or not isinstance(user_args, dict):
        raise ValueError("Get Questions Controller: User arguments must be provided")

    questions_folder = user_args.get("questions_folder")
    if not questions_folder:
        raise ValueError("Get Questions Controller: 'questions_folder' must be provided in user arguments")

    questions_payload = [
        serialize_question(question["qid"], question["path"], question["extension"])
        for question in get_questions(questions_folder)
    ]

    # One response carries every question, so bound the combined asset size as
    # well as the size of each individual file.
    total_asset_bytes = sum(
        question["size"] for question in questions_payload
        if question["encoding"] == "base64"
    )
    if total_asset_bytes > MAX_QUESTION_ASSET_BYTES:
        raise ValueError(
            f"Question assets are too large in aggregate: "
            f"{total_asset_bytes} bytes (limit {MAX_QUESTION_ASSET_BYTES})"
        )

    return {
        "status": "SUCCESS",
        "message": f"Questions retrieved successfully.",
        "payload": {
            "questions": questions_payload
        }
    }


def get_questions(questions_folder):
    """Find question files in the subfolders of `questions_folder`.

    Folders starting with '~' hold judge/testcase/wrapper data and are never
    served to remote PCs.
    """
    questions = []
    allowed_extensions = TEXT_EXTENSIONS | BINARY_EXTENSIONS

    for root, dirs, _ in os.walk(questions_folder):
        for dir in dirs:
            if dir.startswith('~'):
                continue  # Skip directory whose name starts with ~
            if dir in ('.', '..') or os.sep in dir or (os.altsep and os.altsep in dir):
                continue  # A question ID must be a single path component

            dir_path = os.path.join(root, dir)
            for file in os.listdir(dir_path):
                extension = os.path.splitext(file)[1].lower()
                if extension in allowed_extensions:
                    questions.append({
                        "qid": dir,
                        "path": os.path.join(dir_path, file),
                        "extension": extension
                    })

    return questions
