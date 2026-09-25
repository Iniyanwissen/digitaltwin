import { Link } from "react-router";

export function NotFound() {
  return (
    <div className="text-sm text-slate-600">
      Page not found.{" "}
      <Link to="/" className="text-brand-600 underline">
        Back to Overview
      </Link>
    </div>
  );
}
