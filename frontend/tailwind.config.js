/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        heading: ['"Space Grotesk"', 'sans-serif'],
        body: ['"DM Sans"', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
      colors: {
        brand: {
          yellow: '#ffe17c',
          dark:   '#171e19',
          muted:  '#b7c6c2',
          bg:     '#f5f4f0',
        },
      },
      boxShadow: {
        brutal:   '5px 5px 0px 0px #000',
        'brutal-sm': '3px 3px 0px 0px #000',
        'brutal-lg': '8px 8px 0px 0px #000',
      },
    },
  },
  plugins: [],
};
