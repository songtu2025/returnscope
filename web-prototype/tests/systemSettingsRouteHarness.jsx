import { vi } from "vitest";
import { useHashRoute } from "../src/app/hashRouter";
import { SystemSettingsPage } from "../src/features/system-settings/SystemSettingsPage";

export function SystemSettingsRouteHarness() {
  const { route } = useHashRoute();
  return (
    <SystemSettingsPage
      route={route}
      notify={vi.fn()}
      currentUser={{ id: "user-1", is_admin: true }}
    />
  );
}
