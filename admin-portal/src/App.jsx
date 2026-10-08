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
import ResultsFeed from './components/ResultsFeed';
import { NotificationProvider, useNotification } from './contexts/NotificationContext';
import NotificationBanner from './components/NotificationBanner';
import SecurityDialog from './components/SecurityDialog';
import { LayoutDashboard, ShieldCheck, UserCircle, Users, Activity, Map, Settings, FileText } from 'lucide-react';

function LayoutShell({ children, activeView, setActiveView, onLogout, walletStatus, onRefreshWallet, hasPerm }) {
  const { isDarkMode, toggleTheme } = useTheme();
  const { showNotification } = useNotification();

  React.useEffect(() => {
    const handleOnline = () => showNotification('Connection restored. You are back online.', 'success');
    const handleOffline = () => showNotification('No Internet Connection. Working Offline.', 'warning');

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, [showNotification]);

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
            {walletStatus && walletStatus.balance !== null && (
              <div className="flex flex-col items-end mr-3">
                <div className="flex items-center space-x-2">
                  <span className="text-[9px] uppercase tracking-widest text-white/70">Wallet Unit</span>
                  {walletStatus.address && (
                    <div className="flex items-center space-x-1">
                      <button 
                        onClick={() => { navigator.clipboard.writeText(walletStatus.address); showNotification('Wallet address copied to clipboard.', 'success'); }} 
                        className="text-[8px] bg-white/20 px-1 py-0.5 rounded hover:bg-white/30 text-white"
                        title="Copy Address"
                      >
                        Copy
                      </button>
                      <button 
                        onClick={onRefreshWallet} 
                        className="text-[8px] bg-white/20 px-1 py-0.5 rounded hover:bg-white/30 text-white"
                        title="Refresh Balance"
                      >
                        Refresh
                      </button>

                    </div>
                  )}
                </div>
                <span className={`text-xs font-black font-mono ${walletStatus.balance < 0.05 ? 'text-red-400' : 'text-green-400'}`}>
                  {walletStatus.balance.toFixed(4)} POL
                </span>
              </div>
            )}
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
          { (hasPerm("view_live_telemetry") || hasPerm("view_results")) && <button
            onClick={() => setActiveView('dashboard')}
            className={`flex flex-col items-center justify-center w-full h-full transition-colors ${activeView === 'dashboard' ? 'text-brand' : 'text-gray-400'}`}
          >
            <LayoutDashboard className="w-5 h-5 mb-1" />
            <span className="text-[9px] font-black uppercase tracking-widest">Room</span>
          </button> }

          { hasPerm("approve_results") && <button
            onClick={() => setActiveView('verify')}
            className={`flex flex-col items-center justify-center w-full h-full transition-colors ${activeView === 'verify' ? 'text-brand' : 'text-gray-400'}`}
          >
            <ShieldCheck className="w-5 h-5 mb-1" />
            <span className="text-[9px] font-black uppercase tracking-widest">Verify</span>
          </button> }

          { hasPerm("view_agents") && <button
            onClick={() => setActiveView('agents')}
            className={`flex flex-col items-center justify-center w-full h-full transition-colors ${activeView === 'agents' ? 'text-brand' : 'text-gray-400'}`}
          >
            <Users className="w-5 h-5 mb-1" />
            <span className="text-[9px] font-black uppercase tracking-widest">Agents</span>
          </button> }

          { hasPerm("view_agents") && <button
            onClick={() => setActiveView('workforce')}
            className={`flex flex-col items-center justify-center w-full h-full transition-colors ${activeView === 'workforce' ? 'text-brand' : 'text-gray-400'}`}
          >
            <Activity className="w-5 h-5 mb-1" />
            <span className="text-[9px] font-black uppercase tracking-widest">Monitor</span>
          </button> }

          { hasPerm("view_results") && <button
            onClick={() => setActiveView('audit')}
            className={`flex flex-col items-center justify-center w-full h-full transition-colors ${activeView === 'audit' ? 'text-brand' : 'text-gray-400'}`}
          >
            <Map className="w-5 h-5 mb-1" />
            <span className="text-[9px] font-black uppercase tracking-widest">Audit</span>
          </button> }

          <button
            onClick={() => setActiveView('profile')}
            className={`flex flex-col items-center justify-center w-full h-full transition-colors ${activeView === 'profile' ? 'text-brand' : 'text-gray-400'}`}
          >
            <UserCircle className="w-5 h-5 mb-1" />
            <span className="text-[9px] font-black uppercase tracking-widest">Profile</span>
          </button>

          { (hasPerm("trigger_factory_reset") || hasPerm("view_system_users")) && <button
            onClick={() => setActiveView('settings')}
            className={`flex flex-col items-center justify-center w-full h-full transition-colors ${activeView === 'settings' ? 'text-brand' : 'text-gray-400'}`}
          >
            <Settings className="w-5 h-5 mb-1" />
            <span className="text-[9px] font-black uppercase tracking-widest">Config</span>
          </button> }
        </div>
      </nav>
    </div>
  );
}


const originalFetch = window.fetch.bind(window);
window.fetch = async (url, options = {}) => {
    // Only intercept backend API calls
    if (typeof url === 'string' && (url.startsWith('/admin') || url.startsWith('/auth') || url.startsWith('/api'))) {
        const token = localStorage.getItem('adminToken');
        if (token) {
            options.headers = {
                ...options.headers,
                'Authorization': `Bearer ${token}` 
            };
        }
    }
    
    const response = await originalFetch(url, options);
    
    // Zero-vulnerability fallback: Auto-logout on 401 Unauthorized (only if authenticated and not on login page)
    if (response.status === 401 && typeof url === 'string' && !url.includes('/auth/login')) {
        console.warn('Security Token Expired or Invalid. Logging out.');
        localStorage.clear();
        sessionStorage.clear();
        window.location.reload();
    }
    
    return response;
};

