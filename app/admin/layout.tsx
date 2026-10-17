import { AdminTopRail } from "./admin-top-rail"

export default function AdminLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <><AdminTopRail />{children}</>
}