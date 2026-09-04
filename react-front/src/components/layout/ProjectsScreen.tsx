import React, { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, getActiveJobs } from "../../api/images";
import { createProject, deleteProject, exportProject, getProjects, importProject, renameProject } from "../../api/projects";
import avroomLogo from "../../assets/avroom.png";
import { useAuth } from "../../context/AuthContext";
import type { JobInfo, ProjectInfo } from "../../types/api";
import { byMostRecentlyEdited } from "../../utils/time";
import { triggerBlobDownload } from "../../utils/preview";
import { ProjectCard } from "../dashboard/ProjectCard";
import { FlaskIcon, LogoutIcon, PlusIcon, UploadIcon } from "../icons";
import { ConfirmDialog } from "../widgets/ConfirmDialog";

function archiveDownloadFilename(name: string): string {
  const base = (name.trim() || "project").replace(/[<>:"/\\|?*]/g, "_").slice(0, 80);
  return `${base}.avroom.zip`;
}

// Same cadence as the Rooms dashboard's job poll (see DashboardScreen) --
// cheap, one endpoint for every session regardless of project.
const JOBS_POLL_INTERVAL_MS = 5000;

export interface ProjectsScreenProps {
  onOpenProject: (project: ProjectInfo) => void;
  onOpenDebug: () => void;
}

type LoadState = "loading" | "ready" | "offline";

/**
 * Home screen: the top of the hierarchy (`User -> Project -> Room`). Starting
 * a project, reopening one, renaming or deleting one. Rooms live one level
 * down, in DashboardScreen.
 */
export const ProjectsScreen: React.FC<ProjectsScreenProps> = ({ onOpenProject, onOpenDebug }) => {
  const { user, logout } = useAuth();
  const [projects, setProjects] = useState<ProjectInfo[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [activeJobs, setActiveJobs] = useState<JobInfo[]>([]);

  const [isCreating, setIsCreating] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createBusy, setCreateBusy] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const [renameTarget, setRenameTarget] = useState<ProjectInfo | null>(null);
  const [renameName, setRenameName] = useState("");
  const [renameBusy, setRenameBusy] = useState(false);
  const [renameError, setRenameError] = useState<string | null>(null);

  const [deleteTarget, setDeleteTarget] = useState<ProjectInfo | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [exportingId, setExportingId] = useState<string | null>(null);
  const [importBusy, setImportBusy] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const importInputRef = useRef<HTMLInputElement | null>(null);

  const load = useCallback(async () => {
    try {
      const list = await getProjects();
      setProjects([...list].sort(byMostRecentlyEdited));
      setLoadState("ready");
    } catch {
      setLoadState("offline");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const jobs = await getActiveJobs();
        if (!cancelled) {
          setActiveJobs(jobs);
        }
      } catch {
        // Non-fatal — next tick tries again.
      }
    };
    void poll();
    const interval = setInterval(() => void poll(), JOBS_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  const handleCreate = useCallback(async () => {
    const name = createName.trim();
    if (!name) {
      return;
    }
    setCreateBusy(true);
    setCreateError(null);
    try {
      const project = await createProject(name);
      setProjects((prev) => [...prev, project].sort(byMostRecentlyEdited));
      setIsCreating(false);
      setCreateName("");
    } catch (createErr) {
      setCreateError(createErr instanceof Error ? createErr.message : "Failed to create the project.");
    } finally {
      setCreateBusy(false);
    }
  }, [createName]);

  const handleRename = useCallback(async () => {
    const name = renameName.trim();
    if (!renameTarget || !name) {
      return;
    }
    setRenameBusy(true);
    setRenameError(null);
    try {
      const updated = await renameProject(renameTarget.id, name);
      setProjects((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
      setRenameTarget(null);
    } catch (renameErr) {
      setRenameError(renameErr instanceof Error ? renameErr.message : "Failed to rename the project.");
    } finally {
      setRenameBusy(false);
    }
  }, [renameName, renameTarget]);

  const handleExport = useCallback(async (project: ProjectInfo) => {
    setExportingId(project.id);
    try {
      const blob = await exportProject(project.id);
      triggerBlobDownload(blob, archiveDownloadFilename(project.name));
    } catch (exportErr) {
      setError(exportErr instanceof Error ? exportErr.message : "Failed to export the project.");
    } finally {
      setExportingId(null);
    }
  }, []);

  const handleImportFile = useCallback(async (file: File) => {
    setImportBusy(true);
    setImportError(null);
    try {
      const project = await importProject(file);
      setProjects((prev) => [...prev, project].sort(byMostRecentlyEdited));
    } catch (importErr) {
      // 422 is a malformed/unsupported archive -- a normal answer, same as
      // UploadScreen's photo-validation rejection. Anything else is a
      // genuine failure and goes to the shared error dialog instead.
      if (importErr instanceof ApiError && importErr.status === 422) {
        setImportError(importErr.detail || "That file isn't a valid AVRoom project export.");
      } else {
        setError(importErr instanceof Error ? importErr.message : "Failed to import the project.");
      }
    } finally {
      setImportBusy(false);
    }
  }, []);

  const handleImportInputChange: React.ChangeEventHandler<HTMLInputElement> = useCallback(
    (event) => {
      const picked = event.target.files?.[0];
      event.target.value = "";
      if (picked) {
        void handleImportFile(picked);
      }
    },
    [handleImportFile],
  );

  const handleConfirmDelete = useCallback(async () => {
    if (!deleteTarget) {
      return;
    }
    setIsDeleting(true);
    try {
      await deleteProject(deleteTarget.id);
      setProjects((prev) => prev.filter((p) => p.id !== deleteTarget.id));
      setDeleteTarget(null);
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Failed to delete the project.");
    } finally {
      setIsDeleting(false);
    }
  }, [deleteTarget]);

  return (
    <div className="dashboard">
      <header className="dash-header">
        <img src={avroomLogo} alt="" className="dash-logo" />
        <span className="dash-wordmark">AVRoom</span>
        <div className="dash-header-end">
          {user?.is_admin && (
            <button
              type="button"
              className="tool-btn"
              onClick={onOpenDebug}
              aria-label="Pipeline debug"
              data-tip="Pipeline debug"
            >
              <FlaskIcon />
            </button>
          )}
          <button type="button" className="tool-btn" onClick={logout} aria-label="Sign out" data-tip="Sign out">
            <LogoutIcon />
          </button>
        </div>
      </header>

      <main className="dash-main">
        <div className="new-session-row">
          <button type="button" className="new-session" onClick={() => setIsCreating(true)}>
            <span className="new-session-mark">
              <PlusIcon size={22} />
            </span>
            <span className="new-session-label">New project</span>
            <span className="new-session-hint">Groups rooms together</span>
          </button>
          <button
            type="button"
            className="new-session-import-btn"
            onClick={() => importInputRef.current?.click()}
            disabled={importBusy}
            aria-label="Import project"
            data-tip="Import project from a zip"
          >
            {importBusy ? <span className="tool-spinner" /> : <UploadIcon size={18} />}
          </button>
          <input
            ref={importInputRef}
            type="file"
            accept=".zip"
            className="file-input"
            onChange={handleImportInputChange}
          />
        </div>
        {importError ? <p className="upload-rejection">{importError}</p> : null}

        <div className="dash-eyebrow">
          <span className="dash-eyebrow-title">Projects</span>
          {loadState === "ready" && projects.length > 0 ? (
            <span className="dash-eyebrow-count">{String(projects.length).padStart(2, "0")}</span>
          ) : null}
        </div>

        <div className="session-scroll">
          {loadState === "loading" ? (
            <div className="project-list">
              <div className="project-row-skeleton" />
              <div className="project-row-skeleton" />
              <div className="project-row-skeleton" />
            </div>
          ) : loadState === "offline" ? (
            <div className="dash-note">
              <p className="dash-note-line">No answer from the image service</p>
              <button type="button" className="btn" onClick={() => void load()}>
                Try again
              </button>
            </div>
          ) : projects.length === 0 ? (
            <div className="dash-note">
              <p className="dash-note-line">Nothing here yet</p>
              <p className="dash-note-hint">Start a project to group the rooms you upload.</p>
            </div>
          ) : (
            <div className="project-list">
              {projects.map((project) => {
                const projectJobs = activeJobs.filter((job) => job.project_id === project.id);
                return (
                  <ProjectCard
                    key={project.id}
                    project={project}
                    isBusy={projectJobs.some((job) => job.status === "queued" || job.status === "running")}
                    isFailed={projectJobs.some((job) => job.status === "failed" || job.status === "conflict")}
                    isExporting={exportingId === project.id}
                    onOpen={onOpenProject}
                    onRequestRename={(target) => {
                      setRenameTarget(target);
                      setRenameName(target.name);
                      setRenameError(null);
                    }}
                    onRequestDelete={setDeleteTarget}
                    onRequestExport={(target) => void handleExport(target)}
                  />
                );
              })}
            </div>
          )}
        </div>
      </main>

      {isCreating ? (
        <ConfirmDialog
          title="New project"
          body={
            <input
              type="text"
              className="session-name"
              value={createName}
              onChange={(event) => setCreateName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void handleCreate();
              }}
              placeholder="Project name"
              autoFocus
            />
          }
          confirmLabel="Create"
          busy={createBusy}
          onConfirm={() => void handleCreate()}
          onCancel={() => {
            setIsCreating(false);
            setCreateName("");
            setCreateError(null);
          }}
        />
      ) : null}
      {createError ? <p className="upload-rejection">{createError}</p> : null}

      {renameTarget ? (
        <ConfirmDialog
          title="Rename project"
          body={
            <input
              type="text"
              className="session-name"
              value={renameName}
              onChange={(event) => setRenameName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void handleRename();
              }}
              placeholder="Project name"
              autoFocus
            />
          }
          confirmLabel="Rename"
          busy={renameBusy}
          onConfirm={() => void handleRename()}
          onCancel={() => setRenameTarget(null)}
        />
      ) : null}
      {renameError ? <p className="upload-rejection">{renameError}</p> : null}

      {deleteTarget ? (
        <ConfirmDialog
          title="Delete this project?"
          body={
            <>
              <strong>{deleteTarget.name}</strong> and its {deleteTarget.room_count}{" "}
              {deleteTarget.room_count === 1 ? "room" : "rooms"} will be permanently deleted. This
              can&rsquo;t be undone.
            </>
          }
          confirmLabel="Delete project"
          destructive
          busy={isDeleting}
          onConfirm={() => void handleConfirmDelete()}
          onCancel={() => setDeleteTarget(null)}
        />
      ) : null}

      {error ? (
        <div className="modal-backdrop" role="presentation" onClick={() => setError(null)}>
          <div
            className="modal is-error"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="proj-error-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="modal-head">
              <h2 id="proj-error-title">Request failed</h2>
              <button type="button" className="modal-close" onClick={() => setError(null)}>
                Close
              </button>
            </div>
            <pre className="modal-body">{error}</pre>
          </div>
        </div>
      ) : null}
    </div>
  );
};
