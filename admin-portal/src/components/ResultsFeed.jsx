import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { FileText, Maximize2, X, AlertCircle, Copy, Search, Download, MapPin } from 'lucide-react';
import { useNotification } from '../contexts/NotificationContext';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

// ── Presence-trail viewer: map + timeline of an agent's GPS breadcrumbs ──
const PresenceTrailModal = ({ doc, onClose }) => {
    const [trail, setTrail] = useState(null);
    const [loadError, setLoadError] = useState(null);
    const mapElRef = useRef(null);
    const mapRef = useRef(null);

    useEffect(() => {
        fetch(`/admin/results/${doc.id}/trail`)
            .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
            .then(setTrail)
            .catch(e => setLoadError(e.message));
    }, [doc.id]);

    useEffect(() => {
        if (!trail || mapRef.current || !mapElRef.current) return;
        const map = L.map(mapElRef.current, { zoomControl: true });
        L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '&copy; OpenStreetMap contributors'
        }).addTo(map);

        const bounds = [];
        const addPt = (lat, lng) => { if (lat != null && lng != null) bounds.push([lat, lng]); };

        if (trail.anchor) {
            addPt(trail.anchor.lat, trail.anchor.lng);
            L.circle([trail.anchor.lat, trail.anchor.lng], {
                radius: trail.geofence_radius_m || 400,
                color: '#2563eb', weight: 1, fillOpacity: 0.06
            }).addTo(map).bindPopup(`Geofence: ${trail.pu_code} (±${trail.geofence_radius_m || 400} m)`);
            L.circleMarker([trail.anchor.lat, trail.anchor.lng], {
                radius: 5, color: '#2563eb', fillColor: '#2563eb', fillOpacity: 0.9
            }).addTo(map).bindPopup(`Anchor: ${trail.pu_name || trail.pu_code}`);
        }

        const pingPts = (trail.pings || [])
            .filter(p => p.lat != null && p.lng != null)
            .map(p => [p.lat, p.lng]);
        if (pingPts.length > 1) {
            L.polyline(pingPts, { color: '#10b981', weight: 2, opacity: 0.7, dashArray: '4 4' }).addTo(map);
        }
        (trail.pings || []).forEach(p => {
            if (p.lat == null || p.lng == null) return;
            addPt(p.lat, p.lng);
            L.circleMarker([p.lat, p.lng], {
                radius: 5,
                color: p.outside_geofence ? '#dc2626' : '#10b981',
                fillColor: p.outside_geofence ? '#dc2626' : '#10b981',
                fillOpacity: 0.85
            }).addTo(map).bindPopup(
                `Ping ${new Date(p.at).toLocaleTimeString()}<br/>` +
                `Distance from anchor: ${p.distance_m != null ? Math.round(p.distance_m) + ' m' : 'unknown'}` +
                (p.outside_geofence ? '<br/><b>OUTSIDE GEOFENCE</b>' : '')
            );
        });

        if (trail.check_in && trail.check_in.lat != null) {
            addPt(trail.check_in.lat, trail.check_in.lng);
            L.circleMarker([trail.check_in.lat, trail.check_in.lng], {
                radius: 7, color: '#1d4ed8', fillColor: '#3b82f6', fillOpacity: 0.9
            }).addTo(map).bindPopup(`Verify-entry ${new Date(trail.check_in.at).toLocaleString()}`);
        }
        if (trail.submission && trail.submission.lat != null) {
            addPt(trail.submission.lat, trail.submission.lng);
            L.circleMarker([trail.submission.lat, trail.submission.lng], {
                radius: 7, color: '#111827', fillColor: '#111827', fillOpacity: 0.9
            }).addTo(map).bindPopup(`Result submitted ${new Date(trail.submission.at).toLocaleString()}`);
        }

        if (bounds.length > 0) {
            map.fitBounds(L.latLngBounds(bounds).pad(0.35));
        } else {
            map.setView([9.082, 8.6753], 6); // Nigeria fallback
        }
        mapRef.current = map;
        return () => { map.remove(); mapRef.current = null; };
    }, [trail]);

    const outsideCount = (trail?.pings || []).filter(p => p.outside_geofence).length;

    return (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/80 z-[200] flex items-center justify-center p-4 backdrop-blur-sm">
            <motion.div initial={{ scale: 0.95, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.95, y: 20 }}
                className="bg-white dark:bg-gray-900 rounded-2xl shadow-2xl max-w-4xl w-full overflow-hidden border border-gray-100 dark:border-gray-800">
                <div className="p-4 border-b border-gray-100 dark:border-gray-800 flex justify-between items-center bg-gray-50 dark:bg-gray-800/50">
                    <h3 className="font-bold text-gray-900 dark:text-white flex items-center">
                        <MapPin className="w-4 h-4 mr-2 text-brand" />
                        Presence Trail — {trail?.pu_code || doc.pu_code}
                        {trail?.gps_trail_flag && (
                            <span className="ml-3 text-[10px] font-black uppercase bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-400 px-2 py-0.5 rounded-full">
                                Thin GPS trail
                            </span>
                        )}
                    </h3>
                    <button onClick={onClose} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200">
                        <X className="w-5 h-5" />
                    </button>
                </div>

                <div className="p-4">
                    {loadError ? (
                        <div className="p-8 text-center text-sm text-red-500">Failed to load trail: {loadError}</div>
                    ) : !trail ? (
                        <div className="p-8 text-center text-sm text-gray-400">Loading trail…</div>
                    ) : (
                        <>
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3 text-center">
                                <div className="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-2">
                                    <p className="text-[9px] text-gray-400 font-bold uppercase">Pings</p>
                                    <p className="font-black text-sm">{trail.pings.length}</p>
                                </div>
                                <div className="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-2">
                                    <p className="text-[9px] text-gray-400 font-bold uppercase">Outside fence</p>
                                    <p className={`font-black text-sm ${outsideCount > 0 ? 'text-red-500' : 'text-green-600'}`}>{outsideCount}</p>
                                </div>
                                <div className="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-2">
                                    <p className="text-[9px] text-gray-400 font-bold uppercase">Verify-entry</p>
                                    <p className="font-black text-[10px]">{trail.check_in?.at ? new Date(trail.check_in.at).toLocaleTimeString() : '—'}</p>
                                </div>
                                <div className="bg-gray-50 dark:bg-gray-800/50 rounded-lg p-2">
                                    <p className="text-[9px] text-gray-400 font-bold uppercase">Submitted</p>
                                    <p className="font-black text-[10px]">{trail.submission?.at ? new Date(trail.submission.at).toLocaleTimeString() : '—'}</p>
                                </div>
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
                                <div ref={mapElRef} className="md:col-span-3 h-72 rounded-xl overflow-hidden border border-gray-200 dark:border-gray-700 z-0" />
                                <div className="md:col-span-2 max-h-72 overflow-y-auto pr-1 space-y-1">
                                    {trail.pings.length === 0 && (
                                        <p className="text-xs text-gray-400 text-center py-6">No GPS pings recorded for this window.</p>
                                    )}
                                    {[...(trail.pings || [])].reverse().map((p, i) => (
                                        <div key={i} className={`flex items-center justify-between text-[11px] px-2 py-1.5 rounded-lg border ${p.outside_geofence ? 'bg-red-50 border-red-200 dark:bg-red-500/10 dark:border-red-500/30' : 'bg-gray-50 border-gray-100 dark:bg-gray-800/50 dark:border-gray-800'}`}>
                                            <span className="font-mono">{p.at ? new Date(p.at).toLocaleTimeString() : '—'}</span>
                                            <span className={p.outside_geofence ? 'text-red-500 font-bold' : 'text-gray-400'}>
                                                {p.distance_m != null ? `${Math.round(p.distance_m)} m` : '—'}
                                                {p.outside_geofence ? ' ⚠ outside' : ''}
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </>
                    )}
                </div>
            </motion.div>
        </motion.div>
    );
};

const ResultsFeed = () => {
    const [documents, setDocuments] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [isLoadingMore, setIsLoadingMore] = useState(false);
    const [fullImageOpen, setFullImageOpen] = useState(false);
    const [currentImage, setCurrentImage] = useState(null);
    const { showNotification } = useNotification();

    // Filter hierarchy: client -> election -> state -> lga -> ward -> pu.
    // All of it is applied server-side; the geo dropdowns only ever offer
    // what is inside the selected election's scope.
    const isPlatformAdmin = (() => {
        try { return !localStorage.getItem('adminClientId'); } catch (e) { return false; }
    })();

    const [clients, setClients] = useState([]);
    const [elections, setElections] = useState([]);
    const [states, setStates] = useState([]);
    const [lgas, setLgas] = useState([]);
    const [wards, setWards] = useState([]);
    const [pus, setPus] = useState([]);
    const [filters, setFilters] = useState({
        client_id: '',
        election_id: '',
        state_id: '',
        lga_id: '',
        ward_id: '',
        pu_id: '',
    });

    // New Advanced Filters State
    const [searchQuery, setSearchQuery] = useState('');
    const [startDate, setStartDate] = useState('');
    const [endDate, setEndDate] = useState('');
    const [page, setPage] = useState(0);
    const [hasMore, setHasMore] = useState(true);
    const limit = 50;

    useEffect(() => {
        (async () => {
            try {
                const [cRes, eRes] = await Promise.all([
                    isPlatformAdmin ? fetch('/admin/clients') : Promise.resolve(null),
                    fetch('/admin/elections'),
                ]);
                if (cRes && cRes.ok) setClients((await cRes.json()).clients || []);
                if (eRes.ok) setElections((await eRes.json()).elections || []);
            } catch (e) { console.error(e); }
        })();
    }, []);

    const visibleElections = isPlatformAdmin && filters.client_id
        ? elections.filter(e => e.client_id === filters.client_id)
        : elections;

    const geoQuery = (electionId = filters.election_id) =>
        electionId ? `?election_id=${electionId}` : '';

    const fetchDocuments = async (pageNum = 0) => {
        if (pageNum === 0) setIsLoading(true);
        else setIsLoadingMore(true);

        try {
            const params = new URLSearchParams({
                skip: pageNum * limit,
                limit: limit
            });
            if (searchQuery) params.append('search', searchQuery);
            if (startDate) params.append('start_date', startDate);
            if (endDate) params.append('end_date', endDate);
            if (filters.client_id) params.append('client_id', filters.client_id);
            if (filters.election_id) params.append('election_id', filters.election_id);
            if (filters.state_id) params.append('state_id', filters.state_id);
            if (filters.lga_id) params.append('lga_id', filters.lga_id);
            if (filters.ward_id) params.append('ward_id', filters.ward_id);
            if (filters.pu_id) params.append('pu_id', filters.pu_id);

            const res = await fetch(`/admin/all-documents?${params.toString()}`);
            if (res.ok) {
                const data = await res.json();
                if (pageNum === 0) {
                    setDocuments(data);
                } else {
                    setDocuments(prev => [...prev, ...data]);
                }
                setHasMore(data.length === limit);
                setPage(pageNum);
            } else {
                showNotification("Failed to fetch documents.", "error");
            }
        } catch (e) {
            showNotification("Error connecting to server.", "error");
        } finally {
            setIsLoading(false);
            setIsLoadingMore(false);
        }
    };

    useEffect(() => {
        fetchDocuments(0);
        
        // Auto-refresh feed every 30 seconds to show real-time activities from agent portal
        const intervalId = setInterval(() => {
            fetchDocuments(0);
        }, 30000);

        return () => clearInterval(intervalId);
    }, [searchQuery, startDate, endDate, showNotification,
        filters.client_id, filters.election_id, filters.state_id,
        filters.lga_id, filters.ward_id, filters.pu_id]);

    const [proofModalDoc, setProofModalDoc] = useState(null);
    const [trailModalDoc, setTrailModalDoc] = useState(null);

    const handleCopy = (text, type) => {
        navigator.clipboard.writeText(text);
        showNotification(`${type} copied to clipboard!`, "success");
    };

    // Cascade: each level resets everything below it and (when an election
    // is involved) reloads from the scope-filtered geo endpoints.
    const handleFilterChange = (key, value) => {
        setFilters(prev => {
            const next = { ...prev, [key]: value };
            if (key === 'client_id') return { ...next, election_id: '', state_id: '', lga_id: '', ward_id: '', pu_id: '' };
            if (key === 'election_id') return { ...next, state_id: '', lga_id: '', ward_id: '', pu_id: '' };
            if (key === 'state_id') return { ...next, lga_id: '', ward_id: '', pu_id: '' };
            if (key === 'lga_id') return { ...next, ward_id: '', pu_id: '' };
            if (key === 'ward_id') return { ...next, pu_id: '' };
            return next;
        });

        if (key === 'client_id') {
            setStates([]); setLgas([]); setWards([]); setPus([]);
        }
        if (key === 'election_id') {
            setLgas([]); setWards([]); setPus([]);
            if (value) {
                fetch(`/admin/geo/states${geoQuery(value)}`)
                    .then(r => (r.ok ? r.json() : []))
                    .then(setStates)
                    .catch(() => setStates([]));
            } else {
                setStates([]);
            }
        }
        if (key === 'state_id') {
            setWards([]); setPus([]);
            if (value) {
                fetch(`/admin/geo/states/${value}/lgas${geoQuery()}`)
                    .then(r => (r.ok ? r.json() : []))
                    .then(setLgas)
                    .catch(() => setLgas([]));
            } else {
                setLgas([]);
            }
        }
        if (key === 'lga_id') {
            setPus([]);
            if (value) {
                fetch(`/admin/geo/lgas/${value}/wards${geoQuery()}`)
                    .then(r => (r.ok ? r.json() : []))
                    .then(setWards)
                    .catch(() => setWards([]));
            } else {
                setWards([]);
            }
        }
        if (key === 'ward_id') {
            if (value) {
                fetch(`/admin/geo/wards/${value}/pus${geoQuery()}`)
                    .then(r => (r.ok ? r.json() : []))
                    .then(setPus)
                    .catch(() => setPus([]));
            } else {
                setPus([]);
            }
        }
    };

    const downloadReceipt = (doc) => {
        const receiptText = `CIVICLENS BLOCKCHAIN CERTIFICATE OF IMMUTABILITY\n\n` +
                            `State: ${doc.state || 'N/A'}\n` +
                            `Local Government: ${doc.lga || 'N/A'}\n` +
                            `Ward: ${doc.ward || 'N/A'}\n` +
                            `Polling Unit: ${doc.pu_name || 'N/A'} (${doc.pu_code})\n` +
                            `Timestamp: ${new Date(doc.uploaded_at).toISOString()}\n` +
                            `Status: ANCHORED & IMMUTABLE\n\n` +
                            `Cryptographic Hash (SHA-256):\n${doc.blockchain_hash}\n\n` +
                            `Blockchain Transaction ID:\n${doc.blockchain_tx_id}\n\n` +
                            `This cryptographic proof guarantees that the data has not been altered since the timestamp above.\n`;
        
        const blob = new Blob([receiptText], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `CivicLens_Proof_${doc.pu_code}.txt`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    };

    const downloadCSV = () => {
        if (documents.length === 0) {
            showNotification("No data to export", "error");
            return;
        }

        const headers = ["Election", "State", "LGA", "Ward", "PU Code", "PU Name", "Party A", "Party B", "Party C", "Uploaded At", "Blockchain Hash", "Transaction ID"];
        const rows = documents.map(doc => [
            doc.election_code || "",
            doc.state || "",
            doc.lga || "",
            doc.ward || "",
            doc.pu_code || "",
            doc.pu_name || "",
            doc.party_a || 0,
            doc.party_b || 0,
            doc.party_c || 0,
            doc.uploaded_at || "",
            doc.blockchain_hash || "",
            doc.blockchain_tx_id || ""
        ]);

        const csvContent = [
            headers.join(","),
            ...rows.map(e => e.map(field => `"${String(field).replace(/"/g, '""')}"`).join(","))
        ].join("\n");

        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.setAttribute("href", url);
        link.setAttribute("download", `civiclens_results_${new Date().toISOString().split('T')[0]}.csv`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
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
                            src={currentImage}
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

                {proofModalDoc && (
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="fixed inset-0 bg-black/80 z-[200] flex items-center justify-center p-4 backdrop-blur-sm"
                    >
                        <motion.div
                            initial={{ scale: 0.95, y: 20 }}
                            animate={{ scale: 1, y: 0 }}
                            exit={{ scale: 0.95, y: 20 }}
                            className="bg-white dark:bg-gray-900 rounded-2xl shadow-2xl max-w-lg w-full overflow-hidden border border-gray-100 dark:border-gray-800"
                        >
                            <div className="p-6 border-b border-gray-100 dark:border-gray-800 flex justify-between items-center bg-gray-50 dark:bg-gray-800/50">
                                <h3 className="font-bold text-gray-900 dark:text-white flex items-center">
                                    <span className="w-2 h-2 bg-green-500 rounded-full mr-2 animate-pulse"></span>
                                    Blockchain Verification
                                </h3>
                                <button onClick={() => setProofModalDoc(null)} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200">
                                    <X className="w-5 h-5" />
                                </button>
                            </div>
                            <div className="p-6 space-y-4">
                                <div className="bg-gray-50 dark:bg-gray-800/50 p-4 rounded-lg border border-gray-100 dark:border-gray-800 mb-4">
                                    <p className="text-xs font-bold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-2">Location Details</p>
                                    <div className="grid grid-cols-2 gap-2 text-sm text-gray-800 dark:text-gray-200">
                                        <div><span className="font-semibold text-gray-500">State:</span> {proofModalDoc.state}</div>
                                        <div><span className="font-semibold text-gray-500">LGA:</span> {proofModalDoc.lga}</div>
                                        <div><span className="font-semibold text-gray-500">Ward:</span> {proofModalDoc.ward}</div>
                                        <div><span className="font-semibold text-gray-500">PU:</span> <span title={proofModalDoc.pu_name}>{proofModalDoc.pu_code}</span></div>
                                    </div>
                                </div>

                                <div>
                                    <div className="flex justify-between items-center mb-1">
                                        <p className="text-xs font-bold text-gray-500 dark:text-gray-400 uppercase tracking-wider">Cryptographic Hash</p>
                                        <button onClick={() => handleCopy(proofModalDoc.blockchain_hash, "Hash")} className="text-gray-400 hover:text-brand transition-colors" title="Copy Hash">
                                            <Copy className="w-4 h-4" />
                                        </button>
                                    </div>
                                    <div className="bg-gray-100 dark:bg-gray-950 p-3 rounded-lg border border-gray-200 dark:border-gray-800 font-mono text-xs break-all text-gray-800 dark:text-gray-300">
                                        {proofModalDoc.blockchain_hash}
                                    </div>
                                </div>
                                <div>
                                    <div className="flex justify-between items-center mb-1">
                                        <p className="text-xs font-bold text-gray-500 dark:text-gray-400 uppercase tracking-wider">Transaction ID (Receipt)</p>
                                        <button onClick={() => handleCopy(proofModalDoc.blockchain_tx_id, "Transaction ID")} className="text-gray-400 hover:text-brand transition-colors" title="Copy TxID">
                                            <Copy className="w-4 h-4" />
                                        </button>
                                    </div>
                                    <div className="bg-gray-100 dark:bg-gray-950 p-3 rounded-lg border border-gray-200 dark:border-gray-800 font-mono text-xs break-all text-brand">
                                        {proofModalDoc.blockchain_tx_id}
                                    </div>
                                </div>
                                <div className="pt-2">
                                    <p className="text-sm text-gray-600 dark:text-gray-400">
                                        Status: <strong className="text-green-600 dark:text-green-500">IMMUTABLE</strong>
                                    </p>
                                </div>
                            </div>
                            <div className="p-6 border-t border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50 flex justify-end space-x-3">
                                <button
                                    onClick={() => setProofModalDoc(null)}
                                    className="px-4 py-2 text-sm font-bold text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg transition-colors"
                                >
                                    Close
                                </button>
                                <a
                                    href={`https://polygonscan.com/tx/${proofModalDoc.blockchain_tx_id}`}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="px-4 py-2 text-sm font-bold text-brand bg-brand/10 hover:bg-brand/20 rounded-lg transition-colors flex items-center"
                                >
                                    Verify on PolygonScan
                                </a>
                                <button
                                    onClick={() => downloadReceipt(proofModalDoc)}
                                    className="px-4 py-2 text-sm font-bold text-white bg-brand hover:bg-brand/90 rounded-lg shadow-lg shadow-brand/20 transition-all flex items-center"
                                >
                                    Download Certificate
                                </button>
                            </div>
                        </motion.div>
                    </motion.div>
                )}
                {trailModalDoc && (
                    <PresenceTrailModal doc={trailModalDoc} onClose={() => setTrailModalDoc(null)} />
                )}
            </AnimatePresence>

            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <h3 className="font-bold flex items-center space-x-2 text-gray-900 dark:text-white">
                    <FileText className="w-5 h-5 text-brand" />
                    <span>Uploaded Documents Feed</span>
                </h3>
                <span className="text-[10px] font-black bg-gray-100 dark:bg-gray-800 px-3 py-1 rounded-full whitespace-nowrap">{documents.length} Results</span>
            </div>

            <div className="bg-white dark:bg-gray-950 p-4 rounded-xl border border-gray-100 dark:border-gray-800 shadow-sm space-y-4">
                <div className="flex flex-col md:flex-row gap-4">
                    <div className="flex-1 relative">
                        <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
                        <input 
                            type="text" 
                            placeholder="Search by PU Code or Name..." 
                            className="w-full pl-10 pr-4 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 text-sm rounded-lg focus:ring-brand focus:border-brand"
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                        />
                    </div>
                    <div className="flex items-center gap-2">
                        <input 
                            type="date" 
                            className="bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 text-sm rounded-lg focus:ring-brand focus:border-brand p-2"
                            value={startDate}
                            onChange={(e) => setStartDate(e.target.value)}
                        />
                        <span className="text-gray-400 text-sm font-bold">to</span>
                        <input 
                            type="date" 
                            className="bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 text-sm rounded-lg focus:ring-brand focus:border-brand p-2"
                            value={endDate}
                            onChange={(e) => setEndDate(e.target.value)}
                        />
                    </div>
                    <button 
                        onClick={downloadCSV}
                        className="px-4 py-2 bg-green-50 text-green-600 dark:bg-green-500/10 dark:text-green-500 hover:bg-green-100 dark:hover:bg-green-500/20 text-sm font-bold rounded-lg transition-colors flex items-center gap-2"
                    >
                        <Download className="w-4 h-4" />
                        Export CSV
                    </button>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-4 border-t border-gray-100 dark:border-gray-800 pt-4">
                    {isPlatformAdmin && (
                        <div>
                            <label className="block text-xs font-bold text-gray-500 mb-1">Client</label>
                            <select
                                className="w-full bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 text-sm rounded-lg focus:ring-brand focus:border-brand p-2"
                                value={filters.client_id}
                                onChange={(e) => handleFilterChange('client_id', e.target.value)}
                            >
                                <option value="">All Clients</option>
                                {clients.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                            </select>
                        </div>
                    )}
                    <div>
                        <label className="block text-xs font-bold text-gray-500 mb-1">Election</label>
                        <select
                            className="w-full bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 text-sm rounded-lg focus:ring-brand focus:border-brand p-2"
                            value={filters.election_id}
                            onChange={(e) => handleFilterChange('election_id', e.target.value)}
                        >
                            <option value="">All Elections</option>
                            {visibleElections.map(el => <option key={el.id} value={el.id}>{el.name} ({el.code})</option>)}
                        </select>
                    </div>
                    <div>
                        <label className="block text-xs font-bold text-gray-500 mb-1">State</label>
                        <select
                            className="w-full bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 text-sm rounded-lg focus:ring-brand focus:border-brand p-2 disabled:opacity-50 disabled:cursor-not-allowed"
                            value={filters.state_id}
                            onChange={(e) => handleFilterChange('state_id', e.target.value)}
                            disabled={!filters.election_id}
                        >
                            <option value="">{filters.election_id ? "All States" : "Pick an election first"}</option>
                            {states.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                        </select>
                    </div>
                    <div>
                        <label className="block text-xs font-bold text-gray-500 mb-1">Local Government</label>
                        <select
                            className="w-full bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 text-sm rounded-lg focus:ring-brand focus:border-brand p-2 disabled:opacity-50 disabled:cursor-not-allowed"
                            value={filters.lga_id}
                            onChange={(e) => handleFilterChange('lga_id', e.target.value)}
                            disabled={!filters.state_id}
                        >
                            <option value="">{filters.state_id ? "All LGAs" : "Select State First"}</option>
                            {lgas.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
                        </select>
                    </div>
                    <div>
                        <label className="block text-xs font-bold text-gray-500 mb-1">Ward</label>
                        <select
                            className="w-full bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 text-sm rounded-lg focus:ring-brand focus:border-brand p-2 disabled:opacity-50 disabled:cursor-not-allowed"
                            value={filters.ward_id}
                            onChange={(e) => handleFilterChange('ward_id', e.target.value)}
                            disabled={!filters.lga_id}
                        >
                            <option value="">{filters.lga_id ? "All Wards" : "Select LGA First"}</option>
                            {wards.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
                        </select>
                    </div>
                    <div>
                        <label className="block text-xs font-bold text-gray-500 mb-1">Polling Unit</label>
                        <select
                            className="w-full bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 text-sm rounded-lg focus:ring-brand focus:border-brand p-2 disabled:opacity-50 disabled:cursor-not-allowed"
                            value={filters.pu_id}
                            onChange={(e) => handleFilterChange('pu_id', e.target.value)}
                            disabled={!filters.ward_id}
                        >
                            <option value="">{filters.ward_id ? "All Polling Units" : "Select Ward First"}</option>
                            {pus.map(p => <option key={p.id} value={p.id}>{p.name} ({p.code})</option>)}
                        </select>
                    </div>
                </div>
            </div>

            {isLoading && page === 0 ? (
                <div className="flex justify-center p-12">
                    <div className="w-8 h-8 border-4 border-brand border-t-transparent rounded-full animate-spin"></div>
                </div>
            ) : documents.length === 0 ? (
                <div className="bg-white dark:bg-gray-950 p-12 rounded-2xl border border-gray-100 dark:border-gray-800 text-center shadow-xl">
                    <AlertCircle className="w-12 h-12 text-gray-400 mx-auto mb-4 opacity-50" />
                    <h3 className="font-black text-gray-400 uppercase tracking-widest text-sm">No Documents Found</h3>
                </div>
            ) : (
                <>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {documents.map((doc) => (
                            <div key={doc.id} className="bg-white dark:bg-gray-950 rounded-2xl shadow-xl border border-gray-100 dark:border-gray-800 overflow-hidden">
                                <div className="p-4 border-b border-gray-50 dark:border-gray-800">
                                    <div className="flex justify-between items-center mb-1">
                                        <span className="text-xs font-black uppercase tracking-widest text-brand" title={doc.pu_name}>{doc.pu_code}</span>
                                        <span className="text-[10px] text-gray-400 font-bold">{new Date(doc.uploaded_at).toLocaleString()}</span>
                                    </div>
                                    <div className="text-[9px] text-gray-500 font-medium truncate uppercase">
                                        {doc.state} • {doc.lga} • {doc.ward}
                                    </div>
                                    {doc.election_code && (
                                        <span className="inline-block mt-1 text-[8px] font-black uppercase tracking-widest px-1.5 py-0.5 rounded bg-brand/10 text-brand" title={doc.election_name}>
                                            🗳 {doc.election_code}
                                        </span>
                                    )}
                                </div>
                                
                                <div 
                                    onClick={() => {
                                        if(doc.image_url) {
                                            setCurrentImage(doc.image_url);
                                            setFullImageOpen(true);
                                        }
                                    }}
                                    className="relative h-48 bg-gray-100 dark:bg-gray-900 cursor-zoom-in group"
                                >
                                    {doc.image_url ? (
                                        <>
                                            <img src={doc.image_url} alt="Evidence" className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105" />
                                            <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                                                <Maximize2 className="w-6 h-6 text-white" />
                                            </div>
                                        </>
                                    ) : (
                                        <div className="w-full h-full flex items-center justify-center text-gray-400 text-xs font-bold uppercase tracking-widest">
                                            No Image Provided
                                        </div>
                                    )}
                                </div>

                                <div className="p-4 grid grid-cols-3 gap-2 text-center border-t border-gray-50 dark:border-gray-800">
                                    <div>
                                        <p className="text-[9px] text-gray-400 font-bold">Party A</p>
                                        <p className="font-black text-sm">{doc.party_a}</p>
                                    </div>
                                    <div>
                                        <p className="text-[9px] text-gray-400 font-bold">Party B</p>
                                        <p className="font-black text-sm">{doc.party_b}</p>
                                    </div>
                                    <div>
                                        <p className="text-[9px] text-gray-400 font-bold">Party C</p>
                                        <p className="font-black text-sm">{doc.party_c}</p>
                                    </div>
                                </div>

                                <div className="p-3 bg-slate-50 dark:bg-slate-900 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between">
                                    <span className={`text-[9px] font-black uppercase tracking-widest flex items-center ${doc.gps_trail_flag ? 'text-amber-600 dark:text-amber-400' : 'text-gray-400'}`}>
                                        {doc.gps_trail_flag && <AlertCircle className="w-3 h-3 mr-1" />}
                                        {doc.gps_trail_flag ? 'GPS trail thin' : 'Presence trail'}
                                    </span>
                                    <button onClick={() => setTrailModalDoc(doc)} className="text-[9px] font-bold text-brand hover:underline flex items-center">
                                        <MapPin className="w-3 h-3 mr-1" />
                                        View trail
                                    </button>
                                </div>

                                {doc.blockchain_hash && (
                                    <div className="p-3 bg-slate-50 dark:bg-slate-900 border-t border-slate-100 dark:border-slate-800 flex flex-col space-y-1">
                                        <div className="flex items-center justify-between">
                                            <span className="text-[9px] font-black uppercase text-green-600 dark:text-green-500 tracking-widest flex items-center">
                                                <span className="w-1.5 h-1.5 bg-green-500 rounded-full mr-1.5 animate-pulse"></span>
                                                Ledger Anchored
                                            </span>
                                            <button onClick={() => setProofModalDoc(doc)} className="text-[9px] font-bold text-brand hover:underline">
                                                Verify Proof
                                            </button>
                                        </div>
                                        <p className="text-[8px] font-mono text-gray-400 truncate opacity-70">
                                            Tx: {doc.blockchain_tx_id}
                                        </p>
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                    {hasMore && (
                        <div className="flex justify-center mt-8">
                            <button
                                onClick={() => fetchDocuments(page + 1)}
                                disabled={isLoadingMore}
                                className="px-6 py-2 bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 font-bold rounded-full hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors disabled:opacity-50"
                            >
                                {isLoadingMore ? 'Loading...' : 'Load More Documents'}
                            </button>
                        </div>
                    )}
                </>
            )}
        </div>
    );
};

export default ResultsFeed;
