import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { FileText, Maximize2, X, AlertCircle, Copy, Search, Download } from 'lucide-react';
import { useNotification } from '../contexts/NotificationContext';

const ResultsFeed = () => {
    const [documents, setDocuments] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [isLoadingMore, setIsLoadingMore] = useState(false);
    const [fullImageOpen, setFullImageOpen] = useState(false);
    const [currentImage, setCurrentImage] = useState(null);
    const { showNotification } = useNotification();
    
    // New Advanced Filters State
    const [searchQuery, setSearchQuery] = useState('');
    const [startDate, setStartDate] = useState('');
    const [endDate, setEndDate] = useState('');
    const [page, setPage] = useState(0);
    const [hasMore, setHasMore] = useState(true);
    const limit = 50;

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
    }, [searchQuery, startDate, endDate, showNotification]);

    const [proofModalDoc, setProofModalDoc] = useState(null);

    const handleCopy = (text, type) => {
        navigator.clipboard.writeText(text);
        showNotification(`${type} copied to clipboard!`, "success");
    };

    const [filterState, setFilterState] = useState('');
    const [filterLGA, setFilterLGA] = useState('');
    const [filterWard, setFilterWard] = useState('');
    const [filterPU, setFilterPU] = useState('');

    const uniqueStates = [...new Set(documents.map(d => d.state).filter(Boolean))].sort();
    const uniqueLGAs = filterState ? [...new Set(documents.filter(d => d.state === filterState).map(d => d.lga).filter(Boolean))].sort() : [];
    const uniqueWards = filterLGA ? [...new Set(documents.filter(d => d.lga === filterLGA).map(d => d.ward).filter(Boolean))].sort() : [];
    const uniquePUs = filterWard ? [...new Set(documents.filter(d => d.ward === filterWard).map(d => d.pu_code).filter(Boolean))].sort() : [];

    const filteredDocuments = documents.filter(doc => {
        if (filterState && doc.state !== filterState) return false;
        if (filterLGA && doc.lga !== filterLGA) return false;
        if (filterWard && doc.ward !== filterWard) return false;
        if (filterPU && doc.pu_code !== filterPU) return false;
        return true;
    });

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
        if (filteredDocuments.length === 0) {
            showNotification("No data to export", "error");
            return;
        }

        const headers = ["State", "LGA", "Ward", "PU Code", "PU Name", "Party A", "Party B", "Party C", "Uploaded At", "Blockchain Hash", "Transaction ID"];
        const rows = filteredDocuments.map(doc => [
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
            </AnimatePresence>

            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <h3 className="font-bold flex items-center space-x-2 text-gray-900 dark:text-white">
                    <FileText className="w-5 h-5 text-brand" />
                    <span>Uploaded Documents Feed</span>
                </h3>
                <span className="text-[10px] font-black bg-gray-100 dark:bg-gray-800 px-3 py-1 rounded-full whitespace-nowrap">{filteredDocuments.length} Results Filtered</span>
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

                <div className="grid grid-cols-1 md:grid-cols-4 gap-4 border-t border-gray-100 dark:border-gray-800 pt-4">
                    <div>
                        <label className="block text-xs font-bold text-gray-500 mb-1">State</label>
                        <select 
                            className="w-full bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 text-sm rounded-lg focus:ring-brand focus:border-brand p-2"
                            value={filterState}
                            onChange={(e) => { setFilterState(e.target.value); setFilterLGA(''); setFilterWard(''); setFilterPU(''); }}
                        >
                            <option value="">All States</option>
                            {uniqueStates.map(s => <option key={s} value={s}>{s}</option>)}
                        </select>
                    </div>
                    <div>
                        <label className="block text-xs font-bold text-gray-500 mb-1">Local Government</label>
                        <select 
                            className="w-full bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 text-sm rounded-lg focus:ring-brand focus:border-brand p-2 disabled:opacity-50 disabled:cursor-not-allowed"
                            value={filterLGA}
                            onChange={(e) => { setFilterLGA(e.target.value); setFilterWard(''); setFilterPU(''); }}
                            disabled={!filterState}
                        >
                            <option value="">{filterState ? "All LGAs" : "Select State First"}</option>
                            {uniqueLGAs.map(l => <option key={l} value={l}>{l}</option>)}
                        </select>
                    </div>
                    <div>
                        <label className="block text-xs font-bold text-gray-500 mb-1">Ward</label>
                        <select 
                            className="w-full bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 text-sm rounded-lg focus:ring-brand focus:border-brand p-2 disabled:opacity-50 disabled:cursor-not-allowed"
                            value={filterWard}
                            onChange={(e) => { setFilterWard(e.target.value); setFilterPU(''); }}
                            disabled={!filterLGA}
                        >
                            <option value="">{filterLGA ? "All Wards" : "Select LGA First"}</option>
                            {uniqueWards.map(w => <option key={w} value={w}>{w}</option>)}
                        </select>
                    </div>
                    <div>
                        <label className="block text-xs font-bold text-gray-500 mb-1">Polling Unit</label>
                        <select 
                            className="w-full bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 text-sm rounded-lg focus:ring-brand focus:border-brand p-2 disabled:opacity-50 disabled:cursor-not-allowed"
                            value={filterPU}
                            onChange={(e) => setFilterPU(e.target.value)}
                            disabled={!filterWard}
                        >
                            <option value="">{filterWard ? "All Polling Units" : "Select Ward First"}</option>
                            {uniquePUs.map(p => <option key={p} value={p}>{p}</option>)}
                        </select>
                    </div>
                </div>
            </div>

            {isLoading && page === 0 ? (
                <div className="flex justify-center p-12">
                    <div className="w-8 h-8 border-4 border-brand border-t-transparent rounded-full animate-spin"></div>
                </div>
            ) : filteredDocuments.length === 0 ? (
                <div className="bg-white dark:bg-gray-950 p-12 rounded-2xl border border-gray-100 dark:border-gray-800 text-center shadow-xl">
                    <AlertCircle className="w-12 h-12 text-gray-400 mx-auto mb-4 opacity-50" />
                    <h3 className="font-black text-gray-400 uppercase tracking-widest text-sm">No Documents Found</h3>
                </div>
            ) : (
                <>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {filteredDocuments.map((doc) => (
                            <div key={doc.id} className="bg-white dark:bg-gray-950 rounded-2xl shadow-xl border border-gray-100 dark:border-gray-800 overflow-hidden">
                                <div className="p-4 border-b border-gray-50 dark:border-gray-800">
                                    <div className="flex justify-between items-center mb-1">
                                        <span className="text-xs font-black uppercase tracking-widest text-brand" title={doc.pu_name}>{doc.pu_code}</span>
                                        <span className="text-[10px] text-gray-400 font-bold">{new Date(doc.uploaded_at).toLocaleString()}</span>
                                    </div>
                                    <div className="text-[9px] text-gray-500 font-medium truncate uppercase">
                                        {doc.state} • {doc.lga} • {doc.ward}
                                    </div>
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
