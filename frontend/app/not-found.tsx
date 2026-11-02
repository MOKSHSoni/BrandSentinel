import Link from "next/link";

export default function NotFound() {
  return (
    <div className="py-16 text-center">
      <h1 className="text-2xl font-semibold text-slate-900">Page not found</h1>
      <p className="mt-2 text-sm text-slate-500">That address does not exist in BrandSentinel.</p>
      <Link href="/" className="mt-4 inline-block text-sm font-medium text-indigo-700 hover:underline">← Back to drafts</Link>
    </div>
  );
}
