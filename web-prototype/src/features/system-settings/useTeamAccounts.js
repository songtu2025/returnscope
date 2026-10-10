import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api";
import { errorMessage } from "../../shared/api/requestErrors";
/** @typedef {import("../../shared/api/systemSettingsContracts").TeamUser} TeamUser */
/** @typedef {import("../../shared/api/systemSettingsContracts").TeamInvitation} TeamInvitation */

/** @param {(message: string, tone?: string) => void} notify */
export function useTeamAccounts(notify) {
  const [users, setUsers] = useState(/** @type {TeamUser[]} */ ([]));
  const [invitations, setInvitations] = useState(/** @type {TeamInvitation[]} */ ([]));
  const [loadState, setLoadState] = useState(
    /** @type {"loading" | "ready" | "error"} */ ("loading"),
  );
  const [loadError, setLoadError] = useState("");
  const hasLoadedUsers = useRef(false);
  const load = useCallback(async () => {
    const isInitialLoad = !hasLoadedUsers.current;
    if (isInitialLoad) {
      setLoadState("loading");
      setLoadError("");
    }
    try {
      const [userValues, invitationValues] = await Promise.all([
        api.users(),
        api.invitations(),
      ]);
      setUsers(userValues);
      setInvitations(invitationValues);
      hasLoadedUsers.current = true;
      setLoadState("ready");
      setLoadError("");
    } catch (error) {
      if (isInitialLoad) {
        setLoadState("error");
        setLoadError(errorMessage(error));
      }
      throw error;
    }
  }, []);
  useEffect(() => {
    load().catch((error) => notify(error.message, "error"));
  }, [load, notify]);
  return { users, invitations, loadState, loadError, load };
}
