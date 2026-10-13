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

    const isPlatformAdmin = !localStorage.getItem('adminClientId');
    const [filters, setFilters] = useState({ client_id: '', election_id: '', state_id: '', lga_id: '' });
    const [clients, setClients] = useState([]);
    const [elections, setElections] = useState([]);
    const [states, setStates] = useState([]);
    const [lgas, setLgas] = useState([]);

    const visibleElections = filters.client_id
        ? elections.filter(e => String(e.client_id) === String(filters.client_id))
        : elections;

    useEffect(() => {
        if (!isPlatformAdmin) return;
        fetch('/admin/clients').then(r => r.ok ? r.json() : []).then(setClients).catch(() => {});
    }, [isPlatformAdmin]);

    useEffect(() => {
        fetch('/admin/elections').then(r => r.ok ? r.json() : []).then(setElections).catch(() => {});
    }, []);

    useEffect(() => {
        if (!filters.election_id) { setStates([]); return; }
        fetch(`/admin/geo/states?election_id=${filters.election_id}`)
            .then(r => r.ok ? r.json() : [])
            .then(setStates).catch(() => {});
    }, [filters.election_id]);

    useEffect(() => {
        if (!filters.state_id) { setLgas([]); return; }
        const qs = filters.election_id ? `?election_id=${filters.election_id}` : '';
        fetch(`/admin/geo/states/${filters.state_id}/lgas${qs}`)
            .then(r => r.ok ? r.json() : [])
            .then(setLgas).catch(() => {});
    }, [filters.state_id, filters.election_id]);

    const fetchQueue = async () => {
        setIsLoading(true);
        try {
            const params = new URLSearchParams();
            if (filters.client_id) params.set('client_id', filters.client_id);
            if (filters.election_id) params.set('election_id', filters.election_id);
            if (filters.state_id) params.set('state_id', filters.state_id);
            if (filters.lga_id) params.set('lga_id', filters.lga_id);
            const qs = params.toString();
            const res = await fetch(`/admin/pending-verifications${qs ? '?' + qs : ''}`);
            if (res.ok) {
                const data = await res.json();
                setItems(data);
                setActiveIndex(0);
            }
        } catch (e) {
            showNotification("Verification Queue Sync Failed. Network integrity check required.", "error");
        } finally {
            setIsLoading(false);
        }
    };

    // Initial load: party config + full queue
    useEffect(() => {
        (async () => {
            try {
                const configRes = await fetch('/admin/election-config');
                if (configRes.ok) setPartyConfig(await configRes.json());
            } catch (e) {}
        })();
    }, []);

    // Refetch queue whenever a filter changes
    useEffect(() => { fetchQueue(); }, [filters.client_id, filters.election_id, filters.state_id, filters.lga_id]);

    const handleFilterChange = (field, value, next = {}) => {
        if (field === 'client_id') {
            setFilters({ client_id: value, election_id: '', state_id: '', lga_id: '' });
        } else if (field === 'election_id') {
            setFilters(f => ({ ...f, election_id: value, state_id: '', lga_id: '' }));
        } else if (field === 'state_id') {
            setFilters(f => ({ ...f, state_id: value, lga_id: '' }));
        } else {
            setFilters(f => ({ ...f, [field]: value }));
        }
    };

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
            const res = await fetch(`/admin/verify/${current.id}?action=${action}`, {
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

            {/* Queue Filters */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 bg-white dark:bg-gray-900 p-4 rounded-2xl border border-gray-100 dark:border-gray-800 shadow-sm">
                {isPlatformAdmin && (
                    <select
                        value={filters.client_id}
                        onChange={e => handleFilterChange('client_id', e.target.value)}
                        className="w-full text-xs font-bold bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand/50 text-gray-700 dark:text-gray-200"
                    >
                        <option value="">All Clients</option>
                        {clients.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                    </select>
                )}
                <select
                    value={filters.election_id}
                    onChange={e => handleFilterChange('election_id', e.target.value)}
                    className="w-full text-xs font-bold bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand/50 text-gray-700 dark:text-gray-200"
                >
                    <option value="">All Elections</option>
                    {visibleElections.map(el => <option key={el.id} value={el.id}>{el.name}</option>)}
                </select>
                <select
                    value={filters.state_id}
                    onChange={e => handleFilterChange('state_id', e.target.value)}
                    disabled={!filters.election_id}
                    className="w-full text-xs font-bold bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand/50 text-gray-700 dark:text-gray-200 disabled:opacity-50"
                >
                    <option value="">{filters.election_id ? 'All States' : 'Pick an election first'}</option>
                    {states.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
                <select
                    value={filters.lga_id}
                    onChange={e => handleFilterChange('lga_id', e.target.value)}
                    disabled={!filters.state_id}
                    className="w-full text-xs font-bold bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-xl px-3 py-2 focus:outline-none focus:ring-2 focus:ring-brand/50 text-gray-700 dark:text-gray-200 disabled:opacity-50"
                >
                    <option value="">{filters.state_id ? 'All LGAs' : 'Select State First'}</option>
                    {lgas.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
                </select>
            </div>

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
                            {current.election_code && (
                                <span className="ml-auto text-[8px] font-black bg-brand/10 text-brand px-2 py-0.5 rounded-full uppercase tracking-widest">{current.election_code}</span>
                            )}
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


