import animate from "tailwindcss-animate";

/** Colours come only from the CSS variables in src/styles/index.css (spec §8.0). */
const token = (name) => `hsl(var(--${name}) / <alpha-value>)`;

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: token("bg"),
        surface: token("surface"),
        muted: { DEFAULT: token("surface-muted"), foreground: token("text-muted") },
        border: token("border"),
        input: token("border"),
        foreground: token("text"),
        ring: token("ring"),
        primary: { DEFAULT: token("primary"), foreground: token("primary-fg") },
        success: { DEFAULT: token("success"), subtle: token("success-subtle"), strong: token("success-strong") },
        warning: { DEFAULT: token("warning"), subtle: token("warning-subtle"), strong: token("warning-strong") },
        danger: { DEFAULT: token("danger"), subtle: token("danger-subtle"), strong: token("danger-strong") },
        info: { DEFAULT: token("info"), subtle: token("info-subtle"), strong: token("info-strong") },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "var(--radius-control)",
        sm: "calc(var(--radius-control) - 2px)",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      fontSize: {
        xs: ["12px", "16px"],
        sm: ["14px", "20px"],
        base: ["16px", "24px"],
        lg: ["20px", "28px"],
        xl: ["24px", "32px"],
      },
    },
  },
  plugins: [animate],
};
