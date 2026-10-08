/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    darkMode: 'class', // Enable toggling dark mode via class name
    theme: {
        extend: {
            fontFamily: {
                sans: ['"Plus Jakarta Sans"', 'sans-serif'],
            },
            colors: {
                // Civic Lens Brand Colors
                brand: {
                    light: '#FDE68A', // Amber 200
                    DEFAULT: '#D97706', // Amber 600
                    dark: '#92400E', // Amber 800
                },
                surface: {
                    light: '#ffffff',
                    dark: '#1F2937' // Dark gray for dark mode surfaces
                }
            }
        },
    },
    plugins: [],
}


