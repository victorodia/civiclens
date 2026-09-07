import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, CheckCircle, AlertCircle, Info, AlertTriangle } from 'lucide-react';
import { useNotification } from '../contexts/NotificationContext';

const NotificationBanner = () => {
    const { notification, dismissNotification } = useNotification();

    if (!notification) return null;

    const styles = {
        success: {
            bg: 'bg-green-500',
            icon: <CheckCircle className="w-5 h-5 text-white" />
        },
        error: {
            bg: 'bg-red-500',
            icon: <AlertCircle className="w-5 h-5 text-white" />
        },
        warning: {
            bg: 'bg-amber-500',
            icon: <AlertTriangle className="w-5 h-5 text-white" />
        },
        info: {
            bg: 'bg-brand',
            icon: <Info className="w-5 h-5 text-white" />
        }
    };

    const currentStyle = styles[notification.type] || styles.info;

    return (
        <AnimatePresence>
            {notification && (
                <motion.div
                    initial={{ opacity: 0, y: -100 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -100 }}
                    className="fixed top-0 left-0 right-0 z-[100] flex justify-center p-4 pointer-events-none"
                >
                    <div className={`${currentStyle.bg} pointer-events-auto shadow-2xl rounded-2xl flex items-center p-4 min-w-[300px] max-w-md border border-white/10 backdrop-blur-md bg-opacity-90`}>
                        <div className="mr-3">
                            {currentStyle.icon}
                        </div>
                        <div className="flex-1 mr-4">
                            <p className="text-white text-xs font-black uppercase tracking-tight leading-tight">
                                {notification.message}
                            </p>
                        </div>
                        <button
                            onClick={dismissNotification}
                            className="text-white/50 hover:text-white transition-colors"
                        >
                            <X className="w-4 h-4" />
                        </button>
                    </div>
                </motion.div>
            )}
        </AnimatePresence>
    );
};

export default NotificationBanner;
