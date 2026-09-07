import React, { useEffect, useState } from 'react';
import { Html5QrcodeScanner } from 'html5-qrcode';
import { X, QrCode, ShieldCheck, Loader2 } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { saveDraft } from '../db/db';

const QRScannerModal = ({ isOpen, onClose }) => {
    const [scanning, setScanning] = useState(false);
    const [success, setSuccess] = useState(false);

    useEffect(() => {
        let scanner = null;

        if (isOpen && !success) {
            setScanning(true);
            scanner = new Html5QrcodeScanner(
                "qr-reader",
                { fps: 10, qrbox: { width: 250, height: 250 } },
        /* verbose= */ false
            );

            scanner.render((decodedText) => {
                handleScanSuccess(decodedText);
                scanner.clear();
            }, (error) => {
                // Ignored silent errors
            });
        }

        return () => {
            if (scanner) {
                scanner.clear().catch(e => console.error("Scanner clear cleanup failed", e));
            }
        };
    }, [isOpen, success]);

    const handleScanSuccess = async (data) => {
        try {
            const payload = JSON.parse(data);
            if (payload.p && payload.va) {
                // Re-construct the draft data
                const draftData = {
                    puCode: payload.p,
                    partyAVotes: payload.va,
                    partyBVotes: payload.vb,
                    createdAt: payload.c,
                    location: payload.l,
                    image: null, // Hard limitation of QR: Image must be synced separately via SMS fallback or later
                    isProxy: true
                };

                await saveDraft(draftData);
                setSuccess(true);
                setTimeout(() => {
                    setSuccess(false);
                    onClose();
                }, 2000);
            }
        } catch (err) {
            console.error("Malformed QR Payload", err);
        } finally {
            setScanning(false);
        }
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
            <div className="absolute inset-0 bg-black/80 backdrop-blur-md" onClick={onClose}></div>

            <motion.div
                initial={{ scale: 0.9, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                className="relative bg-white dark:bg-gray-950 w-full max-w-sm rounded-3xl overflow-hidden shadow-2xl"
            >
                <div className="p-6 border-b border-gray-100 dark:border-gray-900 flex justify-between items-center">
                    <h3 className="font-black text-gray-900 dark:text-white uppercase tracking-tighter flex items-center space-x-2">
                        <QrCode className="w-5 h-5 text-brand" />
                        <span>Proxy Sync Scanner</span>
                    </h3>
                    <button onClick={onClose} className="p-2 text-gray-400">
                        <X className="w-5 h-5" />
                    </button>
                </div>

                <div className="p-8">
                    {success ? (
                        <div className="flex flex-col items-center justify-center space-y-4 py-10 animate-in zoom-in duration-300">
                            <ShieldCheck className="w-16 h-16 text-brand" />
                            <p className="font-bold text-gray-900 dark:text-white">Proxy Data Imported!</p>
                            <p className="text-xs text-gray-500 text-center uppercase tracking-widest font-black">Ready for background sync</p>
                        </div>
                    ) : (
                        <div className="space-y-6">
                            <div id="qr-reader" className="overflow-hidden rounded-2xl border-4 border-brand/20"></div>
                            <p className="text-[10px] text-gray-400 font-bold text-center uppercase tracking-widest px-4">
                                Align the Proxy QR code within the frame to pick up the offline agent's result.
                            </p>
                        </div>
                    )}
                </div>
            </motion.div>
        </div>
    );
};

export default QRScannerModal;


