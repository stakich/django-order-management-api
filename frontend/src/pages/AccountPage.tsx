import { useState, type SubmitEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { changePassword } from "../api/auth";
import { useAuth } from "../auth/useAuth";

export default function AccountPage() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const [passwordError, setPasswordError] = useState("");
  const [isChangingPassword, setIsChangingPassword] = useState(false);

  function handleLogout() {
    signOut();
    navigate("/", { replace: true });
  }

  async function handleChangePassword(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();

    const form = new FormData(event.currentTarget);
    setPasswordError("");
    setIsChangingPassword(true);

    try {
      await changePassword({
        current_password: String(form.get("current_password") ?? ""),
        new_password: String(form.get("new_password") ?? ""),
        new_password_confirm: String(form.get("new_password_confirm") ?? ""),
      });

      signOut();
      navigate("/login", { replace: true });
    } catch (error) {
      setPasswordError(
        error instanceof Error ? error.message : "Could not change password",
      );
    } finally {
      setIsChangingPassword(false);
    }
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

      <form
        onSubmit={handleChangePassword}
        className="mt-8 space-y-4 border border-neutral-200 p-6"
      >
        <h2 className="text-xl font-semibold">Change password</h2>

        <label className="block">
          Current password
          <input
            type="password"
            name="current_password"
            autoComplete="current-password"
            className="mt-1 block w-full border px-3 py-2"
            required
          />
        </label>

        <label className="block">
          New password
          <input
            type="password"
            name="new_password"
            autoComplete="new-password"
            className="mt-1 block w-full border px-3 py-2"
            required
          />
        </label>

        <label className="block">
          Confirm new password
          <input
            type="password"
            name="new_password_confirm"
            autoComplete="new-password"
            className="mt-1 block w-full border px-3 py-2"
            required
          />
        </label>

        {passwordError && (
          <p role="alert" className="text-red-700">
            {passwordError}
          </p>
        )}

        <button
          type="submit"
          disabled={isChangingPassword}
          className="bg-violet-900 px-6 py-3 font-medium text-white disabled:opacity-50"
        >
          {isChangingPassword ? "Changing password..." : "Change password"}
        </button>
      </form>
    </main>
  );
}