import React, { useState, useEffect } from 'react';
import { ThemeProvider, useTheme } from './contexts/ThemeContext';
import ResultCaptureForm from './components/ResultCaptureForm';
import SyncManager from './components/SyncManager';
import LoginScreen from './components/LoginScreen';
import PasswordResetScreen from './components/PasswordResetScreen';
import UserProfileScreen from './components/UserProfileScreen';
import { NotificationProvider } from './contexts/NotificationContext';
import NotificationBanner from './components/NotificationBanner';
import { Camera, UserCircle } from 'lucide-react';

function LayoutShell({ children, activeView, setActiveView, onLogout, assignedPu }) {
  const { isDarkMode, toggleTheme } = useTheme();
  const [isOnline, setIsOnline] = useState(navigator.onLine);

  useEffect(() => {
    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  return (
    <div className="min-h-screen flex flex-col font-sans">
      {/* Offline Banner */}
      <div className={`offline-banner ${!isOnline ? 'visible' : ''}`}>
        No Internet Connection - Working Offline
      </div>

      {/* Header */}
      <header className="bg-brand text-white shadow-md pt-5 pb-4 px-4 sticky top-0 z-40 transition-colors duration-200 dark:bg-brand-dark">
        <div className="flex justify-between items-center mt-2 max-w-md mx-auto">
          <div className="flex items-center space-x-2">
            <div className="w-8 h-8 bg-white rounded-full flex items-center justify-center text-brand font-bold text-sm">
              CL
            </div>
            <h1 className="text-base font-black tracking-[0.15em] uppercase">AGENT PORTAL</h1>
          </div>

          <div className="flex items-center space-x-2">
            <button
              onClick={toggleTheme}
              className="p-2 rounded-full focus:outline-none hover:bg-white/10 transition-colors text-lg"
              title="Toggle Theme"
            >
              {isDarkMode ? '🌞' : '🌙'}
            </button>
            <button
              onClick={onLogout}
              className="px-3 py-1.5 bg-white/10 hover:bg-white/20 border border-white/20 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all active:scale-95"
            >
              Sign Out
            </button>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 w-full max-w-md mx-auto p-4 flex flex-col bg-gray-50/50 dark:bg-gray-950 pb-24">
        {children}
      </main>

      <SyncManager assignedPu={assignedPu} />

      {/* Navigation */}
      <nav className="fixed bottom-0 left-0 right-0 bg-white/80 dark:bg-gray-900/80 backdrop-blur-lg border-t border-gray-200 dark:border-gray-800 pb-safe z-50">
        <div className="flex justify-around items-center h-16 w-full max-w-md mx-auto px-4">
          <button
            onClick={() => setActiveView('capture')}
            className={`flex flex-col items-center justify-center w-full h-full transition-colors ${activeView === 'capture' ? 'text-brand' : 'text-gray-400'}`}
          >
            <Camera className="w-5 h-5 mb-1" />
            <span className="text-[9px] font-black uppercase tracking-widest">Capture</span>
          </button>

          <button
            onClick={() => setActiveView('profile')}
            className={`flex flex-col items-center justify-center w-full h-full transition-colors ${activeView === 'profile' ? 'text-brand' : 'text-gray-400'}`}
          >
            <UserCircle className="w-5 h-5 mb-1" />
            <span className="text-[9px] font-black uppercase tracking-widest">Profile</span>
          </button>
        </div>
      </nav>
    </div>
  );
}

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isResetRequired, setIsResetRequired] = useState(false);
  const [resetEmail, setResetEmail] = useState('');
  const [activeView, setActiveView] = useState('capture');
  const [assignedPu, setAssignedPu] = useState(null);

  useEffect(() => {
    console.log("[CIVIC LENS] Agent Portal v1.0.0-PROD Initialization Complete");
  }, []);

  return (
    <ThemeProvider>
      <NotificationProvider>
        <NotificationBanner />

        {!isAuthenticated && !isResetRequired && (
          <LoginScreen
            onLoginSuccess={(pu) => { setAssignedPu(pu); setIsAuthenticated(true); }}
            onRequireReset={(email) => { setResetEmail(email); setIsResetRequired(true); }}
          />
        )}

        {isResetRequired && (
          <PasswordResetScreen
            email={resetEmail}
            onComplete={() => { setIsResetRequired(false); setIsAuthenticated(false); }}
          />
        )}

        {isAuthenticated && !isResetRequired && (
          <LayoutShell
            activeView={activeView}
            setActiveView={setActiveView}
            onLogout={() => { setIsAuthenticated(false); setAssignedPu(null); }}
            assignedPu={assignedPu}
          >
            <div className="flex-1 flex flex-col">
              {activeView === 'capture' && (
                <div className="bg-white dark:bg-gray-900 rounded-3xl shadow-xl border border-gray-100 dark:border-gray-800 p-6">
                  <div className="mb-6">
                    <h2 className="text-xl font-black text-gray-900 dark:text-white uppercase tracking-tight">Agent Submission</h2>
                    <p className="text-xs text-gray-400 font-bold uppercase tracking-wider">Field Data Capture</p>
                  </div>
                  <ResultCaptureForm assignedPu={assignedPu} />
                </div>
              )}

              {activeView === 'profile' && <UserProfileScreen onLogout={() => setIsAuthenticated(false)} />}
            </div>
          </LayoutShell>
        )}
      </NotificationProvider>
    </ThemeProvider>
  );
}

export default App;


