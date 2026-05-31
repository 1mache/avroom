import React from "react";

import type { SegmentMaskOption } from "../../types/api";

export interface MaskPickerModalProps {
  masks: SegmentMaskOption[];
  selectedMaskId?: string | null;
  isInpainting: boolean;
  onSelect: (maskId: string) => void;
  onClose: () => void;
}

// Converts base64 cutout payload to a data URL for use as <img src>.
// Transparent (non-mask) pixels render against the CSS checkerboard background.
const toDataUrl = (mask: SegmentMaskOption): string => {
  return `data:image/${mask.format};base64,${mask.cutout_b64}`;
};

export const MaskPickerModal: React.FC<MaskPickerModalProps> = ({
  masks,
  selectedMaskId,
  isInpainting,
  onSelect,
  onClose,
}) => {
  // Backdrop click closes the modal, but not while inpainting is in progress —
  // dismissing mid-flight would leave the UI in an unrecoverable pending state.
  const handleBackdropClick: React.MouseEventHandler<HTMLDivElement> = () => {
    if (isInpainting) {
      return;
    }

    onClose();
  };

  return (
    // Full-screen backdrop intercepts outside clicks; inner modal stops propagation.
    <div className="mask-modal-backdrop" role="presentation" onClick={handleBackdropClick}>
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
            disabled={isInpainting}
            aria-label="Close mask picker"
          >
            Close
          </button>
        </div>

        {/* Grid of candidate masks returned by SAM. Each card shows the BGRA
            cutout — opaque where the object was segmented, transparent elsewhere.
            Clicking a card triggers inpainting for that mask immediately. */}
        <div className="mask-option-grid" aria-busy={isInpainting}>
          {masks.map((mask, index) => {
            const selected = selectedMaskId === mask.mask_id;
            return (
              <button
                key={mask.mask_id}
                type="button"
                className={`mask-option-card${selected ? " is-selected" : ""}`}
                onClick={() => onSelect(mask.mask_id)}
                disabled={isInpainting}
              >
                <span className="mask-option-label">
                  {/* Swap label text while the selected card's inpaint request is in flight. */}
                  {selected && isInpainting ? "Inpainting..." : `Option ${index + 1}`}
                </span>
                <span className="mask-option-preview">
                  <img src={toDataUrl(mask)} alt={`Mask option ${index + 1}`} />
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
};
