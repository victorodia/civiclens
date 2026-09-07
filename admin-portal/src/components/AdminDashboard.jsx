import React, { useState, useEffect } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, PieChart, Pie } from 'recharts';
import { ShieldCheck, TrendingUp, Users, Map, Clock, AlertTriangle } from 'lucide-react';
import { motion } from 'framer-motion';
import { useNotification } from '../contexts/NotificationContext';

const AdminDashboard = ({ setActiveView }) => {
    const { showNotification } = useNotification();
    const [stats, setStats] = useState({
        total_votes: 0,
        party_a: 0,
        party_b: 0,
        party_c: 0,
        verified_percentage: 0,
        agents_provisioned: 0,
        flagged_count: 0
    });
    const [health, setHealth] = useState({
        reporting_states: 0,
        total_states: 36,
        status: 'OPERATIONAL',
        latency: '...'
    });
    const [partyConfig, setPartyConfig] = useState({
        party_a_name: 'Party A',
        party_b_name: 'Party B',
        party_c_name: 'Party C',
        election_name: 'General Election'
    });
    const [isLoading, setIsLoading] = useState(true);

    // Filtering State
    const [filters, setFilters] = useState({
        state: '',
        lga: '',
        ward: '',
        pu: ''
    });

    const [geoOptions, setGeoOptions] = useState({
        states: [],
        lgas: [],
        wards: [],
        pus: []
    });

    const fetchGeo = async (type, id = null) => {
        let url = `http://127.0.0.1:8001/admin/geo/${type}`;
        if (id) {
            if (type === 'lgas') url = `http://127.0.0.1:8001/admin/geo/states/${id}/lgas`;
            if (type === 'wards') url = `http://127.0.0.1:8001/admin/geo/lgas/${id}/wards`;
            if (type === 'pus') url = `http://127.0.0.1:8001/admin/geo/wards/${id}/pus`;
        }
        try {
            const res = await fetch(url);
            if (res.ok) return await res.json();
        } catch (e) {
            showNotification(`Failed to fetch ${type}. Network integrity check required.`, "error");
        }
        return [];
    };

    useEffect(() => {
        fetchGeo('states').then(data => setGeoOptions(prev => ({ ...prev, states: data })));
    }, []);

    const handleFilterChange = (key, value) => {
        setFilters(prev => {
            const next = { ...prev, [key]: value };
            if (key === 'state') return { ...next, lga: '', ward: '', pu: '' };
            if (key === 'lga') return { ...next, ward: '', pu: '' };
            if (key === 'ward') return { ...next, pu: '' };
            return next;
        });

        if (key === 'state') {
            if (value) {
                fetchGeo('lgas', value).then(data => setGeoOptions(prev => ({ ...prev, lgas: data, wards: [], pus: [] })));
            } else {
                setGeoOptions(prev => ({ ...prev, lgas: [], wards: [], pus: [] }));
            }
        }
        if (key === 'lga') {
            if (value) {
                fetchGeo('wards', value).then(data => setGeoOptions(prev => ({ ...prev, wards: data, pus: [] })));
            } else {
                setGeoOptions(prev => ({ ...prev, wards: [], pus: [] }));
            }
        }
        if (key === 'ward') {
            if (value) {
                fetchGeo('pus', value).then(data => setGeoOptions(prev => ({ ...prev, pus: data })));
            } else {
                setGeoOptions(prev => ({ ...prev, pus: [] }));
            }
        }
    };

    const fetchStats = async () => {
        try {
            const query = new URLSearchParams();
            if (filters.state) query.append('state_id', filters.state);
            if (filters.lga) query.append('lga_id', filters.lga);
            if (filters.ward) query.append('ward_id', filters.ward);
            if (filters.pu) query.append('pu_id', filters.pu);

            const response = await fetch(`http://127.0.0.1:8001/admin/stats/collation?${query.toString()}`);
            if (response.ok) {
                const data = await response.json();
                setStats(data);
            }
        } catch (error) {
            showNotification("Dashboard Sync Failed. Retrying in background...", "warning");
        } finally {
            setIsLoading(false);
        }
    };

    const fetchHealth = async () => {
        try {
            const res = await fetch('http://127.0.0.1:8001/admin/health');
            if (res.ok) setHealth(await res.json());
        } catch (e) { console.error(e); }
    };

    useEffect(() => {
        const fetchPartyConfig = async () => {
            try {
                const response = await fetch('http://127.0.0.1:8001/admin/election-config');
                if (response.ok) {
                    const data = await response.json();
                    setPartyConfig(data);
                }
            } catch (error) {
                console.error("Config fetch failed:", error);
            }
        };

        fetchPartyConfig();
    }, []);

    useEffect(() => {
        fetchStats();
        fetchHealth();
        const interval = setInterval(() => {
            fetchStats();
            fetchHealth();
        }, 30000);
        return () => clearInterval(interval);
    }, [filters]);

    const chartData = [
        { name: partyConfig.party_a_name, votes: stats.party_a, color: '#0D9488' },
        { name: partyConfig.party_b_name, votes: stats.party_b, color: '#115E59' },
        { name: partyConfig.party_c_name, votes: stats.party_c, color: '#0F766E' },
    ];

    const COLORS = ['#0D9488', '#115E59', '#334155'];

    return (
        <div className="space-y-6 animate-in fade-in duration-700">
            {/* Hierarchy Filter Bar */}
            <div className="bg-white dark:bg-gray-900 p-4 rounded-2xl border border-gray-100 dark:border-gray-800 shadow-sm flex flex-wrap gap-4 items-center">
                <div className="flex items-center space-x-2 text-brand">
                    <Map className="w-5 h-5" />
                    <span className="text-xs font-black uppercase tracking-widest text-gray-400">Filters</span>
                </div>

                <select
                    value={filters.state}
                    onChange={e => handleFilterChange('state', e.target.value)}
                    className="bg-gray-50 dark:bg-gray-800 border-none rounded-xl text-xs font-bold p-2 focus:ring-2 focus:ring-brand"
                >
                    <option value="">All States</option>
                    {geoOptions.states?.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>

                <select
                    value={filters.lga}
                    onChange={e => handleFilterChange('lga', e.target.value)}
                    className="bg-gray-50 dark:bg-gray-800 border-none rounded-xl text-xs font-bold p-2 focus:ring-2 focus:ring-brand disabled:opacity-50"
                    disabled={!filters.state}
                >
                    <option value="">All LGAs</option>
                    {geoOptions.lgas?.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
                </select>

                <select
                    value={filters.ward}
                    onChange={e => handleFilterChange('ward', e.target.value)}
                    className="bg-gray-50 dark:bg-gray-800 border-none rounded-xl text-xs font-bold p-2 focus:ring-2 focus:ring-brand disabled:opacity-50"
                    disabled={!filters.lga}
                >
                    <option value="">All Wards</option>
                    {geoOptions.wards?.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
                </select>

                <select
                    value={filters.pu}
                    onChange={e => handleFilterChange('pu', e.target.value)}
                    className="bg-gray-50 dark:bg-gray-800 border-none rounded-xl text-xs font-bold p-2 focus:ring-2 focus:ring-brand disabled:opacity-50"
                    disabled={!filters.ward}
                >
                    <option value="">All PUs</option>
                    {geoOptions.pus?.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>

                <button
                    onClick={() => {
                        setFilters({ state: '', lga: '', ward: '', pu: '' });
                        setGeoOptions(prev => ({ ...prev, lgas: [], wards: [], pus: [] }));
                    }}
                    className="ml-auto text-[10px] uppercase font-black text-gray-400 hover:text-brand transition-colors"
                >
                    Clear All
                </button>
            </div>
            {/* Top Stats Grid */}
            <div className="grid grid-cols-2 gap-4">
                <motion.div
                    whileHover={{ y: -5 }}
                    className="bg-brand text-white p-4 rounded-2xl shadow-lg flex flex-col justify-between"
                >
                    <TrendingUp className="w-5 h-5 opacity-70" />
                    <div className="mt-4">
                        <p className="text-2xl font-black">{stats.total_votes.toLocaleString()}</p>
                        <p className="text-[10px] uppercase tracking-tighter opacity-80 font-bold">Total Votes Collated</p>
                    </div>
                </motion.div>

                <motion.div
                    whileHover={{ y: -5 }}
                    className="bg-slate-800 text-white p-4 rounded-2xl shadow-lg flex flex-col justify-between"
                >
                    <ShieldCheck className="w-5 h-5 text-brand" />
                    <div className="mt-4">
                        <p className="text-2xl font-black">{stats.verified_percentage}%</p>
                        <p className="text-[10px] uppercase tracking-tighter opacity-80 font-bold">Integrity Verified</p>
                    </div>
                </motion.div>

                <motion.div
                    whileHover={{ y: -5 }}
                    className="bg-white dark:bg-gray-900 p-4 rounded-2xl shadow-lg border border-gray-100 dark:border-gray-800 flex flex-col justify-between"
                >
                    <Users className="w-5 h-5 text-brand" />
                    <div className="mt-4">
                        <p className="text-2xl font-black text-gray-900 dark:text-white">
                            {stats.agents_provisioned?.toLocaleString() || 0}
                        </p>
                        <p className="text-[10px] uppercase tracking-tighter text-gray-500 font-bold">Agents Provisioned</p>
                    </div>
                </motion.div>
            </div>

            {/* Main Live Chart */}
            <div className="bg-white dark:bg-gray-900 p-6 rounded-2xl border border-gray-100 dark:border-gray-800 shadow-xl">
                <div className="flex justify-between items-center mb-6">
                    <h3 className="font-bold text-gray-800 dark:text-white flex items-center space-x-2">
                        <TrendingUp className="w-4 h-4 text-brand" />
                        <span>Live Rolling Tally</span>
                    </h3>
                    <span className="text-[10px] bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400 px-2 py-1 rounded-full font-black animate-pulse">LIVE</span>
                </div>

                <div className="h-48 w-full">
                    <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={chartData}>
                            <XAxis dataKey="name" hide />
                            <Tooltip
                                contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 15px -3px rgba(0,0,0,0.1)' }}
                            />
                            <Bar dataKey="votes" radius={[8, 8, 0, 0]}>
                                {chartData.map((entry, index) => (
                                    <Cell key={`cell-${index}`} fill={entry.color} />
                                ))}
                            </Bar>
                        </BarChart>
                    </ResponsiveContainer>
                </div>

                <div className="mt-4 grid grid-cols-3 gap-2">
                    {chartData.map((party) => (
                        <div key={party.name} className="text-center">
                            <p className="text-[10px] font-bold text-gray-400 uppercase">{party.name}</p>
                            <p className="text-sm font-black text-slate-800 dark:text-gray-100">
                                {party.votes?.toLocaleString() || 0}
                            </p>
                            <p className="text-[9px] font-bold text-brand bg-brand/5 dark:bg-brand/10 px-2 py-0.5 rounded-full inline-block mt-1">
                                {stats.total_votes > 0 ? (party.votes / stats.total_votes * 100).toFixed(1) : "0.0"}%
                            </p>
                        </div>
                    ))}
                </div>
            </div>

            {/* Verification Feed Access */}
            <div
                onClick={() => setActiveView?.('verify')}
                className="bg-slate-50 dark:bg-gray-950 p-4 rounded-2xl border border-gray-200 dark:border-gray-800 flex items-center justify-between group cursor-pointer hover:border-brand transition-all shadow-sm active:scale-[0.99]"
            >
                <div className="flex items-center space-x-3">
                    <div className="bg-white dark:bg-gray-900 p-2 rounded-xl shadow-sm">
                        <Clock className="w-5 h-5 text-brand" />
                    </div>
                    <div>
                        <p className="text-xs font-bold text-gray-900 dark:text-white uppercase tracking-tight">Pending Human Review</p>
                        <p className="text-[10px] text-gray-500 font-bold">
                            {stats.flagged_count || 0} results flagged by AI
                        </p>
                    </div>
                </div>
                <div className="flex items-center space-x-2">
                    {stats.flagged_count > 0 && (
                        <div className="w-2 h-2 bg-amber-500 rounded-full animate-ping"></div>
                    )}
                    <AlertTriangle className="w-5 h-5 text-amber-500 group-hover:scale-110 transition-transform" />
                </div>
            </div>

            {/* Network Health */}
            <div className="flex items-center justify-between px-2">
                <div className="flex flex-col">
                    <p className="text-[10px] font-black text-gray-400 uppercase tracking-widest flex items-center space-x-1">
                        <Map className="w-3 h-3 text-brand" />
                        <span>Nodes: {health.reporting_states}/{health.total_states} States Reporting</span>
                    </p>
                    <p className="text-[8px] font-bold text-brand uppercase mt-0.5 tracking-tighter">System Status: {health.status} ({health.latency})</p>
                </div>
                <div className="ml-auto flex space-x-1">
                    {[1, 2, 3, 4, 5].map(i => (
                        <motion.div
                            key={i}
                            animate={{ opacity: [0.3, 1, 0.3] }}
                            transition={{ duration: 2, repeat: Infinity, delay: i * 0.2 }}
                            className="w-1.5 h-4 bg-brand rounded-full"
                        ></motion.div>
                    ))}
                </div>
            </div>
        </div>
    );
};

export default AdminDashboard;


