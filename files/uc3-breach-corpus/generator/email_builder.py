"""
Builds .eml files with real attachments (a PDF or DOCX generated the same
way as the standalone documents), since Section 4 requires PII extraction
to reach into email attachments, not just the message body.
"""
from email.message import EmailMessage
from pathlib import Path


def render_eml(path: Path, sender: str, recipient: str, subject: str,
                body_lines: list[str], attachment_path: Path = None):
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content("\n\n".join(body_lines))

    if attachment_path is not None and attachment_path.exists():
        data = attachment_path.read_bytes()
        suffix = attachment_path.suffix.lower()
        if suffix == ".pdf":
            maintype, subtype = "application", "pdf"
        elif suffix == ".docx":
            maintype, subtype = "application", "vnd.openxmlformats-officedocument.wordprocessingml.document"
        else:
            maintype, subtype = "application", "octet-stream"
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=attachment_path.name)

    path.write_bytes(bytes(msg))
