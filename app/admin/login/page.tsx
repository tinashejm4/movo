"use client"

import { useRouter } from "next/navigation"
import { useState, type FormEvent } from "react"
import styles from "./styles.module.css"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"

export default function AdminLoginPage() {
  const router = useRouter()
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState("")
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError("")
    setIsSubmitting(true)

    try {
      const response = await fetch(`${API_BASE}/api/users/staff/login/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      })
      const data = await response.json().catch(() => null)

      if (!response.ok || !data?.access || !data?.refresh) {
        setError(data?.detail || data?.error || "Wrong username or password.")
        return
      }

      window.sessionStorage.setItem("movo_access_token", data.access)
      window.sessionStorage.setItem("movo_refresh_token", data.refresh)
      window.sessionStorage.setItem("movo_admin_name", username)
      router.push("/admin")
    } catch {
      setError("Connection failed. Please check your network.")
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <main className={styles.container}>
      <form className={styles.card} onSubmit={handleSubmit} aria-labelledby="admin-login-heading">
        <h1 id="admin-login-heading">Admin Login</h1>
        <p>Sign in to access the Movo administration area.</p>

        <label htmlFor="username">
          Username
          <input
            id="username"
            type="text"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
            disabled={isSubmitting}
            required
          />
        </label>

        <label htmlFor="password">
          Password
          <input
            id="password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
            disabled={isSubmitting}
            required
          />
        </label>

        {error && <p className={styles.error} role="alert">{error}</p>}

        <button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Signing in..." : "Sign in"}
        </button>
      </form>
    </main>
  )
}