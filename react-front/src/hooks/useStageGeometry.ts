import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type React from "react";

import { getContainedImageRect } from "../utils/stageGeometry";
import type { Size } from "../utils/stageGeometry";

/**
 * Where the Origin Photo actually is on screen.
 *
 * The photo is drawn `object-fit: contain`, so its rendered box is neither
 * the stage box nor the image's natural size — it is whatever letterboxed
 * rect those two produce together. Almost every interaction on the stage
 * needs that rect, so it is derived in one place and re-derived whenever
 * either input changes (the stage resizes, or a different photo loads).
 *
 * @param sessionId Re-observes the stage when the room changes.
 */
export function useStageGeometry(sessionId: string) {
  const stageRef = useRef<HTMLDivElement>(null);
  const [naturalSize, setNaturalSize] = useState<Size | null>(null);
  const [stageSize, setStageSize] = useState<Size | null>(null);

  const measureStage = useCallback(() => {
    const stage = stageRef.current;
    if (!stage) {
      return;
    }

    const next = { width: stage.clientWidth, height: stage.clientHeight };
    // Same-size writes are dropped: a ResizeObserver fires on every layout
    // pass, and a fresh object each time would re-render the whole stage.
    setStageSize((previous) =>
      previous && previous.width === next.width && previous.height === next.height
        ? previous
        : next,
    );
  }, []);

  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) {
      return;
    }

    measureStage();
    const observer = new ResizeObserver(measureStage);
    observer.observe(stage);
    return () => observer.disconnect();
  }, [measureStage, sessionId]);

  /** Wire to the photo's `onLoad`: its natural size is only known then. */
  const handleImageLoad: React.ReactEventHandler<HTMLImageElement> = useCallback(
    (event) => {
      setNaturalSize({
        width: event.currentTarget.naturalWidth,
        height: event.currentTarget.naturalHeight,
      });
      measureStage();
    },
    [measureStage],
  );

  const renderedRect = useMemo(
    () => (stageSize && naturalSize ? getContainedImageRect(stageSize, naturalSize) : null),
    [stageSize, naturalSize],
  );

  return { stageRef, naturalSize, renderedRect, handleImageLoad };
}
