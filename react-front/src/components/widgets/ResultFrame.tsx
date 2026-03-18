import React from "react";

export interface ResultFrameProps {
  title: string;
  imageSrc?: string | null;
}

export const ResultFrame: React.FC<ResultFrameProps> = ({ title, imageSrc }) => {
  return (
    <div className="frame result-frame">
      <div className="frame-title">{title}</div>
      {imageSrc ? (
        <img src={imageSrc} alt={title} className="frame-image" />
      ) : (
        <div className="frame-placeholder">Result will appear here</div>
      )}
    </div>
  );
};

