/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: { 950: '#0b0e14', 900: '#10141c', 850: '#151a24', 800: '#1a202c', 700: '#242c3b', 600: '#303a4d', 500: '#47536b' },
        brand: { 300: '#a5b4fc', 400: '#818cf8', 500: '#6366f1', 600: '#4f46e5', 700: '#4338ca' },
      },
      fontFamily: { sans: ['Inter', 'Segoe UI', 'system-ui', 'sans-serif'] },
      keyframes: { slidein: { from: { opacity: 0, transform: 'translateY(8px)' }, to: { opacity: 1, transform: 'none' } } },
      animation: { slidein: 'slidein .18s ease-out' },
    },
  },
  plugins: [],
}
