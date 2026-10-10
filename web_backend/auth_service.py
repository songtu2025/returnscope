"""组合邀请、注册、密码重置和邮箱变更能力。"""

from web_backend.authentication.contracts import AuthServiceError as AuthServiceError
from web_backend.authentication.email_change import EmailChangeActions
from web_backend.authentication.invitations import InvitationActions
from web_backend.authentication.password_reset import PasswordResetActions
from web_backend.authentication.registration import RegistrationActions


class AuthService(
    InvitationActions,
    RegistrationActions,
    PasswordResetActions,
    EmailChangeActions,
):
    """沿用统一服务入口与认证上下文，各流程独立维护。"""
