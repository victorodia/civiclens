/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    darkMode: 'class', // Enable toggling dark mode via class name
    theme: {
        extend: {
            colors: {
                // Civic Lens Brand Colors
                brand: {
                    light: '#E6F8F3', // Light Teal/Green background
                    DEFAULT: '#0D9488', // Core Nigeria-inspired Green
                    dark: '#115E59', // Deep Green for headers
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


