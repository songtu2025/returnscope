/** @typedef {{id: string, email: string, display_name: string, is_admin?: boolean}} CurrentUser */

export const PASSWORD_MIN_LENGTH = 12;

/** @param {string} email */
export function maskedEmail(email) {
  const [local = "", domain = ""] = email.split("@");
  const visible = local.slice(0, Math.min(2, local.length));
  return `${visible}${"*".repeat(Math.max(3, local.length - visible.length))}@${domain}`;
}
