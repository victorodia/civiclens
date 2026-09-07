import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { ShieldAlert, X, CheckCircle, Lock, AlertTriangle, Eye, EyeOff } from 'lucide-react';
import { useNotification } from '../contexts/NotificationContext';

const SecurityDialog = () => {
    const { dialog, closeDialog } = useNotification();
    const [inputValue, setInputValue] = useState('');
    const [showPassword, setShowPassword] = useState(false);

    useEffect(() => {
        if (dialog) {
            setInputValue('');
            setShowPassword(false);
        }
    }, [dialog]);

    const handleConfirm = (e) => {
        e.preventDefault();
        closeDialog(inputValue);
    };

    const handleCancel = () => {
        closeDialog(null);
    };

    return createPortal(
        <AnimatePresence>
            {dialog && (
                <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 overflow-hidden">
                    {/* Backdrop */}
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        onClick={handleCancel}
                        className="absolute inset-0 bg-gray-950/90 backdrop-blur-md"
                    />

                    {/* Dialog Card */}
                    <motion.div
                        initial={{ scale: 0.9, opacity: 0, y: 20 }}
                        animate={{ scale: 1, opacity: 1, y: 0 }}
                        exit={{ scale: 0.9, opacity: 0, y: 20 }}
                        className="relative bg-white dark:bg-gray-900 w-full max-w-sm rounded-[2.5rem] shadow-2xl overflow-hidden border border-white/10"
                    >
                        {/* Header Branding */}
                        <div className="bg-brand h-2 w-full" />

                        <div className="p-8 space-y-6">
                            <div className="flex flex-col items-center text-center space-y-3">
                                <div className="bg-brand/10 p-3 rounded-2xl">
                                    <ShieldAlert className="w-8 h-8 text-brand" />
                                </div>
                                <h3 className="text-xl font-black text-gray-900 dark:text-white uppercase tracking-tight leading-tight">
                                    {dialog.title || 'Security Verification'}
                                </h3>
                                <p className="text-[10px] text-gray-500 font-bold leading-relaxed px-4 uppercase tracking-wider">
                                    {dialog.message}
                                </p>
                            </div>

                            <form onSubmit={handleConfirm} className="space-y-4">
                                <div className="relative group">
                                    <div className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400 group-focus-within:text-brand transition-colors">
                                        <Lock className="w-4 h-4" />
                                    </div>
                                    <input
                                        autoFocus
                                        type={showPassword ? "text" : "password"}
                                        placeholder="Enter Security Key"
                                        value={inputValue}
                                        onChange={(e) => setInputValue(e.target.value)}
                                        className="w-full pl-11 pr-12 py-4 bg-gray-50 dark:bg-gray-950 border border-gray-100 dark:border-gray-800 rounded-2xl text-sm font-bold outline-none focus:ring-4 focus:ring-brand/10 focus:border-brand transition-all"
                                    />
                                    <button
                                        type="button"
                                        onClick={() => setShowPassword(!showPassword)}
                                        className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-400 hover:text-brand transition-colors"
                                    >
                                        {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                                    </button>
                                </div>

                                <div className="flex space-x-3 pt-2">
                                    <button
                                        type="button"
                                        onClick={handleCancel}
                                        className="flex-1 py-4 text-[10px] font-black uppercase tracking-widest text-gray-400 hover:text-gray-600 transition-colors"
                                    >
                                        Cancel
                                    </button>
                                    <button
                                        type="submit"
                                        className="flex-1 py-4 bg-brand text-white rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-xl shadow-brand/20 active:scale-95 transition-all flex items-center justify-center space-x-2"
                                    >
                                        <CheckCircle className="w-3.5 h-3.5" />
                                        <span>Confirm Access</span>
                                    </button>
                                </div>
                            </form>
                        </div>
                    </motion.div>
                </div>
            )}
        </AnimatePresence>,
        document.body
    );
};

export default SecurityDialog;
