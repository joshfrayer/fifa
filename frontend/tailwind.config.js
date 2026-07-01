/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./src/**/*.{js,ts,jsx,tsx,html,scss}",
    "../backend/bracket/templates/**/*.html",
  ],
  theme: {
    extend: {
      colors: {
        pitch: {
          dark: "#2e7c45",
          light: "#368a4f",
        },
      },
    },
  },
  plugins: [],
};
