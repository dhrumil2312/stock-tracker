export default function BrandMark() {
  return (
    <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
      <defs>
        <linearGradient id="vt-brand" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#1a73e8" />
          <stop offset="100%" stopColor="#174ea6" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="8" fill="url(#vt-brand)" />
      <polyline
        points="5.5,21.5 10.5,16 14.5,18.5 21,9.5 26.5,13"
        fill="none"
        stroke="#fff"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="21" cy="9.5" r="2.2" fill="#e6f4ea" />
    </svg>
  );
}
