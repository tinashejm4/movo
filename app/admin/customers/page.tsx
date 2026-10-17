"use client"

import Link from "next/link"
import { Fragment, useEffect, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import styles from "./styles.module.css"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"

type CustomerMetrics = {
  total_customers: number
  new_signups_today: number
  new_signups_this_month: number
  active_customers: number
  deactivated_customers: number
}

type Customer = {
  id: number
  name: string
  username: string
  date_joined: string
  number_of_orders: number
}

type CustomerPackage = {
  id: number
  tracking_number: string
  sender: string
  receiver: string
  from_suburb: string
  to_suburb: string
  status: string
  created_at: string
}

type CustomerDetails = {
  orders: CustomerPackage[]
}

const metricCards: { key: keyof CustomerMetrics; label: string }[] = [
  { key: "total_customers", label: "Total customers" },
  { key: "new_signups_today", label: "Joined today" },
  { key: "new_signups_this_month", label: "Joined this month" },
  { key: "active_customers", label: "Active customers" },
  { key: "deactivated_customers", label: "Deactivated customers" },
]

export default function AdminCustomersPage() {
  const router = useRouter()
  const [metrics, setMetrics] = useState<CustomerMetrics | null>(null)
  const [customers, setCustomers] = useState<Customer[]>([])
  const [customerCount, setCustomerCount] = useState(0)
  const [hasPrevious, setHasPrevious] = useState(false)
  const [hasNext, setHasNext] = useState(false)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [expandedCustomerId, setExpandedCustomerId] = useState<number | null>(null)
  const [customerDetails, setCustomerDetails] = useState<CustomerDetails | null>(null)
  const [detailsLoading, setDetailsLoading] = useState(false)
  const [detailsError, setDetailsError] = useState("")
  const detailRequestId = useRef(0)

  async function toggleCustomerDetails(customerId: number) {
    if (expandedCustomerId === customerId) {
      detailRequestId.current += 1
      setExpandedCustomerId(null)
      setCustomerDetails(null)
      setDetailsLoading(false)
      setDetailsError("")
      return
    }

    const requestId = detailRequestId.current + 1
    detailRequestId.current = requestId
    setExpandedCustomerId(customerId)
    setCustomerDetails(null)
    setDetailsLoading(true)
    setDetailsError("")

    const accessToken = window.sessionStorage.getItem("movo_access_token")
    if (!accessToken) {
      setDetailsLoading(false)
      router.replace("/admin/login")
      return
    }

    try {
      const response = await fetch(`${API_BASE}/api/adminportal/customers/${customerId}/`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      })

      if (response.status === 401) {
        router.replace("/admin/login")
        return
      }

      const data = await response.json().catch(() => null)
      if (!response.ok) {
        throw new Error(data?.detail || data?.error || "Unable to load customer packages.")
      }

      if (requestId === detailRequestId.current) {
        setCustomerDetails({ orders: Array.isArray(data?.orders) ? data.orders : [] })
      }
    } catch (loadError) {
      if (requestId === detailRequestId.current) {
        setDetailsError(loadError instanceof Error ? loadError.message : "Unable to load customer packages.")
      }
    } finally {
      if (requestId === detailRequestId.current) setDetailsLoading(false)
    }
  }

  useEffect(() => {
    if (!window.sessionStorage.getItem("movo_access_token")) router.replace("/admin/login")
  }, [router])

  useEffect(() => {
    let isMounted = true

    async function loadCustomers() {
      const accessToken = window.sessionStorage.getItem("movo_access_token")
      if (!accessToken) return

      setLoading(true)
      setError("")

      try {
        const headers = { Authorization: `Bearer ${accessToken}` }
        const [metricsResponse, customersResponse] = await Promise.all([
          fetch(`${API_BASE}/api/adminportal/customers-metrics/`, { headers }),
          fetch(`${API_BASE}/api/adminportal/customers/?page=${page}`, { headers }),
        ])

        if (metricsResponse.status === 401 || customersResponse.status === 401) {
          router.replace("/admin/login")
          return
        }

        const metricsData = await metricsResponse.json().catch(() => null)
        const customersData = await customersResponse.json().catch(() => null)
        if (!metricsResponse.ok) {
          throw new Error(metricsData?.detail || metricsData?.error || "Unable to load customer metrics.")
        }
        if (!customersResponse.ok) {
          throw new Error(customersData?.detail || customersData?.error || "Unable to load customers.")
        }

        if (!isMounted) return
        setMetrics(metricsData)
        setCustomers(Array.isArray(customersData?.results) ? customersData.results : [])
        setCustomerCount(Number(customersData?.count) || 0)
        setHasPrevious(Boolean(customersData?.previous))
        setHasNext(Boolean(customersData?.next))
      } catch (loadError) {
        if (isMounted) setError(loadError instanceof Error ? loadError.message : "Unable to load customers.")
      } finally {
        if (isMounted) setLoading(false)
      }
    }

    void loadCustomers()
    return () => {
      isMounted = false
    }
  }, [page, router])

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <div>
          <Link href="/admin" className={styles.backLink}>Back to dashboard</Link>
          <p className={styles.eyebrow}>Movo administration</p>
          <h1>Customers</h1>
          <p className={styles.intro}>Customer records and account details.</p>
        </div>
      </header>

      {error && <p className={styles.error} role="alert">{error}</p>}

      <section className={styles.metricsSection} aria-labelledby="customer-metrics-heading">
        <div className={styles.sectionHeader}>
          <h2 id="customer-metrics-heading">Customer metrics</h2>
          {loading && <span className={styles.loading}>Loading...</span>}
        </div>
        <div className={styles.metricGrid}>
          {metricCards.map((metric) => (
            <article className={styles.metricCard} key={metric.key}>
              <p>{metric.label}</p>
              <strong>{metrics?.[metric.key] ?? "-"}</strong>
            </article>
          ))}
        </div>
      </section>

      <section className={styles.listSection} aria-labelledby="customers-heading">
        <div className={styles.sectionHeader}>
          <h2 id="customers-heading">Customer records</h2>
          <span className={styles.count}>{customerCount} customers</span>
        </div>
        {loading && customers.length === 0 && <p className={styles.status}>Loading customers...</p>}
        {!loading && !error && customers.length === 0 && <p className={styles.status}>No customers found.</p>}
        {customers.length > 0 && (
          <>
            <div className={styles.tableWrap}>
              <table className={styles.customerTable}>
                <thead>
                  <tr>
                    <th scope="col">Name</th>
                    <th scope="col">Customer</th>
                    <th scope="col">Joined</th>
                    <th scope="col">Orders</th>
                  </tr>
                </thead>
                <tbody>
                  {customers.map((customer) => (
                    <Fragment key={customer.id}>
                      <tr>
                        <td>
                          <button
                            type="button"
                            className={styles.expandButton}
                            onClick={() => void toggleCustomerDetails(customer.id)}
                            aria-expanded={expandedCustomerId === customer.id}
                            aria-controls={`customer-details-${customer.id}`}
                          >
                            <span className={styles.expandIcon} aria-hidden="true">
                              {expandedCustomerId === customer.id ? "−" : "+"}
                            </span>
                            {customer.name.trim() || "-"}
                          </button>
                        </td>
                        <td>{customer.username}</td>
                        <td>{new Date(customer.date_joined).toLocaleDateString()}</td>
                        <td>{customer.number_of_orders}</td>
                      </tr>
                      {expandedCustomerId === customer.id && (
                        <tr>
                          <td colSpan={4} className={styles.detailsCell}>
                            <div id={`customer-details-${customer.id}`} className={styles.detailsPanel}>
                              <h3>Recent packages</h3>
                              {detailsLoading && <p className={styles.status}>Loading packages...</p>}
                              {detailsError && <p className={styles.error} role="alert">{detailsError}</p>}
                              {!detailsLoading && !detailsError && customerDetails?.orders.length === 0 && (
                                <p className={styles.status}>No packages found.</p>
                              )}
                              {!detailsLoading && customerDetails && customerDetails.orders.length > 0 && (
                                <div className={styles.packageTableWrap}>
                                  <table className={styles.packageTable}>
                                    <thead>
                                      <tr>
                                        <th scope="col">Tracking number</th>
                                        <th scope="col">Sender</th>
                                        <th scope="col">Receiver</th>
                                        <th scope="col">Route</th>
                                        <th scope="col">Status</th>
                                        <th scope="col">Created</th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {customerDetails.orders.map((order) => (
                                        <tr key={order.id}>
                                          <td>{order.tracking_number}</td>
                                          <td>{order.sender}</td>
                                          <td>{order.receiver}</td>
                                          <td>{order.from_suburb} to {order.to_suburb}</td>
                                          <td>{order.status}</td>
                                          <td>{new Date(order.created_at).toLocaleDateString()}</td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
            <div className={styles.pagination}>
              <button type="button" onClick={() => setPage((current) => current - 1)} disabled={!hasPrevious || loading}>
                Previous
              </button>
              <span>Page {page}</span>
              <button type="button" onClick={() => setPage((current) => current + 1)} disabled={!hasNext || loading}>
                Next
              </button>
            </div>
          </>
        )}
      </section>
    </main>
  )
}