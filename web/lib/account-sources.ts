export type AccountSource = "Revolut" | "Sparkasse"

// Keep bank identity color to the small source dots unless a stronger cue is needed.
export const ACCOUNT_SOURCE_DOT_COLORS: Record<AccountSource, string> = {
  Revolut: "bg-[#95afd2]",
  Sparkasse: "bg-[#347be0]",
}
