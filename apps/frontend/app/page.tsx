import UsernameFilter from '@/components/UsernameFilter';
import Link from 'next/link';

export default function DashboardPage() {

  const buttonClass =
    'group relative border border-black bg-transparent px-8 py-3 font-mono text-sm font-bold uppercase text-black transition-all duration-150 ease-in-out hover:bg-black hover:text-white cursor-pointer';

  return (
    <main className="min-h-screen bg-gray-50">
      <header>
        <UsernameFilter />
      </header>
      <div className="p-8">
        <h1 className="text-2xl font-bold mb-4">Dashboard</h1>
        <div className="flex flex-col gap-4 md:flex-row md:gap-12">
          <Link href="/dashboard" className={buttonClass}>
            {'home.launchApp'}
          </Link>
          <Link href="/tailor" className={buttonClass}>
            Tailor Resume
          </Link>
          <a
            href="https://resumematcher.fyi"
            target="_blank"
            rel="noopener noreferrer"
            className={buttonClass}
          >
            {'home.docs'}
          </a>
        </div>
      </div>
    </main>
  );
}
