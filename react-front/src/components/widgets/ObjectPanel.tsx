import React, { useCallback } from "react";

interface ObjectEntry {
  objectId: number;
  cutoutSrc: string;
}

interface ObjectPanelProps {
  objects: ObjectEntry[];
  activeObjectId: number | null;
  isAddingObject: boolean;
  disabled: boolean;
  onSelectObject: (objectId: number) => void;
  onAddObject: () => void;
  collapsed: boolean;
  onToggleCollapsed: () => void;
}

export const ObjectPanel: React.FC<ObjectPanelProps> = ({
  objects,
  activeObjectId,
  isAddingObject,
  disabled,
  onSelectObject,
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

  const handleAddObject = useCallback(() => {
    if (!disabled) {
      onAddObject();
    }
  }, [disabled, onAddObject]);

  return (
    <div className="object-panel-container">
      <button
        type="button"
        className="object-panel-toggle"
        onClick={onToggleCollapsed}
        aria-label={collapsed ? "Expand objects panel" : "Collapse objects panel"}
        title={collapsed ? "Expand" : "Collapse"}
      >
        {collapsed ? "▶" : "◀"}
      </button>

      <div className={`object-panel-body${collapsed ? " is-collapsed" : ""}`}>
        <span className="object-panel-label">Objects</span>

        <div className="object-panel-list">
          {objects.map((obj) => (
            <button
              key={obj.objectId}
              type="button"
              className={`object-thumbnail-btn${obj.objectId === activeObjectId ? " is-active" : ""}`}
              onClick={() => handleSelectObject(obj.objectId)}
              disabled={disabled}
              aria-label={`Select object ${obj.objectId}`}
              title={`Object ${obj.objectId}`}
            >
              <img
                src={obj.cutoutSrc}
                alt={`Object ${obj.objectId}`}
                className="object-thumbnail-img"
              />
            </button>
          ))}
        </div>

        <button
          type="button"
          className={`object-panel-add-btn${isAddingObject ? " is-active" : ""}`}
          onClick={handleAddObject}
          disabled={disabled}
          aria-label="Add new object"
          title="Add object"
        >
          +
        </button>
      </div>
    </div>
  );
};
