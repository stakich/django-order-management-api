import { useState, type SubmitEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/useAuth";

export default function LoginPage() {
  const navigate = useNavigate();
  const { state } = useLocation();

  const { signIn } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setLoading(true);

    try {
      await signIn(username, password);
      const from: unknown = state?.from;
      const canReturn =
        typeof from === "string" &&
        /^\/(?:cart|orders(?:\/[1-9]\d*)?|checkout\/(?:success|cancel))(?:\?[^#]*)?$/.test(from);
      navigate(canReturn ? from : "/account", { replace: true });
    } catch (error) {
      setError(
        error instanceof Error ? error.message : "Login failed"
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-neutral-100 px-4">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-md space-y-5 bg-white p-8 shadow-sm"
      >
        <h1 className="text-2xl font-bold">Sign in</h1>

        {error && (
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        )}

        <div>
          <label htmlFor="username" className="block mb-2">
            Username
          </label>
          <input
            id="username"
            className="w-full border p-3"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
            required
          />
        </div>

        <div>
          <label htmlFor="password" className="block mb-2">
            Password
          </label>
          <input
            id="password"
            type="password"
            className="w-full border p-3"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            required
          />
        </div>

        <button
          type="submit"
          disabled={loading}
          className="w-full bg-violet-900 p-3 font-medium text-white disabled:opacity-50"
        >
          {loading ? "Signing in..." : "Sign in"}
        </button>

        <p className="text-center text-sm">
          No account?{" "}
          <Link to="/register" className="text-violet-800">
            Register
          </Link>
        </p>
      </form>
    </main>
  );
}
