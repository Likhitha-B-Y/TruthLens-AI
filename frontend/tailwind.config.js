const v = (name) => `rgb(var(--${name}) / <alpha-value>)`;

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: v("bg"), surface: v("surface"), sunken: v("sunken"), line: v("line"),
        ink: v("ink"), muted: v("muted"), brand: v("brand"), "brand-fg": v("brand-fg"),
        secondary: v("secondary"), accent: v("accent"),
        ok: v("ok"), "ok-bg": v("ok-bg"), bad: v("bad"), "bad-bg": v("bad-bg"), warn: v("warn"), "warn-bg": v("warn-bg"),
      },
      fontFamily: {
        sans: ['"Manrope Variable"', "ui-sans-serif", "system-ui", "Segoe UI", "sans-serif"],
        display: ['"Fraunces Variable"', "Georgia", "serif"],
      },
      boxShadow: {
        card: "0 1px 2px rgb(15 23 42 / 0.05), 0 10px 28px -14px rgb(15 23 42 / 0.14)",
        pop: "0 20px 50px -20px rgb(15 23 42 / 0.35)",
      },
      keyframes: {
        shimmer: { "100%": { transform: "translateX(100%)" } },
      },
    },
  },
  plugins: [],
};
