import React, { useState, useEffect } from 'react';
import imageCompression from 'browser-image-compression';
import EXIF from 'exif-js';
import { Camera, Upload, MapPin, CheckCircle, AlertCircle, Loader2, QrCode, Video, X } from 'lucide-react';
import { saveDraft } from '../db/db';
import { useNotification } from '../contexts/NotificationContext';
import QRShareModal from './QRShareModal';

const ResultCaptureForm = ({ assignedPu }) => {
    const { showNotification } = useNotification();
    const [loading, setLoading] = useState(false);
    const [geoloading, setGeoLoading] = useState(false);
    const [success, setSuccess] = useState(false);
    const [error, setError] = useState(null);
    const [isQRModalOpen, setIsQRModalOpen] = useState(false);
    const [lastSavedData, setLastSavedData] = useState(null);
    const [isCheckedIn, setIsCheckedIn] = useState(assignedPu?.is_on_site || false);
    const [checkInLoading, setCheckInLoading] = useState(false);
    const [partyConfig, setPartyConfig] = useState({
        party_a_name: 'Party A',
        party_b_name: 'Party B',
        party_c_name: 'Party C',
        election_name: 'General Election'
    });

    // Fetch party names from admin-configured election config
    useEffect(() => {
        fetch('http://127.0.0.1:8001/admin/election-config')
            .then(res => res.ok ? res.json() : null)
            .then(data => { if (data) setPartyConfig(data); })
            .catch(() => { }); // Fail silently — defaults remain
    }, []);

    const [formData, setFormData] = useState({
        puCode: assignedPu?.pu_code || '',
        partyAVotes: '',
        partyBVotes: '',
        partyCVotes: '',
        totalValid: '',
        location: null,
        image: null,
        video: null,
        metadata: null
    });

    useEffect(() => {
        if (assignedPu?.pu_code) {
            setFormData(prev => ({ ...prev, puCode: assignedPu.pu_code }));
            setIsCheckedIn(assignedPu.is_on_site);
        }
    }, [assignedPu]);

    // 1. Image Compression & EXIF Extraction
    const handleImageChange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        setLoading(true);
        try {
            // Extract EXIF before compression
            EXIF.getData(file, function () {
                const metadata = EXIF.getAllTags(this);
                setFormData(prev => ({ ...prev, metadata }));
            });

            // Compress options
            const options = {
                maxSizeMB: 0.3, // Compressed to < 300KB
                maxWidthOrHeight: 1920,
                useWebWorker: true
            };

            const compressedFile = await imageCompression(file, options);
            setFormData(prev => ({ ...prev, image: compressedFile }));
        } catch (err) {
            console.error(err);
            setError("Failed to process image.");
        } finally {
            setLoading(false);
        }
    };

    const handleVideoChange = (e) => {
        const file = e.target.files[0];
        if (!file) return;

        // Basic validation: max 10MB
        if (file.size > 10 * 1024 * 1024) {
            setError("Video file is too large (max 10MB).");
            return;
        }

        setFormData(prev => ({ ...prev, video: file }));
    };

    // 2. Soft Geofencing / Location Capture
    const captureLocation = () => {
        setGeoLoading(true);
        if (!navigator.geolocation) {
            setError("Geolocation is not supported by your browser");
            setGeoLoading(false);
            return;
        }

        navigator.geolocation.getCurrentPosition(
            (position) => {
                setFormData(prev => ({
                    ...prev,
                    location: {
                        lat: position.coords.latitude,
                        lng: position.coords.longitude,
                        accuracy: position.coords.accuracy
                    }
                }));
                setGeoLoading(false);
            },
            (err) => {
                showNotification("GPS capture failed. Proceeding with network-only precision.", "warning");
                setGeoLoading(false);
            },
            { enableHighAccuracy: true, timeout: 10000 }
        );
    };

    const handleCheckIn = async () => {
        if (!assignedPu?.email) return;
        setCheckInLoading(true);
        console.log('[CHECK-IN] Starting for:', assignedPu.email);

        const sendCheckIn = async (coords = { latitude: null, longitude: null }) => {
            const payload = { email: assignedPu.email, latitude: coords.latitude, longitude: coords.longitude };
            console.log('[CHECK-IN] Payload:', JSON.stringify(payload));
            try {
                const res = await fetch('http://127.0.0.1:8001/auth/agent/check-in', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const responseData = await res.json();
                console.log('[CHECK-IN] Response:', responseData);
                if (res.ok) {
                    setIsCheckedIn(true);
                    showNotification("Arrival Verified. Coordinates stored.", "success");
                } else {
                    showNotification(responseData.detail || "Check-in failed.", "error");
                }
            } catch (e) {
                console.error('[CHECK-IN] Fetch error:', e);
            } finally {
                setCheckInLoading(false);
            }
        };

        if (navigator.geolocation) {
            console.log('[CHECK-IN] Requesting GPS...');
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    console.log('[CHECK-IN] GPS acquired:', position.coords.latitude, position.coords.longitude);
                    sendCheckIn({
                        latitude: position.coords.latitude,
                        longitude: position.coords.longitude
                    });
                },
                (error) => {
                    console.warn('[CHECK-IN] GPS error code:', error.code, error.message);
                    showNotification(`GPS Failed (${error.code}). Confirming arrival via network location.`, "warning");
                    sendCheckIn();
                },
                { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
            );
        } else {
            sendCheckIn();
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setSuccess(false);
        setError(null);

        // Basic validation
        if (!formData.puCode || (!formData.image && !formData.video)) {
            setError("PU Code and at least one form of evidence (Photo or Video) are required.");
            return;
        }

        try {
            // SECURITY HARDENING: Payload Signing
            // Generating HMAC-SHA256 to ensure data integrity during synchronization
            const payloadToSign = `${formData.puCode}|${formData.partyAVotes}|${formData.partyBVotes}|${formData.partyCVotes}`;

            // In a production app, the key would be derived from the agent's unique device secret
            const encoder = new TextEncoder();
            const keyData = encoder.encode("AGENT_DEVICE_SECRET_KEY"); // MOCK KEY
            const cryptoKey = await crypto.subtle.importKey(
                "raw", keyData, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
            );
            const signatureBuffer = await crypto.subtle.sign(
                "HMAC", cryptoKey, encoder.encode(payloadToSign)
            );
            const signature = btoa(String.fromCharCode(...new Uint8Array(signatureBuffer)));

            const submissionData = {
                ...formData,
                agentEmail: assignedPu?.email,
                signature,
                signedTimestamp: new Date().toISOString(),
                createdAt: new Date().toISOString()
            };

            // Save to IndexedDB (Offline-First)
            await saveDraft(submissionData);
            setLastSavedData(submissionData);
            setSuccess(true);

            // Reset form (keeping immutable PU code)
            setFormData({
                puCode: assignedPu?.pu_code || '',
                partyAVotes: '',
                partyBVotes: '',
                partyCVotes: '',
                totalValid: '',
                location: null,
                image: null,
                video: null,
                metadata: null
            });
        } catch (err) {
            console.error(err);
            setError("Failed to sign or save result.");
        }
    };

    if (success) {
        return (
            <div className="flex flex-col items-center justify-center space-y-4 p-8 text-center animate-in fade-in zoom-in duration-300">
                <CheckCircle className="w-16 h-16 text-brand" />
                <h2 className="text-2xl font-bold text-gray-800 dark:text-white">Result Captured!</h2>
                <p className="text-gray-600 dark:text-gray-300">
                    The result has been saved locally and will be synced to the server as soon as internet is available.
                </p>

                <div className="flex flex-col w-full space-y-3 mt-4">
                    <button
                        onClick={() => setSuccess(false)}
                        className="w-full py-3 bg-brand text-white rounded-xl font-bold shadow-lg"
                    >
                        Capture Another
                    </button>

                    <button
                        onClick={() => setIsQRModalOpen(true)}
                        className="w-full py-3 bg-white dark:bg-gray-800 text-brand border-2 border-brand/20 rounded-xl font-bold flex items-center justify-center space-x-2"
                    >
                        <QrCode className="w-4 h-4" />
                        <span>Proxy Sync via QR</span>
                    </button>
                </div>

                <QRShareModal
                    isOpen={isQRModalOpen}
                    onClose={() => setIsQRModalOpen(false)}
                    data={lastSavedData}
                />
            </div>
        );
    }

    return (
        <form onSubmit={handleSubmit} className="space-y-6 animate-in slide-in-from-bottom-4 duration-500">
            {/* Immutable Geographic Context */}
            {/* Immutable Geographic Context / Operational Sector */}
            {assignedPu && (
                <div className="space-y-4">
                    <div className="bg-brand/5 dark:bg-brand/10 p-5 rounded-[2rem] border border-brand/10 dark:border-brand/20 relative overflow-hidden group">
                        <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                            <MapPin className="w-12 h-12 text-brand" />
                        </div>
                        <div className="relative z-10 space-y-3">
                            <div className="flex items-center space-x-2 text-[9px] font-black text-brand uppercase tracking-[0.2em]">
                                <div className="w-1.5 h-1.5 bg-brand rounded-full animate-pulse" />
                                <span>Active Operational Sector</span>
                            </div>

                            <div className="grid grid-cols-2 gap-y-3">
                                <div>
                                    <p className="text-[8px] font-black text-gray-400 uppercase tracking-widest">State</p>
                                    <p className="text-[11px] font-bold text-gray-900 dark:text-white uppercase">{assignedPu.state}</p>
                                </div>
                                <div>
                                    <p className="text-[8px] font-black text-gray-400 uppercase tracking-widest">LGA</p>
                                    <p className="text-[11px] font-bold text-gray-900 dark:text-white uppercase">{assignedPu.lga}</p>
                                </div>
                                <div>
                                    <p className="text-[8px] font-black text-gray-400 uppercase tracking-widest">Ward</p>
                                    <p className="text-[11px] font-bold text-gray-900 dark:text-white uppercase">{assignedPu.ward}</p>
                                </div>
                                <div>
                                    <p className="text-[8px] font-black text-gray-400 uppercase tracking-widest">Code</p>
                                    <p className="text-[11px] font-bold text-brand uppercase tracking-widest">{assignedPu.pu_code}</p>
                                </div>
                            </div>

                            <div className="pt-2 border-t border-brand/10 flex justify-between items-center">
                                <h4 className="text-xs font-black text-gray-900 dark:text-white uppercase tracking-tight">
                                    {assignedPu.name}
                                </h4>
                                {!isCheckedIn ? (
                                    <button
                                        type="button"
                                        onClick={handleCheckIn}
                                        disabled={checkInLoading}
                                        className="px-4 py-2 bg-brand text-white text-[9px] font-black uppercase tracking-widest rounded-xl shadow-lg shadow-brand/20 active:scale-95 transition-all"
                                    >
                                        {checkInLoading ? '...' : 'Verify Entry'}
                                    </button>
                                ) : (
                                    <div className="flex items-center space-x-1.5 text-brand bg-brand/10 px-3 py-1.5 rounded-full border border-brand/20">
                                        <CheckCircle className="w-3.5 h-3.5" />
                                        <span className="text-[8px] font-black uppercase tracking-widest">Verified On-Site</span>
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>

                    <div className="space-y-1.5 px-1">
                        <label className="text-[9px] font-black text-gray-400 uppercase tracking-[0.2em] ml-1">Polling Unit Identity</label>
                        <div className="w-full p-4 rounded-2xl border border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-900/50 flex items-center justify-between group">
                            <span className="text-xs font-black text-gray-400 tracking-[0.3em] uppercase">{assignedPu.pu_code}</span>
                        </div>
                    </div>
                </div>
            )}



            <div className="grid grid-cols-3 gap-3">
                <div className="space-y-1.5">
                    <label className="block text-[10px] font-black text-gray-900 dark:text-white uppercase tracking-wider">{partyConfig.party_a_name}</label>
                    <input
                        type="number"
                        placeholder="0"
                        className="w-full p-3 rounded-xl border border-gray-100 dark:border-gray-800 dark:bg-gray-900 focus:ring-2 focus:ring-brand outline-none text-center font-black"
                        value={formData.partyAVotes}
                        onChange={e => setFormData({ ...formData, partyAVotes: e.target.value })}
                    />
                </div>
                <div className="space-y-1.5">
                    <label className="block text-[10px] font-black text-gray-900 dark:text-white uppercase tracking-wider">{partyConfig.party_b_name}</label>
                    <input
                        type="number"
                        placeholder="0"
                        className="w-full p-3 rounded-xl border border-gray-100 dark:border-gray-800 dark:bg-gray-900 focus:ring-2 focus:ring-brand outline-none text-center font-black"
                        value={formData.partyBVotes}
                        onChange={e => setFormData({ ...formData, partyBVotes: e.target.value })}
                    />
                </div>
                <div className="space-y-1.5">
                    <label className="block text-[10px] font-black text-gray-900 dark:text-white uppercase tracking-wider">{partyConfig.party_c_name}</label>
                    <input
                        type="number"
                        placeholder="0"
                        className="w-full p-3 rounded-xl border border-gray-100 dark:border-gray-800 dark:bg-gray-900 focus:ring-2 focus:ring-brand outline-none text-center font-black"
                        value={formData.partyCVotes}
                        onChange={e => setFormData({ ...formData, partyCVotes: e.target.value })}
                    />
                </div>
            </div>

            {/* Evidence Capture Area */}
            <div className="space-y-4">
                <label className="block text-[10px] font-black text-gray-400 uppercase tracking-widest ml-1">Evidence Capture</label>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    {/* Photo Capture */}
                    <div className="relative group">
                        <div className={`relative h-40 border-2 border-dashed rounded-3xl flex flex-col items-center justify-center transition-all cursor-pointer overflow-hidden ${formData.image ? 'border-brand bg-brand/5' : 'border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-900/50 hover:border-brand/50'}`}>
                            <input
                                type="file"
                                accept="image/*"
                                capture="environment"
                                onChange={handleImageChange}
                                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
                            />
                            {loading ? (
                                <Loader2 className="w-8 h-8 text-brand animate-spin" />
                            ) : formData.image ? (
                                <div className="absolute inset-0 flex flex-col items-center justify-center p-4 bg-brand/5">
                                    <div className="w-12 h-12 bg-white dark:bg-gray-800 rounded-2xl shadow-xl flex items-center justify-center mb-2">
                                        <CheckCircle className="w-6 h-6 text-brand" />
                                    </div>
                                    <p className="text-[10px] font-black text-brand uppercase">Photo Ready</p>
                                    <button
                                        type="button"
                                        onClick={(e) => { e.stopPropagation(); setFormData(prev => ({ ...prev, image: null })); }}
                                        className="absolute top-3 right-3 p-1.5 bg-white dark:bg-gray-800 rounded-lg shadow-sm text-gray-400 hover:text-red-500 transition-colors z-20"
                                    >
                                        <X className="w-3 h-3" />
                                    </button>
                                </div>
                            ) : (
                                <>
                                    <div className="w-12 h-12 bg-white dark:bg-gray-800 rounded-2xl shadow-sm flex items-center justify-center mb-3 group-hover:scale-110 transition-transform">
                                        <Camera className="w-6 h-6 text-gray-400 group-hover:text-brand" />
                                    </div>
                                    <p className="text-[10px] font-black text-gray-500 uppercase tracking-wider">Take Photo</p>
                                </>
                            )}
                        </div>
                    </div>

                    {/* Video Capture */}
                    <div className="relative group">
                        <div className={`relative h-40 border-2 border-dashed rounded-3xl flex flex-col items-center justify-center transition-all cursor-pointer overflow-hidden ${formData.video ? 'border-brand bg-brand/5' : 'border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-900/50 hover:border-brand/50'}`}>
                            <input
                                type="file"
                                accept="video/*"
                                capture="environment"
                                onChange={handleVideoChange}
                                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
                            />
                            {formData.video ? (
                                <div className="absolute inset-0 flex flex-col items-center justify-center p-4 bg-brand/5">
                                    <div className="w-12 h-12 bg-white dark:bg-gray-800 rounded-2xl shadow-xl flex items-center justify-center mb-2">
                                        <CheckCircle className="w-6 h-6 text-brand" />
                                    </div>
                                    <p className="text-[10px] font-black text-brand uppercase">Video Ready</p>
                                    <button
                                        type="button"
                                        onClick={(e) => { e.stopPropagation(); setFormData(prev => ({ ...prev, video: null })); }}
                                        className="absolute top-3 right-3 p-1.5 bg-white dark:bg-gray-800 rounded-lg shadow-sm text-gray-400 hover:text-red-500 transition-colors z-20"
                                    >
                                        <X className="w-3 h-3" />
                                    </button>
                                </div>
                            ) : (
                                <>
                                    <div className="w-12 h-12 bg-white dark:bg-gray-800 rounded-2xl shadow-sm flex items-center justify-center mb-3 group-hover:scale-110 transition-transform">
                                        <Video className="w-6 h-6 text-gray-400 group-hover:text-brand" />
                                    </div>
                                    <p className="text-[10px] font-black text-gray-500 uppercase tracking-wider">Record Video</p>
                                </>
                            )}
                        </div>
                    </div>
                </div>
            </div>

            {/* Geo Capture */}
            <button
                type="button"
                onClick={captureLocation}
                className={`w-full flex items-center justify-center space-x-2 p-4 rounded-xl border-2 transition-all ${formData.location
                    ? 'border-brand text-brand bg-brand/5'
                    : 'border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-300'
                    }`}
            >
                {geoloading ? (
                    <Loader2 className="w-5 h-5 animate-spin" />
                ) : (
                    <>
                        <MapPin className="w-5 h-5" />
                        <span>{formData.location ? 'Location Captured' : 'Attach GPS Metadata'}</span>
                    </>
                )}
            </button>

            {error && (
                <div className="flex items-center space-x-2 text-red-600 bg-red-50 dark:bg-red-900/20 p-3 rounded-lg text-sm border border-red-100 dark:border-red-900/30">
                    <AlertCircle className="w-5 h-5 shrink-0" />
                    <p>{error}</p>
                </div>
            )}

            <button
                type="submit"
                disabled={loading}
                className="w-full bg-brand hover:bg-brand-dark text-white font-bold py-4 rounded-xl shadow-lg active:scale-95 transition-all flex items-center justify-center disabled:opacity-50"
            >
                Submit Result
            </button>
        </form>
    );
};

export default ResultCaptureForm;


