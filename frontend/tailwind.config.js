/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Soft violet → midnight-blue palette. Designed to be calm,
        // readable, and to avoid neon saturation.
        bg: {
          0: "#0a0a14",   // deep ink
          1: "#11111d",   // card base
          2: "#171728",   // raised
        },
        ink: {
          DEFAULT: "#e6e7ee",
          muted: "#9aa0b3",
          dim: "#6a6f80",
        },
        line: {
          DEFAULT: "rgba(255,255,255,0.08)",
          strong: "rgba(255,255,255,0.14)",
        },
        violet: {
          // muted, less neon than #a855f7
          400: "#9b87f5",
          500: "#7c6ae0",
          600: "#5d4ec0",
        },
        indigo: {
          500: "#5161c4",
          600: "#3f4ea3",
        },
        // back-compat aliases (used in a few places)
        "violet-neon": "#9b87f5",
        "violet-deep": "#5d4ec0",
        "blue-deep": "#3f4ea3",
        "accent-cyan": "#7dd3fc",
      },
      fontFamily: {
        sans: ['"Inter"', "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
      },
      boxShadow: {
        // Soft, lifted shadow — no glow halo.
        card: "0 1px 0 rgba(255,255,255,0.04) inset, 0 12px 32px -16px rgba(0,0,0,0.6)",
        glow: "0 1px 0 rgba(255,255,255,0.04) inset, 0 12px 32px -16px rgba(0,0,0,0.6)",
      },
      borderRadius: {
        xl: "0.9rem",
        "2xl": "1.1rem",
      },
    },
  },
  plugins: [],
};
