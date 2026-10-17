"use client"

import Link from "next/link"
import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import styles from "./styles.module.css"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"

type Account = {
  id: number
  name: string
  branch: string | null
  currency: string
  balance: number | string
  number: string
}

function formatBalance(balance: number | string, currency: string) {
  const value = Number(balance)
  if (Number.isNaN(value)) return `${currency} ${balance}`
  return `${currency} ${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export default function AdminAccountsPage() {
  const router = useRouter()
  const [accounts, setAccounts] = useState<Account[]>([])
  const [accountsCount, setAccountsCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")

  useEffect(() => {
    let isMounted = true

    async function loadAccounts() {
      const accessToken = window.sessionStorage.getItem("movo_access_token")
      if (!accessToken) {
        router.replace("/admin/login")
        return
      }

      try {
        const response = await fetch(`${API_BASE}/api/adminportal/accounts/`, {
          headers: { Authorization: `Bearer ${accessToken}` },
        })
        if (response.status === 401) {
          router.replace("/admin/login")
          return
        }

        const data = await response.json().catch(() => null)
        if (!response.ok) throw new Error(data?.detail || data?.error || "Unable to load accounts.")

        if (!isMounted) return
        setAccounts(Array.isArray(data?.accounts) ? data.accounts : [])
        setAccountsCount(Number(data?.accounts_count) || 0)
      } catch (loadError) {
        if (isMounted) setError(loadError instanceof Error ? loadError.message : "Unable to load accounts.")
      } finally {
        if (isMounted) setLoading(false)
      }
    }

    void loadAccounts()
    return () => {
      isMounted = false
    }
  }, [router])

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <div>
          <Link href="/admin" className={styles.backLink}>Back to dashboard</Link>
          <p className={styles.eyebrow}>Movo administration</p>
          <h1>Accounts</h1>
          <p className={styles.intro}>All bookkeeping accounts and their balances.</p>
        </div>
      </header>

      {error && <p className={styles.error} role="alert">{error}</p>}

      <section aria-labelledby="accounts-heading">
        <div className={styles.sectionHeader}>
          <h2 id="accounts-heading">Account list</h2>
          <span className={styles.count}>{loading ? "Loading..." : `${accountsCount} accounts`}</span>
        </div>
        {!loading && !error && accounts.length === 0 && <p className={styles.count}>No accounts found.</p>}
        <div className={styles.cardGrid}>
          {accounts.map((account) => (
            <Link href={`/admin/accounts/${account.id}`} className={styles.card} key={account.id}>
              <div className={styles.cardHeader}>
                <h3>{account.name}</h3>
                <span className={styles.currency}>{account.currency}</span>
              </div>
              <strong className={styles.balance}>{formatBalance(account.balance, account.currency)}</strong>
              <dl className={styles.details}>
                <div><dt>Account number</dt><dd>{account.number}</dd></div>
                <div><dt>Branch</dt><dd>{account.branch ?? "-"}</dd></div>
                <div><dt>Currency</dt><dd>{account.currency}</dd></div>
              </dl>
            </Link>
          ))}
        </div>
      </section>
    </main>
  )
}
