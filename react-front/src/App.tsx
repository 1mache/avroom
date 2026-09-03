import React, { useCallback, useState } from "react";

import { AuthScreen } from "./components/layout/AuthScreen";
import { DashboardScreen } from "./components/layout/DashboardScreen";
import { DebugScreen } from "./components/layout/DebugScreen";
import { ProjectsScreen } from "./components/layout/ProjectsScreen";
import { UploadScreen } from "./components/layout/UploadScreen";
import { WorkspaceScreen } from "./components/layout/WorkspaceScreen";
import { AuthProvider, useAuth } from "./context/AuthContext";
import type { ProjectInfo } from "./types/api";

// Projects dashboard is home; a project opens its rooms dashboard; a room
// opens the workspace. Not enough surface to justify a router: every screen
// below Projects is always entered from the one above it.
type Route =
  | { screen: "projects" }
  | { screen: "rooms"; projectId: string; projectName: string }
  | { screen: "upload"; projectId: string; projectName: string }
  | { screen: "workspace"; uid: string; projectId: string; projectName: string }
  | { screen: "debug" };

const AppShell: React.FC = () => {
  const { status } = useAuth();
  const [route, setRoute] = useState<Route>({ screen: "projects" });

  const openProject = useCallback(
    (project: ProjectInfo) => setRoute({ screen: "rooms", projectId: project.id, projectName: project.name }),
    [],
  );
  const goToProjects = useCallback(() => setRoute({ screen: "projects" }), []);

  // "checking" resolves near-instantly (one GET /auth/me) — no spinner is
  // worth the flash it would add.
  if (status === "checking") {
    return <div className="dashboard" />;
  }

  if (status === "anon") {
    return <AuthScreen />;
  }

  if (route.screen === "workspace") {
    const { projectId, projectName, uid } = route;
    // Keyed by uid so switching sessions remounts the workspace rather than
    // leaving one session's objects, geometry and in-flight jobs behind.
    return (
      <WorkspaceScreen
        key={uid}
        uid={uid}
        onExit={() => setRoute({ screen: "rooms", projectId, projectName })}
      />
    );
  }

  if (route.screen === "upload") {
    const { projectId, projectName } = route;
    return (
      <UploadScreen
        projectId={projectId}
        onCancel={() => setRoute({ screen: "rooms", projectId, projectName })}
        onUploaded={(uid) => setRoute({ screen: "workspace", uid, projectId, projectName })}
      />
    );
  }

  if (route.screen === "debug") {
    return <DebugScreen onExit={goToProjects} />;
  }

  if (route.screen === "rooms") {
    const { projectId, projectName } = route;
    return (
      <DashboardScreen
        key={projectId}
        projectId={projectId}
        projectName={projectName}
        onOpenSession={(uid) => setRoute({ screen: "workspace", uid, projectId, projectName })}
        onNewSession={() => setRoute({ screen: "upload", projectId, projectName })}
        onBack={goToProjects}
      />
    );
  }

  return <ProjectsScreen onOpenProject={openProject} onOpenDebug={() => setRoute({ screen: "debug" })} />;
};

export const App: React.FC = () => (
  <AuthProvider>
    <AppShell />
  </AuthProvider>
);
