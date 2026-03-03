let currentUsername: string | null = null;

/**
 * Sets the username for all subsequent API requests.
 * This should be called from the UI when the app initializes or when the user changes.
 * @param username The username to use for API requests.
 */
export function setApiUsername(username: string | null) {
    currentUsername = username;
}

/**
 * A wrapper around fetch to automatically add the API prefix and necessary headers.
 * @param url The URL path for the API endpoint (e.g., '/resumes/list').
 * @param options The standard RequestInit options for fetch.
 * @returns A Promise that resolves to the Response object.
 */
async function fetchWithAuth(url: string, options: RequestInit = {}): Promise<Response> {
    const headers = new Headers(options.headers || {});

    if (currentUsername) {
        headers.set('X-Username', currentUsername);
    } else {
        console.warn('X-Username header is not set. API calls may fail in multi-user mode.');
    }

    // Ensure Content-Type is set for POST/PUT requests if a body is present
    if (options.body && !headers.has('Content-Type')) {
        headers.set('Content-Type', 'application/json');
    }

    const apiPrefix = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

    const response = await fetch(`${apiPrefix}${url}`, {
        ...options,
        headers,
    });

    if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(errorData.detail || 'An API error occurred');
    }

    return response;
}

// Example of how you would use it to fetch resumes
export async function listResumes() {
    const response = await fetchWithAuth('/resumes/list');
    return response.json();
}

// You would create similar functions for all other API endpoints,
// ensuring they all use `fetchWithAuth`.