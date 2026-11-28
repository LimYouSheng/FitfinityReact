"""Plain transactional messages; exclude health notes, private comments and credentials."""

from dataclasses import dataclass


@dataclass(frozen=True)
class EmailContent:
    subject: str
    text: str


def render(kind, values):
    """Render only explicitly selected event fields, never an entire domain record."""
    name = values["name"].strip()
    if kind == "client_welcome":
        subject = "Welcome to OneFitfinity"
        body = (
            f"Welcome to OneFitfinity. Your trainer is {values['trainer']}.\n"
            "Your trainer will help you arrange your sessions. No app login is needed."
        )
    elif kind == "trainer_termination":
        subject = "Your OneFitfinity trainer account"
        body = (
            "Your OneFitfinity trainer account has been deactivated. "
            "Please contact the team if you have any questions."
        )
    elif kind in {"package_added", "package_update", "session_complete"}:
        subject = {
            "package_added": "Your new OneFitfinity package",
            "package_update": "Your OneFitfinity package update",
            "session_complete": "Your OneFitfinity session and package update",
        }[kind]
        intro = "Your session has been acknowledged.\n" if kind == "session_complete" else ""
        body = (
            f"{intro}Package: {values['package']}\n"
            f"Sessions used: {values['used']} of {values['total']}\n"
            f"Sessions remaining: {max(0, values['total'] - values['used'])}\n"
            f"Valid from {values['start']} through {values['end']}."
        )
    elif kind == "progress_report":
        subject = "Your OneFitfinity progress report"
        body = values["report"].strip()
    else:
        raise ValueError("Unsupported email event")
    return EmailContent(subject, f"Hi {name},\n\n{body}\n\nOneFitfinity\n")
