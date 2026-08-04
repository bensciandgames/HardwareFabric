import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        void: "#0A0F1E",
        panel: "#101A30",
        "panel-raised": "#152142",
        "blue-medium": "#3B7DFF",
        "blue-dim": "#1E3A66",
        "blue-faint": "#132248",
        "yellow-signal": "#FFD60A",
        "yellow-dim": "#8A6E00",
        "text-primary": "#E8EDF7",
        "text-muted": "#7C8AA8",
        "text-faint": "#4A5776",
        danger: "#FF5C5C",
      },
      fontFamily: {
        display: ["var(--font-space-grotesk)", "sans-serif"],
        body: ["var(--font-inter)", "sans-serif"],
        mono: ["var(--font-jetbrains-mono)", "monospace"],
      },
      backgroundSize: {
        "circuit-grid": "28px 28px",
      },
      keyframes: {
        "dash-pulse": {
          "0%, 100%": { opacity: "0.35" },
          "50%": { opacity: "0.9" },
        },
        "glow-breathe": {
          "0%, 100%": { boxShadow: "0 0 0 rgba(255,214,10,0)" },
          "50%": { boxShadow: "0 0 18px rgba(255,214,10,0.35)" },
        },
        "trace-flow": {
          "0%": { strokeDashoffset: "40" },
          "100%": { strokeDashoffset: "0" },
        },
      },
      animation: {
        "dash-pulse": "dash-pulse 2.2s ease-in-out infinite",
        "glow-breathe": "glow-breathe 2.6s ease-in-out infinite",
        "trace-flow": "trace-flow 1.1s linear infinite",
      },
    },
  },
  plugins: [],
};

export default config;
