// Small line icons used across the app. Shapes follow the Lucide icon set
// (ISC licence), drawn on a 24x24 grid.
// `size` is the width/height in px; `stroke` is the line width in px at any
// size (theme.css sets vector-effect: non-scaling-stroke on .icon).
function Icon({ size = 24, stroke = 2, className = "", children }) {
  return (
    <svg
      className={`icon ${className}`}
      width={size} height={size} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth={stroke}
      strokeLinecap="round" strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

// The AutoRefund mark: an arrow turning back.
export function LogoIcon(props) {
  return <Icon {...props}><path d="M9 14 4 9l5-5" /><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11" /></Icon>;
}

export function ArrowLeftIcon(props) {
  return <Icon {...props}><path d="M19 12H5" /><path d="m12 19-7-7 7-7" /></Icon>;
}

export function HelpIcon(props) {
  return <Icon {...props}><circle cx="12" cy="12" r="10" /><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3" /><path d="M12 17h.01" /></Icon>;
}

export function CloseIcon(props) {
  return <Icon {...props}><path d="M18 6 6 18" /><path d="m6 6 12 12" /></Icon>;
}

export function ScaleIcon(props) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="5.5" r="2.5" />
      <path d="M9.5 10h5l2.5 9h-10Z" /><path d="M4 19h16" />
    </Icon>
  );
}

export function ReceiptIcon(props) {
  return (
    <Icon {...props}>
      <path d="M3 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1 2-1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1-2-1Z" />
      <path d="M8 7h8" /><path d="M8 11h8" /><path d="M8 15h8" />
    </Icon>
  );
}

export function CardIcon(props) {
  return <Icon {...props}><rect x="2" y="5" width="20" height="14" rx="2" /><path d="M2 10h20" /></Icon>;
}

export function CheckIcon(props) {
  return <Icon {...props}><path d="M20 6 9 17l-5-5" /></Icon>;
}

export function LockIcon(props) {
  return <Icon {...props}><rect x="3" y="11" width="18" height="11" rx="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" /></Icon>;
}

// Stands in for a product photo.
export function BoxIcon(props) {
  return (
    <Icon {...props}>
      <path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z" />
      <path d="m3.3 7 8.7 5 8.7-5" /><path d="M12 22V12" />
    </Icon>
  );
}

export function CameraIcon(props) {
  return (
    <Icon {...props}>
      <path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3Z" />
      <circle cx="12" cy="13" r="3" />
    </Icon>
  );
}

export function InfoIcon(props) {
  return <Icon {...props}><circle cx="12" cy="12" r="10" /><path d="M12 16v-4" /><path d="M12 8h.01" /></Icon>;
}

export function AlertIcon(props) {
  return <Icon {...props}><circle cx="12" cy="12" r="10" /><path d="M12 8v4" /><path d="M12 16h.01" /></Icon>;
}

export function UserIcon(props) {
  return <Icon {...props}><circle cx="12" cy="8" r="5" /><path d="M20 21a8 8 0 0 0-16 0" /></Icon>;
}

export function BarcodeIcon(props) {
  return <Icon {...props}><path d="M3 5v14" /><path d="M6.6 5v14" /><path d="M10.2 5v14" /><path d="M13.8 5v14" /><path d="M17.4 5v14" /><path d="M21 5v14" /></Icon>;
}

export function GridIcon(props) {
  return (
    <Icon {...props}>
      <rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" />
    </Icon>
  );
}

export function InboxIcon(props) {
  return (
    <Icon {...props}>
      <path d="M22 12h-6l-2 3h-4l-2-3H2" />
      <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11Z" />
    </Icon>
  );
}

export function ListIcon(props) {
  return (
    <Icon {...props}>
      <path d="M8 6h13" /><path d="M8 12h13" /><path d="M8 18h13" />
      <path d="M3 6h.01" /><path d="M3 12h.01" /><path d="M3 18h.01" />
    </Icon>
  );
}

export function RefreshIcon(props) {
  return (
    <Icon {...props}>
      <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" /><path d="M3 3v5h5" />
      <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" /><path d="M16 16h5v5" />
    </Icon>
  );
}

export function ChevronDownIcon(props) {
  return <Icon {...props}><path d="m6 9 6 6 6-6" /></Icon>;
}

export function ChevronUpIcon(props) {
  return <Icon {...props}><path d="m18 15-6-6-6 6" /></Icon>;
}

export function CalendarIcon(props) {
  return (
    <Icon {...props}>
      <rect x="3" y="4" width="18" height="18" rx="2" />
      <path d="M16 2v4" /><path d="M8 2v4" /><path d="M3 10h18" />
    </Icon>
  );
}
