import UsernameFilter from "@/components/UsernameFilter";

export default function DashboardPage() {
    return (
        <main className="min-h-screen bg-gray-50">
            <header>
                <UsernameFilter />
            </header>
            <div className="p-8">
                <h1 className="text-2xl font-bold mb-4">Dashboard</h1>
                <div className="bg-white p-6 border border-gray-200 rounded">
                    <p>Your content for the selected user will appear here.</p>
                    {/* You would fetch and display user-specific data below */}
                </div>
            </div>
        </main>
    );
}