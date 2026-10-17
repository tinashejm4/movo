"use client"

import Link from "next/link"
import { useParams, useRouter } from "next/navigation"
import { useEffect, useState, type FormEvent } from "react"
import styles from "./styles.module.css"
import { AddExpenseModal } from "./add-expense-modal"
import { AddChargeModal } from "./add-charge-modal"
import { TransferModal } from "./transfer-modal"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"

type AccountDetails = {
  account_id: number
  account_name: string
  branch: string | null
  owner: string | null
  currency: string
  description: string | null
  number: string
  current_balance: number | string
}

type Transaction = {
  entry_type: "credit" | "debit"
  id: number
  amount: number | string
  balance: number | string
  description: string | null
  date: string
  transaction_type: string
}

function formatMoney(value: number | string, currency: string) {
  const amount = Number(value)
  if (Number.isNaN(amount)) return `${currency} ${value}`
  return `${currency} ${amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function formatNumber(value: number | string) {
  const amount = Number(value)
  if (Number.isNaN(amount)) return String(value)
  return amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function toDateInput(date: Date) {
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

function defaultRange() {
  const today = new Date()
  const start = new Date()
  start.setDate(today.getDate() - 7)
  return { start: toDateInput(start), end: toDateInput(today) }
}

function formatDate(value: string | null | undefined) {
  if (!value) return "-"
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

export default function AdminAccountDetailPage() {
  const router = useRouter()
  const { accountId } = useParams<{ accountId: string }>()
  const [account, setAccount] = useState<AccountDetails | null>(null)
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [startDate, setStartDate] = useState(() => defaultRange().start)
  const [endDate, setEndDate] = useState(() => defaultRange().end)
  const [appliedRange, setAppliedRange] = useState(defaultRange)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [filterError, setFilterError] = useState("")
  const [showExpenseModal, setShowExpenseModal] = useState(false)
  const [showChargeModal, setShowChargeModal] = useState(false)
  const [showTransferModal, setShowTransferModal] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let isMounted = true

    async function load() {
      const accessToken = window.sessionStorage.getItem("movo_access_token")
      if (!accessToken) {
        router.replace("/admin/login")
        return
      }

      setLoading(true)
      setError("")

      try {
        const headers = { Authorization: `Bearer ${accessToken}` }
        const query = `?start_date=${appliedRange.start}&end_date=${appliedRange.end}`
        const transactionsResponse = await fetch(
          `${API_BASE}/api/adminportal/accounts/${accountId}/transactions/${query}`,
          { headers },
        )

        if (transactionsResponse.status === 401) {
          router.replace("/admin/login")
          return
        }

        const transactionsData = await transactionsResponse.json().catch(() => null)
        if (!transactionsResponse.ok) {
          throw new Error(transactionsData?.detail || transactionsData?.error || "Unable to load transactions.")
        }

        if (!isMounted) return
        const list: Transaction[] = Array.isArray(transactionsData?.transactions) ? transactionsData.transactions : []
        setAccount(transactionsData?.account_details ?? null)
        setTransactions([...list].sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime()))
      } catch (loadError) {
        if (isMounted) setError(loadError instanceof Error ? loadError.message : "Unable to load account.")
      } finally {
        if (isMounted) setLoading(false)
      }
    }

    void load()
    return () => {
      isMounted = false
    }
  }, [accountId, appliedRange, reloadKey, router])

  function applyFilter(event: FormEvent) {
    event.preventDefault()
    if (!startDate || !endDate) {
      setFilterError("Select both a start and end date.")
      return
    }
    if (startDate > endDate) {
      setFilterError("Start date must be before the end date.")
      return
    }
    setFilterError("")
    setAppliedRange({ start: startDate, end: endDate })
  }

  function resetFilter() {
    const range = defaultRange()
    setStartDate(range.start)
    setEndDate(range.end)
    setFilterError("")
    setAppliedRange(range)
  }

  const currency = account?.currency ?? ""
  const details: [string, string][] = account
    ? [
        ["Account number", account.number],
        ["Branch", account.branch ?? "-"],
        ["Owner", account.owner ?? "-"],
        ["Currency", account.currency],
        ["Description", account.description || "-"],
        ["ID", String(account.account_id)],
      ]
    : []

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <div>
          <Link href="/admin/accounts" className={styles.backLink}>Back to accounts</Link>
          <p className={styles.eyebrow}>Movo administration</p>
          <h1>{account?.account_name ?? "Account"}</h1>
          {account && <strong className={styles.balance}>{formatMoney(account.current_balance, currency)}</strong>}
        </div>
        <div className={styles.actions}>
          <button type="button" onClick={() => setShowExpenseModal(true)}>Add expense</button>
          <button type="button" onClick={() => setShowChargeModal(true)}>Add charge</button>
          <button type="button" onClick={() => setShowTransferModal(true)}>Transfer</button>
        </div>
      </header>

      {error && <p className={styles.error} role="alert">{error}</p>}

      {account && (
        <section className={styles.panel} aria-labelledby="account-details-heading">
          <h2 id="account-details-heading">Account details</h2>
          <dl className={styles.details}>
            {details.map(([label, value]) => (
              <div key={label}><dt>{label}</dt><dd>{value}</dd></div>
            ))}
          </dl>
        </section>
      )}

      <section className={styles.panel} aria-labelledby="transactions-heading">
        <div className={styles.sectionHeader}>
          <h2 id="transactions-heading">Transactions</h2>
          <span className={styles.count}>{loading ? "Loading..." : `${transactions.length} transactions`}</span>
        </div>

        <form className={styles.filter} onSubmit={applyFilter}>
          <label>From<input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} /></label>
          <label>To<input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} /></label>
          <button type="submit">Apply</button>
          <button type="button" onClick={resetFilter}>Last 7 days</button>
        </form>
        {filterError && <p className={styles.error} role="alert">{filterError}</p>}

        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr><th>Date</th><th>Description</th><th>Transaction type</th><th>Amount</th><th>Balance</th></tr>
            </thead>
            <tbody>
              {transactions.map((transaction) => (
                <tr key={transaction.id}>
                  <td>{formatDate(transaction.date)}</td>
                  <td>{transaction.description || "-"}</td>
                  <td>{transaction.transaction_type || "-"}</td>
                  <td className={transaction.entry_type === "credit" ? styles.credit : styles.debit}>
                    {transaction.entry_type === "credit" ? "+" : "-"}
                    {formatNumber(Math.abs(Number(transaction.amount)))}
                  </td>
                  <td>{formatNumber(transaction.balance)}</td>
                </tr>
              ))}
              {!loading && transactions.length === 0 && (
                <tr><td colSpan={5} className={styles.empty}>No transactions found.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
      {showExpenseModal && (
        <AddExpenseModal
          accountId={accountId}
          currency={currency}
          onClose={() => setShowExpenseModal(false)}
          onCreated={() => {
            setShowExpenseModal(false)
            setReloadKey((key) => key + 1)
          }}
        />
      )}
      {showChargeModal && (
        <AddChargeModal
          accountId={accountId}
          currency={currency}
          onClose={() => setShowChargeModal(false)}
          onCreated={() => {
            setShowChargeModal(false)
            setReloadKey((key) => key + 1)
          }}
        />
      )}
      {showTransferModal && (
        <TransferModal
          accountId={accountId}
          accountName={account?.account_name ?? "This account"}
          currency={currency}
          onClose={() => setShowTransferModal(false)}
          onCreated={() => {
            setShowTransferModal(false)
            setReloadKey((key) => key + 1)
          }}
        />
      )}
    </main>
  )
}
