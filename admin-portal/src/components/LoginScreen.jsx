import React, { useState, useEffect, useRef } from 'react';
import { Shield, Lock, Mail, Loader2, Eye, EyeOff } from 'lucide-react';
import { useNotification } from '../contexts/NotificationContext';

const LoginScreen = ({ onLoginSuccess, onRequireReset }) => {
    const { showNotification } = useNotification();
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    const [step, setStep] = useState('login'); // 'login', 'mfa', 'mfa_setup'
    const [mfaCode, setMfaCode] = useState('');
    const [qrCode, setQrCode] = useState('');
    const [totpSecret, setTotpSecret] = useState('');
    const [loading, setLoading] = useState(false);
    const [captchaText, setCaptchaText] = useState('');
    const [captchaInput, setCaptchaInput] = useState('');
    const canvasRef = useRef(null);

    const generateCaptcha = () => {
        const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
        let str = '';
        for(let i=0; i<5; i++) str += chars.charAt(Math.floor(Math.random() * chars.length));
        setCaptchaText(str);
        setCaptchaInput('');
    };

    useEffect(() => {
        if (step === 'login') {
            generateCaptcha();
        }
    }, [step]);

    useEffect(() => {
        if (step === 'login' && canvasRef.current && captchaText) {
            const canvas = canvasRef.current;
            const ctx = canvas.getContext('2d');
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.fillStyle = '#f3f4f6';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            
            // Add noise lines
            for (let i = 0; i < 5; i++) {
                ctx.beginPath();
                ctx.moveTo(Math.random() * canvas.width, Math.random() * canvas.height);
                ctx.lineTo(Math.random() * canvas.width, Math.random() * canvas.height);
                ctx.strokeStyle = '#9ca3af';
                ctx.stroke();
            }
            
            ctx.font = 'bold 24px monospace';
            ctx.fillStyle = '#0D9488';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            // Add some rotation
            ctx.save();
            ctx.translate(canvas.width/2, canvas.height/2);
            const angle = (Math.random() - 0.5) * 0.2;
            ctx.rotate(angle);
            ctx.fillText(captchaText, 0, 0);
            ctx.restore();
        }
    }, [captchaText, step]);


    const handleLogin = async (e) => {
        e.preventDefault();
        setLoading(true);

        if (captchaInput.toUpperCase() !== captchaText) {
            showNotification("Incorrect CAPTCHA. Please try again.", "error");
            generateCaptcha();
            setLoading(false);
            return;
        }


        try {
            const response = await fetch('/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, password, device_fingerprint: 'ADMIN_TRUSTED_DEVICE' })
            });

            const text = await response.text();
            let data;
            try {
                data = JSON.parse(text);
            } catch (e) {
                throw new Error(response.status >= 500 ? "Service temporarily unavailable. Please retry in a few seconds." : "Unexpected server response. Please try again.");
            }

            if (!response.ok) {
                throw new Error(data.detail || 'Authentication failed');
            }

            if (data.role === 'agent') {
                throw new Error('Unauthorized: This portal is restricted to administrative personnel. Agents must use the Agent Portal.');
            }

            if (data.requires_password_reset) {
                onRequireReset(email);
            } else if (data.requires_mfa_setup) {
                setStep('mfa_setup');
                setQrCode(data.qr_code_base64);
                setTotpSecret(data.totp_secret);
                showNotification("MFA Setup is mandatory for Admins.", "info");
            } else if (data.requires_mfa) {
                setStep('mfa');
                showNotification("Primary Credentials Authenticated. MFA Required.", "info");
            } else if (data.access_token) {
                onLoginSuccess(data.access_token, data.role);
                showNotification("Login Successful.", "success");
            }
        } catch (err) {
            showNotification(err.message, "error");
            generateCaptcha();
        } finally {
            setLoading(false);
        }
    };

    const handleMfaSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);

        if (captchaInput.toUpperCase() !== captchaText) {
            showNotification("Incorrect CAPTCHA. Please try again.", "error");
            generateCaptcha();
            setLoading(false);
            return;
        }


        try {
            const response = await fetch('/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    email, 
                    password, 
                    device_fingerprint: 'ADMIN_TRUSTED_DEVICE',
                    mfa_token: mfaCode
                })
            });

            const text = await response.text();
            let data;
            try {
                data = JSON.parse(text);
            } catch (e) {
                throw new Error(response.status >= 500 ? "Service temporarily unavailable. Please retry in a few seconds." : "Unexpected server response. Please try again.");
            }

            if (!response.ok) {
                throw new Error(data.detail || 'MFA Authentication failed');
            }

            if (data.access_token) {
                onLoginSuccess(data.access_token, data.role);
            } else {
                throw new Error(data.message || 'Invalid MFA Code.');
            }
        } catch (err) {
            showNotification(err.message, "error");
            generateCaptcha();
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

                {step === 'mfa_setup' ? (
                    <form onSubmit={handleMfaSubmit} className="space-y-5 bg-gray-50/50 dark:bg-gray-900 border border-gray-100 dark:border-gray-800 p-6 rounded-3xl shadow-2xl">
                        <div className="text-center mb-2">
                            <p className="text-xs font-bold text-brand uppercase tracking-tighter">Setup Mandatory 2FA</p>
                            <p className="text-[10px] text-gray-500 mt-1">Scan this QR code with Google Authenticator or Authy</p>
                        </div>
                        
                        <div className="flex justify-center bg-white p-4 rounded-xl border border-gray-200">
                            <img src={qrCode} alt="MFA QR Code" className="w-48 h-48" />
                        </div>
                        
                        <div className="text-center">
                            <p className="text-[9px] text-gray-400 uppercase tracking-widest">Or enter this secret manually:</p>
                            <p className="text-xs font-mono font-bold text-gray-700 dark:text-gray-300 mt-1">{totpSecret}</p>
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
                            {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <span>Verify & Enable</span>}
                        </button>
                    </form>
                ) : step === 'login' ? (
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


                        <div className="space-y-2">
                            <label className="text-xs font-bold text-gray-700 dark:text-gray-400 uppercase tracking-wider ml-1">Security Verification</label>
                            <div className="flex space-x-2">
                                <div className="w-32 h-14 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden shrink-0 bg-gray-100 flex items-center justify-center cursor-pointer" onClick={generateCaptcha} title="Click to refresh">
                                    <canvas ref={canvasRef} width="128" height="56" className="w-full h-full"></canvas>
                                </div>
                                <input
                                    type="text"
                                    value={captchaInput}
                                    onChange={(e) => setCaptchaInput(e.target.value)}
                                    className="w-full px-4 py-4 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-950 text-gray-900 dark:text-white focus:ring-2 focus:ring-brand outline-none transition-all placeholder:text-gray-400 uppercase font-mono"
                                    placeholder="Enter CAPTCHA"
                                    required
                                    maxLength="5"
                                />
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
                            onClick={() => {
                                setEmail('');
                                setPassword('');
                                setCaptchaInput('');
                                setMfaCode('');
                                setStep('login');
                            }}
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
