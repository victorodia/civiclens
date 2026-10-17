import React, { createContext, useContext, useState, useCallback } from 'react';

const NotificationContext = createContext();

export const useNotification = () => useContext(NotificationContext);

export const NotificationProvider = ({ children }) => {
    const [notification, setNotification] = useState(null);
    const [dialog, setDialog] = useState(null);

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

    const showDialog = useCallback((options) => {
        return new Promise((resolve) => {
            setDialog({ ...options, resolve });
        });
    }, []);

    const closeDialog = useCallback((value = null) => {
        if (dialog?.resolve) {
            dialog.resolve(value);
        }
        setDialog(null);
    }, [dialog]);

    return (
        <NotificationContext.Provider value={{
            notification, showNotification, dismissNotification,
            dialog, showDialog, closeDialog
        }}>
            {children}
        </NotificationContext.Provider>
    );
};
