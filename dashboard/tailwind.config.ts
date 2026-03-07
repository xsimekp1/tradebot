import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0f1117",
        card: "#1a1d27",
        border: "#2a2d3a",
        muted: "#6b7280",
        accent: "#6366f1",
        green: { 400: "#4ade80", 500: "#22c55e" },
        red: { 400: "#f87171", 500: "#ef4444" },
      },
    },
  },
  plugins: [],
};

export default config;
