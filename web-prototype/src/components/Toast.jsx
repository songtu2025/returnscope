import { CheckCircle, WarningCircle } from "@phosphor-icons/react";

import { classNames } from "../lib/presentation";

/** @param {{message: import("react").ReactNode, tone?: string}} props */
export function Toast({ message, tone }) {
  return (
    <div
      className={classNames("toast", tone)}
      role={tone === "error" ? "alert" : "status"}
      aria-live={tone === "error" ? "assertive" : "polite"}
    >
      {tone === "error" ? (
        <WarningCircle size={20} />
      ) : (
        <CheckCircle size={20} weight="fill" />
      )}
      {message}
    </div>
  );
}
