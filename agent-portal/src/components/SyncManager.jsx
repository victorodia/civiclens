import React, { useState, useEffect } from 'react';
import { RefreshCw, Check, CloudUpload, AlertTriangle, QrCode, X } from 'lucide-react';
import { getPendingDrafts, deleteDraft } from '../db/db';
import QRScannerModal from './QRScannerModal';

const SyncManager = ({ assignedPu }) => {
    const [pendingDrafts, setPendingDrafts] = useState([]);
    const [syncing, setSyncing] = useState(false);
    const [isOnline, setIsOnline] = useState(navigator.onLine);
    const [isScanOpen, setIsScanOpen] = useState(false);
    const [error, setError] = useState(null);
    const [isDismissed, setIsDismissed] = useState(false);

    useEffect(() => {
        const updateOnlineStatus = () => setIsOnline(navigator.onLine);
        window.addEventListener('online', updateOnlineStatus);
        window.addEventListener('offline', updateOnlineStatus);

        // Initial check and periodic polling for pending drafts
        loadDrafts();
        const interval = setInterval(loadDrafts, 5000);

        return () => {
            window.removeEventListener('online', updateOnlineStatus);
            window.removeEventListener('offline', updateOnlineStatus);
            clearInterval(interval);
        };
    }, []);

    // Reset dismissal if draft count INCREASES
    useEffect(() => {
        if (pendingDrafts.length > 0) {
            // We only reset if it was dismissed and we have a new count
            // This is a simple heuristic: if count > 0 and it was dismissed, 
            // we could either keep it dismissed or show it. 
            // Better UX: Keep it dismissed unless a NEW draft is added.
        } else {
            setIsDismissed(false); // Reset when empty so it shows next time one appears
        }
    }, [pendingDrafts.length]);

    const loadDrafts = async () => {
        const drafts = await getPendingDrafts();
        setPendingDrafts(drafts);
    };

    const handleSync = async () => {
        if (!isOnline || pendingDrafts.length === 0) return;

        setSyncing(true);
        setError(null);

        for (const draft of pendingDrafts) {
            try {
                console.log(`Syncing PU: ${draft.puCode}`);
                let uploadedImageUrl = null;
                let uploadedVideoUrl = null;
                let aiAnalysis = null;

                // 1. Upload Image (if exists)
                if (draft.image) {
                    console.log("Uploading image...");
                    const imageFormData = new FormData();
                    imageFormData.append('file', draft.image);
                    const uploadResponse = await fetch('http://127.0.0.1:8001/upload/form-ec8a', {
                        method: 'POST',
                        body: imageFormData
                    });
                    if (!uploadResponse.ok) {
                        const errorText = await uploadResponse.text();
                        console.error("Image upload failed:", errorText);
                        throw new Error(`Image upload failed: ${errorText}`);
                    }
                    const uploadData = await uploadResponse.json();
                    uploadedImageUrl = uploadData.secure_url;
                    aiAnalysis = uploadData.ai_analysis;
                    console.log("Image uploaded with AI data:", uploadedImageUrl, aiAnalysis);
                }

                // 2. Upload Video (if exists)
                if (draft.video) {
                    console.log("Uploading video...");
                    const videoFormData = new FormData();
                    videoFormData.append('file', draft.video);
                    const uploadResponse = await fetch('http://127.0.0.1:8001/upload/form-ec8a', {
                        method: 'POST',
                        body: videoFormData
                    });
                    if (!uploadResponse.ok) {
                        const errorText = await uploadResponse.text();
                        console.error("Video upload failed:", errorText);
                        throw new Error(`Video upload failed: ${errorText}`);
                    }
                    const uploadData = await uploadResponse.json();
                    uploadedVideoUrl = uploadData.secure_url;
                    console.log("Video uploaded:", uploadedVideoUrl);
                }

                // 3. Upload Result Data
                console.log("Submitting result data...");
                const resultPayload = {
                    pu_code: draft.puCode,
                    agent_email: draft.agentEmail || assignedPu?.email,
                    party_a_votes: parseInt(draft.partyAVotes) || 0,
                    party_b_votes: parseInt(draft.partyBVotes) || 0,
                    party_c_votes: parseInt(draft.partyCVotes) || 0,
                    total_valid: parseInt(draft.totalValid) || 0,
                    image_url: uploadedImageUrl,
                    video_url: uploadedVideoUrl,
                    ai_party_a_votes: aiAnalysis?.party_a,
                    ai_party_b_votes: aiAnalysis?.party_b,
                    ai_party_c_votes: aiAnalysis?.party_c,
                    ai_confidence: aiAnalysis?.avg_confidence,
                    captured_at: draft.createdAt,
                    latitude: draft.location?.lat,
                    longitude: draft.location?.lng
                };

                const submitResponse = await fetch('http://127.0.0.1:8001/results/submit', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(resultPayload)
                });

                if (!submitResponse.ok) {
                    const errorData = await submitResponse.json();
                    console.error("Submission failed:", errorData);
                    throw new Error(errorData.detail || "Result submission failed");
                }

                console.log("Sync successful for PU:", draft.puCode);
                // 4. Delete upon success
                await deleteDraft(draft.id);

            } catch (err) {
                console.error("Sync error for draft:", draft.id, err);
                setError(`Sync failed: ${err.message}`);
                // Break the loop on critical error to avoid spamming the server
                break;
            }
        }

        await loadDrafts();
        setSyncing(false);
    };

    if (pendingDrafts.length === 0 || isDismissed) return null;

    return (
        <div className="fixed bottom-24 left-4 right-4 animate-in slide-in-from-bottom-8 duration-500 z-40">
            <div className="bg-brand-dark text-white p-4 rounded-2xl shadow-2xl flex flex-col space-y-4 border border-white/10 backdrop-blur-md bg-opacity-90 relative">
                {/* Close Button */}
                <button
                    onClick={() => setIsDismissed(true)}
                    className="absolute -top-3 -right-1 bg-gray-800 text-white p-1.5 rounded-full shadow-xl border border-white/20 hover:bg-gray-700 transition-all active:scale-90"
                >
                    <X className="w-3 h-3" />
                </button>

                <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-3">
                        <div className="bg-white/20 p-2 rounded-full">
                            <CloudUpload className="w-5 h-5" />
                        </div>
                        <div>
                            <p className="text-sm font-bold">{pendingDrafts.length} Results Pending Sync</p>
                            <p className="text-xs text-white/70">
                                {isOnline ? 'Online - Ready to sync' : 'Offline - Waiting for connection'}
                            </p>
                            {error && (
                                <div className="flex items-center space-x-2 text-red-200 bg-red-900/40 p-2 rounded-lg text-[10px] mt-2 border border-red-500/30">
                                    <AlertTriangle className="w-3 h-3 shrink-0" />
                                    <p className="font-black uppercase">{error}</p>
                                </div>
                            )}
                        </div>
                    </div>

                    <button
                        onClick={handleSync}
                        disabled={!isOnline || syncing}
                        className={`flex items-center space-x-2 px-4 py-2 rounded-xl font-bold transition-all ${isOnline ? 'bg-white text-brand-dark hover:bg-white/90' : 'bg-white/10 text-white/50 cursor-not-allowed'
                            }`}
                    >
                        {syncing ? (
                            <RefreshCw className="w-4 h-4 animate-spin" />
                        ) : (
                            <>
                                <RefreshCw className="w-4 h-4" />
                                <span>Sync Now</span>
                            </>
                        )}
                    </button>
                </div>

                <button
                    onClick={() => setIsScanOpen(true)}
                    className="w-full py-2 bg-white/10 hover:bg-white/20 text-white rounded-xl text-[10px] uppercase font-black tracking-widest flex items-center justify-center space-x-2 transition-colors border border-white/5"
                >
                    <QrCode className="w-3 h-3" />
                    <span>Scan Proxy QR from another Agent</span>
                </button>

                <QRScannerModal isOpen={isScanOpen} onClose={() => setIsScanOpen(false)} />
            </div>
        </div>
    );
};

export default SyncManager;


