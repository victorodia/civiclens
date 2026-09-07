import React, { createContext, useContext, useState, useCallback } from 'react';

const NotificationContext = createContext();

export const useNotification = () => useContext(NotificationContext);

export const NotificationProvider = ({ children }) => {
    const [notification, setNotification] = useState(null);

    const showNotification = useCallback((message, type = 'info') => {
        setNotification({ message, type });
        // Auto-dismiss after 5 seconds
        setTimeout(() => {
            setNotification(null);
        }, 5000);
    }, []);

    const dismissNotification = useCallback(() => {
        setNotification(null);
    }, []);

    return (
        <NotificationContext.Provider value={{ notification, showNotification, dismissNotification }}>
            {children}
        </NotificationContext.Provider>
    );
};
