// Tiny inline icon set (stroke icons, no dependency). Decorative: hidden from screen readers.
const P = {
  home: "M3 11l9-7 9 7M5 10v10h5v-6h4v6h5V10",
  file: "M7 3h7l5 5v13H7zM14 3v5h5",
  process: "M4 6h16M4 12h10M4 18h16M18 10l3 2-3 2",
  pdf: "M7 3h7l5 5v13H7zM14 3v5h5M9.5 16h5M9.5 13h5",
  table: "M4 5h16v14H4zM4 10h16M10 5v14",
  candles: "M7 4v16M7 8h0M5 8h4v7H5zM17 3v18M15 6h4v9h-4z",
  trend: "M3 17l6-6 4 4 8-9M15 6h6v6",
  bubble: "M4 5h16v11H9l-5 4z",
  gauge: "M4 17a8 8 0 1116 0M12 17l4-5",
  target: "M12 21a9 9 0 100-18 9 9 0 000 18zM12 16a4 4 0 100-8 4 4 0 000 8z",
  book: "M5 4h10a3 3 0 013 3v13H8a3 3 0 01-3-3zM5 17a3 3 0 013-3h10",
  menu: "M4 7h16M4 12h16M4 17h16",
  close: "M6 6l12 12M18 6L6 18",
  send: "M5 12h13M13 6l6 6-6 6",
  clip: "M8 12.5l6.5-6.5a3 3 0 014.2 4.2l-8 8a5 5 0 01-7-7l7.5-7.5",
  plus: "M12 5v14M5 12h14",
  info: "M12 11v6M12 7.5v.5M12 21a9 9 0 100-18 9 9 0 000 18z",
};
export default function Icon({ name, size = 18 }) {
  return (
    <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <path d={P[name] || P.info} />
    </svg>
  );
}
