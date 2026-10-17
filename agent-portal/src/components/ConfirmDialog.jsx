import React from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { AlertTriangle, CheckCircle } from 'lucide-react';
import { useNotification } from '../contexts/NotificationContext';

// Styled replacement for window.confirm(): same visual language as the
// admin portal's SecurityDialog. The promise resolves `true` on confirm
// and `null` on cancel.
const ConfirmDialog = () => {
    const { dialog, closeDialog } = useNotification();

    return createPortal(
        <AnimatePresence>
            {dialog && (
                <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 overflow-hidden">
                    {/* Backdrop */}
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        onClick={() => closeDialog(null)}
                        className="absolute inset-0 bg-gray-950/90 backdrop-blur-md"
                    />

                    {/* Dialog Card */}
                    <motion.div
                        initial={{ scale: 0.9, opacity: 0, y: 20 }}
                        animate={{ scale: 1, opacity: 1, y: 0 }}
                        exit={{ scale: 0.9, opacity: 0, y: 20 }}
                        className="relative bg-white dark:bg-gray-900 w-full max-w-sm rounded-[2.5rem] shadow-2xl overflow-hidden border border-white/10"
                    >
                        <div className="bg-brand h-2 w-full" />

                        <div className="p-8 space-y-6">
                            <div className="flex flex-col items-center text-center space-y-3">
                                <div className={`p-3 rounded-2xl ${dialog.danger ? 'bg-red-500/10' : 'bg-brand/10'}`}>
                                    <AlertTriangle className={`w-8 h-8 ${dialog.danger ? 'text-red-500' : 'text-brand'}`} />
                                </div>
                                <h3 className="text-xl font-black text-gray-900 dark:text-white uppercase tracking-tight leading-tight">
                                    {dialog.title || 'Please Confirm'}
                                </h3>
                                <p className="text-[10px] text-gray-500 font-bold leading-relaxed px-4 uppercase tracking-wider whitespace-pre-line">
                                    {dialog.message}
                                </p>
                            </div>

                            <div className="flex space-x-3 pt-2">
                                <button
                                    type="button"
                                    onClick={() => closeDialog(null)}
                                    className="flex-1 py-4 text-[10px] font-black uppercase tracking-widest text-gray-400 hover:text-gray-600 transition-colors"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="button"
                                    onClick={() => closeDialog(true)}
                                    className={`flex-1 py-4 text-white rounded-2xl text-[10px] font-black uppercase tracking-widest shadow-xl active:scale-95 transition-all flex items-center justify-center space-x-2 ${dialog.danger ? 'bg-red-500 shadow-red-500/20' : 'bg-brand shadow-brand/20'}`}
                                >
                                    <CheckCircle className="w-3.5 h-3.5" />
                                    <span>Confirm</span>
                                </button>
                            </div>
                        </div>
                    </motion.div>
                </div>
            )}
        </AnimatePresence>,
        document.body
    );
};

export default ConfirmDialog;
