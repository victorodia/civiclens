import React, { useState, useEffect } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { ShieldCheck, TrendingUp, Map, Info } from 'lucide-react';
import { motion } from 'framer-motion';

const PublicDashboard = () => {
    const [stats, setStats] = useState({
        total_votes: 0,
        party_a: 0,
        party_b: 0,
        party_c: 0,
        update_timestamp: "Syncing..."
    });
    const [partyConfig, setPartyConfig] = useState({
        party_a_name: 'Party A',
        party_b_name: 'Party B',
        party_c_name: 'Party C',
        election_name: 'General Election'
    });
    const [isLoading, setIsLoading] = useState(true);

    const [filters, setFilters] = useState({ state: '', lga: '', ward: '', pu: '' });
    const [geoOptions, setGeoOptions] = useState({ states: [], lgas: [], wards: [], pus: [] });

    const fetchGeo = async (type, id = null) => {
        let url = `/admin/geo/${type}`;
        if (id) {
            if (type === 'lgas') url = `/admin/geo/states/${id}/lgas`;
            if (type === 'wards') url = `/admin/geo/lgas/${id}/wards`;
            if (type === 'pus') url = `/admin/geo/wards/${id}/pus`;
        }
        try {
            const res = await fetch(url);
            if (res.ok) return await res.json();
        } catch (e) {
            console.error(`Failed to fetch ${type}`, e);
        }
        return [];
    };

    useEffect(() => {
        fetchGeo('states').then(data => setGeoOptions(prev => ({ ...prev, states: data })));
    }, [filters]);

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


    useEffect(() => {
        const fetchData = async () => {
            try {
                // Fetch stats
                const query = new URLSearchParams();
                if (filters.state) query.append('state_id', filters.state);
                if (filters.lga) query.append('lga_id', filters.lga);
                if (filters.ward) query.append('ward_id', filters.ward);
                if (filters.pu) query.append('pu_id', filters.pu);
                const statsRes = await fetch(`/admin/stats/collation?${query.toString()}`);
                if (statsRes.ok) {
                    const statsData = await statsRes.json();
                    setStats({
                        ...statsData,
                        update_timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                    });
                }

                // Fetch party names
                const configRes = await fetch('/admin/election-config');
                if (configRes.ok) {
                    const configData = await configRes.json();
                    setPartyConfig(configData);
                }
            } catch (error) {
                console.error("Public Dashboard Sync Failed:", error);
            } finally {
                setIsLoading(false);
            }
        };

        fetchData();
        const interval = setInterval(fetchData, 60000); // 60s refresh for public
        return () => clearInterval(interval);
    }, [filters]);

    const chartData = [
        { name: partyConfig.party_a_name, votes: stats.party_a, color: '#0D9488' },
        { name: partyConfig.party_b_name, votes: stats.party_b, color: '#115E59' },
        { name: partyConfig.party_c_name, votes: stats.party_c, color: '#334155' },
    ];

    return (
        <div className="space-y-6 animate-in fade-in duration-700">

            {/* Live Indicator Section */}
            <div className="bg-brand-light dark:bg-brand-dark/20 p-4 rounded-2xl border border-brand/20 flex items-center justify-between">
                <div className="flex items-center space-x-3">
                    <div className="w-3 h-3 bg-red-500 rounded-full animate-ping"></div>
                    <p className="text-[10px] font-black uppercase text-brand tracking-widest">Live Transparency Feed</p>
                </div>
                <div className="flex items-center space-x-1">
                    <ShieldCheck className="w-4 h-4 text-brand" />
                    <span className="text-[10px] font-bold text-gray-500 uppercase">Verified Results Only</span>
                </div>
            </div>

            
            {/* Hierarchy Filter Bar */}
            <div className="bg-white dark:bg-gray-900 p-4 rounded-3xl border border-gray-100 dark:border-gray-800 shadow-sm flex flex-col gap-3">
                <div className="flex items-center space-x-2 text-brand mb-1">
                    <Map className="w-4 h-4" />
                    <span className="text-[10px] font-black uppercase tracking-widest text-gray-400">Filter By Location</span>
                </div>
                
                <div className="grid grid-cols-2 gap-3">
                    <select
                        value={filters.state}
                        onChange={e => handleFilterChange('state', e.target.value)}
                        className="w-full bg-gray-50 dark:bg-gray-800 border-none rounded-xl text-xs font-bold p-2.5 focus:ring-2 focus:ring-brand"
                    >
                        <option value="">All States</option>
                        {geoOptions.states?.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                    </select>

                    <select
                        value={filters.lga}
                        onChange={e => handleFilterChange('lga', e.target.value)}
                        className="w-full bg-gray-50 dark:bg-gray-800 border-none rounded-xl text-xs font-bold p-2.5 focus:ring-2 focus:ring-brand disabled:opacity-50"
                        disabled={!filters.state}
                    >
                        <option value="">All LGAs</option>
                        {geoOptions.lgas?.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
                    </select>

                    <select
                        value={filters.ward}
                        onChange={e => handleFilterChange('ward', e.target.value)}
                        className="w-full bg-gray-50 dark:bg-gray-800 border-none rounded-xl text-xs font-bold p-2.5 focus:ring-2 focus:ring-brand disabled:opacity-50"
                        disabled={!filters.lga}
                    >
                        <option value="">All Wards</option>
                        {geoOptions.wards?.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
                    </select>

                    <select
                        value={filters.pu}
                        onChange={e => handleFilterChange('pu', e.target.value)}
                        className="w-full bg-gray-50 dark:bg-gray-800 border-none rounded-xl text-xs font-bold p-2.5 focus:ring-2 focus:ring-brand disabled:opacity-50"
                        disabled={!filters.ward}
                    >
                        <option value="">All PUs</option>
                        {geoOptions.pus?.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                    </select>
                </div>
                {filters.state && (
                    <button
                        onClick={() => {
                            setFilters({ state: '', lga: '', ward: '', pu: '' });
                            setGeoOptions(prev => ({ ...prev, lgas: [], wards: [], pus: [] }));
                        }}
                        className="text-[9px] uppercase font-black text-gray-400 hover:text-brand transition-colors text-right mt-1"
                    >
                        Clear Filters
                    </button>
                )}
            </div>

            {/* Main Stats */}
            <div className="grid grid-cols-1 gap-4">
                <motion.div
                    whileHover={{ y: -2 }}
                    className="bg-white dark:bg-gray-900 p-6 rounded-3xl shadow-sm border border-gray-100 dark:border-gray-800"
                >
                    <div className="flex items-center justify-between mb-4">
                        <p className="text-[10px] font-black uppercase text-gray-400 tracking-widest">Total Verified Votes</p>
                        <TrendingUp className="w-4 h-4 text-brand" />
                    </div>
                    <p className="text-4xl font-black text-gray-900 dark:text-white">{stats.total_votes.toLocaleString()}</p>
                    <div className="mt-4 flex items-center space-x-2">
                        <div className="h-1.5 flex-1 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
                            <div className="h-full bg-brand w-[88%]"></div>
                        </div>
                        <span className="text-[10px] font-bold text-gray-400">88% Reporting</span>
                    </div>
                </motion.div>
            </div>

            {/* Graphical Tally */}
            <div className="bg-white dark:bg-gray-900 p-6 rounded-3xl shadow-sm border border-gray-100 dark:border-gray-800">
                <h3 className="text-xs font-black text-gray-900 dark:text-white uppercase tracking-widest mb-6">Verified Rolling Tally</h3>

                <div className="h-56 w-full">
                    <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={chartData} layout="vertical">
                            <XAxis type="number" hide />
                            <YAxis dataKey="name" type="category" hide />
                            <Tooltip
                                cursor={{ fill: 'transparent' }}
                                contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 15px -3px rgba(0,0,0,0.1)' }}
                            />
                            <Bar dataKey="votes" radius={[0, 10, 10, 0]} barSize={32}>
                                {chartData.map((entry, index) => (
                                    <Cell key={`cell-${index}`} fill={entry.color} />
                                ))}
                            </Bar>
                        </BarChart>
                    </ResponsiveContainer>
                </div>

                <div className="space-y-4 mt-6">
                    {chartData.map((party) => (
                        <div key={party.name} className="flex items-center justify-between">
                            <div className="flex items-center space-x-2">
                                <div className="w-2 h-2 rounded-full" style={{ backgroundColor: party.color }}></div>
                                <span className="text-xs font-bold text-gray-900 dark:text-gray-200">{party.name}</span>
                            </div>
                            <div className="text-right">
                                <p className="text-xs font-black dark:text-white">{party.votes.toLocaleString()}</p>
                                <p className="text-[8px] font-bold text-gray-400 uppercase">{(party.votes / stats.total_votes * 100).toFixed(1)}%</p>
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            {/* Info Footer */}
            <div className="flex items-center justify-between px-2 text-gray-400">
                <div className="flex items-center space-x-1">
                    <Map className="w-3 h-3" />
                    <span className="text-[10px] font-bold uppercase tracking-widest">36/36 States</span>
                </div>
                <div className="flex items-center space-x-1">
                    <Info className="w-3 h-3" />
                    <span className="text-[10px] font-bold uppercase tracking-widest">Updated {stats.update_timestamp}</span>
                </div>
            </div>

        </div>
    );
};

export default PublicDashboard;