// Safe JSON parsing: returns null instead of throwing on HTML error pages
async function safeJson(response) {
  const contentType = response.headers.get('content-type') || '';
  if (!contentType.includes('application/json')) {
    // Backend returned HTML (502/504/etc.) — not JSON
    return null;
  }
  try {
    return await response.json();
  } catch {
    return null;
  }
}


function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(() => {
    return localStorage.getItem('isAdminAuthenticated') === 'true';
  });
  const [isResetRequired, setIsResetRequired] = useState(false);
  const [resetEmail, setResetEmail] = useState('');
  const [activeView, setActiveView] = useState(() => {
    return localStorage.getItem('adminActiveView') || 'dashboard';
  });
  
  const setPersistedActiveView = (view) => {
    localStorage.setItem('adminActiveView', view);
    setActiveView(view);
  };

  const [walletStatus, setWalletStatus] = useState({ address: null, balance: null });
  const [userPermissions, setUserPermissions] = useState(null);
  const hasPerm = (p) => userPermissions !== null && userPermissions.includes(p);

  


  React.useEffect(() => {
    if (!isAuthenticated) return;
    
    
    const fetchPerms = async () => {
      try {
        const res = await fetch('/admin/my-permissions');
        if (res.ok) {
          const data = await res.json();
          setUserPermissions(data.permissions);
        }
      } catch (err) {}
    };
    fetchPerms();
    
    const fetchWallet = async () => {
      try {
        const res = await fetch('/admin/wallet-balance');
        if (res.ok) {
          const data = await res.json();
          setWalletStatus(data);
        }
      } catch (err) {
        console.error('Failed to fetch wallet status', err);
      }
    };
    
    fetchWallet();
    const interval = setInterval(fetchWallet, 30000);
    return () => clearInterval(interval);
  }, [isAuthenticated]);


  if (!isAuthenticated && !isResetRequired) {
    return (
      <ThemeProvider>
        <NotificationProvider>
          <NotificationBanner />
        {walletStatus.balance !== null && walletStatus.balance < 0.05 && (
          <div className="bg-red-600 text-white font-black p-3 text-center z-[9999] relative flex flex-col items-center">
            <span className="text-sm uppercase tracking-widest">🚨 Critical: Wallet out of Unit. Uploads currently suspended 🚨</span>
          </div>
        )}
          <SecurityDialog />
          <LoginScreen
            onLoginSuccess={(token) => {
                localStorage.setItem('adminToken', token);
                localStorage.setItem('isAdminAuthenticated', 'true');
                setIsAuthenticated(true);
            }}
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
        {walletStatus.balance !== null && walletStatus.balance < 0.05 && (
          <div className="bg-red-600 text-white font-black p-3 text-center z-[9999] relative flex flex-col items-center">
            <span className="text-sm uppercase tracking-widest">🚨 Critical: Wallet out of Unit. Uploads currently suspended 🚨</span>
          </div>
        )}
          <SecurityDialog />
          <PasswordResetScreen
            email={resetEmail}
            onComplete={() => { setIsResetRequired(false); setIsAuthenticated(false); }}
          />
        </NotificationProvider>
      </ThemeProvider>
    );
  }

  const handleLogout = async () => {
    setIsAuthenticated(false);
    
    // Only purge session state, DO NOT touch Service Worker Caches
    localStorage.clear();
    sessionStorage.clear();
    
    window.location.reload();
  };

  const renderView = () => {
    switch (activeView) {
      case 'dashboard':
        return <AdminDashboard setActiveView={setPersistedActiveView} />;
      case 'feed':
        return <ResultsFeed />;
      case 'verify':
        return <VerificationScreen />;
      case 'agents':
        return <AgentManagement />;
      case 'workforce':
        return <WorkforceMonitor />;
      case 'audit':
        return <CoverageAudit setActiveView={setPersistedActiveView} />;
      case 'profile':
        return <UserProfileScreen onLogout={handleLogout} />;
      case 'settings':
        return <ElectionConfig />;
      default:
        return <AdminDashboard setActiveView={setPersistedActiveView} />;
    }
  };

  return (
    <ThemeProvider>
      <NotificationProvider>
        <NotificationBanner />
        {walletStatus.balance !== null && walletStatus.balance < 0.05 && (
          <div className="bg-red-600 text-white font-black p-3 text-center z-[9999] relative flex flex-col items-center">
            <span className="text-sm uppercase tracking-widest">🚨 Critical: Wallet out of Unit. Uploads currently suspended 🚨</span>
          </div>
        )}
        <SecurityDialog />
        <LayoutShell
          activeView={activeView}
          setActiveView={setPersistedActiveView}
          onLogout={handleLogout}
          walletStatus={walletStatus}
          hasPerm={hasPerm}
          onRefreshWallet={async () => {
            try {
              const res = await fetch('/admin/wallet-balance');
              if (res.ok) {
                const data = await res.json();
                setWalletStatus(data);
              }
            } catch (err) {}
          }}
        >
          <div className="flex-1 flex flex-col">
            {renderView()}
          </div>
        </LayoutShell>
      </NotificationProvider>
    </ThemeProvider>
  );
}

export default App;


