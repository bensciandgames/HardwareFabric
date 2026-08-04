"""
app/services/email.py

Plain-SMTP email sending, deliberately provider-agnostic — works against
Namecheap Private Email, Gmail, or any other SMTP host by just changing env
vars (SMTP_HOST/SMTP_USERNAME/SMTP_PASSWORD), no code change or provider SDK.

If SMTP isn't configured (smtp_host empty — the default), send_email() logs
the message instead of sending it. This lets registration/verification be
exercised end-to-end in a fresh deploy before a real mailbox exists, and the
moment real SMTP creds are set, delivery starts working with no other change.
"""

from __future__ import annotations

import logging
from email.message import EmailMessage

import aiosmtplib

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger("hardwarefabric.email")


async def send_email(to_email: str, subject: str, text_body: str, html_body: str | None = None) -> None:
    if not settings.smtp_host:
        logger.warning(
            "SMTP not configured (SMTP_HOST unset) — logging email instead of sending.\n"
            "  To: %s\n  Subject: %s\n  Body:\n%s",
            to_email, subject, text_body,
        )
        return

    message = EmailMessage()
    message["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(text_body)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    await aiosmtplib.send(
        message,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username or None,
        password=settings.smtp_password or None,
        start_tls=settings.smtp_use_tls,
    )


async def send_verification_email(to_email: str, token: str) -> None:
    verify_url = f"{settings.frontend_origin}{settings.frontend_verify_email_path}?token={token}"
    subject = "Verify your HardwareFabric email"
    text_body = (
        f"Welcome to HardwareFabric.\n\n"
        f"Verify your email to activate your account:\n{verify_url}\n\n"
        f"This link expires in {settings.email_verification_token_expire_hours} hours.\n"
        f"If you didn't create this account, you can ignore this email."
    )
    html_body = f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto;">
      <h2>Welcome to HardwareFabric</h2>
      <p>Verify your email to activate your account:</p>
      <p>
        <a href="{verify_url}"
           style="display:inline-block;background:#f4c430;color:#0a0e17;
                  padding:10px 20px;text-decoration:none;font-weight:600;
                  border-radius:2px;">Verify Email</a>
      </p>
      <p style="color:#888;font-size:13px;">
        Or paste this link into your browser:<br>{verify_url}
      </p>
      <p style="color:#888;font-size:13px;">
        This link expires in {settings.email_verification_token_expire_hours} hours.
        If you didn't create this account, you can ignore this email.
      </p>
    </div>
    """
    await send_email(to_email, subject, text_body, html_body)
