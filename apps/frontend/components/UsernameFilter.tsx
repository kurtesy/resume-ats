"use client";

import { useState, useEffect } from "react";
import { setApiUsername } from "@/lib/api/client";

export default function UsernameFilter() {
    const [username, setUsername] = useState("");

    useEffect(() => {
        // On component mount, load the username from local storage
        const savedUsername = localStorage.getItem("username");
        if (savedUsername) {
            setUsername(savedUsername);
            setApiUsername(savedUsername);
        }
    }, []);

    const handleUsernameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const newUsername = e.target.value;
        setUsername(newUsername);
    };

    const handleApplyUsername = () => {
        // Basic sanitization to prevent invalid characters
        const safeUsername = username.replace(/[^a-zA-Z0-9_-]/g, "");
        localStorage.setItem("username", safeUsername);
        setApiUsername(safeUsername);
        // Reload the page to refetch all data for the new user context
        window.location.reload();
    };

    return (
        <div className="p-4 border-b border-gray-200 bg-white flex items-center gap-2">
            <label htmlFor="username-filter" className="font-medium text-sm">
                Username:
            </label>
            <input
                id="username-filter"
                type="text"
                value={username}
                onChange={handleUsernameChange}
                placeholder="Enter username to filter data"
                className="border border-gray-300 rounded px-2 py-1 text-sm flex-grow"
            />
            <button onClick={handleApplyUsername} className="bg-blue-600 text-white px-4 py-1 rounded text-sm hover:bg-blue-700">
                Apply
            </button>
        </div>
    );
}