import React from "react";

import type { SegmentMaskResult } from "../../types/api";

export interface MaskPickerModalProps {
  masks: SegmentMaskResult[];
  onSelect: (maskId: string) => void;
  onClose: () => void;
}

const toDataUrl = (mask: SegmentMaskResult): string =>
  `data:image/${mask.format};base64,${mask.cutout_b64}`;

// Selecting a mask closes this modal immediately and fires inpainting detached
// (see useSessionJobs.selectMask) — the object appears as a pending row in the
// object rail while it runs. There is no in-flight state left for this modal
// to protect, so a backdrop click or Close always dismisses.
export const MaskPickerModal: React.FC<MaskPickerModalProps> = ({ masks, onSelect, onClose }) => {
  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="modal is-masks"
        role="dialog"
        aria-modal="true"
        aria-labelledby="mask-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="modal-head">
          <div>
            <h2 id="mask-title">Choose a cutout</h2>
            <p className="modal-sub">Removal starts as soon as you pick one.</p>
          </div>
          <button type="button" className="modal-close" onClick={onClose}>
            Close
          </button>
        </div>

        {/* Candidate masks from SAM: opaque where the object was segmented,
            transparent elsewhere, shown against a checkerboard. */}
        <div className="mask-grid">
          {masks.map((mask, index) => (
            <button
              key={mask.mask_id}
              type="button"
              className="mask-card"
              onClick={() => onSelect(mask.mask_id)}
            >
              <span className="mask-card-preview">
                <img src={toDataUrl(mask)} alt={`Cutout option ${index + 1}`} />
              </span>
              <span className="mask-card-label">{String(index + 1).padStart(2, "0")}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};
