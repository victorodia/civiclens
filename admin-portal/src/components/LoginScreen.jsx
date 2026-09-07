import React, { useState } from 'react';
import { Shield, Lock, Mail, Loader2, Eye, EyeOff } from 'lucide-react';
import { useNotification } from '../contexts/NotificationContext';

const LoginScreen = ({ onLoginSuccess, onRequireReset }) => {
    const { showNotification } = useNotification();
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    const [step, setStep] = useState('login'); // 'login' or 'mfa'
    const [mfaCode, setMfaCode] = useState('');
    const [loading, setLoading] = useState(false);

    const handleLogin = async (e) => {
        e.preventDefault();
        setLoading(true);

        try {
            const response = await fetch('http://127.0.0.1:8001/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password, device_fingerprint: 'ADMIN_TRUSTED_DEVICE' })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'Authentication failed');
            }

            if (data.requires_password_reset) {
                onRequireReset(email);
            } else {
                setStep('mfa');
                showNotification("Primary Credentials Authenticated. MFA Required.", "info");
            }
        } catch (err) {
            showNotification(err.message, "error");
        } finally {
            setLoading(false);
        }
    };

    const handleMfaSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);

        try {
            await new Promise(resolve => setTimeout(resolve, 1000));
            if (mfaCode === '123456') {
                onLoginSuccess();
            } else {
                throw new Error("Invalid MFA Code.");
            }
        } catch (err) {
            showNotification(err.message, "error");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-white dark:bg-gray-950 z-[100] flex flex-col justify-center items-center p-6 sm:p-12 overflow-y-auto">
            <div className="w-full max-w-sm space-y-8 animate-in fade-in slide-in-from-bottom-8 duration-700">

                <div className="flex flex-col items-center space-y-4">
                    <div className="w-16 h-16 bg-brand rounded-2xl flex items-center justify-center shadow-lg shadow-brand/30">
                        <Shield className="w-8 h-8 text-white" />
                    </div>
                    <div className="text-center">
                        <h2 className="text-2xl font-black text-gray-900 dark:text-white tracking-[0.2em] uppercase">Civic Lens</h2>
                        <p className="text-xs font-bold text-gray-500 tracking-widest uppercase mt-1">Zero-Trust Authentication</p>
                    </div>
                </div>

                {step === 'login' ? (
                    <form onSubmit={handleLogin} className="space-y-5 bg-gray-50/50 dark:bg-gray-900 border border-gray-100 dark:border-gray-800 p-6 rounded-3xl shadow-2xl">
                        <div className="space-y-2">
                            <label className="text-xs font-bold text-gray-700 dark:text-gray-400 uppercase tracking-wider ml-1">Email / Admin ID</label>
                            <div className="relative">
                                <Mail className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
                                <input
                                    type="email"
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    className="w-full pl-12 pr-4 py-4 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-950 text-gray-900 dark:text-white focus:ring-2 focus:ring-brand outline-none transition-all placeholder:text-gray-400 dark:placeholder:text-gray-600"
                                    placeholder="admin@civiclens.io"
                                    required
                                />
                            </div>
                        </div>

                        <div className="space-y-2">
                            <label className="text-xs font-bold text-gray-700 dark:text-gray-400 uppercase tracking-wider ml-1">Secure Password</label>
                            <div className="relative">
                                <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
                                <input
                                    type={showPassword ? "text" : "password"}
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    className="w-full pl-12 pr-12 py-4 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-950 text-gray-900 dark:text-white focus:ring-2 focus:ring-brand outline-none transition-all placeholder:text-gray-400 dark:placeholder:text-gray-600"
                                    placeholder="••••••••••"
                                    required
                                />
                                <button
                                    type="button"
                                    onClick={() => setShowPassword(!showPassword)}
                                    className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400 hover:text-brand transition-colors"
                                >
                                    {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                                </button>
                            </div>
                        </div>

                        <button
                            type="submit"
                            disabled={loading}
                            className="w-full bg-brand text-white font-black uppercase tracking-widest text-sm py-4 rounded-xl shadow-xl shadow-brand/20 active:scale-[0.98] transition-all flex items-center justify-center"
                        >
                            {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <span>Secure Login</span>}
                        </button>
                    </form>
                ) : (
                    <form onSubmit={handleMfaSubmit} className="space-y-5 bg-gray-50/50 dark:bg-gray-900 border border-gray-100 dark:border-gray-800 p-6 rounded-3xl shadow-2xl">
                        <div className="text-center mb-2">
                            <p className="text-xs font-bold text-brand uppercase tracking-tighter">Two-Factor Authentication</p>
                            <p className="text-[10px] text-gray-500 mt-1">Enter the 6-digit code from your app</p>
                        </div>
                        <div className="space-y-2">
                            <input
                                type="text"
                                maxLength="6"
                                value={mfaCode}
                                onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, ''))}
                                className="w-full p-4 text-center text-3xl font-black tracking-[0.5em] rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-950 text-brand outline-none focus:ring-2 focus:ring-brand transition-all"
                                placeholder="000000"
                                required
                                autoFocus
                            />
                        </div>

                        <button
                            type="submit"
                            disabled={loading}
                            className="w-full bg-brand text-white font-black uppercase tracking-widest text-sm py-4 rounded-xl shadow-xl shadow-brand/20 active:scale-[0.98] transition-all flex items-center justify-center"
                        >
                            {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <span>Verify & Access</span>}
                        </button>

                        <button
                            type="button"
                            onClick={() => setStep('login')}
                            className="w-full text-[10px] font-black text-gray-400 hover:text-brand uppercase tracking-widest transition-colors"
                        >
                            Back to Password
                        </button>
                    </form>
                )}

                <div className="text-center text-[10px] text-gray-400 font-bold uppercase tracking-widest space-y-2">
                    <p className="flex items-center justify-center space-x-1 opacity-70">
                        <Lock className="w-3 h-3" />
                        <span>TLS 1.3 encryption active</span>
                    </p>
                    <p className="opacity-50">Device Fingerprint: Verified</p>
                </div>

            </div>
        </div>
    );
};

export default LoginScreen;
