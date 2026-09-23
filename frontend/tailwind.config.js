/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'Noto Sans Devanagari', 'system-ui', 'sans-serif'],
      },
      colors: {
        brand: {
          50: '#eef4ff',
          100: '#dbe6fe',
          200: '#bfd3fe',
          300: '#93b4fd',
          400: '#608bfa',
          500: '#3b63f6',
          600: '#2546eb',
          700: '#1d35d8',
          800: '#1e2eaf',
          900: '#1e2c8a',
          950: '#171d54',
        },
        ink: {
          50: '#f6f7f9',
          100: '#eceef2',
          200: '#d5d9e2',
          300: '#b1b9c8',
          400: '#8792a9',
          500: '#68748f',
          600: '#535d76',
          700: '#444c60',
          800: '#3b4151',
          900: '#343946',
          950: '#23262e',
        },
      },
      boxShadow: {
        card: '0 1px 2px rgba(16, 24, 40, 0.04), 0 1px 3px rgba(16, 24, 40, 0.06)',
        lift: '0 10px 30px -12px rgba(16, 24, 40, 0.25)',
      },
      keyframes: {
        pulseSoft: { '0%, 100%': { opacity: 1 }, '50%': { opacity: 0.45 } },
        fadeUp: { '0%': { opacity: 0, transform: 'translateY(6px)' }, '100%': { opacity: 1, transform: 'translateY(0)' } },
      },
      animation: {
        pulseSoft: 'pulseSoft 1.4s ease-in-out infinite',
        fadeUp: 'fadeUp 0.35s ease-out both',
      },
    },
  },
  plugins: [],
}
