import React from 'react';
import { ThemeProvider, useTheme } from './contexts/ThemeContext';
import PublicDashboard from './components/PublicDashboard';

function LayoutShell({ children }) {
  const { isDarkMode, toggleTheme } = useTheme();

  return (
    <div className="min-h-screen flex flex-col font-sans">
      {/* Header */}
      <header className="bg-brand text-white shadow-md pt-5 pb-4 px-4 sticky top-0 z-40 transition-colors duration-200 dark:bg-brand-dark">
        <div className="flex justify-between items-center mt-2 max-w-md mx-auto">
          <div className="flex items-center space-x-2">
            <div className="w-8 h-8 bg-white rounded-full flex items-center justify-center text-brand font-bold text-sm">
              CL
            </div>
            <h1 className="text-base font-black tracking-[0.15em] uppercase">CITIZEN PORTAL</h1>
          </div>

          <button
            onClick={toggleTheme}
            className="p-2 rounded-full focus:outline-none hover:bg-white/10 transition-colors text-lg"
          >
            {isDarkMode ? '🌞' : '🌙'}
          </button>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 w-full max-w-md mx-auto p-4 flex flex-col bg-gray-50/50 dark:bg-gray-950">
        {children}
      </main>

      <footer className="p-6 text-center text-[10px] text-gray-400 font-bold uppercase tracking-widest bg-gray-50 dark:bg-gray-950">
        CIVIC LENS Public Transparency Dashboard v1.0
      </footer>
    </div>
  );
}

function App() {
  return (
    <ThemeProvider>
      <LayoutShell>
        <div className="flex-1 flex flex-col">
          <div className="bg-white dark:bg-gray-900 rounded-3xl shadow-xl border border-gray-100 dark:border-gray-800 p-6 mb-6">
            <div className="mb-4">
              <h2 className="text-xl font-black text-gray-900 dark:text-white uppercase tracking-tight italic">Public Collation</h2>
              <p className="text-[10px] text-brand font-black uppercase tracking-widest">Verified Election Results in Real-Time</p>
            </div>
            <PublicDashboard />
          </div>
        </div>
      </LayoutShell>
    </ThemeProvider>
  );
}

export default App;


