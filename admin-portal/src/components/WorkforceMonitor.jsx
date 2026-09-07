import React, { useState, useEffect } from 'react';
import { Users, MapPin, CheckCircle, Clock, Image as ImageIcon, Filter, Search, RefreshCw, X, Shield, ExternalLink } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

const WorkforceMonitor = () => {
    const [workforce, setWorkforce] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [isRefreshing, setIsRefreshing] = useState(false);

    // Geographic State for Filters
    const [states, setStates] = useState([]);
    const [lgas, setLgas] = useState([]);
    const [wards, setWards] = useState([]);
    const [pus, setPus] = useState([]);

    const [filters, setFilters] = useState({
        state_id: '',
        lga_id: '',
        ward_id: '',
        pu_id: '',
        on_site: '', // 'true', 'false', ''
        result_uploaded: '' // 'true', 'false', ''
    });
    const [securityAudit, setSecurityAudit] = useState(false);

    useEffect(() => {
        fetchStates();
        fetchWorkforce();
    }, []);

    const fetchStates = async () => {
        try {
            const res = await fetch('http://127.0.0.1:8001/admin/geo/states');
            if (res.ok) setStates(await res.json());
        } catch (e) { console.error(e); }
    };

    const fetchWorkforce = async () => {
        setIsRefreshing(true);
        try {
            const queryParams = new URLSearchParams();
            if (filters.state_id) queryParams.append('state_id', filters.state_id);
            if (filters.lga_id) queryParams.append('lga_id', filters.lga_id);
            if (filters.ward_id) queryParams.append('ward_id', filters.ward_id);
            if (filters.pu_id) queryParams.append('pu_id', filters.pu_id);
            if (filters.on_site !== '') queryParams.append('on_site', filters.on_site);
            if (filters.result_uploaded !== '') queryParams.append('result_uploaded', filters.result_uploaded);

            const res = await fetch(`http://127.0.0.1:8001/admin/workforce-status?${queryParams.toString()}`);
            if (res.ok) {
                const data = await res.json();
                setWorkforce(Array.isArray(data) ? data : []);
            }
        } catch (e) {
            console.error("Failed to fetch workforce status", e);
        } finally {
            setIsLoading(false);
            setIsRefreshing(false);
        }
    };

    const handleFilterChange = (key, value) => {
        setFilters(prev => {
            const next = { ...prev, [key]: value };
            if (key === 'state_id') return { ...next, lga_id: '', ward_id: '', pu_id: '' };
            if (key === 'lga_id') return { ...next, ward_id: '', pu_id: '' };
            if (key === 'ward_id') return { ...next, pu_id: '' };
            return next;
        });

        if (key === 'state_id') {
            if (value) fetchLgas(value); else setLgas([]);
            setWards([]); setPus([]);
        }
        if (key === 'lga_id') {
            if (value) fetchWards(value); else setWards([]);
            setPus([]);
        }
        if (key === 'ward_id') {
            if (value) fetchPus(value); else setPus([]);
        }
    };

    const fetchLgas = async (stateId) => {
        if (!stateId) { setLgas([]); return; }
        try {
            const res = await fetch(`http://127.0.0.1:8001/admin/geo/states/${stateId}/lgas`);
            if (res.ok) setLgas(await res.json());
        } catch (e) { console.error(e); }
    };

    const fetchWards = async (lgaId) => {
        if (!lgaId) { setWards([]); return; }
        try {
            const res = await fetch(`http://127.0.0.1:8001/admin/geo/lgas/${lgaId}/wards`);
            if (res.ok) setWards(await res.json());
        } catch (e) { console.error(e); }
    };

    const fetchPus = async (wardId) => {
        if (!wardId) { setPus([]); return; }
        try {
            const res = await fetch(`http://127.0.0.1:8001/admin/geo/wards/${wardId}/pus`);
            if (res.ok) setPus(await res.json());
        } catch (e) { console.error(e); }
    };

    useEffect(() => {
        fetchWorkforce();
    }, [filters.on_site, filters.result_uploaded, filters.pu_id, filters.ward_id, filters.lga_id, filters.state_id]);

    return (
        <div className="space-y-6 animate-in fade-in duration-500">
            {/* Header / Stats Summary */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                <div className="bg-white dark:bg-gray-900 p-4 rounded-3xl border border-gray-100 dark:border-gray-800 shadow-sm">
                    <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-1">Total Agents</p>
                    <p className="text-2xl font-black text-gray-900 dark:text-white leading-none">{workforce.length}</p>
                </div>
                <div className="bg-white dark:bg-gray-900 p-4 rounded-3xl border border-gray-100 dark:border-gray-800 shadow-sm border-l-4 border-l-brand">
                    <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-1">On-Site</p>
                    <p className="text-2xl font-black text-brand leading-none">
                        {workforce.filter(a => a.is_on_site).length}
                    </p>
                </div>
                <div className="bg-white dark:bg-gray-900 p-4 rounded-3xl border border-gray-100 dark:border-gray-800 shadow-sm border-l-4 border-l-green-500">
                    <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-1">Uploaded</p>
                    <p className="text-2xl font-black text-green-500 leading-none">
                        {workforce.filter(a => a.has_result).length}
                    </p>
                </div>
                <div className="bg-white dark:bg-gray-900 p-4 rounded-3xl border border-gray-100 dark:border-gray-800 shadow-sm border-l-4 border-l-amber-500">
                    <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-1">Pending</p>
                    <p className="text-2xl font-black text-amber-500 leading-none">
                        {workforce.filter(a => a.is_on_site && !a.has_result).length}
                    </p>
                </div>
            </div>

            {/* Filter Panel */}
            <div className="bg-white dark:bg-gray-900 p-6 rounded-[2.5rem] border border-gray-100 dark:border-gray-800 shadow-xl space-y-6">
                <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-3">
                        <div className="bg-brand/10 p-2 rounded-xl">
                            <Filter className="w-5 h-5 text-brand" />
                        </div>
                        <div>
                            <h3 className="font-black text-gray-900 dark:text-white uppercase tracking-tight">Workforce Filters</h3>
                            <p className="text-[10px] text-gray-500 font-bold uppercase">Refine situational awareness</p>
                        </div>
                    </div>
                    <div className="flex items-center space-x-2">
                        <button
                            onClick={() => {
                                setSecurityAudit(!securityAudit);
                                console.log("Workforce Integrity Audit Active");
                            }}
                            className={`p-2 transition-all ${securityAudit ? 'text-brand bg-brand/10 rounded-xl shadow-inner' : 'text-gray-400 hover:text-brand'}`}
                            title="Workforce Integrity Audit"
                        >
                            <Shield className={`w-5 h-5 ${securityAudit ? 'animate-pulse' : ''}`} />
                        </button>
                        <button
                            onClick={() => {
                                setFilters({ state_id: '', lga_id: '', ward_id: '', pu_id: '', on_site: '', result_uploaded: '' });
                                setLgas([]); setWards([]); setPus([]);
                                fetchWorkforce();
                            }}
                            className="p-2 text-gray-400 hover:text-brand transition-colors"
                            title="Reset & Refresh"
                        >
                            <RefreshCw className={`w-5 h-5 ${isRefreshing ? 'animate-spin' : ''}`} />
                        </button>
                    </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    <div className="space-y-1.5">
                        <label className="text-[9px] font-black text-gray-400 uppercase tracking-widest ml-1">State</label>
                        <select
                            value={filters.state_id}
                            onChange={(e) => handleFilterChange('state_id', e.target.value)}
                            className="w-full px-4 py-3 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-950 text-[9px] font-bold uppercase outline-none focus:ring-2 focus:ring-brand"
                        >
                            <option value="">All States</option>
                            {states.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                        </select>
                    </div>

                    <div className="space-y-1.5">
                        <label className="text-[9px] font-black text-gray-400 uppercase tracking-widest ml-1">LGA</label>
                        <select
                            value={filters.lga_id}
                            onChange={(e) => handleFilterChange('lga_id', e.target.value)}
                            disabled={!filters.state_id}
                            className="w-full px-4 py-3 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-950 text-xs font-black uppercase outline-none focus:ring-2 focus:ring-brand disabled:opacity-50"
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
                            className="w-full px-4 py-3 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-950 text-xs font-black uppercase outline-none focus:ring-2 focus:ring-brand disabled:opacity-50"
                        >
                            <option value="">All Wards</option>
                            {wards.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
                        </select>
                    </div>

                    <div className="space-y-1.5">
                        <label className="text-[9px] font-black text-gray-400 uppercase tracking-widest ml-1">Polling Unit</label>
                        <select
                            value={filters.pu_id}
                            onChange={(e) => handleFilterChange('pu_id', e.target.value)}
                            disabled={!filters.ward_id}
                            className="w-full px-4 py-3 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-950 text-xs font-black uppercase outline-none focus:ring-2 focus:ring-brand disabled:opacity-50"
                        >
                            <option value="">All Units</option>
                            {pus.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                        </select>
                    </div>

                    <div className="space-y-1.5">
                        <label className="text-[9px] font-black text-gray-400 uppercase tracking-widest ml-1">Arrival Status</label>
                        <select
                            value={filters.on_site}
                            onChange={(e) => handleFilterChange('on_site', e.target.value)}
                            className="w-full px-4 py-3 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-950 text-[9px] font-bold uppercase outline-none focus:ring-2 focus:ring-brand border-l-4 border-l-brand"
                        >
                            <option value="">Any Status</option>
                            <option value="true">Arrived On-Site</option>
                            <option value="false">In Transit</option>
                        </select>
                    </div>

                    <div className="space-y-1.5">
                        <label className="text-[9px] font-black text-gray-400 uppercase tracking-widest ml-1">Data Submission</label>
                        <select
                            value={filters.result_uploaded}
                            onChange={(e) => handleFilterChange('result_uploaded', e.target.value)}
                            className="w-full px-4 py-3 rounded-xl border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-950 text-[9px] font-bold uppercase outline-none focus:ring-2 focus:ring-brand border-l-4 border-l-green-500"
                        >
                            <option value="">Any Result</option>
                            <option value="true">Result Uploaded</option>
                            <option value="false">Pending Upload</option>
                        </select>
                    </div>
                </div>
            </div>

            {/* Workforce Table */}
            <div className="bg-white dark:bg-gray-900 rounded-[2.5rem] border border-gray-100 dark:border-gray-800 shadow-xl overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse">
                        <thead>
                            <tr className="bg-gray-50/50 dark:bg-gray-950">
                                <th className="p-5 text-[10px] font-black text-gray-400 uppercase tracking-widest border-b border-gray-100 dark:border-gray-800">Agent Identifier</th>
                                <th className="p-5 text-[10px] font-black text-gray-400 uppercase tracking-widest border-b border-gray-100 dark:border-gray-800">Location Context</th>
                                <th className="p-5 text-[10px] font-black text-gray-400 uppercase tracking-widest border-b border-gray-100 dark:border-gray-800 text-center">On-Site</th>
                                <th className="p-5 text-[10px] font-black text-gray-400 uppercase tracking-widest border-b border-gray-100 dark:border-gray-800 text-center">Arrival GPS</th>
                                <th className="p-5 text-[10px] font-black text-gray-400 uppercase tracking-widest border-b border-gray-100 dark:border-gray-800 text-center">Submission GPS</th>
                                <th className="p-5 text-[10px] font-black text-gray-400 uppercase tracking-widest border-b border-gray-100 dark:border-gray-800 text-center">Result</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-50 dark:divide-gray-800">
                            {workforce.map((agent) => (
                                <tr key={agent.agent_id} className="hover:bg-gray-50/50 dark:hover:bg-gray-800/20 transition-colors group">
                                    <td className="p-5">
                                        <div className="flex items-center space-x-3">
                                            <div className="w-8 h-8 bg-gray-100 dark:bg-gray-800 rounded-lg flex items-center justify-center text-gray-400 group-hover:text-brand transition-colors">
                                                <Users className="w-4 h-4" />
                                            </div>
                                            <div>
                                                <p className="text-xs font-black text-gray-900 dark:text-white leading-none mb-1">{agent.email}</p>
                                                <p className="text-[9px] text-gray-400 font-bold uppercase">{agent.full_name}</p>
                                            </div>
                                        </div>
                                    </td>
                                    <td className="p-5">
                                        <div className="space-y-1">
                                            <div className="flex items-center space-x-1">
                                                <MapPin className="w-3 h-3 text-gray-400" />
                                                <span className="text-[10px] font-black text-gray-900 dark:text-white uppercase">{agent.pu_code}</span>
                                            </div>
                                            <p className="text-[9px] text-gray-500 font-bold uppercase tracking-wider">
                                                {agent.state} / {agent.lga} / {agent.ward}
                                            </p>
                                        </div>
                                    </td>
                                    <td className="p-5 text-center">
                                        {agent.is_on_site ? (
                                            <div className="inline-flex flex-col items-center">
                                                <div className="w-6 h-6 bg-green-50 dark:bg-green-900/20 rounded-full flex items-center justify-center mb-1">
                                                    <CheckCircle className="w-3.5 h-3.5 text-green-600" />
                                                </div>
                                                <span className="text-[8px] font-black text-green-600 uppercase tracking-tighter">Arrived</span>
                                            </div>
                                        ) : (
                                            <div className="inline-flex flex-col items-center opacity-30">
                                                <Clock className="w-5 h-5 text-gray-400 mb-1" />
                                                <span className="text-[8px] font-black text-gray-400 uppercase">Transit</span>
                                            </div>
                                        )}
                                    </td>
                                    <td className="p-5 text-center">
                                        {agent.is_on_site &&
                                            Number.isFinite(agent.check_in_lat) &&
                                            Number.isFinite(agent.check_in_lng) ? (
                                            <div className="inline-flex flex-col items-center">
                                                <p className="text-[10px] font-mono font-black text-gray-900 dark:text-white">
                                                    {Number(agent.check_in_lat).toFixed(6)}
                                                </p>
                                                <p className="text-[10px] font-mono font-black text-gray-900 dark:text-white">
                                                    {Number(agent.check_in_lng).toFixed(6)}
                                                </p>
                                                <span className="text-[7px] font-black text-gray-400 uppercase mt-1">Raw Telemetry</span>
                                            </div>
                                        ) : (
                                            <span className="text-[9px] text-gray-300 font-bold uppercase italic cursor-help" title="Awaiting field signal">No Signal</span>
                                        )}
                                    </td>
                                    <td className="p-5 text-center">
                                        {agent.has_result &&
                                            Number.isFinite(agent.submission_lat) &&
                                            Number.isFinite(agent.submission_lng) ? (
                                            <div className="inline-flex flex-col items-center">
                                                <p className="text-[10px] font-mono font-black text-brand dark:text-brand-light">
                                                    {Number(agent.submission_lat).toFixed(6)}
                                                </p>
                                                <p className="text-[10px] font-mono font-black text-brand dark:text-brand-light">
                                                    {Number(agent.submission_lng).toFixed(6)}
                                                </p>
                                                <span className="text-[7px] font-black text-gray-400 uppercase mt-1">Upload Location</span>
                                            </div>
                                        ) : (
                                            <span className="text-[9px] text-gray-300 font-bold uppercase italic cursor-help" title="Awaiting upload telemetry">No Result</span>
                                        )}
                                    </td>
                                    <td className="p-5 text-center">
                                        {agent.has_result ? (
                                            <div className="inline-flex flex-col items-center">
                                                <div className="w-6 h-6 bg-brand/10 rounded-full flex items-center justify-center mb-1">
                                                    <ImageIcon className="w-3.5 h-3.5 text-brand" />
                                                </div>
                                                <span className="text-[8px] font-black text-brand uppercase tracking-tighter">Uploaded</span>
                                            </div>
                                        ) : (
                                            <div className="inline-flex flex-col items-center opacity-30">
                                                <ImageIcon className="w-5 h-5 text-gray-400 mb-1" />
                                                <span className="text-[8px] font-black text-gray-400 uppercase tracking-tighter">Waiting</span>
                                            </div>
                                        )}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
};

export default WorkforceMonitor;


