import { describe, expect, test } from "bun:test";
import { classify, parseCsvBytes } from "./import";

function csvLine(fields: string[], delimiter: string): string {
  return fields.map((field) => `"${field.replaceAll('"', '""')}"`).join(delimiter);
}

const sparkasseColumns = [
  "Auftragskonto", "Buchungstag", "Valutadatum", "Buchungstext", "Verwendungszweck",
  "Glaeubiger ID", "Mandatsreferenz", "Kundenreferenz (End-to-End)",
  "Beguenstigter/Zahlungspflichtiger", "Kontonummer/IBAN", "Betrag", "Waehrung", "Info",
];

const revolutColumns = [
  "Type", "Product", "Started Date", "Completed Date", "Description",
  "Amount", "Fee", "Currency", "State", "Balance",
];

describe("fake bank CSVs", () => {
  test("Sparkasse Latin-1, cents, merchant, own transfer and stable hash", () => {
    const lines = [
      csvLine(sparkasseColumns, ";"),
      csvLine(["DE001234", "15.01.26", "16.01.26", "KARTENZAHLUNG", "2026-01-15T12:34 Café", "", "", "A1", "Café/High Street/Berlin/DE/0", "", "-1.234,56", "EUR", "Umsatz gebucht"], ";"),
      csvLine(["DE001234", "16.01.26", "16.01.26", "SEPA-UEBERWEISUNG", "Savings", "", "", "A2", "Lovelace Ada", "DE009999", "-50,00", "EUR", "Umsatz vorgemerkt"], ";"),
    ];
    const latin1 = Uint8Array.from([...lines.join("\n")].map((char) => char.charCodeAt(0)));
    const parsed = parseCsvBytes(latin1);
    expect(parsed.format).toBe("sparkasse");
    expect(parsed.rows).toHaveLength(2);
    expect(parsed.rows[0].amountCents).toBe(-123456);
    expect(parsed.rows[0].merchant).toBe("Café");
    expect(parsed.rows[0].city).toBe("Berlin");
    expect(parsed.rows[0].transactedAt).toStartWith("2026-01-15 12:34");
    expect(parsed.rows[1].status).toBe("pending");
    expect(parsed.rows[1].dedupHash).toBe(parseCsvBytes(latin1).rows[1].dedupHash);
    const mapped = classify(parsed.rows[1], parsed.format, ["Ada Lovelace"], new Set(["DE009999"]), new Set());
    expect(mapped.type).toBe("transfer");
  });

  test("Revolut fees, pending rows, own card top-up and unknown transfer", () => {
    const lines = [
      csvLine(revolutColumns, ","),
      csvLine(["Card Payment", "Current", "2026-01-15 12:34:00", "2026-01-16 08:00:00", "Fake Shop", "-10.00", "0.50", "EUR", "COMPLETED", "100.00"], ","),
      csvLine(["Topup", "Current", "2026-01-17 09:00:00", "", "Apple Pay top-up by *1234", "25.00", "0.00", "EUR", "PENDING", ""], ","),
      csvLine(["Transfer", "Current", "2026-01-18 10:00:00", "", "Bank transfer", "-5.00", "0.00", "EUR", "REVERTED", ""], ","),
    ];
    const parsed = parseCsvBytes(new TextEncoder().encode(lines.join("\n")));
    expect(parsed.format).toBe("revolut");
    expect(parsed.rows).toHaveLength(3);
    expect(parsed.rows[0].amountCents).toBe(-1050);
    expect(parsed.rows[0].feeCents).toBe(50);
    expect(parsed.rows[0].bookingDate).toBe("2026-01-16");
    expect(parsed.rows[0].merchant).toBe("Fake Shop");
    expect(parsed.rows[1].status).toBe("pending");
    expect(parsed.rows[1].bookingDate).toBe("2026-01-17");
    const mapped = parsed.rows.map((row) => classify(row, parsed.format, ["Ada Lovelace"], new Set(), new Set(["1234"])));
    expect(mapped.map((row) => row.type)).toEqual(["expense", "transfer", "expense"]);
    expect(mapped[2].needsReview).toBe(true);
    expect(parsed.rows[2].status).toBe("reverted");
  });
});
