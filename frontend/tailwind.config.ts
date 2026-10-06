import type { Config } from "tailwindcss";
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#eef2f7", panel: "#ffffff", panel2: "#f3f6fb", line: "#d3dce8", text: "#24344a", muted: "#5d6f87", accent: "#1d6fd8", strong: "#0b1b33",
        p1: "#d62f35", p2: "#e0721a", p3: "#c99700", p4: "#6b7a90", ok: "#1f9d6b", warn: "#a56a00",
      },
      fontFamily: { sans: ["Segoe UI", "system-ui", "-apple-system", "Roboto", "Helvetica Neue", "Arial", "sans-serif"], mono: ["Cascadia Mono", "Consolas", "ui-monospace", "monospace"] },
    },
  },
  plugins: [],
};
export default config;
