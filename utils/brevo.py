def parse_brevo_recipients(emails: str) -> list[dict[str, str]]:
    """Parse a comma-separated list of emails into Brevo recipient objects."""
    if not emails:
        return []
    return [{"email": email.strip()} for email in emails.split(",") if email.strip()]


def internal_notification_emails(*parts: str) -> str:
    """Join configured internal notification addresses into a comma-separated string."""
    return ",".join(part.strip() for part in parts if part and part.strip())


def add_optional_recipients(
    payload: dict,
    *,
    cc: str = "",
    bcc: str = "",
) -> dict:
    """Add cc/bcc fields to a Brevo payload when configured."""
    cc_recipients = parse_brevo_recipients(cc)
    bcc_recipients = parse_brevo_recipients(bcc)
    if cc_recipients:
        payload["cc"] = cc_recipients
    if bcc_recipients:
        payload["bcc"] = bcc_recipients
    return payload
