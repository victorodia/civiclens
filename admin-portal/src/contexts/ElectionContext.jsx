import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';

const ElectionContext = createContext(null);

export function ElectionProvider({ children }) {
    const [elections, setElections] = useState([]);
    const [activeElectionId, setActiveElectionId] = useState(() =>
        localStorage.getItem('adminActiveElection') || '');

    const refresh = useCallback(async () => {
        try {
            const res = await fetch('/admin/elections');
            if (!res.ok) return;
            const data = await res.json();
            setElections(data.elections || []);
        } catch (e) { /* offline — keep stale list */ }
    }, []);

    useEffect(() => {
        refresh();
        const t = setInterval(refresh, 60000);
        return () => clearInterval(t);
    }, [refresh]);

    const setActiveElection = (id) => {
        const v = id || '';
        localStorage.setItem('adminActiveElection', v);
        setActiveElectionId(v);
    };

    const activeElection = elections.find(e => e.id === activeElectionId) || null;

    return (
        <ElectionContext.Provider value={{ elections, activeElectionId, activeElection, setActiveElection, refresh }}>
            {children}
        </ElectionContext.Provider>
    );
}

export function useElection() {
    return useContext(ElectionContext);
}
