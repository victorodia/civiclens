import React, { useState, useRef, useEffect } from 'react';
import { ShieldAlert, KeyRound, Loader2, CheckCircle2, Eye, EyeOff, Camera, UserSquare2, RefreshCw } from 'lucide-react';
import { useNotification } from '../contexts/NotificationContext';

const PasswordResetScreen = ({ email, onComplete }) => {
    const { showNotification } = useNotification();
    const [step, setStep] = useState(1);
    
    // Step 1 State
    const [newPassword, setNewPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [duressPassword, setDuressPassword] = useState('');
    const [showMainPassword, setShowMainPassword] = useState(false);
    const [showDuressPassword, setShowDuressPassword] = useState(false);
    
    // Step 2 State
    const [stream, setStream] = useState(null);
    const [imageStr, setImageStr] = useState(null);
    
    const videoRef = useRef(null);
    const canvasRef = useRef(null);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (step === 2) {
            startCamera();
        }
        return () => {
            stopCamera();
        };
    }, [step]);

    const startCamera = async () => {
        try {
            const mediaStream = await navigator.mediaDevices.getUserMedia({ 
                video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 640 } } 
            });
            setStream(mediaStream);
            if (videoRef.current) {
                videoRef.current.srcObject = mediaStream;
                videoRef.current.onloadedmetadata = () => {
                    videoRef.current.play().catch(e => console.error("Error playing video:", e));
                };
            }
        } catch (err) {
            console.error("Camera access denied:", err);
            showNotification("Camera access is required for identity verification.", "error");
        }
    };

    const stopCamera = () => {
        if (stream) {
            stream.getTracks().forEach(track => track.stop());
            setStream(null);
        }
    };

    const handleCapture = () => {
        if (videoRef.current && canvasRef.current) {
            const context = canvasRef.current.getContext('2d');
            canvasRef.current.width = videoRef.current.videoWidth;
            canvasRef.current.height = videoRef.current.videoHeight;
            context.drawImage(videoRef.current, 0, 0, canvasRef.current.width, canvasRef.current.height);
            const dataUrl = canvasRef.current.toDataURL('image/jpeg', 0.8);
            setImageStr(dataUrl);
            stopCamera();
        }
    };

    const handleRetake = () => {
        setImageStr(null);
        startCamera();
    };

    const handlePasswordsSubmit = (e) => {
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
        setStep(2);
    };

    const handleFinalSubmit = async () => {
        if (!imageStr) {
            showNotification("Please capture your profile photo.", "warning");
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
                    duress_password: duressPassword,
                    profile_picture_base64: imageStr
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
            onComplete();
        } catch (err) {
            showNotification(err.message, "error");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-brand-dark z-[100] flex flex-col justify-center items-center p-6 sm:p-12 overflow-y-auto w-full h-full">
            <div className="w-full max-w-sm space-y-6 animate-in slide-in-from-right duration-500 pb-10">

                <div className="text-center space-y-3">
                    <div className="mx-auto w-16 h-16 bg-white/10 rounded-2xl flex items-center justify-center">
                        {step === 1 ? <ShieldAlert className="w-8 h-8 text-amber-400" /> : <UserSquare2 className="w-8 h-8 text-amber-400" />}
                    </div>
                    <h2 className="text-xl font-black text-white tracking-widest uppercase">
                        {step === 1 ? "Security Initialization" : "Identity Verification"}
                    </h2>
                    <p className="text-xs text-white/70 leading-relaxed font-bold">
                        {step === 1 
                            ? "For security, your temporary admin-provided password has expired. You must set your permanent credentials now."
                            : "A clear profile photo is required for your official agency ID badge."}
                    </p>
                </div>

                {step === 1 ? (
                    <form onSubmit={handlePasswordsSubmit} className="space-y-4 bg-white/5 p-6 rounded-3xl border border-white/10 backdrop-blur-md shadow-2xl">
                        
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

                        <button type="submit" className="w-full mt-4 bg-white text-brand-dark font-black uppercase tracking-widest py-4 rounded-xl shadow-xl active:scale-95 transition-transform flex items-center justify-center space-x-2">
                            <span>Continue to Verification</span>
                        </button>
                    </form>
                ) : (
                    <div className="space-y-4 bg-white/5 p-6 rounded-3xl border border-white/10 backdrop-blur-md shadow-2xl flex flex-col items-center">
                        
                        <div className="relative w-full aspect-square rounded-2xl overflow-hidden bg-black/50 border-2 border-white/20 flex flex-col items-center justify-center">
                            {imageStr ? (
                                <img src={imageStr} alt="Profile" className="w-full h-full object-cover" />
                            ) : (
                                <>
                                    <video ref={videoRef} autoPlay playsInline muted className="w-full h-full object-cover transform -scale-x-100" />
                                    <div className="absolute inset-0 border-[60px] sm:border-[80px] border-black/50 rounded-[40%] pointer-events-none transition-all"></div>
                                </>
                            )}
                            <canvas ref={canvasRef} className="hidden" />
                        </div>

                        {!imageStr ? (
                            <button onClick={handleCapture} className="w-full bg-brand text-white font-black uppercase tracking-widest py-4 rounded-xl shadow-xl shadow-brand/20 active:scale-95 transition-transform flex items-center justify-center space-x-2">
                                <Camera className="w-5 h-5" />
                                <span>Capture Photo</span>
                            </button>
                        ) : (
                            <div className="w-full space-y-3">
                                <button onClick={handleRetake} className="w-full bg-white/10 hover:bg-white/20 text-white font-black uppercase tracking-widest py-3 rounded-xl transition-colors flex items-center justify-center space-x-2">
                                    <RefreshCw className="w-4 h-4" />
                                    <span>Retake</span>
                                </button>
                                <button disabled={loading} onClick={handleFinalSubmit} className="w-full bg-white text-brand-dark font-black uppercase tracking-widest py-4 rounded-xl shadow-xl active:scale-95 transition-transform flex items-center justify-center space-x-2">
                                    {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <><span>Finalize Security</span> <CheckCircle2 className="w-4 h-4 ml-1" /></>}
                                </button>
                            </div>
                        )}

                    </div>
                )}

            </div>
        </div>
    );
};

export default PasswordResetScreen;
