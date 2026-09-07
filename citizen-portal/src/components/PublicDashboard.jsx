import React, { useState } from 'react';
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

    useEffect(() => {
        const fetchData = async () => {
            try {
                // Fetch stats (using the same admin endpoint for now as it's public-safe summary data)
                const statsRes = await fetch('http://127.0.0.1:8001/admin/stats/collation');
                if (statsRes.ok) {
                    const statsData = await statsRes.json();
                    setStats({
                        ...statsData,
                        update_timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                    });
                }

                // Fetch party names
                const configRes = await fetch('http://127.0.0.1:8001/admin/election-config');
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
    }, []);

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


