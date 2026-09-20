from __future__ import annotations

import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from html import escape
from typing import Protocol

from web_backend.settings import Settings

PRODUCT_NAME = "用户语义分析智能体"
SMTP_TIMEOUT_SECONDS = 30
ACTION_EMAIL_TEMPLATE = """\
<!doctype html>
<html lang="zh-CN">
  <body style="margin:0;background:#f3f6f5;font-family:Arial,'Microsoft YaHei',sans-serif;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
      style="padding:32px 12px;background:#f3f6f5;">
      <tr><td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
          style="max-width:560px;background:#fff;border:1px solid #dce5e2;border-radius:12px;">
          <tr><td style="padding:24px 28px 12px;color:#0b6b57;font-weight:700;">
            {product_name}
          </td></tr>
          <tr><td style="padding:8px 28px 28px;">
            <h1 style="margin:0 0 18px;color:#172321;font-size:24px;">{heading}</h1>
            {paragraphs}
            <p style="margin:24px 0;">
              <a href="{action_url}"
                style="display:inline-block;padding:12px 22px;border-radius:8px;background:#0b6b57;color:#fff;text-decoration:none;font-weight:700;">
                {action_label}
              </a>
            </p>
            <p style="color:#62706d;font-size:13px;">若按钮无法打开，请复制以下链接到浏览器：</p>
            <p style="color:#0b6b57;font-size:12px;word-break:break-all;">{action_url}</p>
            <p style="color:#465552;font-size:13px;">{expiry_text}</p>
            <p style="color:#465552;font-size:13px;">{security_note}</p>
          </td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>
"""


class MailSender(Protocol):
    """定义身份邮件发送边界。"""

    def send_invitation(self, email: str, invitation_url: str) -> None:
        """发送一次性邀请链接。"""

    def send_password_reset(self, email: str, reset_url: str) -> None:
        """发送一次性密码重置链接。"""


@dataclass(frozen=True)
class ActionEmailContent:
    heading: str
    paragraphs: tuple[str, ...]
    action_label: str
    action_url: str
    expiry_text: str
    security_note: str


def _set_action_email_content(
    message: EmailMessage,
    content: ActionEmailContent,
) -> None:
    """生成带纯文本备用版本的身份操作邮件。"""
    message.set_content(
        "\n\n".join(
            (
                *content.paragraphs,
                f"{content.action_label}：\n{content.action_url}",
                content.expiry_text,
                content.security_note,
                PRODUCT_NAME,
            )
        )
    )
    paragraph_html = "".join(
        f'<p style="color:#33413f;font-size:15px;line-height:1.7;">'
        f"{escape(paragraph)}</p>"
        for paragraph in content.paragraphs
    )
    message.add_alternative(
        ACTION_EMAIL_TEMPLATE.format(
            product_name=escape(PRODUCT_NAME),
            heading=escape(content.heading),
            paragraphs=paragraph_html,
            action_url=escape(content.action_url, quote=True),
            action_label=escape(content.action_label),
            expiry_text=escape(content.expiry_text),
            security_note=escape(content.security_note),
        ),
        subtype="html",
    )


class SmtpMailSender:
    """通过标准 SMTP 发送生产身份邮件。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send_invitation(self, email: str, invitation_url: str) -> None:
        message = EmailMessage()
        message["Subject"] = f"你已被邀请加入{PRODUCT_NAME}"
        message["From"] = self.settings.smtp_from
        message["To"] = email
        _set_action_email_content(
            message,
            ActionEmailContent(
                heading=f"加入{PRODUCT_NAME}",
                paragraphs=("管理员邀请你加入团队工作台。", "请设置姓名和登录密码。"),
                action_label="接受邀请",
                action_url=invitation_url,
                expiry_text=(
                    f"链接将在 {self.settings.invitation_ttl_hours} 小时后失效，且只能使用一次。"
                ),
                security_note="请勿转发邀请链接；如果你不认识这份邀请，可以忽略此邮件。",
            ),
        )
        self._send(message)

    def send_password_reset(self, email: str, reset_url: str) -> None:
        message = EmailMessage()
        message["Subject"] = f"重置{PRODUCT_NAME}登录密码"
        message["From"] = self.settings.smtp_from
        message["To"] = email
        _set_action_email_content(
            message,
            ActionEmailContent(
                heading="重置登录密码",
                paragraphs=("我们收到了此邮箱的密码重置请求。", "请设置新的登录密码。"),
                action_label="重置密码",
                action_url=reset_url,
                expiry_text=(
                    f"链接将在 {self.settings.password_reset_ttl_minutes} 分钟后失效，且只能使用一次。"
                ),
                security_note="如果不是你发起的请求，忽略此邮件即可，当前密码不会改变。",
            ),
        )
        self._send(message)

    def _send(self, message: EmailMessage) -> None:
        tls_context = (
            ssl.create_default_context()
            if self.settings.smtp_use_ssl or self.settings.smtp_use_tls
            else None
        )
        if self.settings.smtp_use_ssl:
            client: smtplib.SMTP = smtplib.SMTP_SSL(
                self.settings.smtp_host,
                self.settings.smtp_port,
                timeout=SMTP_TIMEOUT_SECONDS,
                context=tls_context,
            )
        else:
            client = smtplib.SMTP(
                self.settings.smtp_host,
                self.settings.smtp_port,
                timeout=SMTP_TIMEOUT_SECONDS,
            )
        with client:
            if self.settings.smtp_use_tls:
                client.starttls(context=tls_context)
            if self.settings.smtp_user:
                client.login(self.settings.smtp_user, self.settings.smtp_password)
            client.send_message(message)


class ConsoleMailSender:
    """仅供本地开发时在终端显示一次性链接。"""

    def send_invitation(self, email: str, invitation_url: str) -> None:
        print(f"邀请邮箱: {email}")
        print(f"邀请链接: {invitation_url}")

    def send_password_reset(self, email: str, reset_url: str) -> None:
        print(f"重置邮箱: {email}")
        print(f"重置链接: {reset_url}")


def create_mail_sender(settings: Settings) -> MailSender:
    if settings.mail_provider == "smtp":
        return SmtpMailSender(settings)
    return ConsoleMailSender()
