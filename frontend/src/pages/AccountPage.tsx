
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/useAuth";

export default function AccountPage() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();

  function handleLogout() {
    signOut();
    navigate("/", { replace: true });
  }

  return (
    <main className="mx-auto max-w-[800px] px-5 py-12">
      <h1 className="mb-8 text-3xl font-bold">My Account</h1>

      <div className="space-y-4 border border-neutral-200 p-6">
        <p>
          <strong>Username:</strong> {user?.username}
        </p>

        <p>
          <strong>Email:</strong> {user?.email}
        </p>

        <Link to="/orders" className="block text-violet-800 underline">
          View my orders
        </Link>

        <button
          type="button"
          onClick={handleLogout}
          className="bg-violet-900 px-6 py-3 font-medium text-white"
        >
          Logout
        </button>
      </div>
    </main>
  );
}
