import React from "react";

// One hand-drawn icon set for the workspace chrome. Every glyph is drawn on a
// 24-unit grid with a 1.6 stroke and round joins so the toolbar row reads as a
// single instrument rather than a collection of borrowed marks.

interface IconProps {
  size?: number;
}

const stroke = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.6,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

const Svg: React.FC<React.PropsWithChildren<IconProps>> = ({ size = 18, children }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden="true" focusable="false">
    <g {...stroke}>{children}</g>
  </svg>
);

export const BackIcon: React.FC<IconProps> = (props) => (
  <Svg {...props}>
    <path d="M19 12H5" />
    <path d="M11 6l-6 6 6 6" />
  </Svg>
);

export const ScissorsIcon: React.FC<IconProps> = (props) => (
  <Svg {...props}>
    <circle cx="6.5" cy="17.5" r="2.6" />
    <circle cx="6.5" cy="6.5" r="2.6" />
    <path d="M19.5 4.5L8.4 15.9" />
    <path d="M19.5 19.5L8.4 8.1" />
  </Svg>
);

export const RotateIcon: React.FC<IconProps> = (props) => (
  <Svg {...props}>
    <ellipse cx="12" cy="12" rx="9" ry="4.2" transform="rotate(-24 12 12)" />
    <path d="M9.2 4.9L12.4 6l-1 3.1" />
    <path d="M14.8 19.1L11.6 18l1-3.1" />
  </Svg>
);

export const CopyIcon: React.FC<IconProps> = (props) => (
  <Svg {...props}>
    <rect x="8.5" y="8.5" width="11" height="11" rx="1.8" />
    <path d="M15.5 5.5v-1a1 1 0 00-1-1h-9a1 1 0 00-1 1v9a1 1 0 001 1h1" />
  </Svg>
);

export const SmartPasteIcon: React.FC<IconProps> = (props) => (
  <Svg {...props}>
    <rect x="4.5" y="5.5" width="12" height="14" rx="1.8" />
    <path d="M9 5.5V4.4a1 1 0 011-1h1a1 1 0 011 1v1.1" />
    <path d="M19.4 8.6l.7 1.9 1.9.7-1.9.7-.7 1.9-.7-1.9-1.9-.7 1.9-.7z" />
  </Svg>
);

export const TrashIcon: React.FC<IconProps> = (props) => (
  <Svg {...props}>
    <path d="M4.5 6.5h15" />
    <path d="M9.5 6.5V4.9a1 1 0 011-1h3a1 1 0 011 1v1.6" />
    <path d="M6.5 6.5l.9 12a1 1 0 001 .9h7.2a1 1 0 001-.9l.9-12" />
    <path d="M10.4 10v6M13.6 10v6" />
  </Svg>
);

export const CheckIcon: React.FC<IconProps> = (props) => (
  <Svg {...props}>
    <path d="M4.5 12.6l4.8 4.7L19.5 6.9" />
  </Svg>
);

export const EyeIcon: React.FC<IconProps> = (props) => (
  <Svg {...props}>
    <path d="M2.6 12S6.2 5.9 12 5.9 21.4 12 21.4 12 17.8 18.1 12 18.1 2.6 12 2.6 12z" />
    <circle cx="12" cy="12" r="2.7" />
  </Svg>
);

export const EyeOffIcon: React.FC<IconProps> = (props) => (
  <Svg {...props}>
    <path d="M6.1 6.7C3.9 8.2 2.6 12 2.6 12s3.6 6.1 9.4 6.1c2 0 3.7-.7 5.1-1.6" />
    <path d="M19.6 15.1c1.2-1.4 1.8-3.1 1.8-3.1S17.8 5.9 12 5.9c-.7 0-1.4.1-2 .3" />
    <path d="M10.2 10.2a2.7 2.7 0 003.7 3.7" />
    <path d="M4.4 4.4l15.2 15.2" />
  </Svg>
);

/** Reverts an object's on-canvas image to the cutout it had before rotation. */
export const RevertIcon: React.FC<IconProps> = (props) => (
  <Svg {...props}>
    <path d="M4.4 10.2A8 8 0 1112 20" />
    <path d="M4.2 5.6v4.8h4.8" />
  </Svg>
);

export const PlusIcon: React.FC<IconProps> = (props) => (
  <Svg {...props}>
    <path d="M12 4.8v14.4M4.8 12h14.4" />
  </Svg>
);

/** Stands in for a session whose preview hasn't been captured yet. */
export const PhotoIcon: React.FC<IconProps> = (props) => (
  <Svg {...props}>
    <rect x="3.2" y="5.2" width="17.6" height="13.6" rx="1.8" />
    <circle cx="8.6" cy="10" r="1.5" />
    <path d="M3.4 16.2l4.8-4.1 4 3.3 3.2-2.6 5.2 4.3" />
  </Svg>
);
