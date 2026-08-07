import React, { useCallback, useState } from "react";

import { DashboardScreen } from "./components/layout/DashboardScreen";
import { UploadScreen } from "./components/layout/UploadScreen";
import { WorkspaceScreen } from "./components/layout/WorkspaceScreen";

// Two screens and the upload step between them. Not enough surface to justify
// a router: the dashboard is home, and the workspace is always entered with a
// session already chosen.
type Route =
  | { screen: "dashboard" }
  | { screen: "upload" }
  | { screen: "workspace"; uid: string };

export const App: React.FC = () => {
  const [route, setRoute] = useState<Route>({ screen: "dashboard" });

  const openSession = useCallback((uid: string) => setRoute({ screen: "workspace", uid }), []);
  const goToDashboard = useCallback(() => setRoute({ screen: "dashboard" }), []);

  if (route.screen === "workspace") {
    // Keyed by uid so switching sessions remounts the workspace rather than
    // leaving one session's objects, geometry and in-flight jobs behind.
    return <WorkspaceScreen key={route.uid} uid={route.uid} onExit={goToDashboard} />;
  }

  if (route.screen === "upload") {
    return <UploadScreen onCancel={goToDashboard} onUploaded={openSession} />;
  }

  return (
    <DashboardScreen
      onOpenSession={openSession}
      onNewSession={() => setRoute({ screen: "upload" })}
    />
  );
};
