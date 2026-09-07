import { useState } from 'react';
import { UserCircle, Shield, KeyRound, Smartphone, MapPin, CheckCircle2 } from 'lucide-react';
import { useNotification } from '../contexts/NotificationContext';
import { clearAllData } from '../db/db';

const UserProfileScreen = ({ agentId = "AGT-9428-21", puCode = "01-02-03-004", onLogout }) => {
    const { showNotification } = useNotification();
    const [activeTab, setActiveTab] = useState('overview'); // overview, password
    const [loading, setLoading] = useState(false);

    const [mainPassword, setMainPassword] = useState('');
    const [duressPassword, setDuressPassword] = useState('');

    const handlePasswordUpdate = async (e) => {
        e.preventDefault();
        setLoading(true);

        // Mock API call to update passwords
        await new Promise(resolve => setTimeout(resolve, 1500));
        showNotification('Credentials updated. Please log in again.', 'success');
        setTimeout(() => {
            onLogout();
        }, 1500);
        setMainPassword('');
        setDuressPassword('');
        setLoading(false);
    };

    const handlePurge = async () => {
        if (window.confirm("CRITICAL SECURITY ACTION: This will permanently delete all unsynced result drafts and local device settings. This CANNOT be undone. Proceed?")) {
            await clearAllData();
            window.location.reload();
        }
    };

    return (
        <div className="bg-white dark:bg-gray-900 rounded-3xl shadow-xl border border-gray-100 dark:border-gray-800 p-6">

            {/* Header */}
            <div className="flex items-center space-x-4 mb-6">
                <div className="w-16 h-16 bg-brand-light dark:bg-brand-dark/30 rounded-full flex items-center justify-center border-4 border-white dark:border-gray-900 shadow-sm relative">
                    <UserCircle className="w-10 h-10 text-brand" />
                    <div className="absolute bottom-0 right-0 w-4 h-4 bg-green-500 border-2 border-white dark:border-gray-900 rounded-full"></div>
                </div>
                <div>
                    <h2 className="text-xl font-black text-gray-900 dark:text-white uppercase tracking-tight">Agent Profile</h2>
                    <p className="text-xs text-brand font-bold uppercase tracking-wider">{agentId}</p>
                </div>
            </div>

            {/* Tabs */}
            <div className="flex space-x-2 bg-gray-100 dark:bg-gray-800 p-1 rounded-xl mb-6">
                <button
                    onClick={() => setActiveTab('overview')}
                    className={`flex-1 overflow-hidden py-2 text-xs font-bold uppercase tracking-wider rounded-lg transition-colors ${activeTab === 'overview' ? 'bg-white dark:bg-gray-700 text-brand shadow-sm' : 'text-gray-500'}`}
                >
                    Security Posture
                </button>
                <button
                    onClick={() => setActiveTab('password')}
                    className={`flex-1 overflow-hidden py-2 text-xs font-bold uppercase tracking-wider rounded-lg transition-colors ${activeTab === 'password' ? 'bg-white dark:bg-gray-700 text-brand shadow-sm' : 'text-gray-500'}`}
                >
                    Credentials
                </button>
            </div>

            {/* Tab Content */}
            <div className="space-y-4">
                {activeTab === 'overview' && (
                    <div className="space-y-4 animate-in fade-in duration-300">
                        <div className="bg-gray-50 dark:bg-gray-800/50 p-4 rounded-2xl flex items-start space-x-4 border border-gray-100 dark:border-gray-800">
                            <MapPin className="w-5 h-5 text-gray-400 mt-0.5 flex-shrink-0" />
                            <div>
                                <p className="text-[10px] font-black uppercase text-gray-400 tracking-widest">Assigned Location</p>
                                <p className="text-sm font-bold text-gray-800 dark:text-gray-200">PU: {puCode}</p>
                            </div>
                        </div>

                        <div className="bg-teal-50 dark:bg-brand-dark/20 p-4 rounded-2xl flex items-start space-x-4 border border-teal-100 dark:border-brand-dark/50">
                            <Shield className="w-5 h-5 text-brand mt-0.5 flex-shrink-0" />
                            <div>
                                <p className="text-[10px] font-black uppercase text-brand tracking-widest">Connection Security</p>
                                <p className="text-sm font-bold text-teal-900 dark:text-teal-100">TLS 1.3 End-to-End Encrypted</p>
                            </div>
                        </div>

                        <div className="bg-amber-50 dark:bg-amber-900/20 p-4 rounded-2xl flex items-start space-x-4 border border-amber-100 dark:border-amber-900/50">
                            <Smartphone className="w-5 h-5 text-amber-600 mt-0.5 flex-shrink-0" />
                            <div>
                                <p className="text-[10px] font-black uppercase text-amber-600 tracking-widest">Device Fingerprint</p>
                                <p className="text-sm font-bold text-amber-900 dark:text-amber-100 break-all">Locked to current device hash</p>
                            </div>
                        </div>

                    </div>
                )}

                {activeTab === 'password' && (
                    <form onSubmit={handlePasswordUpdate} className="space-y-4 animate-in fade-in duration-300">

                        <div className="space-y-2">
                            <label className="text-[10px] font-black text-gray-500 uppercase tracking-widest flex items-center"><KeyRound className="w-3 h-3 mr-1" /> Update Main Password</label>
                            <input type="password" value={mainPassword} onChange={e => setMainPassword(e.target.value)}
                                className="w-full px-4 py-3 bg-gray-50 dark:bg-gray-800 text-gray-900 dark:text-white border border-gray-200 dark:border-gray-700 rounded-xl outline-none focus:border-brand transition-colors" placeholder="Leave blank to keep unchanged" />
                        </div>

                        <div className="space-y-2 bg-red-50 dark:bg-red-900/20 p-4 rounded-xl border border-red-100 dark:border-red-900/50">
                            <label className="text-[10px] font-black text-red-500 uppercase tracking-widest flex items-center"><Shield className="w-3 h-3 mr-1" /> Update Duress Password</label>
                            <input type="password" value={duressPassword} onChange={e => setDuressPassword(e.target.value)}
                                className="w-full px-4 py-3 bg-white dark:bg-gray-900 text-red-900 dark:text-red-100 border border-red-200 dark:border-red-900 rounded-xl outline-none focus:border-red-400 transition-colors" placeholder="Leave blank to keep unchanged" />
                        </div>

                        <button disabled={loading} type="submit" className="w-full mt-4 bg-brand text-white font-black uppercase tracking-widest py-4 rounded-xl shadow-md active:scale-95 transition-transform flex items-center justify-center">
                            {loading ? 'Updating...' : 'Save Credentials'}
                        </button>
                    </form>
                )}
            </div>

            {/* Global Actions */}
            <div className="mt-8 pt-6 border-t border-gray-100 dark:border-gray-800 space-y-3">
                <button
                    onClick={onLogout}
                    className="w-full py-4 rounded-xl bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 font-black uppercase tracking-widest text-xs hover:bg-red-100 dark:hover:bg-red-900/40 transition-colors"
                >
                    Sign Out Session
                </button>

                <button
                    onClick={handlePurge}
                    className="w-full py-3 rounded-xl border border-gray-200 dark:border-gray-800 text-gray-400 dark:text-gray-600 font-bold uppercase tracking-widest text-[9px] hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors flex items-center justify-center space-x-2"
                >
                    <Shield className="w-3 h-3" />
                    <span>Purge Local Storage / Factory Reset</span>
                </button>
            </div>

        </div>
    );
};

export default UserProfileScreen;


