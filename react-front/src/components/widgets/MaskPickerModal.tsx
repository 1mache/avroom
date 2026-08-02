import React from "react";

import type { SegmentMaskOption } from "../../types/api";

export interface MaskPickerModalProps {
  masks: SegmentMaskOption[];
  onSelect: (maskId: string) => void;
  onClose: () => void;
}

// Converts base64 cutout payload to a data URL for use as <img src>.
// Transparent (non-mask) pixels render against the CSS checkerboard background.
const toDataUrl = (mask: SegmentMaskOption): string => {
  return `data:image/${mask.format};base64,${mask.cutout_b64}`;
};

// Selecting a mask closes this modal immediately and fires inpainting
// detached (see useSessionJobs.selectMask) — the object appears as a pending
// placeholder in ObjectPanel while it runs. There is no in-flight state left
// for this modal to protect, so a backdrop click or Close always dismisses.
export const MaskPickerModal: React.FC<MaskPickerModalProps> = ({ masks, onSelect, onClose }) => {
  return (
    // Full-screen backdrop intercepts outside clicks; inner modal stops propagation.
    <div className="mask-modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="mask-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="mask-modal-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mask-modal-header">
          <div>
            <h2 id="mask-modal-title">Choose mask</h2>
            <p>Pick best object cutout. Background inpaint starts after selection.</p>
          </div>

          <button
            type="button"
            className="error-modal-close"
            onClick={onClose}
            aria-label="Close mask picker"
          >
            Close
          </button>
        </div>

        {/* Grid of candidate masks returned by SAM. Each card shows the BGRA
            cutout — opaque where the object was segmented, transparent elsewhere.
            Clicking a card closes this modal and kicks off inpainting for that
            mask in the background. */}
        <div className="mask-option-grid">
          {masks.map((mask, index) => (
            <button
              key={mask.mask_id}
              type="button"
              className="mask-option-card"
              onClick={() => onSelect(mask.mask_id)}
            >
              <span className="mask-option-label">{`Option ${index + 1}`}</span>
              <span className="mask-option-preview">
                <img src={toDataUrl(mask)} alt={`Mask option ${index + 1}`} />
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};
