import { connection } from "next/server"

export async function WorkspaceStatus() {
  await connection()
  if (process.env.BMW_DEMO !== "1") return null
  return <span className="workspace-status" title="Sample data in a separate local database. Changes made here do not affect your bank data."><span className="demo-label-full">Demo workspace</span><span className="demo-label-short">Demo</span></span>
}
