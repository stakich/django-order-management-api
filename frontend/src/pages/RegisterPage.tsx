import { useState, type SubmitEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { register } from "../api/auth";

export default function RegisterPage() {
  const navigate = useNavigate();

  const [form, setForm] = useState({
    username: "",
    email: "",
    password: "",
    password_confirm: "",
  });

  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");

    if (form.password !== form.password_confirm) {
      setError("Passwords do not match");
      return;
    }

    setLoading(true);

    try {
      await register(form);
      navigate("/login", { replace: true });
    } catch (error) {
      setError(
        error instanceof Error ? error.message : "Registration failed"
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-neutral-100 px-4">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-md space-y-4 bg-white p-8 shadow-sm"
      >
        <h1 className="text-2xl font-bold">Create account</h1>

        {error && (
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        )}

        {(["username", "email", "password", "password_confirm"] as const).map(
          (field) => (
            <div key={field}>
              <label htmlFor={field} className="mb-2 block capitalize">
                {field.replace("_", " ")}
              </label>
              <input
                id={field}
                type={
                  field.includes("password")
                    ? "password"
                    : field === "email"
                      ? "email"
                      : "text"
                }
                className="w-full border p-3"
                value={form[field]}
                onChange={(event) =>
                  setForm((previous) => ({
                    ...previous,
                    [field]: event.target.value,
                  }))
                }
                required
              />
            </div>
          )
        )}

        <button
          type="submit"
          disabled={loading}
          className="w-full bg-violet-900 p-3 font-medium text-white disabled:opacity-50"
        >
          {loading ? "Creating account..." : "Register"}
        </button>

        <p className="text-center text-sm">
          Already registered?{" "}
          <Link to="/login" className="text-violet-800">
            Sign in
          </Link>
        </p>
      </form>
    </main>
  );
}