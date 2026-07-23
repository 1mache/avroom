import React, { useCallback } from "react";

const EyeOpenIcon: React.FC = () => (
  <svg viewBox="0 0 24 24" width="14" height="14" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path
      d="M2 12C2 12 5.5 5.5 12 5.5C18.5 5.5 22 12 22 12C22 12 18.5 18.5 12 18.5C5.5 18.5 2 12 2 12Z"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <circle cx="12" cy="12" r="2.75" stroke="currentColor" strokeWidth="1.5" />
  </svg>
);

const EyeOffIcon: React.FC = () => (
  <svg viewBox="0 0 24 24" width="14" height="14" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path
      d="M2 12C2 12 5.5 5.5 12 5.5C18.5 5.5 22 12 22 12C22 12 18.5 18.5 12 18.5C5.5 18.5 2 12 2 12Z"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
    <circle cx="12" cy="12" r="2.75" stroke="currentColor" strokeWidth="1.5" />
    <line x1="4" y1="4" x2="20" y2="20" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
);

interface ObjectEntry {
  objectId: number;
  cutoutSrc: string;
  hidden: boolean;
}

interface ObjectPanelProps {
  objects: ObjectEntry[];
  selectedObjectId: number | null;
  isAddingObject: boolean;
  disabled: boolean;
  onSelectObject: (objectId: number) => void;
  onToggleHidden: (objectId: number) => void;
  onAddObject: () => void;
  collapsed: boolean;
  onToggleCollapsed: () => void;
}

export const ObjectPanel: React.FC<ObjectPanelProps> = ({
  objects,
  selectedObjectId,
  isAddingObject,
  disabled,
  onSelectObject,
  onToggleHidden,
  onAddObject,
  collapsed,
  onToggleCollapsed,
}) => {
  const handleSelectObject = useCallback(
    (objectId: number) => {
      if (!disabled) {
        onSelectObject(objectId);
      }
    },
    [disabled, onSelectObject],
  );

  const handleToggleHidden = useCallback(
    (event: React.MouseEvent, objectId: number) => {
      // Don't let the eye toggle also trigger selection of the thumbnail
      // underneath it.
      event.stopPropagation();
      if (!disabled) {
        onToggleHidden(objectId);
      }
    },
    [disabled, onToggleHidden],
  );

  const handleAddObject = useCallback(() => {
    if (!disabled) {
      onAddObject();
    }
  }, [disabled, onAddObject]);

  return (
    <div className="object-panel-container">
      {/* Side column — always visible regardless of collapsed state */}
      <div className="object-panel-side">
        <button
          type="button"
          className="object-panel-toggle"
          onClick={onToggleCollapsed}
          aria-label={collapsed ? "Expand objects panel" : "Collapse objects panel"}
          title={collapsed ? "Expand" : "Collapse"}
        >
          {collapsed ? "▶" : "◀"}
        </button>

        {/* + button is always visible so users can add objects even when panel is collapsed */}
        <button
          type="button"
          className={`object-panel-add-side${isAddingObject ? " is-active" : ""}`}
          onClick={handleAddObject}
          disabled={disabled}
          aria-label="Add new object"
          title="Add new object"
        >
          +
        </button>
      </div>

      {/* Expandable body with scrollable thumbnail list */}
      <div className={`object-panel-body${collapsed ? " is-collapsed" : ""}`}>
        <span className="object-panel-label">Objects</span>

        <div className="object-panel-list">
          {objects.map((obj) => (
            <div key={obj.objectId} className="object-thumbnail-row">
              <button
                type="button"
                className={`object-thumbnail-btn${obj.objectId === selectedObjectId ? " is-active" : ""}`}
                onClick={() => handleSelectObject(obj.objectId)}
                disabled={disabled || obj.hidden}
                aria-label={`Select object ${obj.objectId}`}
                title={obj.hidden ? `Object ${obj.objectId} (hidden)` : `Object ${obj.objectId}`}
              >
                <img
                  src={obj.cutoutSrc}
                  alt={`Object ${obj.objectId}`}
                  className="object-thumbnail-img"
                />
              </button>

              <button
                type="button"
                className="object-visibility-btn"
                onClick={(event) => handleToggleHidden(event, obj.objectId)}
                disabled={disabled}
                aria-label={obj.hidden ? `Show object ${obj.objectId}` : `Hide object ${obj.objectId}`}
                title={obj.hidden ? "Show object" : "Hide object"}
              >
                {obj.hidden ? <EyeOffIcon /> : <EyeOpenIcon />}
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
