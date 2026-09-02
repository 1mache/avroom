import React, { useCallback, useState } from "react";

import { AuthScreen } from "./components/layout/AuthScreen";
import { DashboardScreen } from "./components/layout/DashboardScreen";
import { DebugScreen } from "./components/layout/DebugScreen";
import { UploadScreen } from "./components/layout/UploadScreen";
import { WorkspaceScreen } from "./components/layout/WorkspaceScreen";
import { AuthProvider, useAuth } from "./context/AuthContext";

// Two screens, the upload step, and the pipeline debug screen. Not enough
// surface to justify a router: the dashboard is home, and every other screen
// is always entered from it.
type Route =
  | { screen: "dashboard" }
  | { screen: "upload" }
  | { screen: "workspace"; uid: string }
  | { screen: "debug" };

const AppShell: React.FC = () => {
  const { status } = useAuth();
  const [route, setRoute] = useState<Route>({ screen: "dashboard" });

  const openSession = useCallback((uid: string) => setRoute({ screen: "workspace", uid }), []);
  const goToDashboard = useCallback(() => setRoute({ screen: "dashboard" }), []);

  // "checking" resolves near-instantly (one GET /auth/me) — no spinner is
  // worth the flash it would add.
  if (status === "checking") {
    return <div className="dashboard" />;
  }

  if (status === "anon") {
    return <AuthScreen />;
  }

  if (route.screen === "workspace") {
    // Keyed by uid so switching sessions remounts the workspace rather than
    // leaving one session's objects, geometry and in-flight jobs behind.
    return <WorkspaceScreen key={route.uid} uid={route.uid} onExit={goToDashboard} />;
  }

  if (route.screen === "upload") {
    return <UploadScreen onCancel={goToDashboard} onUploaded={openSession} />;
  }

  if (route.screen === "debug") {
    return <DebugScreen onExit={goToDashboard} />;
  }

  return (
    <DashboardScreen
      onOpenSession={openSession}
      onNewSession={() => setRoute({ screen: "upload" })}
      onOpenDebug={() => setRoute({ screen: "debug" })}
    />
  );
};

export const App: React.FC = () => (
  <AuthProvider>
    <AppShell />
  </AuthProvider>
);
