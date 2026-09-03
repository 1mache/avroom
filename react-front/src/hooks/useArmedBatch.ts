import { useCallback, useEffect, useRef, useState } from "react";

import { eraseMask, runSessionBatch } from "../api/images";
import type { ArmedJob, ArmedJobAction, ArmedJobSource } from "../types/armedBatch";
import type { ClickPosition } from "../types/session";
import type { Size } from "../utils/stageGeometry";
import {
  actionsForSource,
  buildArmedBatchPlan,
  defaultCutAction,
} from "../utils/armedBatch";

let nextArmedJobId = 0;

function newArmedJobId(): string {
  nextArmedJobId += 1;
  return `armed-${nextArmedJobId}`;
}

export interface UseArmedBatchOptions {
  imageId: string | null;
  naturalSize: Size | null;
  autoGenerate3d: boolean;
  onMutated?: () => void;
  onError: (error: unknown, context: "inpaint" | "segment" | "generic") => void;
}

export function useArmedBatch({
  imageId,
  naturalSize,
  autoGenerate3d,
  onMutated,
  onError,
}: UseArmedBatchOptions) {
  const [batchMode, setBatchMode] = useState(false);
  const [jobs, setJobs] = useState<ArmedJob[]>([]);
  const [panelOpen, setPanelOpen] = useState(false);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [isApproving, setIsApproving] = useState(false);

  const batchModeRef = useRef(batchMode);
  batchModeRef.current = batchMode;
  const autoGenerate3dRef = useRef(autoGenerate3d);
  autoGenerate3dRef.current = autoGenerate3d;
  const imageIdRef = useRef(imageId);
  imageIdRef.current = imageId;

  useEffect(() => {
    if (jobs.length === 1) {
      setPanelOpen(true);
    }
  }, [jobs.length]);

  const appendJob = useCallback(
    (source: ArmedJobSource, action?: ArmedJobAction) => {
      const resolvedAction =
        action ??
        (source.kind === "lasso"
          ? "erase"
          : source.kind === "objects"
            ? "generate3d"
            : defaultCutAction(autoGenerate3dRef.current));
      const job: ArmedJob = {
        id: newArmedJobId(),
        source,
        action: resolvedAction,
      };
      setJobs((prev) => [...prev, job]);
      setSelectedJobId(job.id);
      return job.id;
    },
    [],
  );

  const appendClicks = useCallback(
    (points: ClickPosition[]) => {
      if (points.length === 0) {
        return;
      }
      appendJob({ kind: "clicks", points: [...points] });
    },
    [appendJob],
  );

  const removeJob = useCallback((id: string) => {
    setJobs((prev) => prev.filter((job) => job.id !== id));
    setSelectedJobId((current) => (current === id ? null : current));
  }, []);

  const setJobAction = useCallback((id: string, action: ArmedJobAction) => {
    setJobs((prev) =>
      prev.map((job) => {
        if (job.id !== id) {
          return job;
        }
        const allowed = actionsForSource(job.source);
        if (!allowed.includes(action)) {
          return job;
        }
        return { ...job, action };
      }),
    );
  }, []);

  const moveJob = useCallback((id: string, direction: "up" | "down") => {
    setJobs((prev) => {
      const index = prev.findIndex((job) => job.id === id);
      if (index < 0) {
        return prev;
      }
      const target = direction === "up" ? index - 1 : index + 1;
      if (target < 0 || target >= prev.length) {
        return prev;
      }
      const next = [...prev];
      const [row] = next.splice(index, 1);
      next.splice(target, 0, row);
      return next;
    });
  }, []);

  const clearJobs = useCallback(() => {
    setJobs([]);
    setSelectedJobId(null);
  }, []);

  const approve = useCallback(async () => {
    const currentImageId = imageIdRef.current;
    if (!currentImageId || !naturalSize || isApproving || jobs.length === 0) {
      return;
    }

    const plan = buildArmedBatchPlan(jobs, naturalSize);
    if (plan.length === 0) {
      return;
    }

    setIsApproving(true);
    const consumed = new Set<string>();

    try {
      for (const entry of plan) {
        if (entry.step.kind === "erase") {
          await eraseMask({
            image_id: currentImageId,
            mask_b64: entry.step.maskB64,
          });
        } else {
          await runSessionBatch(currentImageId, entry.step.payload);
        }
        for (const jobId of entry.jobIds) {
          consumed.add(jobId);
        }
        if (imageIdRef.current === currentImageId) {
          onMutated?.();
        }
      }
      if (imageIdRef.current === currentImageId) {
        setJobs((prev) => {
          const next = prev.filter((job) => !consumed.has(job.id));
          if (next.length === 0) {
            setSelectedJobId(null);
          }
          return next;
        });
      }
    } catch (err) {
      if (imageIdRef.current === currentImageId) {
        setJobs((prev) => prev.filter((job) => !consumed.has(job.id)));
        onError(err, "inpaint");
      }
    } finally {
      if (imageIdRef.current === currentImageId) {
        setIsApproving(false);
      }
    }
  }, [isApproving, jobs, naturalSize, onError, onMutated]);

  return {
    batchMode,
    setBatchMode,
    batchModeRef,
    jobs,
    panelOpen,
    setPanelOpen,
    selectedJobId,
    setSelectedJobId,
    isApproving,
    appendJob,
    appendClicks,
    removeJob,
    setJobAction,
    moveJob,
    clearJobs,
    approve,
  };
}
