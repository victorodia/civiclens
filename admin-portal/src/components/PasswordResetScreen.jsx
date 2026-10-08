import React, { useState, useEffect } from 'react';
import { ShieldAlert, KeyRound, Loader2, CheckCircle2, Eye, EyeOff, Smartphone } from 'lucide-react';
import { useNotification } from '../contexts/NotificationContext';
import { QRCodeCanvas } from 'qrcode.react';

const PasswordResetScreen = ({ email, onComplete }) => {
    const { showNotification } = useNotification();
    const [step, setStep] = useState('password'); // 'password' or 'mfa'

    // Password step state
    const [newPassword, setNewPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [duressPassword, setDuressPassword] = useState('');
    const [showMainPassword, setShowMainPassword] = useState(false);
    const [showDuressPassword, setShowDuressPassword] = useState(false);
    const [loading, setLoading] = useState(false);

    // MFA step state
    const [mfaSecret, setMfaSecret] = useState('');
    const [mfaUri, setMfaUri] = useState('');
    const [mfaCode, setMfaCode] = useState('');

    const handlePasswordSubmit = async (e) => {
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
            const res = await fetch('/auth/secure-initialization', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    email,
                    new_password: newPassword,
                    duress_password: duressPassword
                })
            });

            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Security initialization failed.");

            showNotification("Passwords updated. Proceeding to MFA Setup.", "success");
            
            // Now fetch MFA setup data
            const mfaRes = await fetch(`/admin/mfa/setup?email=${encodeURIComponent(email)}`);
            const mfaData = await mfaRes.json();
            if (!mfaRes.ok) throw new Error(mfaData.detail || "Failed to initialize MFA.");

            setMfaSecret(mfaData.secret);
            setMfaUri(mfaData.provisioning_uri);
            setStep('mfa');

        } catch (err) {
            showNotification(err.message, "error");
        } finally {
            setLoading(false);
        }
    };

    const handleMfaSubmit = async (e) => {
        e.preventDefault();
        if (mfaCode.length !== 6) {
            showNotification("Please enter a 6-digit code.", "warning");
            return;
        }

        setLoading(true);
        try {
            const res = await fetch('/admin/mfa/verify', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    email,
                    token: mfaCode
                })
            });

            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "MFA Verification failed.");

            showNotification("Security Initialization Complete. Access Granted.", "success");
            onComplete();
        } catch (err) {
            showNotification(err.message, "error");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-brand-dark z-[100] flex flex-col justify-center items-center p-6 sm:p-12 overflow-y-auto w-full h-full">
            <div className="w-full max-w-sm space-y-6 animate-in slide-in-from-right duration-500">
                {step === 'password' ? (
                    <>
                        <div className="text-center space-y-3">
                            <div className="mx-auto w-16 h-16 bg-white/10 rounded-2xl flex items-center justify-center">
                                <ShieldAlert className="w-8 h-8 text-amber-400" />
                            </div>
                            <h2 className="text-xl font-black text-white tracking-widest uppercase">Security Initialization</h2>
                            <p className="text-xs text-white/70 leading-relaxed font-bold">
                                For security, your temporary admin-provided password has expired. You must set your permanent credentials now.
                            </p>
                        </div>
                        <form onSubmit={handlePasswordSubmit} className="space-y-4 bg-white/5 p-6 rounded-3xl border border-white/10 backdrop-blur-md shadow-2xl">
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
                                {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <><span>Next Step</span> <CheckCircle2 className="w-4 h-4 ml-1" /></>}
                            </button>
                        </form>
                    </>
                ) : (
                    <>
                        <div className="text-center space-y-3">
                            <div className="mx-auto w-16 h-16 bg-white/10 rounded-2xl flex items-center justify-center">
                                <Smartphone className="w-8 h-8 text-brand-light" />
                            </div>
                            <h2 className="text-xl font-black text-white tracking-widest uppercase">Set Up Authenticator</h2>
                            <p className="text-xs text-white/70 leading-relaxed font-bold">
                                Scan this QR code with Google Authenticator or Authy to secure your account.
                            </p>
                        </div>
                        <form onSubmit={handleMfaSubmit} className="space-y-4 bg-white/5 p-6 rounded-3xl border border-white/10 backdrop-blur-md shadow-2xl flex flex-col items-center">
                            
                            <div className="bg-white p-4 rounded-2xl mb-2">
                                {mfaUri && <QRCodeCanvas value={mfaUri} size={180} level={"H"} />}
                            </div>
                            
                            <p className="text-[10px] text-white/50 tracking-widest font-mono text-center">
                                Secret: {mfaSecret}
                            </p>

                            <div className="w-full space-y-1 mt-4">
                                <label className="text-[10px] font-black text-white/50 uppercase tracking-widest">Enter 6-Digit Code</label>
                                <input 
                                    type="text" 
                                    maxLength="6"
                                    required 
                                    value={mfaCode} 
                                    onChange={e => setMfaCode(e.target.value.replace(/\D/g, ''))}
                                    className="w-full text-center tracking-[0.5em] px-4 py-3 text-2xl font-black bg-black/20 text-white border border-white/10 rounded-xl outline-none focus:border-brand-light transition-colors" 
                                    placeholder="000000" 
                                />
                            </div>

                            <button disabled={loading} type="submit" className="w-full mt-4 bg-white text-brand-dark font-black uppercase tracking-widest py-4 rounded-xl shadow-xl active:scale-95 transition-transform flex items-center justify-center space-x-2">
                                {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <><span>Verify & Complete</span> <CheckCircle2 className="w-4 h-4 ml-1" /></>}
                            </button>
                        </form>
                    </>
                )}
            </div>
        </div>
    );
};

export default PasswordResetScreen;
