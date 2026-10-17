"use client"

  import { useEffect, useState } from "react"
  import { useRouter } from "next/navigation"
  import styles from "./styles.module.css"

  const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
  const POLL_INTERVAL = 30_000

  type MainMetrics = {
    new_customers: number
    total_new_orders: number
    delivered_orders: number
    canceled_orders: number
    in_transit_orders: number
    assigned_orders: number
  }

  type BikerMetrics = {
    biker_id: number
    biker_name: string
    is_active: boolean
    is_busy: boolean
    started_at: string | null
    num_packages_assigned: number
    num_packages_delivered: number
  }

  type PackageMetric = {
    package_id: number
    slug: string
    pickup_area: string
    dropoff_area: string
    current_status: string | null
    is_fast_delivery: boolean
    invoice_amount: number | string | null
  }

  type PackageDetails = {
    package_id: number
    slug: string
    sender: string
    sender_phone: string
    receiver: string
    receiver_phone: string
    pickup_area: string
    pickup_address: string
    dropoff_area: string
    dropoff_address: string
    sender_code: string
    receiver_code: string
    comments: string | null
    current_status: string | null
    is_fast_delivery: boolean
    payment_method: string | null
    invoice_amount: number | string | null
    is_paid: boolean | null
    status_history: { status: string; updated_at: string }[]
  }

  const metricCards: { key: keyof MainMetrics; label: string }[] = [
    { key: "new_customers", label: "New customers" },
    { key: "total_new_orders", label: "New orders" },
    { key: "delivered_orders", label: "Delivered" },
    { key: "canceled_orders", label: "Canceled" },
    { key: "in_transit_orders", label: "In transit" },
    { key: "assigned_orders", label: "Assigned" },
  ]

  async function fetchJson<T>(path: string, accessToken: string) {
    const response = await fetch(`${API_BASE}${path}`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    })
    const data = await response.json().catch(() => null)
    if (!response.ok) throw new Error(data?.detail || data?.error || `Unable to load ${path}.`)
    return data as T
  }

  function formatStartedAt(value: string | null) {
    if (!value) return "Not started"
    return new Date(value).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
  }

  function formatStatusTime(value: string) {
    return new Date(value).toLocaleString([], { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" })
  }

  export default function AdminPage() {
    const router = useRouter()
    const [mainMetrics, setMainMetrics] = useState<MainMetrics | null>(null)
    const [bikerMetrics, setBikerMetrics] = useState<BikerMetrics[]>([])
    const [packages, setPackages] = useState<PackageMetric[]>([])
    const [expandedPackageId, setExpandedPackageId] = useState<number | null>(null)
    const [packageDetails, setPackageDetails] = useState<Record<number, PackageDetails>>({})
    const [loadingPackageId, setLoadingPackageId] = useState<number | null>(null)
    const [packageDetailsError, setPackageDetailsError] = useState("")
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState("")
    const [lastUpdated, setLastUpdated] = useState<Date | null>(null)

    useEffect(() => {
      if (!window.sessionStorage.getItem("movo_access_token")) router.replace("/admin/login")
    }, [router])

    useEffect(() => {
      let isMounted = true

      async function loadDashboard() {
        const accessToken = window.sessionStorage.getItem("movo_access_token")
        if (!accessToken) return

        try {
          const [mainData, bikerData, packageData] = await Promise.all([
            fetchJson<MainMetrics>("/api/adminportal/main-metrics/", accessToken),
            fetchJson<BikerMetrics[] | { bikers: BikerMetrics[] }>("/api/adminportal/bikers-metrics/", accessToken),
            fetchJson<{ packages: PackageMetric[] }>("/api/adminportal/packages-list/", accessToken),
          ])
          if (!isMounted) return
          setMainMetrics(mainData)
          setBikerMetrics(Array.isArray(bikerData) ? bikerData : bikerData.bikers ?? [])
          setPackages(Array.isArray(packageData.packages) ? packageData.packages : [])
          setError("")
          setLastUpdated(new Date())
        } catch (loadError) {
          if (isMounted) setError(loadError instanceof Error ? loadError.message : "Unable to load dashboard metrics.")
        } finally {
          if (isMounted) setLoading(false)
        }
      }

      void loadDashboard()
      const interval = window.setInterval(() => void loadDashboard(), POLL_INTERVAL)
      return () => {
        isMounted = false
        window.clearInterval(interval)
      }
    }, [])

    async function togglePackage(packageId: number) {
      if (expandedPackageId === packageId) {
        setExpandedPackageId(null)
        setPackageDetailsError("")
        return
      }

      setExpandedPackageId(packageId)
      setPackageDetailsError("")
      if (packageDetails[packageId]) return

      const accessToken = window.sessionStorage.getItem("movo_access_token")
      if (!accessToken) return

      setLoadingPackageId(packageId)
      try {
        const response = await fetchJson<{ package: PackageDetails }>(`/api/adminportal/packages-details/?package_id=${packageId}`, accessToken)
        setPackageDetails((current) => ({ ...current, [packageId]: response.package }))
      } catch (loadError) {
        setPackageDetailsError(loadError instanceof Error ? loadError.message : "Unable to load package details.")
      } finally {
        setLoadingPackageId(null)
      }
    }

    return (
      <main className={styles.page}>
        <header className={styles.header}>
          <div>
            <p className={styles.eyebrow}>Movo administration</p>
            <h1>Live dashboard</h1>
            <p className={styles.intro}>Today&apos;s delivery activity at a glance.</p>
          </div>
          {lastUpdated && <p className={styles.updated}>Updated {lastUpdated.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</p>}
        </header>

        {error && <p className={styles.error} role="alert">{error}</p>}

        <section className={styles.section} aria-labelledby="main-metrics-heading">
          <div className={styles.sectionHeader}>
            <div><p className={styles.sectionLabel}>Today</p><h2 id="main-metrics-heading">Main metrics</h2></div>
            {loading && <span className={styles.loading}>Loading...</span>}
          </div>
          <div className={styles.metricGrid}>
            {metricCards.map((metric) => <article className={styles.metricCard} key={metric.key}>
              <p>{metric.label}</p>
              <strong>{mainMetrics?.[metric.key] ?? "-"}</strong>
            </article>)}
          </div>
        </section>

        <section className={styles.section} aria-labelledby="biker-metrics-heading">
          <div className={styles.sectionHeader}><div><p className={styles.sectionLabel}>Delivery team</p><h2 id="biker-metrics-heading">Biker metrics</h2></div><span className={styles.count}>{bikerMetrics.length} bikers</span></div>
          {!loading && bikerMetrics.length === 0 && !error && <p className={styles.empty}>No biker metrics available.</p>}
          <div className={styles.bikerGrid}>
            {bikerMetrics.map((biker) => <article className={styles.bikerCard} key={biker.biker_id}>
              <div className={styles.bikerHeader}><div><h3>{biker.biker_name || "Unnamed biker"}</h3><p className={styles.startedAt}>Started {formatStartedAt(biker.started_at)}</p></div><span className={`${styles.statusBadge} ${biker.is_active ? styles.active : styles.offline}`}>{biker.is_active ? "Active" : "Offline"}</span></div>
              <div className={styles.bikerStatus}><span className={biker.is_busy ? styles.busyDot : styles.readyDot} />{biker.is_busy ? "On delivery" : "Available"}</div>
              <dl className={styles.bikerStats}><div><dt>Assigned today</dt><dd>{biker.num_packages_assigned}</dd></div><div><dt>Delivered today</dt><dd>{biker.num_packages_delivered}</dd></div></dl>
            </article>)}
          </div>
        </section>

        <section className={styles.section} aria-labelledby="packages-heading">
          <div className={styles.sectionHeader}><div><p className={styles.sectionLabel}>Today</p><h2 id="packages-heading">Packages</h2></div><span className={styles.count}>{packages.length} packages</span></div>
          {!loading && packages.length === 0 && !error && <p className={styles.empty}>No packages found today.</p>}
          {packages.length > 0 && <div className={styles.packageList}>
            {packages.map((packageItem) => {
              const isExpanded = expandedPackageId === packageItem.package_id
              const details = packageDetails[packageItem.package_id]
              return <article className={styles.packageRow} key={packageItem.package_id}>
                <div className={styles.packageMain}>
                  <div className={styles.packageIdentity}>
                    <div><strong>{packageItem.slug || `Package #${packageItem.package_id}`}</strong><span>#{packageItem.package_id}</span></div>
                    <div className={styles.packageMeta}><span>{packageItem.is_fast_delivery ? "Fast delivery" : "Standard delivery"}</span><span>{packageItem.invoice_amount === null ? "No invoice" : `Invoice: ${packageItem.invoice_amount}`}</span></div>
                  </div>
                  <div className={styles.route}><span>{packageItem.pickup_area}</span><span className={styles.routeArrow} aria-hidden="true">&gt;</span><span>{packageItem.dropoff_area}</span></div>
                  <span className={styles.packageStatus}>{packageItem.current_status || "No status"}</span>
                  <button type="button" className={`${styles.packageToggle} ${isExpanded ? styles.packageToggleExpanded : ""}`} onClick={() => void togglePackage(packageItem.package_id)} aria-expanded={isExpanded} aria-controls={`package-details-${packageItem.package_id}`} aria-label={`${isExpanded ? "Hide" : "Show"} details for ${packageItem.slug || `package ${packageItem.package_id}`}`}>
                    &gt;
                  </button>
                </div>
                {isExpanded && <div className={styles.packageDetails} id={`package-details-${packageItem.package_id}`}>
                  {loadingPackageId === packageItem.package_id && <p className={styles.detailLoading}>Loading package details...</p>}
                  {packageDetailsError && <p className={styles.detailError} role="alert">{packageDetailsError}</p>}
                  {details && <dl className={styles.packageDetailGrid}>
                    <div><dt>Sender</dt><dd>{details.sender} ({details.sender_phone})</dd></div>
                    <div><dt>Receiver</dt><dd>{details.receiver} ({details.receiver_phone})</dd></div>
                    <div><dt>Pickup</dt><dd>{details.pickup_area}, {details.pickup_address}</dd></div>
                    <div><dt>Dropoff</dt><dd>{details.dropoff_area}, {details.dropoff_address}</dd></div>
                    <div><dt>Payment</dt><dd>{details.payment_method || "Not provided"}{details.is_paid === true ? " - Paid" : details.is_paid === false ? " - Unpaid" : ""}</dd></div>
                    <div><dt>Comments</dt><dd>{details.comments || "None"}</dd></div>
                  </dl>}
                  {details && <div className={styles.statusHistory}>
                    <h4>Status history</h4>
                    {details.status_history.length > 0 ? <ol className={styles.statusTimeline}>
                      {details.status_history.slice().reverse().map((historyItem, index, timeline) => <li className={styles.statusTimelineItem} key={`${historyItem.status}-${historyItem.updated_at}`}>
                        <span className={`${styles.statusTimelineDot} ${index === timeline.length - 1 ? styles.currentStatusDot : ""}`} aria-hidden="true" />
                        <div><strong>{historyItem.status}</strong><time dateTime={historyItem.updated_at}>{formatStatusTime(historyItem.updated_at)}</time></div>
                      </li>)}
                    </ol> : <p className={styles.noStatusHistory}>No status history available.</p>}
                  </div>}
                </div>}
              </article>
            })}
          </div>}
        </section>
      </main>
    )
  }