import React from 'react';
import { QRCodeSVG } from 'qrcode.react';
import { X, Share2, Info, CheckCircle } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

const QRShareModal = ({ isOpen, onClose, data }) => {
    if (!data) return null;

    // We serialize the core result data for the QR. 
    // In a real app, we would compress/encrypt this payload.
    const qrPayload = JSON.stringify({
        p: data.puCode,
        va: data.partyAVotes,
        vb: data.partyBVotes,
        c: data.createdAt,
        l: data.location
    });

    return (
        <AnimatePresence>
            {isOpen && (
                <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        onClick={onClose}
                        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
                    ></motion.div>

                    <motion.div
                        initial={{ scale: 0.9, opacity: 0, y: 20 }}
                        animate={{ scale: 1, opacity: 1, y: 0 }}
                        exit={{ scale: 0.9, opacity: 0, y: 20 }}
                        className="relative bg-white dark:bg-gray-900 w-full max-w-xs rounded-3xl p-8 shadow-2xl border border-gray-100 dark:border-gray-800 flex flex-col items-center"
                    >
                        <button
                            onClick={onClose}
                            className="absolute top-4 right-4 p-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
                        >
                            <X className="w-5 h-5" />
                        </button>

                        <div className="mb-6 text-center">
                            <h3 className="font-black text-gray-900 dark:text-white uppercase tracking-tight text-lg">Proxy Sync QR</h3>
                            <p className="text-[10px] text-gray-500 font-bold uppercase tracking-wider">Show this to an online agent</p>
                        </div>

                        <div className="bg-white p-4 rounded-2xl shadow-inner mb-6">
                            <QRCodeSVG
                                value={qrPayload}
                                size={200}
                                level="M"
                                includeMargin={false}
                            />
                        </div>

                        <div className="bg-brand/5 dark:bg-brand/10 p-4 rounded-xl border border-brand/20 flex items-start space-x-3 mb-4">
                            <Info className="w-4 h-4 text-brand shrink-0 mt-0.5" />
                            <p className="text-[10px] text-gray-600 dark:text-gray-400 leading-relaxed">
                                This QR contains the encrypted result of **PU: {data.puCode}**. Another agent can scan this and sync it to the Situation Room on your behalf.
                            </p>
                        </div>

                        <p className="text-[10px] font-black text-brand uppercase tracking-widest flex items-center space-x-1">
                            <CheckCircle className="w-3 h-3" />
                            <span>Offline Payload Ready</span>
                        </p>
                    </motion.div>
                </div>
            )}
        </AnimatePresence>
    );
};

export default QRShareModal;


