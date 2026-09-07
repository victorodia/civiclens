import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Search, MapPin, Check, X, ShieldAlert, Cpu, RefreshCw, Maximize2 } from 'lucide-react';
import { useNotification } from '../contexts/NotificationContext';

const VerificationScreen = () => {
    const { showNotification } = useNotification();
    const [items, setItems] = useState([]);
    const [partyConfig, setPartyConfig] = useState({
        party_a_name: 'Party A',
        party_b_name: 'Party B',
        party_c_name: 'Party C'
    });
    const [activeIndex, setActiveIndex] = useState(0);
    const [isLoading, setIsLoading] = useState(true);
    const [fullImageOpen, setFullImageOpen] = useState(false);

    useEffect(() => {
        const fetchData = async () => {
            try {
                // Fetch party config
                const configRes = await fetch('http://127.0.0.1:8001/admin/election-config');
                if (configRes.ok) setPartyConfig(await configRes.json());

                // Fetch pending results (mocking the real endpoint for now if not ready, but backend list showed it exists)
                const res = await fetch('http://127.0.0.1:8001/admin/pending-verifications');
                if (res.ok) {
                    const data = await res.json();
                    setItems(data);
                }
            } catch (e) {
                showNotification("Verification Queue Sync Failed. Network integrity check required.", "error");
            } finally {
                setIsLoading(false);
            }
        };
        fetchData();
    }, []);

    const current = items[activeIndex];

    if (isLoading) return (
        <div className="flex items-center justify-center p-20">
            <RefreshCw className="w-8 h-8 animate-spin text-brand" />
        </div>
    );

    if (!current) return (
        <div className="bg-white dark:bg-gray-900 p-12 rounded-3xl border border-dashed border-gray-200 dark:border-gray-800 text-center animate-in fade-in zoom-in">
            <Check className="w-12 h-12 text-green-500 mx-auto mb-4 opacity-20" />
            <h3 className="font-black text-gray-400 uppercase tracking-widest text-sm">Integrity Clear</h3>
            <p className="text-[10px] text-gray-500 uppercase mt-2">No results are currently flagged for human review</p>
        </div>
    );

    const handleVerify = async (action) => {
        try {
            const res = await fetch(`http://127.0.0.1:8001/admin/verify/${current.id}?action=${action}`, {
                method: 'POST'
            });
            if (res.ok) {
                // Remove from local list and move to next or show empty
                const newItems = items.filter(item => item.id !== current.id);
                setItems(newItems);
                if (activeIndex >= newItems.length) {
                    setActiveIndex(Math.max(0, newItems.length - 1));
                }
                showNotification(`Result ${action === 'verify' ? 'Verified' : 'Flagged'} Successfully.`, "success");
            }
        } catch (e) {
            showNotification(`Action "${action}" failed. Database sync error.`, "error");
        }
    };

    return (
        <div className="space-y-6 animate-in slide-in-from-right duration-500">
            <AnimatePresence>
                {fullImageOpen && (
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        onClick={() => setFullImageOpen(false)}
                        className="fixed inset-0 bg-black/95 z-[200] flex items-center justify-center p-4 cursor-zoom-out"
                    >
                        <motion.img
                            initial={{ scale: 0.9, opacity: 0 }}
                            animate={{ scale: 1, opacity: 1 }}
                            exit={{ scale: 0.9, opacity: 0 }}
                            src={current.image_url}
                            className="max-w-full max-h-full object-contain shadow-2xl rounded-lg border border-white/10"
                        />
                        <button
                            onClick={() => setFullImageOpen(false)}
                            className="absolute top-6 right-6 text-white bg-white/10 p-2 rounded-full hover:bg-white/20 transition-colors"
                        >
                            <X className="w-6 h-6" />
                        </button>
                    </motion.div>
                )}
            </AnimatePresence>

            <div className="flex items-center justify-between">
                <h3 className="font-bold flex items-center space-x-2 text-gray-900 dark:text-white">
                    <ShieldAlert className="w-5 h-5 text-amber-500" />
                    <span>Verification Queue</span>
                </h3>
                <span className="text-[10px] font-black bg-gray-100 dark:bg-gray-800 px-3 py-1 rounded-full">{activeIndex + 1} / {items.length}</span>
            </div>

            {/* Split Screen Logic */}
            <div className="space-y-4">
                {/* Paper Evidence (AI Highlighted) */}
                <div
                    onClick={() => setFullImageOpen(true)}
                    className="relative rounded-2xl overflow-hidden border-2 border-brand/20 shadow-inner group cursor-zoom-in"
                >
                    <img src={current.image_url} alt="Evidence" className="w-full h-48 object-cover grayscale brightness-110 group-hover:scale-105 transition-transform duration-700" />
                    <div className="absolute inset-0 bg-brand/5 pointer-events-none group-hover:bg-transparent transition-colors"></div>

                    <div className="absolute top-4 left-4 bg-brand text-white text-[8px] font-black px-2 py-1 rounded flex items-center space-x-1 shadow-lg">
                        <Cpu className="w-2 h-2" />
                        <span>AI OCR ACTIVE ({Math.round(current.ai_confidence)}%)</span>
                    </div>

                    <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                        <div className="bg-black/50 backdrop-blur-sm text-white px-4 py-2 rounded-full flex items-center space-x-2 border border-white/20">
                            <Maximize2 className="w-4 h-4" />
                            <span className="text-[10px] font-black uppercase tracking-widest">Enlarge Evidence</span>
                        </div>
                    </div>

                    {/* AI Confidence Indicator */}
                    <motion.div
                        initial={{ opacity: 0, scale: 0.8 }}
                        animate={{ opacity: 1, scale: 1 }}
                        className="absolute bottom-4 right-4 bg-brand/90 text-white text-[8px] font-black px-2 py-1 rounded-full flex items-center space-x-1 shadow-lg"
                    >
                        <span>Confidence: {current.ai_confidence}%</span>
                    </motion.div>
                </div>

                {/* Data Comparison Card */}
                <div className="bg-white dark:bg-gray-950 p-6 rounded-2xl shadow-xl border border-gray-100 dark:border-gray-800">
                    <div className="grid grid-cols-3 gap-3 mb-6">
                        {/* Party A */}
                        <div className="p-3 bg-gray-50 dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800">
                            <p className="text-[9px] text-gray-400 font-bold uppercase">{partyConfig.party_a_name}</p>
                            <div className="flex items-center justify-between mt-1">
                                <span className="text-sm font-black text-slate-800 dark:text-gray-100">{current.party_a}</span>
                                <span className="text-[8px] font-bold text-brand bg-brand/5 px-1 rounded">AI: {current.ai_party_a}</span>
                            </div>
                        </div>
                        {/* Party B */}
                        <div className="p-3 bg-gray-50 dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800">
                            <p className="text-[9px] text-gray-400 font-bold uppercase">{partyConfig.party_b_name}</p>
                            <div className="flex items-center justify-between mt-1">
                                <span className="text-sm font-black text-slate-800 dark:text-gray-100">{current.party_b}</span>
                                <span className="text-[8px] font-bold text-brand bg-brand/5 px-1 rounded">AI: {current.ai_party_b}</span>
                            </div>
                        </div>
                        {/* Party C */}
                        <div className="p-3 bg-gray-50 dark:bg-gray-900 rounded-xl border border-gray-100 dark:border-gray-800">
                            <p className="text-[9px] text-gray-400 font-bold uppercase">{partyConfig.party_c_name}</p>
                            <div className="flex items-center justify-between mt-1">
                                <span className="text-sm font-black text-slate-800 dark:text-gray-100">{current.party_c}</span>
                                <span className="text-[8px] font-bold text-brand bg-brand/5 px-1 rounded">AI: {current.ai_party_c}</span>
                            </div>
                        </div>
                    </div>

                    <div className="space-y-2 mb-8">
                        <div className="flex justify-between items-center">
                            <p className="text-xs font-bold text-gray-500 uppercase tracking-widest">Metadata Context</p>
                            <span className="text-[8px] font-black text-gray-400 uppercase tracking-widest">Captured: {new Date(current.captured_at).toLocaleString()}</span>
                        </div>
                        <div className="flex items-center space-x-2 text-[11px] text-gray-600 dark:text-gray-400 bg-gray-50 dark:bg-gray-900 p-2 rounded-lg">
                            <MapPin className="w-3 h-3 text-brand" />
                            <span>PU Code: {current.pu_code} (Verified Geofence)</span>
                        </div>
                        <div className="flex items-center space-x-2 text-[11px] text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 p-2 rounded-lg border border-amber-100 dark:border-amber-900/30">
                            <ShieldAlert className="w-3 h-3" />
                            <span>AI Alert: Discrepancy detected in Party vote counts. Human oversight required.</span>
                        </div>
                    </div>

                    {/* Action Buttons */}
                    <div className="flex space-x-3">
                        <button
                            onClick={() => handleVerify('REJECT')}
                            className="flex-1 bg-slate-100 dark:bg-gray-800 text-slate-600 dark:text-gray-300 font-bold py-3 rounded-xl hover:bg-slate-200 transition-colors flex items-center justify-center space-x-2"
                        >
                            <X className="w-5 h-5" />
                            <span>Reject</span>
                        </button>
                        <button
                            onClick={() => handleVerify('APPROVE')}
                            className="flex-2 grow-2 bg-brand text-white font-bold py-3 px-6 rounded-xl shadow-lg shadow-brand/20 hover:scale-[1.02] active:scale-95 transition-all flex items-center justify-center space-x-2"
                        >
                            <Check className="w-5 h-5" />
                            <span>Confirm Integrity</span>
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default VerificationScreen;


