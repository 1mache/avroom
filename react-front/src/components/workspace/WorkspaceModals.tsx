import { ConfirmDialog } from "../widgets/ConfirmDialog";
import { MaskPickerModal } from "../widgets/MaskPickerModal";
import type { SegmentMaskResult } from "../../types/api";
import type { CutoutObject } from "../../types/session";

export interface WorkspaceModalsProps {
  /** Mask candidates awaiting a choice, or null when the picker is closed. */
  maskPicker: {
    masks: SegmentMaskResult[];
    onSelect: (maskId: string) => void;
    onDefer: () => void;
    onDiscard: () => void;
  } | null;
  /** Object the user asked to delete, held until they confirm. */
  pendingDelete: {
    object: CutoutObject;
    busy: boolean;
    onConfirm: () => void;
    onCancel: () => void;
  } | null;
  /** Last unrecoverable error, shown verbatim. */
  error: string | null;
  onDismissError: () => void;
}

/**
 * The three things that sit above the whole workspace.
 *
 * Grouped because they share exactly one property -- being modal -- and
 * because keeping them together makes it obvious at a glance that the
 * workspace has three, not five or one.
 */
export const WorkspaceModals: React.FC<WorkspaceModalsProps> = ({
  maskPicker,
  pendingDelete,
  error,
  onDismissError,
}) => (
  <>
    {maskPicker ? (
      <MaskPickerModal
        masks={maskPicker.masks}
        onSelect={maskPicker.onSelect}
        onDefer={maskPicker.onDefer}
        onDiscard={maskPicker.onDiscard}
      />
    ) : null}

    {pendingDelete ? (
      <ConfirmDialog
        title="Delete this object?"
        body={
          <>
            <strong>
              {pendingDelete.object.name ?? `Object ${pendingDelete.object.objectId}`}
            </strong>{" "}
            will be removed for good. The background keeps its spot filled in — this can&rsquo;t
            be undone.
          </>
        }
        confirmLabel="Delete"
        destructive
        busy={pendingDelete.busy}
        onConfirm={pendingDelete.onConfirm}
        onCancel={pendingDelete.onCancel}
      />
    ) : null}

    {error ? (
      <div className="modal-backdrop" role="presentation" onClick={onDismissError}>
        <div
          className="modal is-error"
          role="alertdialog"
          aria-modal="true"
          aria-labelledby="error-title"
          onClick={(event) => event.stopPropagation()}
        >
          <div className="modal-head">
            <h2 id="error-title">Request failed</h2>
            <button type="button" className="modal-close" onClick={onDismissError}>
              Close
            </button>
          </div>
          <pre className="modal-body">{error}</pre>
        </div>
      </div>
    ) : null}
  </>
);
