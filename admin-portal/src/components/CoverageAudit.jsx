import React, { useState, useEffect } from 'react';
import { AlertTriangle, MapPin, Search, RefreshCw, Filter, UserPlus, Shield } from 'lucide-react';
import { motion } from 'framer-motion';
import { useNotification } from '../contexts/NotificationContext';

const CoverageAudit = ({ setActiveView }) => {
    const { showNotification } = useNotification();
    const [gaps, setGaps] = useState([]);
    const [totalGaps, setTotalGaps] = useState(0);
    const [isLoading, setIsLoading] = useState(true);
    const [states, setStates] = useState([]);
    const [lgas, setLgas] = useState([]);
    const [wards, setWards] = useState([]);

    // Filter hierarchy: client -> election -> state -> lga -> ward. With an
    // election chosen, a "gap" means a PU inside that election's scope with
    // no agent accredited for THAT race; the geo options come from the
    // scope-filtered endpoints.
    const isPlatformAdmin = (() => {
        try { return !localStorage.getItem('adminClientId'); } catch (e) { return false; }
    })();

    const [clients, setClients] = useState([]);
    const [elections, setElections] = useState([]);

    const [filters, setFilters] = useState({
        client_id: '',
        election_id: '',
        state_id: '',
        lga_id: '',
        ward_id: ''
    });
    const [highRiskOnly, setHighRiskOnly] = useState(false);

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
        fetchGaps();
    }, []);

    const visibleElections = isPlatformAdmin && filters.client_id
        ? elections.filter(e => e.client_id === filters.client_id)
        : elections;

    const geoQuery = (electionId = filters.election_id) =>
        electionId ? `?election_id=${electionId}` : '';

    const fetchGaps = async () => {
        setIsLoading(true);
        try {
            const f = filters;
            const queryParams = new URLSearchParams();
            if (f.client_id) queryParams.append('client_id', f.client_id);
            if (f.election_id) queryParams.append('election_id', f.election_id);
            if (f.state_id) queryParams.append('state_id', f.state_id);
            if (f.lga_id) queryParams.append('lga_id', f.lga_id);
            if (f.ward_id) queryParams.append('ward_id', f.ward_id);
            queryParams.append('limit', '100'); // Balanced for rendering performance

            const res = await fetch(`/admin/unassigned-pus?${queryParams.toString()}`);
            if (res.ok) {
                const data = await res.json();
                setGaps(data.gaps || []);
                setTotalGaps(data.total_count || 0);
            }
        } catch (e) {
            console.error("Failed to fetch coverage gaps", e);
        } finally {
            setIsLoading(false);
        }
    };

    const handleFilterChange = (key, value) => {
        setFilters(prev => {
            const next = { ...prev, [key]: value };
            if (key === 'client_id') return { ...next, election_id: '', state_id: '', lga_id: '', ward_id: '' };
            if (key === 'election_id') return { ...next, state_id: '', lga_id: '', ward_id: '' };
            if (key === 'state_id') return { ...next, lga_id: '', ward_id: '' };
            if (key === 'lga_id') return { ...next, ward_id: '' };
            return next;
        });

        if (key === 'client_id') {
            setStates([]); setLgas([]); setWards([]);
        }
        if (key === 'election_id') {
            setLgas([]); setWards([]);
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
            setWards([]);
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
            if (value) {
                fetch(`/admin/geo/lgas/${value}/wards${geoQuery()}`)
                    .then(r => (r.ok ? r.json() : []))
                    .then(setWards)
                    .catch(() => setWards([]));
            } else {
                setWards([]);
            }
        }
    };

    useEffect(() => {
        fetchGaps();
    }, [filters.client_id, filters.election_id, filters.state_id, filters.lga_id, filters.ward_id]);

    return (
        <div className="space-y-6 animate-in fade-in duration-500">
            {/* Legend / Risk Header */}
            <div className="bg-red-50 dark:bg-red-900/10 border border-red-100 dark:border-red-900/30 p-6 rounded-[2.5rem] flex items-center space-x-4 shadow-sm">
                <div className="bg-red-100 dark:bg-red-900/40 p-3 rounded-2xl">
                    <AlertTriangle className="w-6 h-6 text-red-600" />
                </div>
                <div>
                    <h3 className="text-lg font-black text-red-900 dark:text-red-400 uppercase tracking-tight leading-none mb-1">Coverage Audit</h3>
                    <p className="text-[10px] text-red-600 font-bold uppercase tracking-wider">Identifying vulnerable polling units without personnel</p>
                </div>
            </div>

            {/* Filter Hub */}
            <div className="bg-white dark:bg-gray-900 p-6 rounded-[2.5rem] border border-gray-100 dark:border-gray-800 shadow-xl">
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
                    {isPlatformAdmin && (
                        <div className="space-y-1.5">
                            <label className="text-[9px] font-black text-gray-400 uppercase tracking-widest ml-1">Client</label>
                            <select
                                value={filters.client_id}
                                onChange={(e) => handleFilterChange('client_id', e.target.value)}
                                className="w-full px-4 py-3 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-950 text-[9px] font-bold uppercase outline-none focus:ring-2 focus:ring-red-500"
                            >
                                <option value="">All Clients</option>
                                {clients.map(cl => <option key={cl.id} value={cl.id}>{cl.name}</option>)}
                            </select>
                        </div>
                    )}

                    <div className="space-y-1.5">
                        <label className="text-[9px] font-black text-gray-400 uppercase tracking-widest ml-1">Election</label>
                        <select
                            value={filters.election_id}
                            onChange={(e) => handleFilterChange('election_id', e.target.value)}
                            className="w-full px-4 py-3 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-950 text-[9px] font-bold uppercase outline-none focus:ring-2 focus:ring-red-500"
                        >
                            <option value="">{isPlatformAdmin ? 'Whole Registry' : 'Select election'}</option>
                            {visibleElections.map(el => <option key={el.id} value={el.id}>{el.name} ({el.code})</option>)}
                        </select>
                    </div>

                    <div className="space-y-1.5">
                        <label className="text-[9px] font-black text-gray-400 uppercase tracking-widest ml-1">State</label>
                        <select
                            value={filters.state_id}
                            onChange={(e) => handleFilterChange('state_id', e.target.value)}
                            disabled={!filters.election_id}
                            className="w-full px-4 py-3 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-950 text-[9px] font-bold uppercase outline-none focus:ring-2 focus:ring-red-500 disabled:opacity-50"
                        >
                            <option value="">{filters.election_id ? 'All States' : 'Pick an election first'}</option>
                            {states.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                        </select>
                    </div>

                    <div className="space-y-1.5">
                        <label className="text-[9px] font-black text-gray-400 uppercase tracking-widest ml-1">LGA</label>
                        <select
                            value={filters.lga_id}
                            onChange={(e) => handleFilterChange('lga_id', e.target.value)}
                            disabled={!filters.state_id}
                            className="w-full px-4 py-3 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-950 text-[9px] font-bold uppercase outline-none focus:ring-2 focus:ring-red-500 disabled:opacity-50"
                        >
                            <option value="">All LGAs</option>
                            {lgas.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
                        </select>
                    </div>

                    <div className="space-y-1.5">
                        <label className="text-[9px] font-black text-gray-400 uppercase tracking-widest ml-1">Ward</label>
                        <select
                            value={filters.ward_id}
                            onChange={(e) => handleFilterChange('ward_id', e.target.value)}
                            disabled={!filters.lga_id}
                            className="w-full px-4 py-3 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-950 text-[9px] font-bold uppercase outline-none focus:ring-2 focus:ring-red-500 disabled:opacity-50"
                        >
                            <option value="">All Wards</option>
                            {wards.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
                        </select>
                    </div>
                </div>
            </div>

            {/* Gap Registry */}
            <div className="bg-white dark:bg-gray-900 rounded-[2.5rem] border border-gray-100 dark:border-gray-800 shadow-xl overflow-hidden">
                <div className="p-6 border-b border-gray-50 dark:border-gray-800 flex justify-between items-center">
                    <h3 className="font-black text-gray-900 dark:text-white uppercase tracking-tight flex items-center space-x-2">
                        <MapPin className="w-4 h-4 text-red-500" />
                        <span>Coverage Gaps</span>
                    </h3>
                    <div className="flex items-center space-x-2">
                        <button
                            onClick={() => {
                                setHighRiskOnly(!highRiskOnly);
                                // Simulation of a security audit filter triggering
                                console.log("Security Integrity Audit Triggered");
                            }}
                            className={`p-2 transition-all ${highRiskOnly ? 'text-red-600 bg-red-50 dark:bg-red-900/20 rounded-xl shadow-inner' : 'text-gray-400 hover:text-red-600'}`}
                            title="Security Integrity Audit"
                        >
                            <Shield className={`w-5 h-5 ${highRiskOnly ? 'animate-pulse' : ''}`} />
                        </button>
                        <button
                            onClick={fetchGaps}
                            disabled={isLoading}
                            className="p-2 text-gray-400 hover:text-red-600 transition-colors"
                            title="Force Refresh"
                        >
                            <RefreshCw className={`w-5 h-5 ${isLoading ? 'animate-spin' : ''}`} />
                        </button>
                        <span className="bg-red-50 dark:bg-red-950 text-red-600 text-[10px] px-3 py-1 rounded-full font-black uppercase tracking-widest ml-2">
                            {gaps.length < totalGaps ? `Top ${gaps.length} of ${totalGaps}` : `${totalGaps} UNITS`}
                        </span>
                    </div>
                </div>

                <div className="divide-y divide-gray-50 dark:divide-gray-800">
                    {gaps.map((gap) => (
                        <div key={gap.id} className="p-5 hover:bg-red-50/10 dark:hover:bg-red-900/5 transition-colors flex items-center justify-between group">
                            <div className="flex items-center space-x-4">
                                <div className="w-10 h-10 bg-red-50 dark:bg-red-900/10 rounded-2xl flex items-center justify-center border border-red-100 dark:border-red-900/20">
                                    <MapPin className="w-5 h-5 text-red-600 transition-transform group-hover:scale-110" />
                                </div>
                                <div>
                                    <h4 className="text-xs font-black text-gray-900 dark:text-white leading-none mb-1 uppercase tracking-tight">
                                        {gap.name}
                                    </h4>
                                    <div className="flex items-center space-x-2">
                                        <span className="text-[10px] font-black text-red-500 uppercase tracking-widest">{gap.code}</span>
                                        <span className="text-[8px] text-gray-300 font-bold">•</span>
                                        <span className="text-[9px] text-gray-400 font-bold uppercase">{gap.state} / {gap.lga} / {gap.ward}</span>
                                    </div>
                                </div>
                            </div>
                            <button
                                onClick={() => {
                                    showNotification(`Redirecting to Agent Provisioning for ${gap.name}...`, "info");
                                    if (setActiveView) setActiveView('agents');
                                }}
                                className="opacity-0 group-hover:opacity-100 p-2 text-gray-400 hover:text-brand transition-all flex items-center space-x-1"
                                title="Assign Agent"
                            >
                                <UserPlus className="w-4 h-4" />
                                <span className="text-[8px] font-black uppercase tracking-widest">Provision</span>
                            </button>
                        </div>
                    ))}
                    {gaps.length === 0 && !isLoading && (
                        <div className="p-20 text-center">
                            <div className="flex flex-col items-center opacity-30">
                                <MapPin className="w-10 h-10 text-gray-300 mb-4" />
                                <p className="text-[10px] font-black uppercase tracking-widest text-gray-400">Tactical coverage complete in this sector</p>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default CoverageAudit;


