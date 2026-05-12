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
      typography: ({ theme }) => ({
        invert: {
          css: {
            "--tw-prose-body": "#cfd1dc",
            "--tw-prose-headings": "#ffffff",
            "--tw-prose-lead": "#cfd1dc",
            "--tw-prose-links": "#9b87f5",
            "--tw-prose-bold": "#ffffff",
            "--tw-prose-counters": "#9aa0b3",
            "--tw-prose-bullets": "#7c6ae0",
            "--tw-prose-hr": "rgba(255,255,255,0.12)",
            "--tw-prose-quotes": "#e6e7ee",
            "--tw-prose-quote-borders": "#5d4ec0",
            "--tw-prose-code": "#fde68a",
            "--tw-prose-pre-code": "#e6e7ee",
            "--tw-prose-pre-bg": "#0a0a14",
            "--tw-prose-th-borders": "rgba(255,255,255,0.14)",
            "--tw-prose-td-borders": "rgba(255,255,255,0.08)",
            h1: { fontWeight: "700", marginTop: "1.2em", marginBottom: "0.6em" },
            h2: { fontWeight: "700", marginTop: "1.4em", marginBottom: "0.5em", borderBottom: "1px solid rgba(255,255,255,0.08)", paddingBottom: "0.3em" },
            h3: { fontWeight: "600", marginTop: "1.2em", marginBottom: "0.4em" },
            p: { marginTop: "0.7em", marginBottom: "0.7em", lineHeight: "1.7" },
            li: { marginTop: "0.25em", marginBottom: "0.25em" },
            code: {
              backgroundColor: "rgba(155,135,245,0.12)",
              color: "#c4b5fd",
              padding: "0.15em 0.4em",
              borderRadius: "0.35em",
              fontWeight: "500",
            },
            "code::before": { content: '""' },
            "code::after": { content: '""' },
            pre: {
              backgroundColor: "#0a0a14",
              border: "1px solid rgba(255,255,255,0.08)",
              borderRadius: "0.75rem",
              padding: "1rem",
            },
            blockquote: {
              borderLeftColor: "#5d4ec0",
              fontStyle: "normal",
              backgroundColor: "rgba(124,106,224,0.06)",
              padding: "0.6em 1em",
              borderRadius: "0.5em",
            },
          },
        },
      }),
    },
  },
  plugins: [require("@tailwindcss/typography")],
};
