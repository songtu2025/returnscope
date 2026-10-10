import { navigateHash } from "../app/hashRouter";
import { ForgotPasswordPage } from "../features/authentication/ForgotPasswordPage";
import { RegisterPage } from "../features/authentication/RegisterPage";
import { ResetPasswordPage } from "../features/authentication/ResetPasswordPage";
import { ChangeEmailPage } from "../features/authentication/ChangeEmailPage";
import { LoginPage } from "../features/authentication/LoginPage";
import { AuthShell } from "../features/authentication/AuthUi";

/** @typedef {import("../features/authentication/authPresentation").CurrentUser} CurrentUser */
/** @typedef {{page: string, query: Record<string, string | undefined>}} AuthRoute */

/** @param {{route: AuthRoute, onLogin: (user: CurrentUser) => void, onSessionEnded?: () => void}} props */
export function AuthPages({ route, onLogin, onSessionEnded = () => {} }) {
  let content;
  if (route.page === "forgot-password") {
    content = <ForgotPasswordPage />;
  } else if (route.page === "register") {
    content = <RegisterPage token={route.query.token ?? ""} onLogin={onLogin} />;
  } else if (route.page === "reset-password") {
    content = <ResetPasswordPage token={route.query.token ?? ""} />;
  } else if (route.page === "change-email") {
    content = (
      <ChangeEmailPage
        token={route.query.token ?? ""}
        onSessionEnded={onSessionEnded}
      />
    );
  } else {
    content = (
      <LoginPage
        onLogin={(user) => {
          if (route.page === "login") {
            navigateHash("workbench", {}, { replace: true });
          }
          onLogin(user);
        }}
        notice={
          route.query.notice === "password-reset"
            ? "密码已重置，请使用新密码登录。"
            : route.query.notice === "email-changed"
              ? "登录邮箱已更新，请使用新邮箱登录。"
              : ""
        }
      />
    );
  }
  return <AuthShell>{content}</AuthShell>;
}
