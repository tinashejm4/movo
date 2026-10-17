"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import styles from "./admin-top-rail.module.css"

const navigationItems = [
  { href: "/admin", label: "Dashboard", exact: true },
  { href: "/admin/suburbs", label: "Suburbs", exact: false },
  { href: "/admin/bikers", label: "Bikers", exact: false },
  { href: "/admin/customers", label: "Customers", exact: false },
  { href: "/admin/accounts", label: "Accounts", exact: false },
]

export function AdminTopRail() {
  const pathname = usePathname()

  if (pathname === "/admin/login") return null

  return (
    <nav className={styles.rail} aria-label="Admin navigation">
      <div className={styles.content}>
        <Link href="/admin" className={styles.brand}>Movo Admin</Link>
        <div className={styles.links}>
          {navigationItems.map((item) => {
            const isActive = item.exact ? pathname === item.href : pathname.startsWith(item.href)
            return <Link key={item.href} href={item.href} className={isActive ? styles.activeLink : styles.link}>{item.label}</Link>
          })}
        </div>
      </div>
    </nav>
  )
}