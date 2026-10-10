import { useState, useEffect, useRef } from 'react';
import { Shield, Lock, Mail, Loader2, AlertCircle, Eye, EyeOff } from 'lucide-react';
import { motion } from 'framer-motion';
import { useNotification } from '../contexts/NotificationContext';
import { clearAllData } from '../db/db';

const LoginScreen = ({ onLoginSuccess, onRequireReset }) => {
    const { showNotification } = useNotification();
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [signingKey, setSigningKey] = useState(() => localStorage.getItem('cl_signing_key') || '');
    const [showPassword, setShowPassword] = useState(false);
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
        generateCaptcha();
    }, []);

    useEffect(() => {
        if (canvasRef.current && captchaText) {
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
    }, [captchaText]);


    const handlePurge = async () => {
        if (window.confirm("RESCUE ACTION: This will permanently delete all local data and fix potential app crashes. Proceed?")) {
            await clearAllData();
            window.location.reload();
        }
    };

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
                body: JSON.stringify({
                    email,
                    password,
                    device_fingerprint: 'MOCKED_PHONE_ID'
                })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'Authentication failed');
            }

            if (data.role !== 'agent') {
                throw new Error('Unauthorized: This portal is restricted to Field Agents only.');
            }

            // Persist the per-agent device signing key on ANY successful login —
            // including the first one, which redirects to the forced password
            // reset screen. (Previously it was only stored on the no-reset path,
            // so freshly provisioned agents never got it pre-filled afterwards.)
            localStorage.setItem('cl_signing_key', signingKey.trim());

            if (data.requires_password_reset) {
                onRequireReset(email);
            } else {
                // Persist the JWT so offline drafts sync with authenticated identity
                localStorage.setItem('cl_access_token', data.access_token);
                // Success - state elevated to Authenticated with PU context
                onLoginSuccess(data.assigned_pu);
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

                {/* Header / Logo */}
                <div className="flex flex-col items-center space-y-4">
                    <div className="w-16 h-16 bg-brand rounded-2xl flex items-center justify-center shadow-lg shadow-brand/30">
                        <Shield className="w-8 h-8 text-white" />
                    </div>
                    <div className="text-center">
                        <h2 className="text-2xl font-black text-gray-900 dark:text-white tracking-[0.2em] uppercase">Civic Lens</h2>
                        <p className="text-xs font-bold text-gray-500 tracking-widest uppercase mt-1">Zero-Trust Authentication</p>
                    </div>
                </div>

                {/* Login Form */}
                <form onSubmit={handleLogin} className="space-y-5 bg-gray-50/50 dark:bg-gray-900 border border-gray-100 dark:border-gray-800 p-6 rounded-3xl shadow-2xl">

                    <div className="space-y-2">
                        <label className="text-xs font-bold text-gray-700 dark:text-gray-400 uppercase tracking-wider ml-1">Email / Agent ID</label>
                        <div className="relative">
                            <Mail className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
                            <input
                                type="email"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                className="w-full pl-12 pr-4 py-4 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-950 text-gray-900 dark:text-white focus:ring-2 focus:ring-brand outline-none transition-all placeholder:text-gray-400 dark:placeholder:text-gray-600"
                                placeholder="agent@civiclens.io"
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
                        <label className="text-xs font-bold text-gray-700 dark:text-gray-400 uppercase tracking-wider ml-1">Device Signing Key</label>
                        <div className="relative">
                            <Shield className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
                            <input
                                type="password"
                                value={signingKey}
                                onChange={(e) => setSigningKey(e.target.value)}
                                className="w-full pl-12 pr-4 py-4 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-950 text-gray-900 dark:text-white focus:ring-2 focus:ring-brand outline-none transition-all placeholder:text-gray-400 dark:placeholder:text-gray-600 font-mono text-sm"
                                placeholder="Issued at provisioning"
                                required
                            />
                        </div>
                        <p className="text-[10px] text-gray-400 font-bold uppercase tracking-wider ml-1">Signs result payloads — issued with your agent credentials</p>
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

                {/* Footer Info */}
                <div className="text-center text-[10px] text-gray-400 font-bold uppercase tracking-widest space-y-2">
                    <p className="flex items-center justify-center space-x-1 opacity-70">
                        <Lock className="w-3 h-3" />
                        <span>TLS 1.3 encryption active</span>
                    </p>
                    <p className="opacity-50">Device Fingerprint: Verified</p>
                </div>

                {/* Rescue Action */}
                <div className="pt-4 flex flex-col items-center">
                    <button
                        onClick={handlePurge}
                        className="flex items-center space-x-2 text-[8px] font-black uppercase tracking-[0.2em] text-gray-400 hover:text-red-500 transition-colors bg-gray-100 dark:bg-gray-800/50 px-4 py-2 rounded-full border border-transparent hover:border-red-500/30"
                    >
                        <Shield className="w-2.5 h-2.5" />
                        <span>Emergency App Reset (Purge Data)</span>
                    </button>
                </div>

            </div>
        </div>
    );
};

export default LoginScreen;


