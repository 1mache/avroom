import React, { useState } from "react";

import { sessionPreviewUrl } from "../../api/images";
import type { ProjectInfo } from "../../types/api";
import { formatEditedAgo } from "../../utils/time";
import { DownloadIcon, PencilIcon, PhotoIcon, TrashIcon } from "../icons";

export interface ProjectCardProps {
  project: ProjectInfo;
  isBusy?: boolean;
  isFailed?: boolean;
  isExporting?: boolean;
  onOpen: (project: ProjectInfo) => void;
  onRequestRename: (project: ProjectInfo) => void;
  onRequestDelete: (project: ProjectInfo) => void;
  onRequestExport: (project: ProjectInfo) => void;
}

/**
 * One project, shown as a horizontal row -- a folder in a list, not a photo
 * in a grid. Borrows its thumbnail from the project's most recently edited
 * room, same as before, just at filmstrip size instead of full tile width.
 */
export const ProjectCard: React.FC<ProjectCardProps> = ({
  project,
  isBusy = false,
  isFailed = false,
  isExporting = false,
  onOpen,
  onRequestRename,
  onRequestDelete,
  onRequestExport,
}) => {
  const [previewFailed, setPreviewFailed] = useState(false);
  const editedAgo = formatEditedAgo(project.last_changed);
  const roomLabel = project.room_count === 1 ? "1 room" : `${project.room_count} rooms`;

  return (
    <div className="project-row">
      <button
        type="button"
        className="project-row-frame"
        onClick={() => onOpen(project)}
        aria-label={`Open ${project.name}`}
      >
        {(isFailed || isBusy) && (
          <span
            className={`project-row-dot${isFailed ? " is-failed" : ""}`}
            aria-label={isFailed ? "A job in this project failed" : "This project has work in progress"}
            data-tip={isFailed ? "A job failed" : "Working…"}
          />
        )}
        {previewFailed || !project.preview_uid ? (
          <span className="project-row-placeholder">
            <PhotoIcon size={16} />
          </span>
        ) : (
          <img
            src={sessionPreviewUrl(project.preview_uid, project.last_changed)}
            alt=""
            className="project-row-preview"
            onError={() => setPreviewFailed(true)}
            draggable={false}
          />
        )}
      </button>

      <button type="button" className="project-row-body" onClick={() => onOpen(project)}>
        <span className="project-row-name" title={project.name}>
          {project.name}
        </span>
        <span className="project-row-meta">
          {roomLabel} · {editedAgo ?? "never edited"}
        </span>
      </button>

      <div className="project-row-actions">
        <button
          type="button"
          className="project-row-btn"
          onClick={() => onRequestExport(project)}
          disabled={isExporting}
          aria-label={`Export ${project.name}`}
          data-tip="Export project"
        >
          {isExporting ? <span className="tool-spinner" /> : <DownloadIcon size={13} />}
        </button>
        <button
          type="button"
          className="project-row-btn"
          onClick={() => onRequestRename(project)}
          aria-label={`Rename ${project.name}`}
          data-tip="Rename project"
        >
          <PencilIcon size={13} />
        </button>
        <button
          type="button"
          className="project-row-btn is-danger"
          onClick={() => onRequestDelete(project)}
          aria-label={`Delete ${project.name}`}
          data-tip="Delete project"
        >
          <TrashIcon size={14} />
        </button>
      </div>
    </div>
  );
};
