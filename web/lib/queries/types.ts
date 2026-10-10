export type Summary = { spend: number; income: number; net: number; count: number }
export type Daily = { date: string; spend: number }
export type Monthly = { month: string; spend: number; income: number; net: number }
export type CategorySpend = { category: string; spend: number; children: { category: string; spend: number }[] }
export type MerchantSpend = { merchant: string; spend: number }
export type Transaction = {
  id: string; date: string; merchant: string | null; counterparty_raw: string | null
  description_raw: string | null; category: string | null; parent_category: string | null; account_name: string
  type: string; amount: number; fee: number; currency: string
  original_amount: number | null; original_currency: string | null; fx_rate: number | null
  booking_date: string; value_date: string | null; status: string
}
export type Subscription = {
  id: string; name: string; category: string | null; parent_category: string | null; cadence: string
  amount: number; currency: string; yearly_cost: number | null; last_charge: string | null
  status: "active" | "paused" | "cancelled"; notes: string | null
}
