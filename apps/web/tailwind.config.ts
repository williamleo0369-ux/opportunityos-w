import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: "#080A12",
        muted: "#6F7485",
        field: "#F6F7FB",
        line: "#E8EAF1",
        indigo: "#5B5CF6",
        violet: "#7A3FF2",
        indigoElectric: "#5b5cf6",
        signal: "#5B5CF6",
        moss: "#4D6F56",
        clay: "#B2634B",
        lemon: "#E8C547",
        surface: "#ffffff",
      },
      boxShadow: {
        panel: "0 24px 70px rgba(31, 35, 60, 0.08)",
        glow: "0 18px 42px rgba(91, 92, 246, 0.32)",
        card: "0 18px 70px rgba(15, 23, 42, 0.08)",
      },
    },
  },
  plugins: [],
};

export default config;
