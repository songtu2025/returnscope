import { useEffect, useState } from "react";
import { EnvelopeSimple } from "@phosphor-icons/react";
import { api } from "../../api";
import { navigateHash } from "../../app/hashRouter";
import { InlineLoading } from "../../components/SharedUi";
import { InvalidLinkCard } from "./AuthUi";
import { FormError } from "./AuthUi";
import { errorMessage } from "../../shared/api/requestErrors";
import { maskedEmail } from "./authPresentation";

/** @param {{token: string, onSessionEnded: () => void}} props */
export function ChangeEmailPage({ token, onSessionEnded }) {
  const [state, setState] = useState(
    /** @type {"loading" | "valid" | "invalid"} */ ("loading"),
  );
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let active = true;
    if (!token) {
      setState("invalid");
      return () => {
        active = false;
      };
    }
    api
      .validateEmailChange(token)
      .then((result) => {
        if (!active) return;
        setEmail(result.email);
        setState("valid");
      })
      .catch(() => active && setState("invalid"));
    return () => {
      active = false;
    };
  }, [token]);

  const complete = async () => {
    setSubmitting(true);
    setError("");
    try {
      await api.completeEmailChange(token);
      onSessionEnded();
      navigateHash("login", { notice: "email-changed" }, { replace: true });
    } catch (requestError) {
      setError(errorMessage(requestError));
      setSubmitting(false);
    }
  };

  if (state === "loading") {
    return <InlineLoading label="正在验证邮箱修改链接…" />;
  }
  if (state === "invalid") {
    return (
      <InvalidLinkCard
        title="邮箱验证链接不可用"
        description="该链接可能已过期、已使用或已被新请求替代。"
      />
    );
  }

  return (
    <section
      className="login-card auth-result-card"
      aria-labelledby="email-change-title"
    >
      <div className="login-icon">
        <EnvelopeSimple size={24} />
      </div>
      <p className="eyebrow">账号安全</p>
      <h2 id="email-change-title">确认修改登录邮箱</h2>
      <p>
        登录邮箱将修改为 <b>{maskedEmail(email)}</b>
        。完成后所有设备需要使用新邮箱重新登录。
      </p>
      <FormError message={error} />
      <button
        className="primary-button auth-full-button"
        disabled={submitting}
        onClick={complete}
      >
        {submitting ? "正在修改…" : "确认修改邮箱"}
      </button>
      <button
        type="button"
        className="auth-back-action"
        onClick={() => navigateHash("login")}
      >
        暂不修改
      </button>
    </section>
  );
}
