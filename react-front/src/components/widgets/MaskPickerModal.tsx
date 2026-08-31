import React from "react";

import type { SegmentMaskResult } from "../../types/api";

export interface MaskPickerModalProps {
  masks: SegmentMaskResult[];
  onSelect: (maskId: string) => void;
  /** Hide the picker for now; segment job and candidates stay on the server. */
  onDefer: () => void;
  /** Discard this segment result and delete its candidate masks. */
  onDiscard: () => void;
}

const toDataUrl = (mask: SegmentMaskResult): string =>
  `data:image/${mask.format};base64,${mask.cutout_b64}`;

// Selecting a mask closes this modal immediately and fires inpainting detached
// (see useSessionJobs.selectMask). Backdrop click and "Not now" defer only;
// "Close" discards the unconsumed segment job via DELETE /jobs/{id}.
export const MaskPickerModal: React.FC<MaskPickerModalProps> = ({
  masks,
  onSelect,
  onDefer,
  onDiscard,
}) => {
  return (
    <div className="modal-backdrop" role="presentation" onClick={onDefer}>
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
          <div className="modal-head-actions">
            <button
              type="button"
              className="modal-close"
              onClick={(event) => {
                event.stopPropagation();
                onDefer();
              }}
            >
              Not now
            </button>
            <button
              type="button"
              className="modal-close is-danger"
              onClick={(event) => {
                event.stopPropagation();
                onDiscard();
              }}
            >
              Close
            </button>
          </div>
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
