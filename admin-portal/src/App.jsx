import React, { useState } from 'react';
import { ThemeProvider, useTheme } from './contexts/ThemeContext';
import AdminDashboard from './components/AdminDashboard';
import VerificationScreen from './components/VerificationScreen';
import LoginScreen from './components/LoginScreen';
import PasswordResetScreen from './components/PasswordResetScreen';
import AgentManagement from './components/AgentManagement';
import WorkforceMonitor from './components/WorkforceMonitor';
import CoverageAudit from './components/CoverageAudit';
import UserProfileScreen from './components/UserProfileScreen';
import ElectionConfig from './components/ElectionConfig';
import { NotificationProvider } from './contexts/NotificationContext';
import NotificationBanner from './components/NotificationBanner';
import SecurityDialog from './components/SecurityDialog';
import { LayoutDashboard, ShieldCheck, UserCircle, Users, Activity, Map, Settings } from 'lucide-react';

function LayoutShell({ children, activeView, setActiveView, onLogout }) {
  const { isDarkMode, toggleTheme } = useTheme();

  return (
    <div className="min-h-screen flex flex-col font-sans">
      {/* Header */}
      <header className="bg-brand text-white shadow-md pt-5 pb-4 px-4 sticky top-0 z-40 transition-colors duration-200 dark:bg-brand-dark">
        <div className="flex justify-between items-center mt-2 max-w-5xl mx-auto">
          <div className="flex items-center space-x-2">
            <div className="w-8 h-8 bg-white rounded-full flex items-center justify-center text-brand font-bold text-sm">
              CL
            </div>
            <h1 className="text-base font-black tracking-[0.15em] uppercase">ADMIN PORTAL</h1>
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
      <main className="flex-1 w-full max-w-5xl mx-auto p-4 flex flex-col bg-gray-50/50 dark:bg-gray-950 pb-24">
        {children}
      </main>

      {/* Navigation */}
      <nav className="fixed bottom-0 left-0 right-0 bg-white/80 dark:bg-gray-900/80 backdrop-blur-lg border-t border-gray-200 dark:border-gray-800 pb-safe z-50">
        <div className="flex justify-around items-center h-16 w-full max-w-5xl mx-auto px-4">
          <button
            onClick={() => setActiveView('dashboard')}
            className={`flex flex-col items-center justify-center w-full h-full transition-colors ${activeView === 'dashboard' ? 'text-brand' : 'text-gray-400'}`}
          >
            <LayoutDashboard className="w-5 h-5 mb-1" />
            <span className="text-[9px] font-black uppercase tracking-widest">Room</span>
          </button>

          <button
            onClick={() => setActiveView('verify')}
            className={`flex flex-col items-center justify-center w-full h-full transition-colors ${activeView === 'verify' ? 'text-brand' : 'text-gray-400'}`}
          >
            <ShieldCheck className="w-5 h-5 mb-1" />
            <span className="text-[9px] font-black uppercase tracking-widest">Verify</span>
          </button>

          <button
            onClick={() => setActiveView('agents')}
            className={`flex flex-col items-center justify-center w-full h-full transition-colors ${activeView === 'agents' ? 'text-brand' : 'text-gray-400'}`}
          >
            <Users className="w-5 h-5 mb-1" />
            <span className="text-[9px] font-black uppercase tracking-widest">Agents</span>
          </button>

          <button
            onClick={() => setActiveView('workforce')}
            className={`flex flex-col items-center justify-center w-full h-full transition-colors ${activeView === 'workforce' ? 'text-brand' : 'text-gray-400'}`}
          >
            <Activity className="w-5 h-5 mb-1" />
            <span className="text-[9px] font-black uppercase tracking-widest">Monitor</span>
          </button>

          <button
            onClick={() => setActiveView('audit')}
            className={`flex flex-col items-center justify-center w-full h-full transition-colors ${activeView === 'audit' ? 'text-brand' : 'text-gray-400'}`}
          >
            <Map className="w-5 h-5 mb-1" />
            <span className="text-[9px] font-black uppercase tracking-widest">Audit</span>
          </button>

          <button
            onClick={() => setActiveView('profile')}
            className={`flex flex-col items-center justify-center w-full h-full transition-colors ${activeView === 'profile' ? 'text-brand' : 'text-gray-400'}`}
          >
            <UserCircle className="w-5 h-5 mb-1" />
            <span className="text-[9px] font-black uppercase tracking-widest">Profile</span>
          </button>

          <button
            onClick={() => setActiveView('settings')}
            className={`flex flex-col items-center justify-center w-full h-full transition-colors ${activeView === 'settings' ? 'text-brand' : 'text-gray-400'}`}
          >
            <Settings className="w-5 h-5 mb-1" />
            <span className="text-[9px] font-black uppercase tracking-widest">Config</span>
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
  const [activeView, setActiveView] = useState('dashboard');

  if (!isAuthenticated && !isResetRequired) {
    return (
      <ThemeProvider>
        <NotificationProvider>
          <NotificationBanner />
          <SecurityDialog />
          <LoginScreen
            onLoginSuccess={() => setIsAuthenticated(true)}
            onRequireReset={(email) => { setResetEmail(email); setIsResetRequired(true); }}
          />
        </NotificationProvider>
      </ThemeProvider>
    );
  }

  if (isResetRequired) {
    return (
      <ThemeProvider>
        <NotificationProvider>
          <NotificationBanner />
          <SecurityDialog />
          <PasswordResetScreen
            email={resetEmail}
            onComplete={() => { setIsResetRequired(false); setIsAuthenticated(false); }}
          />
        </NotificationProvider>
      </ThemeProvider>
    );
  }

  return (
    <ThemeProvider>
      <NotificationProvider>
        <NotificationBanner />
        <SecurityDialog />
        <LayoutShell
          activeView={activeView}
          setActiveView={setActiveView}
          onLogout={() => setIsAuthenticated(false)}
        >
          <div className="flex-1 flex flex-col">
            {activeView === 'dashboard' && <AdminDashboard setActiveView={setActiveView} />}
            {activeView === 'verify' && <VerificationScreen />}
            {activeView === 'agents' && <AgentManagement />}
            {activeView === 'workforce' && <WorkforceMonitor />}
            {activeView === 'audit' && <CoverageAudit />}
            {activeView === 'profile' && <UserProfileScreen onLogout={() => setIsAuthenticated(false)} />}
            {activeView === 'settings' && <ElectionConfig />}
          </div>
        </LayoutShell>
      </NotificationProvider>
    </ThemeProvider>
  );
}

export default App;


