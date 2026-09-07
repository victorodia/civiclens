import React, { useState } from 'react';
import { ShieldAlert, KeyRound, Loader2, CheckCircle2, Eye, EyeOff } from 'lucide-react';
import { useNotification } from '../contexts/NotificationContext';

const PasswordResetScreen = ({ email, onComplete }) => {
    const { showNotification } = useNotification();
    const [newPassword, setNewPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [duressPassword, setDuressPassword] = useState('');
    const [showMainPassword, setShowMainPassword] = useState(false);
    const [showDuressPassword, setShowDuressPassword] = useState(false);
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (newPassword !== confirmPassword) {
            showNotification("Main passwords do not match.", "warning");
            return;
        }
        if (newPassword.length < 6 || duressPassword.length < 6) {
            showNotification("All passwords must be at least 6 characters.", "warning");
            return;
        }
        if (newPassword === duressPassword) {
            showNotification("Your Main Password and Duress Password MUST be different!", "error");
            return;
        }

        setLoading(true);

        try {
            const res = await fetch('http://127.0.0.1:8001/auth/secure-initialization', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    email,
                    new_password: newPassword,
                    duress_password: duressPassword
                })
            });

            const data = await res.json();
            if (!res.ok) {
                const errorDetail = Array.isArray(data.detail)
                    ? data.detail.map(err => `${err.loc[err.loc.length - 1]}: ${err.msg}`).join(", ")
                    : data.detail;
                throw new Error(errorDetail || "Security initialization failed.");
            }

            showNotification("Security Initialization Complete. Please log in.", "success");
            onComplete(); // Proceeds to login via App.jsx state change
        } catch (err) {
            showNotification(err.message, "error");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-brand-dark z-[100] flex flex-col justify-center items-center p-6 sm:p-12 overflow-y-auto w-full h-full">
            <div className="w-full max-w-sm space-y-6 animate-in slide-in-from-right duration-500">

                <div className="text-center space-y-3">
                    <div className="mx-auto w-16 h-16 bg-white/10 rounded-2xl flex items-center justify-center">
                        <ShieldAlert className="w-8 h-8 text-amber-400" />
                    </div>
                    <h2 className="text-xl font-black text-white tracking-widest uppercase">Security Initialization</h2>
                    <p className="text-xs text-white/70 leading-relaxed font-bold">
                        For security, your temporary admin-provided password has expired. You must set your permanent credentials now.
                    </p>
                </div>

                <form onSubmit={handleSubmit} className="space-y-4 bg-white/5 p-6 rounded-3xl border border-white/10 backdrop-blur-md shadow-2xl">

                    <div className="space-y-1">
                        <label className="text-[10px] font-black text-white/50 uppercase tracking-widest">Main Password</label>
                        <div className="relative">
                            <input type={showMainPassword ? "text" : "password"} required value={newPassword} onChange={e => setNewPassword(e.target.value)}
                                className="w-full px-4 pr-12 py-3 bg-black/20 text-white border border-white/10 rounded-xl outline-none focus:border-brand-light transition-colors" placeholder="••••••••" />
                            <button type="button" onClick={() => setShowMainPassword(!showMainPassword)} className="absolute right-3 top-1/2 -translate-y-1/2 text-white/40 hover:text-white transition-colors">
                                {showMainPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                            </button>
                        </div>
                    </div>

                    <div className="space-y-1">
                        <label className="text-[10px] font-black text-white/50 uppercase tracking-widest">Confirm Main Password</label>
                        <div className="relative">
                            <input type={showMainPassword ? "text" : "password"} required value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)}
                                className="w-full px-4 pr-12 py-3 bg-black/20 text-white border border-white/10 rounded-xl outline-none focus:border-brand-light transition-colors" placeholder="••••••••" />
                        </div>
                    </div>

                    <div className="h-px w-full bg-white/10 my-4"></div>

                    <div className="space-y-2 bg-red-900/40 p-4 rounded-2xl border border-red-500/30">
                        <div className="flex items-center space-x-2">
                            <KeyRound className="w-4 h-4 text-red-400" />
                            <label className="text-[10px] font-black text-red-300 uppercase tracking-widest">Secret Duress Password</label>
                        </div>
                        <p className="text-[9px] text-red-200/80 leading-tight">If forced to log in by hostiles, use this password instead. The app will look normal, but syncs will be secretly flagged.</p>
                        <div className="relative">
                            <input type={showDuressPassword ? "text" : "password"} required value={duressPassword} onChange={e => setDuressPassword(e.target.value)}
                                className="w-full px-4 pr-12 py-3 bg-black/40 text-red-100 border border-red-500/50 rounded-xl outline-none focus:border-red-400 transition-colors" placeholder="Panic Password" />
                            <button type="button" onClick={() => setShowDuressPassword(!showDuressPassword)} className="absolute right-3 top-1/2 -translate-y-1/2 text-red-400/60 hover:text-red-400 transition-colors">
                                {showDuressPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                            </button>
                        </div>
                    </div>


                    <button disabled={loading} type="submit" className="w-full mt-4 bg-white text-brand-dark font-black uppercase tracking-widest py-4 rounded-xl shadow-xl active:scale-95 transition-transform flex items-center justify-center space-x-2">
                        {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <><span>Finalize Security</span> <CheckCircle2 className="w-4 h-4 ml-1" /></>}
                    </button>
                </form>

            </div>
        </div>
    );
};

export default PasswordResetScreen;


